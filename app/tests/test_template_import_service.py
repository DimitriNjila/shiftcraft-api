import io

import pandas as pd
import pytest
from unittest.mock import MagicMock, patch

from app.services.ai_service import AIServiceUnavailableError
from app.services.template_import_service import TemplateImportService
from app.tests.conftest import RESTAURANT_ID


@pytest.fixture
def import_service():
    return TemplateImportService(shift_template_service=MagicMock())


def _csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


def _xlsx_bytes(rows: list[dict]) -> bytes:
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


# === parse_template_file: clean CSV ===


def test_parse_clean_csv(import_service):
    csv = _csv_bytes(
        "day_of_week,start_time,end_time,role,count\n"
        "2,09:00:00,17:00:00,Server,1\n"
        "3,11:00:00,20:00:00,Cook,2\n"
    )
    rows, mapping = import_service.parse_template_file(csv, "templates.csv")
    assert len(rows) == 2
    assert mapping == {
        "day_of_week": "day_of_week",
        "start_time": "start_time",
        "end_time": "end_time",
        "role": "role",
        "count": "count",
    }
    assert rows[0]["role"] == "Server"


# === parse_template_file: messy CSV ===


def test_parse_messy_csv_headers_and_blank_rows(import_service):
    csv = _csv_bytes(
        "Day,Shift Start,Shift End,Position,Qty,Notes\n"
        "Monday,9:00 AM,5:00 PM,Server,1,ignore me\n"
        "\n"
        ",,,,,\n"
        "Tue,11:00,20:00,Cook,2,\n"
    )
    rows, mapping = import_service.parse_template_file(csv, "messy.csv")
    # blank rows dropped, extra "Notes" column ignored
    assert len(rows) == 2
    assert mapping["day_of_week"] == "Day"
    assert mapping["start_time"] == "Shift Start"
    assert mapping["end_time"] == "Shift End"
    assert mapping["role"] == "Position"
    assert mapping["count"] == "Qty"
    assert "Notes" not in mapping.values()


def test_parse_csv_missing_column(import_service):
    csv = _csv_bytes(
        "day_of_week,start_time,end_time\n"
        "2,09:00:00,17:00:00\n"
    )
    rows, mapping = import_service.parse_template_file(csv, "no_role.csv")
    assert "role" not in mapping
    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["is_valid"] is False
    assert any("role" in e for e in validated[0]["errors"])


def test_parse_xlsx(import_service):
    content = _xlsx_bytes(
        [
            {"day_of_week": 4, "start_time": "11:00:00", "end_time": "16:00:00", "role": "Server", "count": 1},
        ]
    )
    rows, mapping = import_service.parse_template_file(content, "templates.xlsx")
    assert len(rows) == 1
    assert mapping["role"] == "role"


def test_parse_unsupported_file_type(import_service):
    with pytest.raises(ValueError):
        import_service.parse_template_file(b"not a real file", "templates.pdf")


def test_parse_csv_name_column_no_role_column_is_valid(import_service):
    csv = _csv_bytes(
        "Name,Day,Shift Start,Shift End\n"
        "Mya Ferrari,Tue,11:00,16:00\n"
    )
    rows, mapping = import_service.parse_template_file(csv, "whiteboard_export.csv")
    assert mapping["name"] == "Name"
    assert "role" not in mapping

    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["is_valid"] is True
    assert validated[0]["name"] == "Mya Ferrari"
    assert validated[0]["role"] is None


def test_employee_role_header_maps_to_role_not_name(import_service):
    """"Employee Role" shouldn't get claimed by the "name" synonym's substring fallback."""
    csv = _csv_bytes(
        "Day,Start,End,Employee Role,Count\n"
        "2,09:00:00,17:00:00,Server,1\n"
    )
    rows, mapping = import_service.parse_template_file(csv, "templates.csv")
    assert mapping["role"] == "Employee Role"
    assert mapping.get("name") != "Employee Role"


# === parse_template_image ===


def _png_bytes(size=(100, 80), color=(200, 50, 50)) -> bytes:
    from PIL import Image
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _heic_bytes(size=(100, 80), color=(50, 120, 200)) -> bytes:
    from PIL import Image
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="HEIF", quality=80)
    return buf.getvalue()


def _mock_ai_returning(shifts):
    mock_ai = MagicMock()
    mock_ai.analyze_image_for_templates.return_value = shifts
    return mock_ai


