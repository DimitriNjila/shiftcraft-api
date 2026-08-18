import logging
from typing import List, Optional

from supabase import Client

from ..core.db import get_supabase

logger = logging.getLogger(__name__)

DEFAULT_ROLES = ["Server", "Cook", "Manager"]


class RestaurantNotFoundError(Exception):
    """Raised when a restaurant lookup returns no row."""

    def __init__(self, restaurant_id: str):
        self.restaurant_id = restaurant_id
        super().__init__(f"Restaurant {restaurant_id} not found")


class RestaurantService:
    """Owns restaurant-level configuration (roles today, more later)."""

    def __init__(self, supabase_client: Optional[Client] = None):
        self._supabase = supabase_client
        self.table_name = "restaurants"

    @property
    def supabase(self) -> Client:
        if self._supabase is None:
            self._supabase = get_supabase()
        return self._supabase

    def get_roles(self, restaurant_id: str) -> List[str]:
        """
        Return the list of valid employee roles for a restaurant.

        Falls back to DEFAULT_ROLES only when the row exists but roles is
        NULL (which shouldn't happen post-migration, since the column has a
        NOT NULL DEFAULT — but guard anyway so a manually-inserted row
        doesn't crash the create-employee path). A missing restaurant row is
        a real error and raises.
        """
        response = (
            self.supabase.table(self.table_name)
            .select("id, roles")
            .eq("id", restaurant_id)
            .execute()
        )
        if not response.data:
            raise RestaurantNotFoundError(restaurant_id)
        roles = response.data[0].get("roles")
        return list(roles) if roles else list(DEFAULT_ROLES)

    def update_roles(self, restaurant_id: str, roles: List[str]) -> List[str]:
        """
        Replace a restaurant's roles list. Callers are expected to have
        already validated and deduped `roles` (see
        RestaurantRolesUpdate.clean_and_dedupe).

        Employees whose current role is no longer in the new list are NOT
        auto-cleaned — they'd fail future role-validated updates but keep
        working today. That's deliberate: silently reassigning them to some
        other role would be worse than a visible mismatch the owner can
        resolve. Add UI to flag them if needed.
        """
        logger.info(
            "Updating roles for restaurant_id=%s: %s", restaurant_id, roles
        )
        response = (
            self.supabase.table(self.table_name)
            .update({"roles": roles})
            .eq("id", restaurant_id)
            .execute()
        )
        if not response.data:
            raise RestaurantNotFoundError(restaurant_id)
        updated = response.data[0].get("roles") or []
        return list(updated)

    def validate_role(self, restaurant_id: str, role: str) -> None:
        """
        Raise ValueError if `role` isn't in the restaurant's roles list.
        Case-insensitive comparison — "server" and "Server" are the same
        role, matching how RestaurantRolesUpdate dedupes on save.
        """
        roles = self.get_roles(restaurant_id)
        if role.strip().lower() not in {r.lower() for r in roles}:
            raise ValueError(
                f"Role {role!r} is not defined for this restaurant. "
                f"Valid roles: {', '.join(roles)}"
            )


restaurant_service = RestaurantService()
