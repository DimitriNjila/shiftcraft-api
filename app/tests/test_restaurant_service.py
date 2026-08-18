import pytest
from unittest.mock import MagicMock

from app.services.restaurant_service import (
    DEFAULT_ROLES,
    RestaurantNotFoundError,
    RestaurantService,
)

from .conftest import RESTAURANT_ID, make_supabase_chain


def test_get_roles_returns_configured_list():
    mock_sb = make_supabase_chain([{"id": RESTAURANT_ID, "roles": ["Barista", "Baker"]}])
    svc = RestaurantService(mock_sb)
    assert svc.get_roles(RESTAURANT_ID) == ["Barista", "Baker"]


def test_get_roles_falls_back_to_defaults_when_null():
    mock_sb = make_supabase_chain([{"id": RESTAURANT_ID, "roles": None}])
    svc = RestaurantService(mock_sb)
    assert svc.get_roles(RESTAURANT_ID) == DEFAULT_ROLES


def test_get_roles_raises_when_restaurant_missing():
    mock_sb = make_supabase_chain([])
    svc = RestaurantService(mock_sb)
    with pytest.raises(RestaurantNotFoundError):
        svc.get_roles(RESTAURANT_ID)


def test_update_roles_returns_stored_list():
    mock_sb = make_supabase_chain(
        [{"id": RESTAURANT_ID, "roles": ["Server", "Host", "Cook"]}]
    )
    svc = RestaurantService(mock_sb)
    result = svc.update_roles(RESTAURANT_ID, ["Server", "Host", "Cook"])
    assert result == ["Server", "Host", "Cook"]
    mock_sb.update.assert_called_once_with({"roles": ["Server", "Host", "Cook"]})


def test_update_roles_raises_when_restaurant_missing():
    mock_sb = make_supabase_chain([])
    svc = RestaurantService(mock_sb)
    with pytest.raises(RestaurantNotFoundError):
        svc.update_roles(RESTAURANT_ID, ["Server"])


def test_validate_role_accepts_configured_role_case_insensitive():
    mock_sb = make_supabase_chain([{"id": RESTAURANT_ID, "roles": ["Server", "Cook"]}])
    svc = RestaurantService(mock_sb)
    svc.validate_role(RESTAURANT_ID, "server")  # should not raise


def test_validate_role_rejects_unknown_role():
    mock_sb = make_supabase_chain([{"id": RESTAURANT_ID, "roles": ["Server", "Cook"]}])
    svc = RestaurantService(mock_sb)
    with pytest.raises(ValueError, match="not defined for this restaurant"):
        svc.validate_role(RESTAURANT_ID, "Barista")


def test_create_employee_rejects_unknown_role():
    from app.services.employee_service import EmployeeService

    mock_sb = make_supabase_chain([{"id": RESTAURANT_ID, "roles": ["Server", "Cook"]}])
    svc = EmployeeService(mock_sb)
    with pytest.raises(ValueError, match="not defined for this restaurant"):
        svc.create_employee(name="Alice", role="Barista", restaurant_id=RESTAURANT_ID)


def test_roles_update_payload_dedupes_and_strips():
    from app.models.restaurant_model import RestaurantRolesUpdate

    payload = RestaurantRolesUpdate(roles=["  Server ", "server", "", "Cook", "COOK"])
    assert payload.roles == ["Server", "Cook"]


def test_roles_update_payload_rejects_empty_after_cleaning():
    from app.models.restaurant_model import RestaurantRolesUpdate

    with pytest.raises(ValueError):
        RestaurantRolesUpdate(roles=["", "   "])
