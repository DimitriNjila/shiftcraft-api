import os

# Set dummy env vars before any service imports so db.py can initialize without real credentials
os.environ.setdefault("SUPABASE_URL", "https://mock.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "mock-anon-key-for-testing")

import pytest
from unittest.mock import MagicMock
from uuid import UUID

EMPLOYEE_ID = "11111111-1111-1111-1111-111111111111"
EMPLOYEE_ID_2 = "11111111-1111-1111-1111-222222222222"
SCHEDULE_ID = "22222222-2222-2222-2222-222222222222"
SHIFT_ID = "33333333-3333-3333-3333-333333333333"
RESTAURANT_ID = "44444444-4444-4444-4444-444444444444"


def make_supabase_chain(return_data=None):
    """Build a chainable Supabase mock where every method returns itself and
    .execute() returns a MagicMock with the given data list."""
    chain = MagicMock()
    for method in ("table", "select", "insert", "update", "delete", "eq", "neq", "gte", "lte", "order"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = MagicMock(data=return_data if return_data is not None else [])
    return chain


@pytest.fixture
def sample_employee():
    return {
        "id": EMPLOYEE_ID,
        "name": "Alice",
        "role": "Server",
        "is_active": True,
        "restaurant_id": RESTAURANT_ID,
        "created_at": "2026-01-01T00:00:00",
        "email": None,
        "deleted_at": None,
    }


@pytest.fixture
def sample_employee_2():
    return {
        "id": EMPLOYEE_ID_2,
        "name": "Bob",
        "role": "Cook",
        "is_active": True,
        "restaurant_id": RESTAURANT_ID,
        "created_at": "2026-01-01T00:00:00",
        "email": None,
        "deleted_at": None,
    }


@pytest.fixture
def sample_schedule():
    return {
        "id": SCHEDULE_ID,
        "restaurant_id": RESTAURANT_ID,
        "week_start": "2026-04-21",  # A Monday
        "created_at": "2026-01-01T00:00:00",
    }


@pytest.fixture
def sample_shift():
    return {
        "id": SHIFT_ID,
        "schedule_id": SCHEDULE_ID,
        "employee_id": EMPLOYEE_ID,
        "shift_date": "2026-04-22",  # Tuesday in the week
        "start_time": "09:00:00",
        "end_time": "17:00:00",
        "notes": None,
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }


@pytest.fixture
def mock_supabase():
    return make_supabase_chain()


@pytest.fixture
def employee_service(mock_supabase):
    from app.services.employee_service import EmployeeService
    return EmployeeService(mock_supabase)


@pytest.fixture
def schedule_service(mock_supabase):
    from app.services.schedule_service import ScheduleService
    return ScheduleService(mock_supabase)


@pytest.fixture
def shifts_service(mock_supabase):
    from app.services.shifts_service import ShiftsService
    return ShiftsService(mock_supabase)


@pytest.fixture
def generator_service(mock_supabase):
    from app.services.schedule_generator_service import ScheduleGenerator
    return ScheduleGenerator(mock_supabase)
