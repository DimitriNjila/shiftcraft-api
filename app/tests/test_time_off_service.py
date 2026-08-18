from datetime import date
from unittest.mock import MagicMock
from uuid import UUID

import pytest

from app.services.employee_service import EmployeeNotFoundError
from app.services.time_off_service import (
    TimeOffNotFoundError,
    TimeOffService,
)

from .conftest import EMPLOYEE_ID, RESTAURANT_ID, make_supabase_chain


TIME_OFF_ID = "66666666-6666-6666-6666-666666666666"


def _sample_row(**overrides):
    base = {
        "id": TIME_OFF_ID,
        "employee_id": EMPLOYEE_ID,
        "restaurant_id": RESTAURANT_ID,
        "start_date": "2026-08-21",
        "end_date": "2026-08-21",
        "reason": "interview",
        "created_at": "2026-08-17T00:00:00",
        "updated_at": "2026-08-17T00:00:00",
    }
    base.update(overrides)
    return base


def test_add_time_off_success(sample_employee):
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_employee]),  # employee lookup
        MagicMock(data=[_sample_row()]),    # insert
    ]
    svc = TimeOffService(mock_sb)
    result = svc.add(
        UUID(EMPLOYEE_ID),
        start_date=date(2026, 8, 21),
        end_date=date(2026, 8, 21),
        reason="interview",
    )
    assert result["reason"] == "interview"
    mock_sb.insert.assert_called_once()


def test_add_time_off_employee_missing():
    mock_sb = make_supabase_chain([])
    svc = TimeOffService(mock_sb)
    with pytest.raises(EmployeeNotFoundError):
        svc.add(UUID(EMPLOYEE_ID), date(2026, 8, 21), date(2026, 8, 21))


def test_add_time_off_rejects_reversed_dates(sample_employee):
    mock_sb = make_supabase_chain([sample_employee])
    svc = TimeOffService(mock_sb)
    with pytest.raises(ValueError, match="on or after start_date"):
        svc.add(UUID(EMPLOYEE_ID), date(2026, 8, 22), date(2026, 8, 21))


def test_list_for_employee_returns_rows():
    mock_sb = make_supabase_chain([_sample_row(), _sample_row(id="x")])
    svc = TimeOffService(mock_sb)
    assert len(svc.list_for_employee(UUID(EMPLOYEE_ID))) == 2


def test_list_overlapping_filters_by_range():
    mock_sb = make_supabase_chain([_sample_row()])
    svc = TimeOffService(mock_sb)
    result = svc.list_overlapping(RESTAURANT_ID, date(2026, 8, 17), date(2026, 8, 23))
    assert len(result) == 1
    mock_sb.lte.assert_any_call("start_date", "2026-08-23")
    mock_sb.gte.assert_any_call("end_date", "2026-08-17")


def test_delete_time_off_scopes_to_employee():
    mock_sb = make_supabase_chain([_sample_row()])
    svc = TimeOffService(mock_sb)
    result = svc.delete(UUID(EMPLOYEE_ID), UUID(TIME_OFF_ID))
    assert result["id"] == TIME_OFF_ID


def test_delete_time_off_not_found_for_employee():
    mock_sb = make_supabase_chain([])
    svc = TimeOffService(mock_sb)
    with pytest.raises(TimeOffNotFoundError):
        svc.delete(UUID(EMPLOYEE_ID), UUID(TIME_OFF_ID))


def test_time_off_create_model_rejects_reversed_dates():
    from app.models.time_off_model import TimeOffCreate

    with pytest.raises(ValueError, match="on or after start_date"):
        TimeOffCreate(start_date=date(2026, 8, 22), end_date=date(2026, 8, 21))


def test_time_off_create_model_strips_blank_reason():
    from app.models.time_off_model import TimeOffCreate

    payload = TimeOffCreate(
        start_date=date(2026, 8, 21), end_date=date(2026, 8, 21), reason="   "
    )
    assert payload.reason is None
