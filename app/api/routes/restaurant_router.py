import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ...core.auth import get_current_user
from ...models.restaurant_model import (
    RestaurantRolesResponse,
    RestaurantRolesUpdate,
)
from ...services.restaurant_service import (
    RestaurantNotFoundError,
    restaurant_service,
)

logger = logging.getLogger(__name__)

restaurant_router = APIRouter(
    prefix="/api/v1/restaurants",
    tags=["restaurants"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
)


@restaurant_router.get(
    "/{restaurant_id}/roles", response_model=RestaurantRolesResponse
)
def get_restaurant_roles(restaurant_id: str):
    """Return the list of valid employee roles for this restaurant."""
    try:
        roles = restaurant_service.get_roles(restaurant_id)
    except RestaurantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"restaurant_id": restaurant_id, "roles": roles}


@restaurant_router.put(
    "/{restaurant_id}/roles", response_model=RestaurantRolesResponse
)
def update_restaurant_roles(restaurant_id: str, body: RestaurantRolesUpdate):
    """
    Replace the restaurant's roles list.

    Employees whose current role is dropped from the list keep working, but
    future updates to those employees will fail role validation until their
    role is reassigned — see RestaurantService.update_roles for why we don't
    auto-clean.
    """
    try:
        roles = restaurant_service.update_roles(restaurant_id, body.roles)
    except RestaurantNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return {"restaurant_id": restaurant_id, "roles": roles}
