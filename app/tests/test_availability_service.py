import pytest
from unittest.mock import MagicMock, patch
from uuid import UUID

from app.services.availability_service import (
    AvailabilityService,
    AvailabilityConflictError,
    AvailabilityNotFoundError,
)
from app.services.employee_service import EmployeeNotFoundError
from app.tests.conftest import (
    make_supabase_chain,
    EMPLOYEE_ID,
    RESTAURANT_ID,
)

AVAIL_ID = "66666666-6666-6666-6666-666666666666"


@pytest.fixture
def sample_availability():
    return {
        "id": AVAIL_ID,
        "employee_id": EMPLOYEE_ID,
        "restaurant_id": RESTAURANT_ID,
        "day_of_week": 2,
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }


def _make_service(avail_data=None, employee_data=None):
    """Build an AvailabilityService with a mocked supabase client."""
    mock_sb = make_supabase_chain(return_data=avail_data or [])
    svc = AvailabilityService(mock_sb)
    # Wire a mock employee_service so we control employee lookup independently
    svc._employee_service = MagicMock()
    svc._employee_service.get_employee_by_id.return_value = employee_data
    return svc, mock_sb


# === get_availability ===

def test_get_availability_returns_list(sample_availability):
    svc, _ = _make_service(avail_data=[sample_availability])
    result = svc.get_availability(UUID(EMPLOYEE_ID))
    assert len(result) == 1
    assert result[0]["day_of_week"] == 2


def test_get_availability_empty():
    svc, _ = _make_service(avail_data=[])
    result = svc.get_availability(UUID(EMPLOYEE_ID))
    assert result == []


def test_get_availability_filters_by_employee(sample_availability):
    svc, mock_sb = _make_service(avail_data=[sample_availability])
    svc.get_availability(UUID(EMPLOYEE_ID))
    mock_sb.eq.assert_any_call("employee_id", EMPLOYEE_ID)


# === add_availability ===

def test_add_availability_success(sample_availability, sample_employee):
    svc, mock_sb = _make_service(
        avail_data=[sample_availability],
        employee_data=sample_employee,
    )
    result = svc.add_availability(
        employee_id=UUID(EMPLOYEE_ID),
        day_of_week=2,
        start_time="09:00:00",
        end_time="17:00:00",
    )
    assert result["day_of_week"] == 2
    mock_sb.insert.assert_called_once()


def test_add_availability_employee_not_found():
    svc, _ = _make_service(employee_data=None)
    with pytest.raises(EmployeeNotFoundError):
        svc.add_availability(
            employee_id=UUID(EMPLOYEE_ID),
            day_of_week=2,
            start_time="09:00:00",
            end_time="17:00:00",
        )


def test_add_availability_end_before_start(sample_employee):
    svc, _ = _make_service(employee_data=sample_employee)
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        svc.add_availability(
            employee_id=UUID(EMPLOYEE_ID),
            day_of_week=2,
            start_time="17:00:00",
            end_time="09:00:00",
        )


def test_add_availability_end_equals_start(sample_employee):
    svc, _ = _make_service(employee_data=sample_employee)
    with pytest.raises(ValueError, match="end_time must be after start_time"):
        svc.add_availability(
            employee_id=UUID(EMPLOYEE_ID),
            day_of_week=2,
            start_time="09:00:00",
            end_time="09:00:00",
        )


def test_add_availability_uses_employee_restaurant_id(sample_availability, sample_employee):
    """restaurant_id on the availability row is pulled from the employee, not the caller."""
    svc, mock_sb = _make_service(
        avail_data=[sample_availability],
        employee_data=sample_employee,
    )
    svc.add_availability(
        employee_id=UUID(EMPLOYEE_ID),
        day_of_week=2,
        start_time="09:00:00",
        end_time="17:00:00",
    )
    inserted = mock_sb.insert.call_args[0][0]
    assert inserted["restaurant_id"] == str(RESTAURANT_ID)


def test_add_availability_duplicate_raises_conflict(sample_employee):
    svc, mock_sb = _make_service(employee_data=sample_employee)
    mock_sb.execute.side_effect = Exception("unique constraint violation")
    with pytest.raises(AvailabilityConflictError):
        svc.add_availability(
            employee_id=UUID(EMPLOYEE_ID),
            day_of_week=2,
            start_time="09:00:00",
            end_time="17:00:00",
        )


def test_add_availability_non_unique_exception_reraises(sample_employee):
    """Exceptions unrelated to uniqueness are not swallowed."""
    svc, mock_sb = _make_service(employee_data=sample_employee)
    mock_sb.execute.side_effect = Exception("connection timeout")
    with pytest.raises(Exception, match="connection timeout"):
        svc.add_availability(
            employee_id=UUID(EMPLOYEE_ID),
            day_of_week=2,
            start_time="09:00:00",
            end_time="17:00:00",
        )


# === delete_availability ===

def test_delete_availability_success(sample_availability):
    svc, mock_sb = _make_service(avail_data=[sample_availability])
    result = svc.delete_availability(UUID(EMPLOYEE_ID), UUID(AVAIL_ID))
    assert result["id"] == AVAIL_ID
    mock_sb.delete.assert_called_once()


def test_delete_availability_not_found():
    svc, _ = _make_service(avail_data=[])
    with pytest.raises(AvailabilityNotFoundError):
        svc.delete_availability(UUID(EMPLOYEE_ID), UUID(AVAIL_ID))


def test_delete_availability_scoped_to_employee(sample_availability):
    """Delete query must include both id and employee_id to prevent cross-employee deletes."""
    svc, mock_sb = _make_service(avail_data=[sample_availability])
    svc.delete_availability(UUID(EMPLOYEE_ID), UUID(AVAIL_ID))
    eq_calls = [str(call) for call in mock_sb.eq.call_args_list]
    assert any("employee_id" in c for c in eq_calls)
    assert any(AVAIL_ID in c for c in eq_calls)
