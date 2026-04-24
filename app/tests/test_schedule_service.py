import pytest
from unittest.mock import MagicMock
from datetime import date
from uuid import UUID

from app.services.schedule_service import (
    ScheduleService,
    ScheduleAlreadyExistsError,
    ScheduleNotFoundError,
)
from app.tests.conftest import make_supabase_chain, SCHEDULE_ID, RESTAURANT_ID


# === get_week_start ===

def test_get_week_start_on_monday():
    monday = date(2026, 4, 20)  # Known Monday
    assert ScheduleService.get_week_start(monday) == monday


def test_get_week_start_on_wednesday():
    wednesday = date(2026, 4, 22)
    expected_monday = date(2026, 4, 20)
    assert ScheduleService.get_week_start(wednesday) == expected_monday


def test_get_week_start_on_sunday():
    sunday = date(2026, 4, 26)
    expected_monday = date(2026, 4, 20)
    assert ScheduleService.get_week_start(sunday) == expected_monday


# === get_schedules ===

def test_get_schedules_no_filters(sample_schedule):
    mock_sb = make_supabase_chain([sample_schedule])
    svc = ScheduleService(mock_sb)
    result = svc.get_schedules()
    assert len(result) == 1
    assert result[0]["id"] == SCHEDULE_ID


def test_get_schedules_with_restaurant_filter(sample_schedule):
    mock_sb = make_supabase_chain([sample_schedule])
    svc = ScheduleService(mock_sb)
    result = svc.get_schedules(restaurant_id=RESTAURANT_ID)
    assert len(result) == 1
    mock_sb.eq.assert_any_call("restaurant_id", RESTAURANT_ID)


def test_get_schedules_with_date_range(sample_schedule):
    mock_sb = make_supabase_chain([sample_schedule])
    svc = ScheduleService(mock_sb)
    result = svc.get_schedules(
        start_date=date(2026, 4, 20), end_date=date(2026, 4, 27)
    )
    assert len(result) == 1
    mock_sb.gte.assert_called_once_with("week_start", "2026-04-20")
    mock_sb.lte.assert_called_once_with("week_start", "2026-04-27")


# === get_schedule_by_id ===

def test_get_schedule_by_id_found(sample_schedule):
    mock_sb = make_supabase_chain([sample_schedule])
    svc = ScheduleService(mock_sb)
    result = svc.get_schedule_by_id(UUID(SCHEDULE_ID))
    assert result["id"] == SCHEDULE_ID


def test_get_schedule_by_id_not_found():
    mock_sb = make_supabase_chain([])
    svc = ScheduleService(mock_sb)
    result = svc.get_schedule_by_id(UUID(SCHEDULE_ID))
    assert result is None


# === get_schedule_with_shifts ===

def test_get_schedule_with_shifts_success(sample_schedule):
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
        MagicMock(data=[shift]),             # shifts query
    ]
    svc = ScheduleService(mock_sb)
    result = svc.get_schedule_with_shifts(UUID(SCHEDULE_ID))
    assert result["total_shifts"] == 1
    assert result["total_hours"] == 8.0
    assert len(result["shifts"]) == 1
    assert result["shifts"][0]["duration_hours"] == 8.0


def test_get_schedule_with_shifts_not_found():
    mock_sb = make_supabase_chain([])
    svc = ScheduleService(mock_sb)
    with pytest.raises(ScheduleNotFoundError):
        svc.get_schedule_with_shifts(UUID(SCHEDULE_ID))


def test_get_schedule_with_shifts_empty(sample_schedule):
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_schedule]),  # get_schedule_by_id
        MagicMock(data=[]),                  # no shifts
    ]
    svc = ScheduleService(mock_sb)
    result = svc.get_schedule_with_shifts(UUID(SCHEDULE_ID))
    assert result["total_shifts"] == 0
    assert result["total_hours"] == 0.0
    assert result["shifts"] == []


# === calculate_duration ===

def test_calculate_duration():
    hours = ScheduleService.calculate_duration("09:00:00", "17:00:00")
    assert hours == 8.0


def test_calculate_duration_fractional():
    hours = ScheduleService.calculate_duration("09:00:00", "13:30:00")
    assert hours == 4.5


# === create_schedule ===

def test_create_schedule_success(sample_schedule):
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[]),              # get_schedule_by_week → not found
        MagicMock(data=[sample_schedule]),  # insert
    ]
    svc = ScheduleService(mock_sb)
    result = svc.create_schedule(
        restaurant_id=UUID(RESTAURANT_ID), week_start=date(2026, 4, 21)
    )
    assert result["id"] == SCHEDULE_ID


def test_create_schedule_already_exists(sample_schedule):
    mock_sb = make_supabase_chain([sample_schedule])  # get_schedule_by_week → found
    svc = ScheduleService(mock_sb)
    with pytest.raises(ScheduleAlreadyExistsError):
        svc.create_schedule(
            restaurant_id=UUID(RESTAURANT_ID), week_start=date(2026, 4, 21)
        )


# === create_schedules_for_range ===

def test_create_schedules_for_range_success(sample_schedule):
    # 3 weeks, none exist yet
    s1 = {**sample_schedule, "id": "aaa", "week_start": "2026-04-21"}
    s2 = {**sample_schedule, "id": "bbb", "week_start": "2026-04-28"}
    s3 = {**sample_schedule, "id": "ccc", "week_start": "2026-05-05"}
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[]),   # week 1 check
        MagicMock(data=[s1]), # week 1 insert
        MagicMock(data=[]),   # week 2 check
        MagicMock(data=[s2]), # week 2 insert
        MagicMock(data=[]),   # week 3 check
        MagicMock(data=[s3]), # week 3 insert
    ]
    svc = ScheduleService(mock_sb)
    result = svc.create_schedules_for_range(
        start_date=date(2026, 4, 21),
        end_date=date(2026, 5, 5),
        restaurant_id=UUID(RESTAURANT_ID),
    )
    assert len(result) == 3


def test_create_schedules_for_range_skips_existing(sample_schedule):
    # 2 weeks: first already exists, second is new
    s2 = {**sample_schedule, "id": "bbb", "week_start": "2026-04-28"}
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_schedule]),  # week 1 check → already exists
        MagicMock(data=[]),                  # week 2 check → not found
        MagicMock(data=[s2]),                # week 2 insert
    ]
    svc = ScheduleService(mock_sb)
    result = svc.create_schedules_for_range(
        start_date=date(2026, 4, 21),
        end_date=date(2026, 4, 28),
        restaurant_id=UUID(RESTAURANT_ID),
    )
    assert len(result) == 1
    assert result[0]["id"] == "bbb"


# === delete_schedule ===

def test_delete_schedule_success(sample_schedule):
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_schedule]),  # get_schedule_by_id
        MagicMock(data=[sample_schedule]),  # delete
    ]
    svc = ScheduleService(mock_sb)
    result = svc.delete_schedule(UUID(SCHEDULE_ID))
    assert result["id"] == SCHEDULE_ID
    mock_sb.delete.assert_called_once()


def test_delete_schedule_not_found():
    mock_sb = make_supabase_chain([])
    svc = ScheduleService(mock_sb)
    with pytest.raises(ScheduleNotFoundError):
        svc.delete_schedule(UUID(SCHEDULE_ID))
