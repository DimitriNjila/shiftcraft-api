from ..core.db import supabase
from supabase import Client
from typing import List, Optional, Dict, Any
from schedule_service import schedule_service, ScheduleNotFoundError
from employee_service import employee_service, EmployeeNotFoundError
from uuid import UUID
from datetime import datetime, date, time, timedelta


class ShiftValidationError(Exception):
    """Raised when shift validation fails."""

    pass


class ShiftNotFoundError(Exception):
    """Raised when shift doesn't exist."""

    def __init__(self, shift_id: UUID):
        self.shift_id = shift_id
        super().__init__(f"Shift with ID {shift_id} not found")


class OverlappingShiftError(ShiftValidationError):
    """Raised when shift overlaps with existing shift."""

    def __init__(self, overlapping_shifts: List[Dict]):
        self.overlapping_shifts = overlapping_shifts
        shift_times = [
            f"{s['start_time']} - {s['end_time']}" for s in overlapping_shifts
        ]
        super().__init__(
            f"Shift overlaps with existing shift(s): {', '.join(shift_times)}"
        )


class ShiftsService:
    """Service to manage the employee shifts"""

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.table_name = "shifts"

    def validate_schedule_exists(schedule_id: UUID):
        """Ensure schedule exists before adding shifts to it."""
        schedule = schedule_service.get_schedule_by_id(schedule_id)
        if not schedule:
            raise ScheduleNotFoundError(schedule_id)
        return schedule

    def validate_shift_times(start_time: time, end_time: time, shift_date: date):
        """Validate shift start/end times are logical."""
        if start_time >= end_time:
            raise ShiftValidationError("End time must be after start time")

        # Calculate duration
        duration = datetime.combine(shift_date, end_time) - datetime.combine(
            shift_date, start_time
        )
        duration_minutes = duration.total_seconds() / 60
        return duration_minutes

    def validate_employee_can_work(employee_id: UUID):
        """Ensure employee exists and is active."""

        employee = employee_service.get_employee_by_id(employee_id)
        if not employee:
            raise EmployeeNotFoundError(employee_id)

        if not employee.get("is_active"):
            raise ShiftValidationError(
                f"Cannot assign shifts to inactive employee {employee['name']}"
            )

        return employee

    def validate_date_in_schedule_week(schedule_id: UUID, shift_date: date):
        """Ensure shift date falls within the schedule's week."""
        schedule = schedule_service.get_schedule_by_id(schedule_id)
        week_start = datetime.strptime(schedule["week_start"], "%Y-%m-%d").date()
        week_end = week_start + timedelta(days=6)

        if not (week_start <= shift_date <= week_end):
            raise ShiftValidationError(
                f"Shift date {shift_date} must be within schedule week "
                f"({week_start} to {week_end})"
            )

    def check_for_overlapping_shifts(
        employee_id: UUID,
        shift_date: date,
        start_time: time,
        end_time: time,
        exclude_shift_id: Optional[UUID] = None,  # For updates
    ) -> List[Dict]:
        """
        Check if employee has overlapping shifts on the same date.

        Returns:
            List of overlapping shifts (empty if no conflicts)
        """
        # Query existing shifts for this employee on this date
        query = (
            supabase.table("shifts")
            .select("*")
            .eq("employee_id", str(employee_id))
            .eq("shift_date", shift_date.isoformat())
        )

        # Exclude current shift if updating
        if exclude_shift_id:
            query = query.neq("id", str(exclude_shift_id))

        response = query.execute()
        existing_shifts = response.data

        overlapping = []

        for shift in existing_shifts:
            existing_start = datetime.strptime(shift["start_time"], "%H:%M:%S").time()
            existing_end = datetime.strptime(shift["end_time"], "%H:%M:%S").time()

            # Check for overlap
            # Two time ranges overlap if: start1 < end2 AND start2 < end1
            if start_time < existing_end and existing_start < end_time:
                overlapping.append(shift)

        return overlapping

    # === READ OPERATIONS ===

    def get_shifts(
        self,
        employee_id: Optional[UUID] = None,
        schedule_id: Optional[UUID] = None,
        shift_date: Optional[date] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get shifts with flexible filtering.
        """
        pass

    def get_shift_by_id(self, shift_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a single shift by ID."""
        pass

    # def get_shifts_for_week(
    #     self,
    #     week_start: date,
    #     employee_id: Optional[UUID] = None
    # ) -> List[Dict[str, Any]]:
    #     """Convenience method for weekly view."""
    #     pass

    def get_employee_shifts(
        self, employee_id: UUID, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """Get all shifts for an employee in a date range."""
        pass

    # === CREATE ===

    def create_shift(
        self,
        schedule_id: UUID,
        employee_id: UUID,
        shift_date: date,
        start_time: time,
        end_time: time,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new shift with full validation.

        Validates:
        1. Schedule exists
        2. Employee exists and is active
        3. Date is within schedule week
        4. Times are valid (TODO)
        5. Within operating hours (TODO)
        6. No overlapping shifts

        Raises:
            ShiftValidationError: If any validation fails
        """
        pass

    # === UPDATE ===

    def update_shift(
        self,
        shift_id: UUID,
        employee_id: Optional[UUID] = None,
        shift_date: Optional[date] = None,
        start_time: Optional[time] = None,
        end_time: Optional[time] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing shift.

        Must re-validate overlap if employee/date/times change.
        """
        pass

    # === DELETE ===

    def delete_shift(self, shift_id: UUID) -> Dict[str, Any]:
        """Delete a shift."""
        pass