def test_parse_template_image_rejects_undecodable_bytes(import_service):
    from app.services.template_import_service import InvalidImageError
    with pytest.raises(InvalidImageError):
        import_service.parse_template_image(b"this is not an image", "image/png")


def test_parse_template_image_ignores_mismatched_content_type(import_service):
    """A real PNG mislabeled as application/pdf should still decode and process —
    decoding is the source of truth, not the browser-reported content-type."""
    mock_ai = _mock_ai_returning([])
    with patch("app.services.template_import_service.get_ai_service", return_value=mock_ai):
        rows = import_service.parse_template_image(_png_bytes(), "application/octet-stream")
    assert rows == []
    mock_ai.analyze_image_for_templates.assert_called_once()
    # normalized to JPEG regardless of what content-type was declared
    assert mock_ai.analyze_image_for_templates.call_args[0][1] == "image/jpeg"


def test_parse_template_image_converts_heic(import_service):
    """The bug this whole normalization step exists for: iPhone HEIC photos."""
    mock_ai = _mock_ai_returning([])
    with patch("app.services.template_import_service.get_ai_service", return_value=mock_ai):
        rows = import_service.parse_template_image(_heic_bytes(), "image/heic")
    assert rows == []
    sent_bytes, sent_mime = mock_ai.analyze_image_for_templates.call_args[0]
    assert sent_mime == "image/jpeg"
    assert sent_bytes[:2] == b"\xff\xd8"  # JPEG magic bytes


def test_parse_template_image_downscales_large_images(import_service):
    from app.services.template_import_service import _MAX_IMAGE_DIMENSION
    from PIL import Image
    mock_ai = _mock_ai_returning([])
    huge = _png_bytes(size=(4000, 3000))
    with patch("app.services.template_import_service.get_ai_service", return_value=mock_ai):
        import_service.parse_template_image(huge, "image/png")
    sent_bytes, _ = mock_ai.analyze_image_for_templates.call_args[0]
    resized = Image.open(io.BytesIO(sent_bytes))
    assert max(resized.size) <= _MAX_IMAGE_DIMENSION


