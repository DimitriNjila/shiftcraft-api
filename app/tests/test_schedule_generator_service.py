import pytest
from unittest.mock import MagicMock, patch
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


def test_generate_schedule_skips_employees_on_time_off(
    sample_schedule, sample_employee, sample_employee_2
):
    """
    Employee on time-off for the shift date is excluded from the candidate
    pool for slots on that date, even if they'd otherwise be the fair pick.
    """
    # Two identical Server slots on Tue (2026-04-22). Alice is on time-off
    # that day; Bob (a Cook) has the wrong role. Result: no shifts assigned.
    server_only = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "13:00:00", "role": "Server", "count": 1},
    ]
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[]),  # _load_availability
        MagicMock(
            data=[
                {
                    "employee_id": EMPLOYEE_ID,  # Alice, the only Server
                    "start_date": "2026-04-22",
                    "end_date": "2026-04-22",
                }
            ]
        ),  # _load_time_off
        MagicMock(data=[]),  # (no insert — nothing to schedule)
    ]

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee, sample_employee_2])
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, server_only)

    assert result["total_shifts"] == 0


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
# Signature: _has_sufficient_rest(existing_intervals, new_start, new_end) —
# checks the new shift against EVERY existing interval (not just the most
# recent), since slots are no longer necessarily processed in date order.

def test_has_sufficient_rest_no_previous_shifts():
    """No prior shifts → always sufficient rest."""
    from datetime import datetime
    result = ScheduleGenerator._has_sufficient_rest(
        [], datetime(2026, 4, 22, 9, 0), datetime(2026, 4, 22, 17, 0)
    )
    assert result is True


def test_has_sufficient_rest_enough_gap_after():
    from datetime import datetime
    existing = [(datetime(2026, 4, 21, 12, 0), datetime(2026, 4, 21, 20, 0))]  # ends 8pm
    result = ScheduleGenerator._has_sufficient_rest(
        existing, datetime(2026, 4, 22, 9, 0), datetime(2026, 4, 22, 17, 0)  # starts 9am next day → 13h gap
    )
    assert result is True


def test_has_sufficient_rest_too_short_after():
    from datetime import datetime
    existing = [(datetime(2026, 4, 22, 14, 0), datetime(2026, 4, 22, 22, 0))]  # ends 10pm
    result = ScheduleGenerator._has_sufficient_rest(
        existing, datetime(2026, 4, 23, 7, 0), datetime(2026, 4, 23, 15, 0)  # starts 7am next day → 9h gap
    )
    assert result is False


def test_has_sufficient_rest_exactly_minimum():
    from datetime import datetime
    existing = [(datetime(2026, 4, 21, 15, 0), datetime(2026, 4, 21, 23, 0))]  # ends 11pm
    result = ScheduleGenerator._has_sufficient_rest(
        existing, datetime(2026, 4, 22, 9, 0), datetime(2026, 4, 22, 17, 0)  # starts 9am → exactly 10h
    )
    assert result is True


def test_has_sufficient_rest_enough_gap_before():
    """New shift chronologically BEFORE an existing one, with enough gap — must also be respected,
    since scarcity-first ordering can assign a later shift before an earlier one."""
    from datetime import datetime
    existing = [(datetime(2026, 4, 23, 9, 0), datetime(2026, 4, 23, 17, 0))]
    result = ScheduleGenerator._has_sufficient_rest(
        existing, datetime(2026, 4, 22, 8, 0), datetime(2026, 4, 22, 12, 0)
    )
    assert result is True


def test_has_sufficient_rest_too_short_before():
    from datetime import datetime
    existing = [(datetime(2026, 4, 23, 9, 0), datetime(2026, 4, 23, 17, 0))]
    result = ScheduleGenerator._has_sufficient_rest(
        existing, datetime(2026, 4, 22, 22, 0), datetime(2026, 4, 23, 2, 0)  # ends 2am, only 7h before existing starts
    )
    assert result is False


def test_has_sufficient_rest_must_satisfy_every_interval():
    """One conflicting interval among several is enough to reject, even if others are fine."""
    from datetime import datetime
    existing = [
        (datetime(2026, 4, 21, 9, 0), datetime(2026, 4, 21, 17, 0)),   # far enough from the new shift
        (datetime(2026, 4, 22, 20, 0), datetime(2026, 4, 23, 4, 0)),   # too close to the new shift below
    ]
    result = ScheduleGenerator._has_sufficient_rest(
        existing, datetime(2026, 4, 23, 8, 0), datetime(2026, 4, 23, 16, 0)
    )
    assert result is False


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


