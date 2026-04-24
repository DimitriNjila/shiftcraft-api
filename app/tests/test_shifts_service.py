import pytest
from unittest.mock import MagicMock, patch
from datetime import date, time
from uuid import UUID

from app.services.shifts_service import (
    ShiftsService,
    ShiftValidationError,
    ShiftNotFoundError,
    OverlappingShiftError,
)
from app.services.employee_service import EmployeeNotFoundError
from app.services.schedule_service import ScheduleNotFoundError
from app.tests.conftest import (
    make_supabase_chain,
    EMPLOYEE_ID,
    SCHEDULE_ID,
    SHIFT_ID,
    RESTAURANT_ID,
)


# === validate_shift_times ===

def test_validate_shift_times_valid():
    svc = ShiftsService(make_supabase_chain())
    result = svc.validate_shift_times(
        time(9, 0), time(17, 0), date(2026, 4, 22)
    )
    assert result is True  # 8 hours < 600 minutes


def test_validate_shift_times_end_before_start():
    svc = ShiftsService(make_supabase_chain())
    with pytest.raises(ShiftValidationError, match="End time must be after start time"):
        svc.validate_shift_times(time(17, 0), time(9, 0), date(2026, 4, 22))


def test_validate_shift_times_end_equals_start():
    svc = ShiftsService(make_supabase_chain())
    with pytest.raises(ShiftValidationError):
        svc.validate_shift_times(time(9, 0), time(9, 0), date(2026, 4, 22))


def test_validate_shift_times_over_10_hours():
    svc = ShiftsService(make_supabase_chain())
    result = svc.validate_shift_times(
        time(6, 0), time(17, 0), date(2026, 4, 22)
    )
    assert result is False  # 11 hours > 600 minutes


# === validate_employee_can_work ===

def test_validate_employee_can_work_active(sample_employee):
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.employee_service") as mock_emp_svc:
        mock_emp_svc.get_employee_by_id.return_value = sample_employee
        result = svc.validate_employee_can_work(UUID(EMPLOYEE_ID))
    assert result["id"] == EMPLOYEE_ID


def test_validate_employee_can_work_not_found():
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.employee_service") as mock_emp_svc:
        mock_emp_svc.get_employee_by_id.return_value = None
        with pytest.raises(EmployeeNotFoundError):
            svc.validate_employee_can_work(UUID(EMPLOYEE_ID))


def test_validate_employee_can_work_inactive(sample_employee):
    svc = ShiftsService(make_supabase_chain())
    inactive = {**sample_employee, "is_active": False}
    with patch("app.services.shifts_service.employee_service") as mock_emp_svc:
        mock_emp_svc.get_employee_by_id.return_value = inactive
        with pytest.raises(ShiftValidationError, match="inactive"):
            svc.validate_employee_can_work(UUID(EMPLOYEE_ID))


# === validate_date_in_schedule_week ===

def test_validate_date_in_schedule_week_valid(sample_schedule):
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched_svc:
        mock_sched_svc.get_schedule_by_id.return_value = sample_schedule
        # Wednesday 2026-04-22 is within week starting 2026-04-21
        svc.validate_date_in_schedule_week(UUID(SCHEDULE_ID), date(2026, 4, 22))


def test_validate_date_in_schedule_week_before(sample_schedule):
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched_svc:
        mock_sched_svc.get_schedule_by_id.return_value = sample_schedule
        with pytest.raises(ShiftValidationError, match="within schedule week"):
            svc.validate_date_in_schedule_week(UUID(SCHEDULE_ID), date(2026, 4, 20))


def test_validate_date_in_schedule_week_after(sample_schedule):
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched_svc:
        mock_sched_svc.get_schedule_by_id.return_value = sample_schedule
        with pytest.raises(ShiftValidationError, match="within schedule week"):
            svc.validate_date_in_schedule_week(UUID(SCHEDULE_ID), date(2026, 4, 28))


def test_validate_date_in_schedule_week_boundary_start(sample_schedule):
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched_svc:
        mock_sched_svc.get_schedule_by_id.return_value = sample_schedule
        # Monday 2026-04-21 is the week_start itself — should pass
        svc.validate_date_in_schedule_week(UUID(SCHEDULE_ID), date(2026, 4, 21))


def test_validate_date_in_schedule_week_boundary_end(sample_schedule):
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched_svc:
        mock_sched_svc.get_schedule_by_id.return_value = sample_schedule
        # Sunday 2026-04-27 is the last day of the week — should pass
        svc.validate_date_in_schedule_week(UUID(SCHEDULE_ID), date(2026, 4, 27))


# === check_for_overlapping_shifts ===

def test_check_for_overlapping_shifts_no_overlap():
    mock_sb = make_supabase_chain([])  # No existing shifts
    svc = ShiftsService(mock_sb)
    result = svc.check_for_overlapping_shifts(
        UUID(EMPLOYEE_ID), date(2026, 4, 22), time(9, 0), time(17, 0)
    )
    assert result == []


