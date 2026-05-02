import pytest
from unittest.mock import MagicMock
from datetime import date, time
from uuid import UUID

from app.services.schedule_generator_service import ScheduleGenerator
from app.tests.conftest import (
    make_supabase_chain,
    EMPLOYEE_ID,
    EMPLOYEE_ID_2,
    SCHEDULE_ID,
    RESTAURANT_ID,
)

WEEK_START = date(2026, 4, 21)  # A Monday

SIMPLE_TEMPLATES = [
    {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Cook", "count": 1},
]


def _make_generator(mock_supabase, schedule_return, employees_return):
    """Build a ScheduleGenerator with mocked schedule, employee, and template services."""
    gen = ScheduleGenerator(mock_supabase)
    gen.schedule_service = MagicMock()
    gen.employee_service = MagicMock()
    gen.shift_template_service = MagicMock()
    # Default: no pre-existing schedule → create_schedule path is taken
    gen.schedule_service.get_schedule_by_week.return_value = None
    gen.schedule_service.get_week_start.return_value = schedule_return["week_start"]
    gen.schedule_service.create_schedule.return_value = schedule_return
    gen.employee_service.get_employees.return_value = employees_return
    # Default: no saved templates → falls back to BELLAGIOS_SHIFT_TEMPLATES constant
    gen.shift_template_service.get_templates.return_value = None
    return gen


# === generate_schedule ===

def test_generate_schedule_success(sample_schedule, sample_employee, sample_employee_2):
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])  # shifts insert

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee, sample_employee_2])
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, SIMPLE_TEMPLATES)

    assert result["total_shifts"] == 2
    assert result["status"] == "Completed"
    assert result["id"] == SCHEDULE_ID


def test_generate_schedule_no_employees(sample_schedule):
    mock_sb = make_supabase_chain()
    gen = _make_generator(mock_sb, sample_schedule, [])

    with pytest.raises(ValueError, match="No active employees found"):
        gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, SIMPLE_TEMPLATES)


def test_generate_schedule_uses_existing_schedule(sample_schedule, sample_employee):
    """When a schedule already exists for the week, it is reused and create_schedule is not called."""
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee])
    gen.schedule_service.get_schedule_by_week.return_value = sample_schedule  # already exists

    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, SIMPLE_TEMPLATES)

    assert result["id"] == SCHEDULE_ID
    gen.schedule_service.create_schedule.assert_not_called()


def test_generate_schedule_fair_distribution(sample_schedule, sample_employee):
    """Two templates for same role with one employee — both shifts go to that employee."""
    two_server_templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "13:00:00", "role": "Server", "count": 1},
        {"day_of_week": 3, "start_time": "09:00:00", "end_time": "13:00:00", "role": "Server", "count": 1},
    ]
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee])
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, two_server_templates)
    assert result["total_shifts"] == 2


def test_generate_schedule_returns_summary(sample_schedule, sample_employee, sample_employee_2):
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee, sample_employee_2])
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, SIMPLE_TEMPLATES)

    assert "id" in result
    assert "restaurant_id" in result
    assert "week_start" in result
    assert "total_shifts" in result
    assert result["status"] == "Completed"


def test_generate_schedule_no_role_match(sample_schedule, sample_employee):
    """Template requires a role that no employee has — skips with warning, no shifts created."""
    manager_template = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Manager", "count": 1},
    ]
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    # sample_employee has role "Server", not "Manager"
    gen = _make_generator(mock_sb, sample_schedule, [sample_employee])
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, manager_template)
    assert result["total_shifts"] == 0


def test_generate_schedule_uses_default_templates(sample_schedule, sample_employee, sample_employee_2):
    """Calling without shift_templates uses BELLAGIOS_SHIFT_TEMPLATES by default."""
    from app.core.constants import BELLAGIOS_SHIFT_TEMPLATES

    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    # Use employees that match the roles in the default templates
    server = {**sample_employee, "role": "Server"}
    cook = {**sample_employee_2, "role": "Cook"}
    gen = _make_generator(mock_sb, sample_schedule, [server, cook])

    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START)
    # Verify it ran without error and used the default templates (sum of counts, not len)
    assert result["status"] == "Completed"
    assert result["total_shifts"] > 0


# === select_employee_with_least_hours ===

def test_select_employee_with_least_hours():
    employees = [
        {"id": "aaa", "name": "A"},
        {"id": "bbb", "name": "B"},
        {"id": "ccc", "name": "C"},
    ]
    hours = {"aaa": 4.0, "bbb": 6.0, "ccc": 2.0}
    result = ScheduleGenerator.select_employee_with_least_hours(employees, hours)
    assert result["id"] == "ccc"