# === _is_available ===

def test_is_available_no_entry_in_map():
    """Employee absent from map → no availability set → always available."""
    result = ScheduleGenerator._is_available(
        EMPLOYEE_ID, 2, time(9, 0), time(17, 0), availability_map={}
    )
    assert result is True


def test_is_available_no_entry_for_day():
    """Employee has availability set, but not for this day → unavailable."""
    availability_map = {EMPLOYEE_ID: {3: [(time(9, 0), time(17, 0))]}}  # only Wednesday
    result = ScheduleGenerator._is_available(
        EMPLOYEE_ID, 2, time(9, 0), time(17, 0), availability_map  # asking about Tuesday
    )
    assert result is False


def test_is_available_window_fully_covers_shift():
    availability_map = {EMPLOYEE_ID: {2: [(time(9, 0), time(17, 0))]}}
    result = ScheduleGenerator._is_available(
        EMPLOYEE_ID, 2, time(9, 0), time(17, 0), availability_map
    )
    assert result is True


def test_is_available_window_wider_than_shift():
    """Window wider than the shift still counts as covering it."""
    availability_map = {EMPLOYEE_ID: {2: [(time(8, 0), time(18, 0))]}}
    result = ScheduleGenerator._is_available(
        EMPLOYEE_ID, 2, time(9, 0), time(17, 0), availability_map
    )
    assert result is True


def test_is_available_window_starts_too_late():
    availability_map = {EMPLOYEE_ID: {2: [(time(10, 0), time(17, 0))]}}
    result = ScheduleGenerator._is_available(
        EMPLOYEE_ID, 2, time(9, 0), time(17, 0), availability_map
    )
    assert result is False


def test_is_available_window_ends_too_early():
    availability_map = {EMPLOYEE_ID: {2: [(time(9, 0), time(15, 0))]}}
    result = ScheduleGenerator._is_available(
        EMPLOYEE_ID, 2, time(9, 0), time(17, 0), availability_map
    )
    assert result is False


def test_is_available_multiple_windows_one_covers():
    """If any window fully covers the shift, the employee is available."""
    availability_map = {
        EMPLOYEE_ID: {
            2: [
                (time(9, 0), time(12, 0)),   # too short
                (time(9, 0), time(17, 0)),   # exact match
            ]
        }
    }
    result = ScheduleGenerator._is_available(
        EMPLOYEE_ID, 2, time(9, 0), time(17, 0), availability_map
    )
    assert result is True


def test_is_available_multiple_windows_none_covers():
    availability_map = {
        EMPLOYEE_ID: {
            2: [
                (time(9, 0), time(12, 0)),
                (time(14, 0), time(17, 0)),
            ]
        }
    }
    result = ScheduleGenerator._is_available(
        EMPLOYEE_ID, 2, time(9, 0), time(17, 0), availability_map
    )
    assert result is False


# === _load_availability ===

def test_load_availability_builds_map():
    rows = [
        {"employee_id": EMPLOYEE_ID, "day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00"},
        {"employee_id": EMPLOYEE_ID, "day_of_week": 3, "start_time": "11:00:00", "end_time": "20:00:00"},
        {"employee_id": EMPLOYEE_ID_2, "day_of_week": 2, "start_time": "09:00:00", "end_time": "13:00:00"},
    ]
    mock_sb = make_supabase_chain(return_data=rows)
    gen = ScheduleGenerator(mock_sb)

    result = gen._load_availability(RESTAURANT_ID)

    assert EMPLOYEE_ID in result
    assert EMPLOYEE_ID_2 in result
    assert 2 in result[EMPLOYEE_ID]
    assert 3 in result[EMPLOYEE_ID]
    assert result[EMPLOYEE_ID][2] == [(time(9, 0), time(17, 0))]
    assert result[EMPLOYEE_ID_2][2] == [(time(9, 0), time(13, 0))]


def test_load_availability_empty_returns_empty_map():
    mock_sb = make_supabase_chain(return_data=[])
    gen = ScheduleGenerator(mock_sb)
    result = gen._load_availability(RESTAURANT_ID)
    assert result == {}


