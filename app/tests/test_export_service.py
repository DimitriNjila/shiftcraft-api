import pytest
from unittest.mock import MagicMock
from uuid import UUID

from app.services.export_service import ExportService
from app.services.schedule_service import ScheduleNotFoundError
from app.tests.conftest import make_supabase_chain, SCHEDULE_ID


def test_generate_ical_success(sample_schedule):
    shift = {
        "id": "aaaa",
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "shift_date": "2026-04-22",
        "employee": {"id": "bbbb", "name": "Alice", "role": "Server"},
    }
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_schedule]),  # get_schedule_by_id
        MagicMock(data=[shift]),  # shifts query
        MagicMock(data=[{"name": "Bellagios"}]),  # restaurants lookup
    ]
    svc = ExportService(mock_sb)
    ical = svc.generate_ical(UUID(SCHEDULE_ID))

    assert "BEGIN:VCALENDAR" in ical
    assert "BEGIN:VEVENT" in ical
    assert "SUMMARY:Shift - Server" in ical
    assert "Bellagios" in ical
    assert "DTSTART" in ical
    assert "DTEND" in ical


def test_generate_ical_no_shifts(sample_schedule):
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_schedule]),  # get_schedule_by_id
        MagicMock(data=[]),  # no shifts
        MagicMock(data=[{"name": "Bellagios"}]),  # restaurants lookup
    ]
    svc = ExportService(mock_sb)
    ical = svc.generate_ical(UUID(SCHEDULE_ID))

    assert "BEGIN:VCALENDAR" in ical
    assert "BEGIN:VEVENT" not in ical


def test_generate_ical_schedule_not_found():
    mock_sb = make_supabase_chain([])
    svc = ExportService(mock_sb)
    with pytest.raises(ScheduleNotFoundError):
        svc.generate_ical(UUID(SCHEDULE_ID))