def test_select_employee_with_least_hours_tie():
    employees = [
        {"id": "aaa", "name": "A"},
        {"id": "bbb", "name": "B"},
    ]
    hours = {"aaa": 4.0, "bbb": 4.0}
    result = ScheduleGenerator.select_employee_with_least_hours(employees, hours)
    assert result is not None  # Either is valid


def test_select_employee_with_least_hours_empty():
    result = ScheduleGenerator.select_employee_with_least_hours([], {})
    assert result is None


# === parse_time ===

def test_parse_time_valid():
    result = ScheduleGenerator.parse_time("09:00:00")
    assert result == time(9, 0, 0)


def test_parse_time_invalid():
    with pytest.raises(ValueError):
        ScheduleGenerator.parse_time("9:00")


# === calculate_duration ===

def test_calculate_duration():
    result = ScheduleGenerator.calculate_duration(time(9, 0), time(17, 0))
    assert result == 8.0


def test_calculate_duration_fractional():
    result = ScheduleGenerator.calculate_duration(time(9, 0), time(13, 30))
    assert result == 4.5


# === _has_sufficient_rest ===

def test_has_sufficient_rest_no_previous_shift():
    """No prior shift → always sufficient rest."""
    from datetime import datetime
    assert ScheduleGenerator._has_sufficient_rest(None, datetime(2026, 4, 22, 9, 0)) is True


def test_has_sufficient_rest_enough_gap():
    from datetime import datetime
    last_end = datetime(2026, 4, 21, 20, 0)  # 8pm
    next_start = datetime(2026, 4, 22, 9, 0)  # 9am next day → 13h gap
    assert ScheduleGenerator._has_sufficient_rest(last_end, next_start) is True


def test_has_sufficient_rest_too_short():
    from datetime import datetime
    last_end = datetime(2026, 4, 22, 22, 0)  # 10pm
    next_start = datetime(2026, 4, 23, 7, 0)  # 7am next day → 9h gap (< 10h)
    assert ScheduleGenerator._has_sufficient_rest(last_end, next_start) is False


def test_has_sufficient_rest_exactly_minimum():
    from datetime import datetime
    last_end = datetime(2026, 4, 21, 23, 0)  # 11pm
    next_start = datetime(2026, 4, 22, 9, 0)  # 9am → exactly 10h
    assert ScheduleGenerator._has_sufficient_rest(last_end, next_start) is True


# === _would_exceed_hours_cap ===

def test_would_exceed_hours_cap_no_cap():
    """Employee without a cap is never blocked."""
    emp = {"id": "aaa", "name": "A"}
    assert ScheduleGenerator._would_exceed_hours_cap(emp, 35.0, 8.0) is False


def test_would_exceed_hours_cap_within_limit():
    emp = {"id": "aaa", "name": "A", "max_hours_per_week": 40.0}
    assert ScheduleGenerator._would_exceed_hours_cap(emp, 30.0, 8.0) is False


def test_would_exceed_hours_cap_exceeds():
    emp = {"id": "aaa", "name": "A", "max_hours_per_week": 40.0}
    assert ScheduleGenerator._would_exceed_hours_cap(emp, 35.0, 8.0) is True


def test_would_exceed_hours_cap_exact_boundary():
    """Adding hours that exactly hit the cap is allowed."""
    emp = {"id": "aaa", "name": "A", "max_hours_per_week": 40.0}
    assert ScheduleGenerator._would_exceed_hours_cap(emp, 32.0, 8.0) is False


# === generate_schedule with constraints ===

def test_generate_schedule_skips_employee_with_insufficient_rest(sample_schedule, sample_employee, sample_employee_2):
    """
    Two overlapping templates assigned to employees of the same role.
    Employee with a recent shift end should be skipped in favour of the other.
    """
    from datetime import datetime
    two_server_templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 2, "start_time": "20:00:00", "end_time": "23:00:00", "role": "Server", "count": 1},
    ]
    server2 = {**sample_employee_2, "role": "Server"}
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee, server2])
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, two_server_templates)

    # Both shifts should be fillable because two employees are available
    assert result["total_shifts"] == 2


def test_generate_schedule_respects_hours_cap(sample_schedule, sample_employee):
    """An employee with a tight hours cap gets skipped once the cap would be exceeded."""
    capped_employee = {**sample_employee, "max_hours_per_week": 8.0}
    # Two 8-hour shifts: first should be assigned, second should be skipped (would hit 16h > 8h cap)
    two_shifts = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ]
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [capped_employee])
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, two_shifts)

    # First shift assigned, second skipped due to cap
    assert result["total_shifts"] == 1