def test_load_availability_multiple_windows_same_day():
    """Multiple availability windows for the same employee+day accumulate in a list."""
    rows = [
        {"employee_id": EMPLOYEE_ID, "day_of_week": 2, "start_time": "09:00:00", "end_time": "13:00:00"},
        {"employee_id": EMPLOYEE_ID, "day_of_week": 2, "start_time": "15:00:00", "end_time": "20:00:00"},
    ]
    mock_sb = make_supabase_chain(return_data=rows)
    gen = ScheduleGenerator(mock_sb)

    result = gen._load_availability(RESTAURANT_ID)
    assert len(result[EMPLOYEE_ID][2]) == 2


def test_load_availability_filters_by_restaurant():
    mock_sb = make_supabase_chain(return_data=[])
    gen = ScheduleGenerator(mock_sb)
    gen._load_availability(RESTAURANT_ID)
    mock_sb.eq.assert_any_call("restaurant_id", RESTAURANT_ID)


# === generate_schedule with availability ===

def test_generate_schedule_respects_availability(sample_schedule, sample_employee):
    """Employee marked unavailable on the shift day is excluded; shift goes unfilled."""
    # availability_map: employee is available Wednesday (3) but shift is Tuesday (2)
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee])
    gen._load_availability = MagicMock(
        return_value={EMPLOYEE_ID: {3: [(time(9, 0), time(17, 0))]}}
    )

    tuesday_template = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ]
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, tuesday_template)

    assert result["total_shifts"] == 0


def test_generate_schedule_available_employee_gets_shift(sample_schedule, sample_employee):
    """Employee available on the shift day is assigned normally."""
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee])
    gen._load_availability = MagicMock(
        return_value={EMPLOYEE_ID: {2: [(time(9, 0), time(17, 0))]}}
    )

    tuesday_template = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ]
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, tuesday_template)

    assert result["total_shifts"] == 1


def test_generate_schedule_no_availability_set_treats_as_available(sample_schedule, sample_employee):
    """Employee with no availability rows in the map is treated as available everywhere."""
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee])
    gen._load_availability = MagicMock(return_value={})  # empty map

    tuesday_template = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ]
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, tuesday_template)

    assert result["total_shifts"] == 1


def test_generate_schedule_availability_skips_one_assigns_other(
    sample_schedule, sample_employee, sample_employee_2
):
    """
    Two server employees. One available Tuesday, one not.
    The available one gets the Tuesday shift; the other is skipped.
    """
    server2 = {**sample_employee_2, "role": "Server"}
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee, server2])
    # EMPLOYEE_ID available Tue; EMPLOYEE_ID_2 only available Wed
    gen._load_availability = MagicMock(return_value={
        EMPLOYEE_ID:   {2: [(time(9, 0), time(17, 0))]},
        EMPLOYEE_ID_2: {3: [(time(9, 0), time(17, 0))]},
    })

    tuesday_template = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ]
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, tuesday_template)

    assert result["total_shifts"] == 1
    assigned_shift = mock_sb.insert.call_args[0][0][0]
    assert assigned_shift["employee_id"] == EMPLOYEE_ID


def test_generate_schedule_partial_window_not_available(sample_schedule, sample_employee):
    """Employee available 09:00–13:00 cannot cover a 09:00–17:00 shift."""
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee])
    gen._load_availability = MagicMock(
        return_value={EMPLOYEE_ID: {2: [(time(9, 0), time(13, 0))]}}
    )

    tuesday_template = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ]
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, tuesday_template)

    assert result["total_shifts"] == 0


# === generate_schedule: dedup, top-up, coverage-first ordering ===

def test_generate_schedule_duplicate_templates_dont_double_fill(
    sample_schedule, sample_employee, sample_employee_2
):
    """Two identical template entries for the same slot need 1 person, not 2."""
    duplicate_templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
    ]
    server2 = {**sample_employee_2, "role": "Server"}
    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [sample_employee, server2])
    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, duplicate_templates)

    assert result["total_shifts"] == 1