def test_parse_template_image_happy_path(import_service):
    mock_ai = _mock_ai_returning([
        {"name": "Mya Ferrari", "day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ])
    with patch("app.services.template_import_service.get_ai_service", return_value=mock_ai):
        rows = import_service.parse_template_image(_png_bytes(), "image/png")

    assert len(rows) == 1
    assert rows[0]["confidence"] == "high"
    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["is_valid"] is True
    assert validated[0]["confidence"] == "high"
    assert validated[0]["name"] == "Mya Ferrari"


def test_parse_template_image_name_only_no_role_is_still_valid(import_service):
    """The common whiteboard case: name is extracted, role is not — this must NOT be an error."""
    mock_ai = _mock_ai_returning([
        {"name": "Mya Ferrari", "day_of_week": 2, "start_time": "11:00:00", "end_time": "16:00:00", "role": None, "count": None},
    ])
    with patch("app.services.template_import_service.get_ai_service", return_value=mock_ai):
        rows = import_service.parse_template_image(_png_bytes(), "image/png")

    # role being null doesn't count against confidence — name/day/times are all present
    assert rows[0]["confidence"] == "high"
    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["is_valid"] is True
    assert validated[0]["role"] is None
    assert validated[0]["name"] == "Mya Ferrari"
    assert not any("role" in e for e in validated[0]["errors"])
    assert any("role" in w for w in validated[0]["warnings"])


def test_parse_template_image_low_confidence_on_null_fields(import_service):
    mock_ai = _mock_ai_returning([
        {"name": "Mya Ferrari", "day_of_week": 2, "start_time": None, "end_time": "17:00:00", "role": "Server", "count": None},
    ])
    with patch("app.services.template_import_service.get_ai_service", return_value=mock_ai):
        rows = import_service.parse_template_image(_png_bytes(), "image/png")

    assert rows[0]["confidence"] == "low"
    validated = import_service.validate_parsed_templates(rows)
    # start_time was null -> becomes an error, not just low confidence
    assert validated[0]["is_valid"] is False
    assert validated[0]["confidence"] == "low"


def test_parse_template_image_neither_name_nor_role_is_error(import_service):
    mock_ai = _mock_ai_returning([
        {"name": None, "day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": None, "count": 1},
    ])
    with patch("app.services.template_import_service.get_ai_service", return_value=mock_ai):
        rows = import_service.parse_template_image(_png_bytes(), "image/png")

    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["is_valid"] is False
    assert any("name or role" in e for e in validated[0]["errors"])


def test_parse_template_image_propagates_ai_unavailable(import_service):
    with patch(
        "app.services.template_import_service.get_ai_service",
        side_effect=AIServiceUnavailableError("GROQ_API_KEY is not configured."),
    ):
        with pytest.raises(AIServiceUnavailableError):
            import_service.parse_template_image(_png_bytes(), "image/png")


def test_parse_template_image_empty_shifts(import_service):
    mock_ai = _mock_ai_returning([])
    with patch("app.services.template_import_service.get_ai_service", return_value=mock_ai):
        rows = import_service.parse_template_image(_png_bytes(), "image/png")
    assert rows == []


# === validate_parsed_templates ===


def test_validate_day_of_week_name_and_abbreviation(import_service):
    rows = [
        {"day_of_week": "Monday", "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": "1"},
        {"day_of_week": "Tue", "start_time": "09:00:00", "end_time": "17:00:00", "role": "Cook", "count": "1"},
    ]
    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["day_of_week"] == 1
    assert validated[1]["day_of_week"] == 2
    assert all(r["is_valid"] for r in validated)


def test_validate_time_formats(import_service):
    rows = [
        {"day_of_week": "2", "start_time": "9:00 AM", "end_time": "5:00 PM", "role": "Server", "count": "1"},
    ]
    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["start_time"] == "09:00:00"
    assert validated[0]["end_time"] == "17:00:00"
    assert validated[0]["is_valid"] is True


def test_validate_end_before_start_is_error(import_service):
    rows = [
        {"day_of_week": "2", "start_time": "17:00:00", "end_time": "09:00:00", "role": "Server", "count": "1"},
    ]
    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["is_valid"] is False
    assert any("end_time" in e for e in validated[0]["errors"])


def test_validate_invalid_day_of_week(import_service):
    rows = [
        {"day_of_week": "Someday", "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": "1"},
    ]
    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["is_valid"] is False
    assert validated[0]["day_of_week"] is None


def test_validate_missing_count_defaults_with_warning(import_service):
    rows = [
        {"day_of_week": "2", "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": ""},
    ]
    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["count"] == 1
    assert validated[0]["is_valid"] is True
    assert any("count" in w for w in validated[0]["warnings"])


def test_validate_non_numeric_count_is_error(import_service):
    rows = [
        {"day_of_week": "2", "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": "two"},
    ]
    validated = import_service.validate_parsed_templates(rows)
    assert validated[0]["is_valid"] is False


def test_validate_row_numbers_are_1_indexed(import_service):
    rows = [
        {"day_of_week": "2", "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": "1"},
        {"day_of_week": "3", "start_time": "09:00:00", "end_time": "17:00:00", "role": "Cook", "count": "1"},
    ]
    validated = import_service.validate_parsed_templates(rows)
    assert [r["row_number"] for r in validated] == [1, 2]


# === save_templates_batch ===


def test_save_templates_batch_merges_with_existing():
    mock_shift_template_service = MagicMock()
    mock_shift_template_service.get_templates.return_value = {
        "restaurant_id": RESTAURANT_ID,
        "templates": [{"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1}],
    }
    mock_shift_template_service.upsert_templates.return_value = {"restaurant_id": RESTAURANT_ID}

    svc = TemplateImportService(shift_template_service=mock_shift_template_service)
    new_rows = [{"day_of_week": 3, "start_time": "11:00:00", "end_time": "20:00:00", "role": "Cook", "count": 2}]
    svc.save_templates_batch(RESTAURANT_ID, new_rows)

    called_restaurant_id, called_templates = mock_shift_template_service.upsert_templates.call_args[0]
    assert called_restaurant_id == RESTAURANT_ID
    assert len(called_templates) == 2


def test_save_templates_batch_no_existing_templates():
    mock_shift_template_service = MagicMock()
    mock_shift_template_service.get_templates.return_value = None
    mock_shift_template_service.upsert_templates.return_value = {"restaurant_id": RESTAURANT_ID}

    svc = TemplateImportService(shift_template_service=mock_shift_template_service)
    new_rows = [{"day_of_week": 3, "start_time": "11:00:00", "end_time": "20:00:00", "role": "Cook", "count": 2}]
    svc.save_templates_batch(RESTAURANT_ID, new_rows)

    called_restaurant_id, called_templates = mock_shift_template_service.upsert_templates.call_args[0]
    assert len(called_templates) == 1
