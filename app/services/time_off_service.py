import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from supabase import Client

from ..core.db import get_supabase
from .employee_service import EmployeeNotFoundError, EmployeeService

logger = logging.getLogger(__name__)

TABLE = "time_off"


class TimeOffNotFoundError(Exception):
    """Raised when a time-off row is not found for the given employee."""

    def __init__(self, time_off_id: UUID):
        self.time_off_id = time_off_id
        super().__init__(f"Time-off entry {time_off_id} not found")


class TimeOffService:
    """CRUD for employee time-off requests."""

    def __init__(
        self,
        supabase_client: Optional[Client] = None,
        employee_service: Optional[EmployeeService] = None,
    ):
        self._supabase = supabase_client
        self._employee_service = employee_service

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

    def list_for_employee(self, employee_id: UUID) -> List[Dict[str, Any]]:
        """Return all time-off rows for an employee, most recent first."""
        response = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("employee_id", str(employee_id))
            .order("start_date", desc=True)
            .execute()
        )
        return response.data

    def list_overlapping(
        self, restaurant_id: str, week_start: date, week_end: date
    ) -> List[Dict[str, Any]]:
        """
        Return every time-off row for the restaurant that overlaps the given
        window. Overlap = row.start_date <= week_end AND row.end_date >=
        week_start; expressed as two range filters in Supabase.

        Used by the schedule generator to build per-employee unavailable-date
        sets in a single query per week (not per employee).
        """
        response = (
            self.supabase.table(TABLE)
            .select("employee_id, start_date, end_date")
            .eq("restaurant_id", restaurant_id)
            .lte("start_date", week_end.isoformat())
            .gte("end_date", week_start.isoformat())
            .execute()
        )
        return response.data

    def add(
        self,
        employee_id: UUID,
        start_date: date,
        end_date: date,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a time-off entry for an employee.

        Overlap with existing rows is allowed — an owner might extend an
        interview absence with a second entry for a follow-up, or split a
        vacation across two reasons. The generator only cares whether ANY
        row covers a shift date, so duplicates are cheap.

        Raises:
            EmployeeNotFoundError: If employee does not exist
            ValueError: If end_date < start_date (also enforced by the model,
                        but re-checked here so direct service callers get the
                        same guarantee).
        """
        employee = self.employee_service.get_employee_by_id(employee_id)
        if not employee:
            raise EmployeeNotFoundError(employee_id)

        if end_date < start_date:
            raise ValueError("end_date must be on or after start_date")

        now = datetime.utcnow().isoformat()
        row = {
            "employee_id": str(employee_id),
            "restaurant_id": str(employee["restaurant_id"]),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "reason": reason,
            "created_at": now,
            "updated_at": now,
        }

        logger.info(
            "Adding time-off: employee_id=%s %s..%s reason=%r",
            employee_id,
            start_date,
            end_date,
            reason,
        )
        response = self.supabase.table(TABLE).insert(row).execute()
        return response.data[0]

    def delete(self, employee_id: UUID, time_off_id: UUID) -> Dict[str, Any]:
        """
        Delete a time-off entry, scoped to employee_id so one employee's
        ID can't be used to delete another's entry.
        """
        response = (
            self.supabase.table(TABLE)
            .select("*")
            .eq("id", str(time_off_id))
            .eq("employee_id", str(employee_id))
            .execute()
        )
        if not response.data:
            raise TimeOffNotFoundError(time_off_id)
        existing = response.data[0]

        self.supabase.table(TABLE).delete().eq("id", str(time_off_id)).execute()
        logger.info("Time-off deleted id=%s", time_off_id)
        return existing


time_off_service = TimeOffService()