def test_check_for_overlapping_shifts_exact_overlap(sample_shift):
    mock_sb = make_supabase_chain([sample_shift])
    svc = ShiftsService(mock_sb)
    result = svc.check_for_overlapping_shifts(
        UUID(EMPLOYEE_ID), date(2026, 4, 22), time(9, 0), time(17, 0)
    )
    assert len(result) == 1


def test_check_for_overlapping_shifts_partial_overlap(sample_shift):
    # New shift starts at 11:00, existing ends at 17:00 → overlap
    mock_sb = make_supabase_chain([sample_shift])
    svc = ShiftsService(mock_sb)
    result = svc.check_for_overlapping_shifts(
        UUID(EMPLOYEE_ID), date(2026, 4, 22), time(11, 0), time(19, 0)
    )
    assert len(result) == 1


def test_check_for_overlapping_shifts_adjacent_no_overlap(sample_shift):
    # New shift starts exactly when existing ends (09:00-17:00 then 17:00-21:00)
    mock_sb = make_supabase_chain([sample_shift])
    svc = ShiftsService(mock_sb)
    result = svc.check_for_overlapping_shifts(
        UUID(EMPLOYEE_ID), date(2026, 4, 22), time(17, 0), time(21, 0)
    )
    assert result == []


def test_check_for_overlapping_shifts_excludes_self(sample_shift):
    # Exclude the same shift ID (update scenario) — should report no overlap
    mock_sb = make_supabase_chain([])  # neq filter removes the shift
    svc = ShiftsService(mock_sb)
    result = svc.check_for_overlapping_shifts(
        UUID(EMPLOYEE_ID),
        date(2026, 4, 22),
        time(9, 0),
        time(17, 0),
        exclude_shift_id=UUID(SHIFT_ID),
    )
    assert result == []
    mock_sb.neq.assert_called_once_with("id", SHIFT_ID)


# === create_shift ===

def test_create_shift_success(sample_employee, sample_schedule, sample_shift):
    mock_sb = make_supabase_chain()
    # check_for_overlapping_shifts query → no overlaps; insert → created shift
    mock_sb.execute.side_effect = [
        MagicMock(data=[]),           # check_for_overlapping_shifts
        MagicMock(data=[sample_shift]),  # insert
    ]
    svc = ShiftsService(mock_sb)
    with patch("app.services.shifts_service.schedule_service") as mock_sched, \
         patch("app.services.shifts_service.employee_service") as mock_emp:
        mock_sched.get_schedule_by_id.return_value = sample_schedule
        mock_emp.get_employee_by_id.return_value = sample_employee
        result = svc.create_shift(
            schedule_id=UUID(SCHEDULE_ID),
            employee_id=UUID(EMPLOYEE_ID),
            shift_date=date(2026, 4, 22),
            start_time=time(9, 0),
            end_time=time(17, 0),
        )
    assert result["id"] == SHIFT_ID


def test_create_shift_schedule_not_found():
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched:
        mock_sched.get_schedule_by_id.return_value = None
        with pytest.raises(ScheduleNotFoundError):
            svc.create_shift(
                schedule_id=UUID(SCHEDULE_ID),
                employee_id=UUID(EMPLOYEE_ID),
                shift_date=date(2026, 4, 22),
                start_time=time(9, 0),
                end_time=time(17, 0),
            )


def test_create_shift_employee_not_found(sample_schedule):
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched, \
         patch("app.services.shifts_service.employee_service") as mock_emp:
        mock_sched.get_schedule_by_id.return_value = sample_schedule
        mock_emp.get_employee_by_id.return_value = None
        with pytest.raises(EmployeeNotFoundError):
            svc.create_shift(
                schedule_id=UUID(SCHEDULE_ID),
                employee_id=UUID(EMPLOYEE_ID),
                shift_date=date(2026, 4, 22),
                start_time=time(9, 0),
                end_time=time(17, 0),
            )


def test_create_shift_employee_inactive(sample_schedule, sample_employee):
    inactive = {**sample_employee, "is_active": False}
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched, \
         patch("app.services.shifts_service.employee_service") as mock_emp:
        mock_sched.get_schedule_by_id.return_value = sample_schedule
        mock_emp.get_employee_by_id.return_value = inactive
        with pytest.raises(ShiftValidationError, match="inactive"):
            svc.create_shift(
                schedule_id=UUID(SCHEDULE_ID),
                employee_id=UUID(EMPLOYEE_ID),
                shift_date=date(2026, 4, 22),
                start_time=time(9, 0),
                end_time=time(17, 0),
            )


