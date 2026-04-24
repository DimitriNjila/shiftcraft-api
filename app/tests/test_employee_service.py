import pytest
from unittest.mock import MagicMock
from uuid import UUID

from app.services.employee_service import EmployeeService, EmployeeNotFoundError
from app.tests.conftest import make_supabase_chain, EMPLOYEE_ID, RESTAURANT_ID


# === get_employees ===

def test_get_employees_returns_list(sample_employee):
    mock_sb = make_supabase_chain([sample_employee, sample_employee])
    svc = EmployeeService(mock_sb)
    result = svc.get_employees()
    assert len(result) == 2
    assert result[0]["name"] == "Alice"


def test_get_employees_with_restaurant_filter(sample_employee):
    mock_sb = make_supabase_chain([sample_employee])
    svc = EmployeeService(mock_sb)
    result = svc.get_employees(restaurant_id=RESTAURANT_ID)
    assert len(result) == 1
    mock_sb.eq.assert_any_call("restaurant_id", RESTAURANT_ID)


def test_get_employees_with_active_filter(sample_employee):
    mock_sb = make_supabase_chain([sample_employee])
    svc = EmployeeService(mock_sb)
    result = svc.get_employees(is_active=True)
    assert len(result) == 1
    mock_sb.eq.assert_any_call("is_active", True)


# === get_employee_by_id ===

def test_get_employee_by_id_found(sample_employee):
    mock_sb = make_supabase_chain([sample_employee])
    svc = EmployeeService(mock_sb)
    result = svc.get_employee_by_id(UUID(EMPLOYEE_ID))
    assert result["id"] == EMPLOYEE_ID


def test_get_employee_by_id_not_found():
    mock_sb = make_supabase_chain([])
    svc = EmployeeService(mock_sb)
    result = svc.get_employee_by_id(UUID(EMPLOYEE_ID))
    assert result is None


# === create_employee ===

def test_create_employee_success(sample_employee):
    mock_sb = make_supabase_chain([sample_employee])
    svc = EmployeeService(mock_sb)
    result = svc.create_employee(
        name="Alice", role="Server", restaurant_id=RESTAURANT_ID
    )
    assert result["name"] == "Alice"
    mock_sb.insert.assert_called_once()


def test_create_employee_empty_name():
    svc = EmployeeService(make_supabase_chain())
    with pytest.raises(ValueError, match="name cannot be empty"):
        svc.create_employee(name="", role="Server", restaurant_id=RESTAURANT_ID)


def test_create_employee_whitespace_name():
    svc = EmployeeService(make_supabase_chain())
    with pytest.raises(ValueError, match="name cannot be empty"):
        svc.create_employee(name="   ", role="Server", restaurant_id=RESTAURANT_ID)


def test_create_employee_empty_role():
    svc = EmployeeService(make_supabase_chain())
    with pytest.raises(ValueError, match="role cannot be empty"):
        svc.create_employee(name="Alice", role="", restaurant_id=RESTAURANT_ID)


def test_create_employee_missing_restaurant():
    svc = EmployeeService(make_supabase_chain())
    with pytest.raises(ValueError, match="Restaurant ID is required"):
        svc.create_employee(name="Alice", role="Server", restaurant_id=None)


# === update_employee ===

def test_update_employee_success(sample_employee):
    updated = {**sample_employee, "name": "Alicia"}
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_employee]),  # get_employee_by_id
        MagicMock(data=[updated]),           # update
    ]
    svc = EmployeeService(mock_sb)
    result = svc.update_employee(UUID(EMPLOYEE_ID), name="Alicia")
    assert result["name"] == "Alicia"


def test_update_employee_not_found():
    mock_sb = make_supabase_chain([])
    svc = EmployeeService(mock_sb)
    with pytest.raises(EmployeeNotFoundError):
        svc.update_employee(UUID(EMPLOYEE_ID), name="Alicia")


def test_update_employee_no_changes(sample_employee):
    # No fields provided — still calls DB with empty dict, returns existing when no data
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_employee]),  # get_employee_by_id
        MagicMock(data=[]),                  # update({}) → empty response
    ]
    svc = EmployeeService(mock_sb)
    result = svc.update_employee(UUID(EMPLOYEE_ID))
    assert result["id"] == EMPLOYEE_ID


# === delete_employee ===

def test_delete_employee_success(sample_employee):
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_employee]),  # get_employee_by_id
        MagicMock(data=[sample_employee]),  # delete
    ]
    svc = EmployeeService(mock_sb)
    result = svc.delete_employee(UUID(EMPLOYEE_ID))
    assert result["id"] == EMPLOYEE_ID
    mock_sb.delete.assert_called_once()


def test_delete_employee_not_found():
    mock_sb = make_supabase_chain([])
    svc = EmployeeService(mock_sb)
    with pytest.raises(EmployeeNotFoundError):
        svc.delete_employee(UUID(EMPLOYEE_ID))


# === deactivate_employee ===

def test_deactivate_employee_success(sample_employee):
    deactivated = {**sample_employee, "is_active": False}
    mock_sb = make_supabase_chain()
    mock_sb.execute.side_effect = [
        MagicMock(data=[sample_employee]),   # get_employee_by_id (deactivate check)
        MagicMock(data=[sample_employee]),   # get_employee_by_id (inside update_employee)
        MagicMock(data=[deactivated]),        # update
    ]
    svc = EmployeeService(mock_sb)
    result = svc.deactivate_employee(UUID(EMPLOYEE_ID))
    assert result["is_active"] is False


def test_deactivate_employee_already_inactive(sample_employee):
    inactive = {**sample_employee, "is_active": False}
    mock_sb = make_supabase_chain([inactive])
    svc = EmployeeService(mock_sb)
    result = svc.deactivate_employee(UUID(EMPLOYEE_ID))
    assert result["is_active"] is False
    # update should NOT be called (early return when already inactive)
    mock_sb.update.assert_not_called()


def test_deactivate_employee_not_found():
    mock_sb = make_supabase_chain([])
    svc = EmployeeService(mock_sb)
    with pytest.raises(EmployeeNotFoundError):
        svc.deactivate_employee(UUID(EMPLOYEE_ID))
