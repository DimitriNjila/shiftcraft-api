import logging

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from supabase import Client

from ..core.db import get_supabase
from .employee_service import EmployeeService, EmployeeNotFoundError

logger = logging.getLogger(__name__)

TABLE = "employee_availability"


class AvailabilityConflictError(Exception):
    """Raised when an identical availability window already exists."""

    def __init__(self):
        super().__init__("An identical availability window already exists for this employee")


class AvailabilityNotFoundError(Exception):
    """Raised when an availability window is not found."""

    def __init__(self, availability_id: UUID):
        self.availability_id = availability_id
        super().__init__(f"Availability window {availability_id} not found")


class AvailabilityService:
    """CRUD for employee availability windows."""

    def __init__(self, supabase_client: Optional[Client] = None):
        self._supabase = supabase_client
        self._employee_service: Optional[EmployeeService] = None

    @property
    def supabase(self) -> Client:
        if self._supabase is None:
            self._supabase = get_supabase()
        return self._supabase

    @property
    def employee_service(self) -> EmployeeService:
        if self._employee_service is None:
            self._employee_service = EmployeeService(self.supabase)
        return self._employee_service

    def get_availability(self, employee_id: UUID) -> List[Dict[str, Any]]:
        """
        Return all availability windows for an employee, ordered by day then start time.

        Args:
            employee_id: UUID of the employee

        Returns:
            List of availability window dicts
        """
        logger.debug("get_availability employee_id=%s", employee_id)
        response = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("employee_id", str(employee_id))
            .order("day_of_week")
            .order("start_time")
            .execute()
        )
        return response.data

    def add_availability(
        self,
        employee_id: UUID,
        day_of_week: int,
        start_time: str,
        end_time: str,
    ) -> Dict[str, Any]:
        """
        Add an availability window for an employee.

        Validates that the employee exists and that end_time > start_time.
        The DB unique constraint on (employee_id, day_of_week, start_time, end_time)
        prevents exact duplicates.

        Args:
            employee_id: UUID of the employee
            day_of_week: ISO 8601 weekday (1=Monday, 7=Sunday)
            start_time: Window start in HH:MM:SS
            end_time: Window end in HH:MM:SS

        Returns:
            Created availability window dict

        Raises:
            EmployeeNotFoundError: If employee does not exist
            ValueError: If end_time <= start_time
            AvailabilityConflictError: If identical window already exists
        """
        employee = self.employee_service.get_employee_by_id(employee_id)
        if not employee:
            raise EmployeeNotFoundError(employee_id)

        start = datetime.strptime(start_time, "%H:%M:%S").time()
        end = datetime.strptime(end_time, "%H:%M:%S").time()
        if end <= start:
            raise ValueError("end_time must be after start_time")

        now = datetime.utcnow().isoformat()
        data = {
            "employee_id": str(employee_id),
            "restaurant_id": str(employee["restaurant_id"]),
            "day_of_week": day_of_week,
            "start_time": start_time,
            "end_time": end_time,
            "created_at": now,
            "updated_at": now,
        }

        logger.info(
            "Adding availability: employee_id=%s day=%d %s–%s",
            employee_id,
            day_of_week,
            start_time,
            end_time,
        )

        try:
            response = self.supabase.table(TABLE).insert(data).execute()
        except Exception as e:
            # Supabase raises on unique constraint violation
            if "unique" in str(e).lower() or "duplicate" in str(e).lower():
                raise AvailabilityConflictError()
            raise

        created = response.data[0]
        logger.info("Availability created id=%s", created.get("id"))
        return created

    def delete_availability(
        self, employee_id: UUID, availability_id: UUID
    ) -> Dict[str, Any]:
        """
        Delete a specific availability window.

        Scopes the delete to employee_id so a manager cannot delete another
        employee's availability by guessing a UUID.

        Args:
            employee_id: UUID of the employee (ownership check)
            availability_id: UUID of the availability window to delete

        Returns:
            Deleted availability window dict

        Raises:
            AvailabilityNotFoundError: If the window does not exist for this employee
        """
        response = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("id", str(availability_id))
            .eq("employee_id", str(employee_id))
            .execute()
        )

        if not response.data:
            raise AvailabilityNotFoundError(availability_id)

        existing = response.data[0]

        self.supabase.table(TABLE).delete().eq("id", str(availability_id)).execute()

        logger.info("Availability deleted id=%s", availability_id)
        return existing


availability_service = AvailabilityService()