def test_create_shift_date_outside_week(sample_employee, sample_schedule):
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched, \
         patch("app.services.shifts_service.employee_service") as mock_emp:
        mock_sched.get_schedule_by_id.return_value = sample_schedule
        mock_emp.get_employee_by_id.return_value = sample_employee
        with pytest.raises(ShiftValidationError, match="within schedule week"):
            svc.create_shift(
                schedule_id=UUID(SCHEDULE_ID),
                employee_id=UUID(EMPLOYEE_ID),
                shift_date=date(2026, 5, 1),  # Outside 2026-04-21 week
                start_time=time(9, 0),
                end_time=time(17, 0),
            )


def test_create_shift_time_invalid(sample_employee, sample_schedule):
    svc = ShiftsService(make_supabase_chain())
    with patch("app.services.shifts_service.schedule_service") as mock_sched, \
         patch("app.services.shifts_service.employee_service") as mock_emp:
        mock_sched.get_schedule_by_id.return_value = sample_schedule
        mock_emp.get_employee_by_id.return_value = sample_employee
        with pytest.raises(ShiftValidationError, match="End time must be after start time"):
            svc.create_shift(
                schedule_id=UUID(SCHEDULE_ID),
                employee_id=UUID(EMPLOYEE_ID),
                shift_date=date(2026, 4, 22),
                start_time=time(17, 0),
                end_time=time(9, 0),
            )


def test_create_shift_overlap(sample_employee, sample_schedule, sample_shift):
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_shift]),  # check_for_overlapping_shifts → overlap found
    ]
    svc = ShiftsService(mock_sb)
    with patch("app.services.shifts_service.schedule_service") as mock_sched, \
         patch("app.services.shifts_service.employee_service") as mock_emp:
        mock_sched.get_schedule_by_id.return_value = sample_schedule
        mock_emp.get_employee_by_id.return_value = sample_employee
        with pytest.raises(OverlappingShiftError):
            svc.create_shift(
                schedule_id=UUID(SCHEDULE_ID),
                employee_id=UUID(EMPLOYEE_ID),
                shift_date=date(2026, 4, 22),
                start_time=time(9, 0),
                end_time=time(17, 0),
            )


# === update_shift ===

def test_update_shift_not_found():
    mock_sb = make_supabase_chain([])  # get_shift_by_id → not found
    svc = ShiftsService(mock_sb)
    with pytest.raises(ShiftNotFoundError):
        svc.update_shift(UUID(SHIFT_ID), start_time=time(10, 0))


def test_update_shift_no_changes(sample_shift):
    # Providing no fields at all → update_data stays empty → returns existing without DB update
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_shift]),  # get_shift_by_id
    ]
    svc = ShiftsService(mock_sb)
    result = svc.update_shift(UUID(SHIFT_ID))
    assert result["id"] == SHIFT_ID
    mock_sb.update.assert_not_called()


def test_update_shift_success(sample_shift, sample_schedule):
    updated = {**sample_shift, "start_time": "10:00:00"}
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_shift]),  # get_shift_by_id
        MagicMock(data=[]),               # check_for_overlapping_shifts
        MagicMock(data=[updated]),        # update
    ]
    svc = ShiftsService(mock_sb)
    with patch("app.services.shifts_service.schedule_service") as mock_sched:
        mock_sched.get_schedule_by_id.return_value = sample_schedule
        result = svc.update_shift(UUID(SHIFT_ID), start_time=time(10, 0))
    assert result["start_time"] == "10:00:00"


def test_update_shift_creates_overlap(sample_shift, sample_schedule):
    other_shift = {**sample_shift, "id": "other-shift", "start_time": "14:00:00", "end_time": "20:00:00"}
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_shift]),    # get_shift_by_id
        MagicMock(data=[other_shift]),     # check_for_overlapping_shifts → overlap
    ]
    svc = ShiftsService(mock_sb)
    with patch("app.services.shifts_service.schedule_service") as mock_sched:
        mock_sched.get_schedule_by_id.return_value = sample_schedule
        with pytest.raises(OverlappingShiftError):
            svc.update_shift(UUID(SHIFT_ID), end_time=time(16, 0))


def test_update_shift_employee_change(sample_shift, sample_schedule, sample_employee):
    new_employee_id = "55555555-5555-5555-5555-555555555555"
    new_employee = {**sample_employee, "id": new_employee_id}
    updated = {**sample_shift, "employee_id": new_employee_id}
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_shift]),  # get_shift_by_id
        MagicMock(data=[]),               # check_for_overlapping_shifts → no overlap
        MagicMock(data=[updated]),        # update
    ]
    svc = ShiftsService(mock_sb)
    with patch("app.services.shifts_service.schedule_service") as mock_sched, \
         patch("app.services.shifts_service.employee_service") as mock_emp:
        mock_sched.get_schedule_by_id.return_value = sample_schedule
        mock_emp.get_employee_by_id.return_value = new_employee
        result = svc.update_shift(UUID(SHIFT_ID), employee_id=UUID(new_employee_id))
    assert result["employee_id"] == new_employee_id
