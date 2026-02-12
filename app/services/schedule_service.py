from datetime import date, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID
from supabase import Client
from ..core.db import supabase
from ..core.config import settings


class ScheduleAlreadyExistsError(Exception):
    """
    Raised when a schedule already exists for the given week
    """

    def __init__(self, week_start: date):
        self.week_start = week_start
        super().__init__(f"Schedule already exists for week starting {week_start}")


class ScheduleNotFoundError(Exception):
    """
    Raised when a schedule is not found
    """

    def __init__(self, week_start: date):
        self.week_start = week_start
        super().__init__(f"Schedule not found for week starting {week_start}")


class ScheduleService:
    """Service for managing weekly bellagios Schedules"""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.table_name = "schedules"

    @staticmethod
    def get_week_start(input_date: date) -> date:
        """Get the monday for the week containing any given date.
        Args:
            input_date: Any date
        Returns:
            The Monday of that week (ISO 8601: Monday = week start)
        """
        days_since_monday = input_date.weekday()
        return input_date - timedelta(days=days_since_monday)

    def get_schedules(
        self,
        restaurant_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get schedules with optional filtering

        Args:
            restaurant_id: Filter by restaurant
            start_date: Get schedules starting on or after this date

        Returns:
            List of schedule dictionaries

        """

        query = self.supabase.table(self.table_name).select("*")

        if restaurant_id is not None:
            query = query.eq("restaurant_id", restaurant_id)

        if start_date is not None:
            query = query.gte("week_start", start_date.isoformat())

        if end_date is not None:
            query = query.lte("week_start", end_date.isoformat())

        query = query.order("week_start", desc=True)

        response = query.execute()
        return response.data

    def get_schedule_by_week(
        self, week_start: date, restaurant_id: UUID
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific schedule based on ID.

        Args:
            week_start: Monday of desired week
            restaurant_id: Optional for filtering
        """
        normalized_week_start = self.get_week_start(week_start)

        query = (
            self.supabase.table(self.table_name)
            .select("*")
            .eq("week_start", normalized_week_start.isoformat())
        )

        if restaurant_id is not None:
            query = query.eq("restaurant_id", restaurant_id)

        response = query.execute()

        return response.data[0] if response.data else None

    def create_schedule(self, restaurant_id: UUID, week_start: date) -> Dict[str, Any]:
        """
        Creates schedule for given week

        Args:
            restaurant_id: Restaurant ID
            week_start: Start date for schedule (normalized to monday of that week)

        Returns:
            Created schedule dictionary

        Raises:
            ScheduleAlreadyExistsError: if schedule already exists for week
        """
        normalized_week_start = self.get_week_start(week_start)

        if self.get_schedule_by_week(normalized_week_start, restaurant_id):
            raise ScheduleAlreadyExistsError(normalized_week_start)

        schedule_data = {
            "week_start": normalized_week_start.isoformat(),
            "restaurant_id": restaurant_id,
        }
        response = self.supabase.table(self.table_name).insert(schedule_data).execute()

        return response.data[0]

    def create_schedules_for_range(
        self, start_date: date, end_date: date, restaurant_id: UUID
    ) -> List[Dict[str, Any]]:
        """
        Create schedules for all weeks in a date range.

        Useful for bulk-creating schedules (e.g., "create next 4 weeks").

        Args:
            start_date: Range start
            end_date: Range end
            restaurant_id: Restaurant ID

        Returns:
            List of created schedules
        """
        created_schedules = []

        current_week_start = self.get_week_start(start_date)
        end_week_start = self.get_week_start(end_date)

        while current_week_start <= end_week_start:
            try:
                schedule = self.create_schedule(current_week_start, restaurant_id)
                created_schedules.append(schedule)
            except ScheduleAlreadyExistsError:
                # Skip weeks that already have schedules
                pass

            current_week_start += timedelta(weeks=1)

        return created_schedules

    def delete_schedule(self, schedule_id: UUID) -> Dict[str, Any]:
        """
        Delete a schedule.


        Args:
            schedule_id: Schedule to delete

        Returns:
            Deleted schedule dictionary

        Raises:
            ScheduleNotFoundError: If schedule doesn't exist
        """
        existing = self.get_schedule_by_id(schedule_id)
        if not existing:
            raise ScheduleNotFoundError(schedule_id)

        response = (
            self.supabase.table(self.table_name)
            .delete()
            .eq("id", str(schedule_id))
            .execute()
        )

        return response.data[0] if response.data else existing


schedule_service = ScheduleService(supabase)
