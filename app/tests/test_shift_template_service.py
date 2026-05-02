import pytest
from unittest.mock import MagicMock

from app.services.shift_template_service import ShiftTemplateService
from app.tests.conftest import make_supabase_chain, RESTAURANT_ID, TEMPLATE_ID


SIMPLE_TEMPLATES = [
    {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    {"day_of_week": 3, "start_time": "11:00:00", "end_time": "20:00:00", "role": "Cook", "count": 1},
]


def make_template_record(templates=None):
    return {
        "id": TEMPLATE_ID,
        "restaurant_id": RESTAURANT_ID,
        "templates": templates if templates is not None else SIMPLE_TEMPLATES,
        "updated_at": "2026-01-01T00:00:00",
    }


# === get_templates ===

def test_get_templates_found(sample_shift_templates):
    mock_sb = make_supabase_chain([sample_shift_templates])
    svc = ShiftTemplateService(mock_sb)

    result = svc.get_templates(RESTAURANT_ID)

    assert result is not None
    assert result["restaurant_id"] == RESTAURANT_ID
    assert len(result["templates"]) == 2
    mock_sb.eq.assert_called_with("restaurant_id", RESTAURANT_ID)


def test_get_templates_not_found():
    mock_sb = make_supabase_chain([])
    svc = ShiftTemplateService(mock_sb)

    result = svc.get_templates(RESTAURANT_ID)

    assert result is None


def test_get_templates_returns_first_record():
    """Only one record per restaurant — always returns data[0]."""
    record = make_template_record()
    mock_sb = make_supabase_chain([record])
    svc = ShiftTemplateService(mock_sb)

    result = svc.get_templates(RESTAURANT_ID)

    assert result["id"] == TEMPLATE_ID


def test_get_templates_queries_correct_table():
    mock_sb = make_supabase_chain([])
    svc = ShiftTemplateService(mock_sb)

    svc.get_templates(RESTAURANT_ID)

    mock_sb.table.assert_called_with("shift_templates")


# === upsert_templates ===

def test_upsert_templates_returns_saved_record(sample_shift_templates):
    mock_sb = make_supabase_chain([sample_shift_templates])
    svc = ShiftTemplateService(mock_sb)

    result = svc.upsert_templates(RESTAURANT_ID, SIMPLE_TEMPLATES)

    assert result["id"] == TEMPLATE_ID
    assert result["restaurant_id"] == RESTAURANT_ID


def test_upsert_templates_calls_upsert_not_insert(sample_shift_templates):
    mock_sb = make_supabase_chain([sample_shift_templates])
    svc = ShiftTemplateService(mock_sb)

    svc.upsert_templates(RESTAURANT_ID, SIMPLE_TEMPLATES)

    mock_sb.upsert.assert_called_once()
    mock_sb.insert.assert_not_called()


def test_upsert_templates_passes_correct_data(sample_shift_templates):
    mock_sb = make_supabase_chain([sample_shift_templates])
    svc = ShiftTemplateService(mock_sb)

    svc.upsert_templates(RESTAURANT_ID, SIMPLE_TEMPLATES)

    call_args = mock_sb.upsert.call_args
    payload = call_args[0][0]
    assert payload["restaurant_id"] == RESTAURANT_ID
    assert payload["templates"] == SIMPLE_TEMPLATES


def test_upsert_templates_uses_restaurant_id_conflict_target(sample_shift_templates):
    mock_sb = make_supabase_chain([sample_shift_templates])
    svc = ShiftTemplateService(mock_sb)

    svc.upsert_templates(RESTAURANT_ID, SIMPLE_TEMPLATES)

    call_kwargs = mock_sb.upsert.call_args[1]
    assert call_kwargs.get("on_conflict") == "restaurant_id"


def test_upsert_templates_empty_list():
    """Saving an empty template list is valid — clears the schedule pattern."""
    empty_record = make_template_record(templates=[])
    mock_sb = make_supabase_chain([empty_record])
    svc = ShiftTemplateService(mock_sb)

    result = svc.upsert_templates(RESTAURANT_ID, [])

    assert result["templates"] == []
    mock_sb.upsert.assert_called_once()


def test_upsert_templates_overwrites_previous(sample_shift_templates):
    """Second upsert replaces the first — only one record per restaurant."""
    new_templates = [
        {"day_of_week": 5, "start_time": "16:00:00", "end_time": "21:00:00", "role": "Server", "count": 2},
    ]
    updated_record = {**sample_shift_templates, "templates": new_templates}
    mock_sb = make_supabase_chain([updated_record])
    svc = ShiftTemplateService(mock_sb)

    result = svc.upsert_templates(RESTAURANT_ID, new_templates)

    assert result["templates"] == new_templates
    # Upsert called once — not insert + update
    assert mock_sb.upsert.call_count == 1
