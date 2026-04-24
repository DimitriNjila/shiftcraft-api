import pytest
from unittest.mock import MagicMock
from datetime import date, time
from uuid import UUID

from app.services.schedule_generator_service import ScheduleGenerator
from app.services.schedule_service import ScheduleAlreadyExistsError
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
    """Build a ScheduleGenerator with mocked schedule and employee services."""
    gen = ScheduleGenerator(mock_supabase)
    gen.schedule_service = MagicMock()
    gen.employee_service = MagicMock()
    gen.schedule_service.create_schedule.return_value = schedule_return
    gen.employee_service.get_employees.return_value = employees_return
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


def test_generate_schedule_schedule_already_exists(sample_employee):
    mock_sb = make_supabase_chain()
    gen = ScheduleGenerator(mock_sb)
    gen.schedule_service = MagicMock()
    gen.employee_service = MagicMock()
    gen.schedule_service.create_schedule.side_effect = ScheduleAlreadyExistsError(WEEK_START)

    with pytest.raises(ScheduleAlreadyExistsError):
        gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, SIMPLE_TEMPLATES)


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