def test_generate_schedule_regenerate_tops_up_missing_only(
    sample_schedule, sample_employee, sample_employee_2
):
    """
    Regenerating a week that already has some shifts filled only creates the
    shifts still missing, not ones that already exist.
    """
    templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 3, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Cook", "count": 1},
    ]
    existing_server_shift = {
        "id": "existing-1",
        "employee_id": EMPLOYEE_ID,
        "shift_date": "2026-04-22",  # Tuesday — matches the Server template's slot
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "notes": "Server",
    }
    server = sample_employee  # role "Server"
    cook = {**sample_employee_2, "role": "Cook"}

    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[existing_server_shift]),  # _preload_existing_shifts
        MagicMock(data=[]),  # _load_availability
        MagicMock(data=[]),  # _load_time_off (overlap query)
        MagicMock(data=[]),  # bulk insert response
    ]

    gen = _make_generator(mock_sb, sample_schedule, [server, cook])
    gen.schedule_service.get_schedule_by_week.return_value = sample_schedule  # already exists

    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, templates)

    assert result["total_shifts"] == 1
    inserted = mock_sb.insert.call_args[0][0][0]
    assert inserted["notes"] == "Cook"


def test_generate_schedule_scarcity_ordering_maximizes_fill(
    sample_schedule, sample_employee, sample_employee_2
):
    """
    Employee A is capped at 8h; Employee B is uncapped. Two Server shifts:
    Tuesday 9-17 (8h, both eligible) and Wednesday 9-13 (4h, only A
    available). Naive input-order processing would greedily tie-break onto A
    for the easy Tuesday shift first, maxing out A's cap and leaving the
    Wednesday shift — which only A could cover — unfillable. Scarcity-first
    ordering processes the scarcer Wednesday shift first, reserving A for it
    and leaving the flexible B for Tuesday, filling both.
    """
    employee_a = {**sample_employee, "max_hours_per_week": 8.0}  # EMPLOYEE_ID
    employee_b = {**sample_employee_2, "role": "Server"}  # EMPLOYEE_ID_2, no cap

    templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "17:00:00", "role": "Server", "count": 1},
        {"day_of_week": 3, "start_time": "09:00:00", "end_time": "13:00:00", "role": "Server", "count": 1},
    ]

    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [employee_a, employee_b])
    gen._load_availability = MagicMock(return_value={
        EMPLOYEE_ID_2: {2: [(time(9, 0), time(17, 0))]},  # B only available Tuesday
    })

    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, templates)

    assert result["total_shifts"] == 2


def test_generate_schedule_rest_check_considers_all_prior_shifts(
    sample_schedule, sample_employee, sample_employee_2
):
    """
    Scarcity-first ordering can assign a chronologically-LATER shift before
    an EARLIER one for the same employee. Rest must be checked against every
    shift already assigned to that employee, not just the most-recently-
    assigned one — otherwise a well-separated earlier shift gets wrongly
    rejected because of a "gap" computed against a later shift the wrong way.

    Setup: Tuesday (scarcity 1, only B available) and Wednesday (scarcity 1,
    only A available) both get processed before Monday (scarcity 2, both
    "available" by role+availability, though B will be capped out by Tuesday
    by the time Monday is reached) — so Monday, the chronologically earliest
    shift, is the LAST one assigned. A must still be recognized as having
    ample rest for it.
    """
    employee_a = sample_employee  # EMPLOYEE_ID, no cap
    employee_b = {**sample_employee_2, "role": "Server", "max_hours_per_week": 2.0}  # tiny cap

    templates = [
        {"day_of_week": 2, "start_time": "09:00:00", "end_time": "11:00:00", "role": "Server", "count": 1},  # Tue 2h — only B
        {"day_of_week": 3, "start_time": "09:00:00", "end_time": "13:00:00", "role": "Server", "count": 1},  # Wed 4h — only A
        {"day_of_week": 1, "start_time": "09:00:00", "end_time": "13:00:00", "role": "Server", "count": 1},  # Mon 4h — both, but B capped out by then
    ]

    mock_sb = make_supabase_chain()
    mock_sb.execute.return_value = MagicMock(data=[])

    gen = _make_generator(mock_sb, sample_schedule, [employee_a, employee_b])
    gen._load_availability = MagicMock(return_value={
        EMPLOYEE_ID:   {1: [(time(9, 0), time(17, 0))], 3: [(time(9, 0), time(17, 0))]},  # A: Mon, Wed
        EMPLOYEE_ID_2: {1: [(time(9, 0), time(13, 0))], 2: [(time(9, 0), time(11, 0))]},  # B: Mon, Tue
    })

    result = gen.generate_schedule(UUID(RESTAURANT_ID), WEEK_START, templates)

    # All 3 should fill: Tue -> B, Wed -> A, Mon -> A (B is capped out by then;
    # a buggy "last shift only" rest check would wrongly reject A for Monday
    # since it was assigned after the chronologically-later Wednesday shift).
    assert result["total_shifts"] == 3
