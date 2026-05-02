import logging

from typing import Optional, List, Dict, Any
from supabase import Client
from ..core.db import supabase

logger = logging.getLogger(__name__)


class ShiftTemplateNotFoundError(Exception):
    """Raised when no shift templates exist for a restaurant."""

    def __init__(self, restaurant_id: str):
        self.restaurant_id = restaurant_id
        super().__init__(f"No shift templates found for restaurant {restaurant_id}")


class ShiftTemplateService:
    """Service for managing per-restaurant shift templates."""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.table_name = "shift_templates"

    def get_templates(self, restaurant_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the saved shift template record for a restaurant.

        Returns:
            Template record dict (with 'templates' key containing the list),
            or None if no templates have been saved yet.
        """
        logger.debug("Fetching shift templates for restaurant_id=%s", restaurant_id)

        response = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("restaurant_id", restaurant_id)
            .execute()
        )

        if response.data:
            record = response.data[0]
            logger.info(
                "Found %d shift templates for restaurant_id=%s",
                len(record.get("templates", [])),
                restaurant_id,
            )
            return record

        logger.info("No shift templates saved for restaurant_id=%s", restaurant_id)
        return None

    def upsert_templates(
        self, restaurant_id: str, templates: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Save or overwrite the shift templates for a restaurant.

        One record per restaurant — subsequent calls overwrite the previous set.

        Args:
            restaurant_id: Restaurant to save templates for
            templates: List of shift template dicts

        Returns:
            Saved template record
        """
        logger.info(
            "Upserting %d shift templates for restaurant_id=%s",
            len(templates),
            restaurant_id,
        )

        data = {
            "restaurant_id": restaurant_id,
            "templates": templates,
        }

        response = (
            self.supabase.table(self.table_name)
            .upsert(data, on_conflict="restaurant_id")
            .execute()
        )

        result = response.data[0]
        logger.info(
            "Shift templates saved id=%s restaurant_id=%s",
            result.get("id"),
            restaurant_id,
        )
        return result


shift_template_service = ShiftTemplateService(supabase)
