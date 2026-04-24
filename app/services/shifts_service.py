import logging

from ..core.db import supabase
from supabase import Client
from typing import List, Optional, Dict, Any
from .schedule_service import schedule_service, ScheduleNotFoundError
from .employee_service import employee_service, EmployeeNotFoundError
from uuid import UUID
from datetime import datetime, date, time, timedelta

logger = logging.getLogger(__name__)


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

    def validate_schedule_exists(self, schedule_id: UUID):
        """Ensure schedule exists before adding shifts to it."""
        logger.debug("Validating schedule exists id=%s", schedule_id)
        schedule = schedule_service.get_schedule_by_id(schedule_id)
        if not schedule:
            logger.error("Schedule not found id=%s", schedule_id)
            raise ScheduleNotFoundError(schedule_id)
        return schedule

    def validate_shift_times(self, start_time: time, end_time: time, shift_date: date):
        """Validate shift start/end times are logical."""
        logger.debug(
            "Validating shift times: %s - %s on %s", start_time, end_time, shift_date
        )
        if start_time >= end_time:
            logger.error(
                "Invalid shift times: end_time %s is not after start_time %s",
                end_time,
                start_time,
            )
            raise ShiftValidationError("End time must be after start time")

        # Calculate duration
        duration = datetime.combine(shift_date, end_time) - datetime.combine(
            shift_date, start_time
        )
        duration_minutes = duration.total_seconds() / 60
        logger.debug("Shift duration: %.0f minutes", duration_minutes)
        # TODO change from hard coded value to restaurant specific max shift length
        return duration_minutes < 600

    def validate_employee_can_work(self, employee_id: UUID):
        """Ensure employee exists and is active."""
        logger.debug("Validating employee can work id=%s", employee_id)
        employee = employee_service.get_employee_by_id(employee_id)
        if not employee:
            logger.error("Employee not found id=%s", employee_id)
            raise EmployeeNotFoundError(employee_id)

        if not employee.get("is_active"):
            logger.error(
                "Employee %s (id=%s) is inactive", employee.get("name"), employee_id
            )
            raise ShiftValidationError(
                f"Cannot assign shifts to inactive employee {employee['name']}"
            )

        return employee

    def validate_date_in_schedule_week(self, schedule_id: UUID, shift_date: date):
        """Ensure shift date falls within the schedule's week."""
        schedule = schedule_service.get_schedule_by_id(schedule_id)
        week_start = datetime.strptime(schedule["week_start"], "%Y-%m-%d").date()
        week_end = week_start + timedelta(days=6)

        logger.debug(
            "Validating shift_date=%s within week %s to %s",
            shift_date,
            week_start,
            week_end,
        )
        if not (week_start <= shift_date <= week_end):
            logger.error(
                "Shift date %s is outside schedule week %s to %s",
                shift_date,
                week_start,
                week_end,
            )
            raise ShiftValidationError(
                f"Shift date {shift_date} must be within schedule week "
                f"({week_start} to {week_end})"
            )

    def check_for_overlapping_shifts(
        self,
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
        logger.debug(
            "Checking overlaps for employee_id=%s on %s", employee_id, shift_date
        )
        # Query existing shifts for this employee on this date
        query = (
            self.supabase.table(self.table_name)
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

        if overlapping:
            logger.warning(
                "Found %d overlapping shift(s) for employee_id=%s on %s",
                len(overlapping),
                employee_id,
                shift_date,
            )
        return overlapping

    # === READ OPERATIONS ===

    def get_shift_by_id(self, shift_id: UUID) -> Optional[Dict[str, Any]]:
        """Get a single shift by ID."""
        logger.debug("Looking up shift id=%s", shift_id)
        query = self.supabase.table(self.table_name).select("*").eq("id", str(shift_id))
        response = query.execute()

        if response.data:
            logger.info("Shift found id=%s", shift_id)
            return response.data[0]
        logger.warning("Shift not found id=%s", shift_id)
        return None

    def get_employee_shifts(
        self, employee_id: UUID, start_date: date, end_date: date
    ) -> List[Dict[str, Any]]:
        """Get all shifts for an employee in a date range."""
        pass

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
        4. Times are valid
        5. Within operating hours (TODO)
        6. No overlapping shifts

        Raises:
            ShiftValidationError: If any validation fails
        """
        logger.info(
            "Creating shift: employee_id=%s date=%s %s-%s",
            employee_id,
            shift_date,
            start_time,
            end_time,
        )
        self.validate_schedule_exists(schedule_id)
        self.validate_employee_can_work(employee_id)
        self.validate_date_in_schedule_week(schedule_id, shift_date)
        self.validate_shift_times(start_time, end_time, shift_date)

        overlapping_shifts = self.check_for_overlapping_shifts(
            employee_id, shift_date, start_time, end_time
        )
        if overlapping_shifts:
            raise OverlappingShiftError(overlapping_shifts)

        shift_data = {
            "schedule_id": str(schedule_id),
            "employee_id": str(employee_id),
            "shift_date": shift_date.isoformat(),
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "notes": notes.strip() if notes else None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        response = self.supabase.table(self.table_name).insert(shift_data).execute()

        if not response.data:
            raise ShiftValidationError("Failed to create shift")

        created = response.data[0]
        logger.info("Shift created id=%s", created.get("id"))
        return created

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

        Args:
            shift_id: ID of shift to update
            employee_id: New employee (optional)
            shift_date: New date (optional)
            start_time: New start time (optional)
            end_time: New end time (optional)
            notes: New notes (optional)

        Returns:
            Updated shift dictionary

        Raises:
            ShiftNotFoundError: If shift doesn't exist
            ShiftValidationError: If validation fails
            EmployeeNotFoundError: If new employee doesn't exist
            OverlappingShiftError: If update creates overlap

        Validation logic:
        1. Shift must exist
        2. If any time/date/employee changes, re-validate:
           - Times are valid (start < end, duration constraints)
           - Within operating hours
           - Date within schedule week
           - Employee exists and is active
           - No overlapping shifts
        """
        existing_shift = self.get_shift_by_id(shift_id)
        if not existing_shift:
            raise ShiftNotFoundError(shift_id)

        update_data = {}

        employee_changed = (
            employee_id is not None
            and str(employee_id) != existing_shift["employee_id"]
        )
        date_changed = (
            shift_date is not None
            and shift_date.isoformat() != existing_shift["shift_date"]
        )
        start_changed = (
            start_time is not None and str(start_time) != existing_shift["start_time"]
        )
        end_changed = (
            end_time is not None and str(end_time) != existing_shift["end_time"]
        )

        # Determine final values for validation
        final_employee_id = (
            employee_id
            if employee_id is not None
            else UUID(existing_shift["employee_id"])
        )
        final_shift_date = (
            shift_date
            if shift_date is not None
            else datetime.fromisoformat(existing_shift["shift_date"]).date()
        )
        final_start_time = (
            start_time
            if start_time is not None
            else datetime.strptime(existing_shift["start_time"], "%H:%M:%S").time()
        )
        final_end_time = (
            end_time
            if end_time is not None
            else datetime.strptime(existing_shift["end_time"], "%H:%M:%S").time()
        )

        if employee_changed or date_changed or start_changed or end_changed:
            # Validate employee exists and is active
            if employee_changed:
                self.validate_employee_can_work(final_employee_id)

            # Validate shift times
            self.validate_shift_times(
                final_start_time, final_end_time, final_shift_date
            )

            # # Validate within operating hours
            # self._validate_within_operating_hours(final_shift_date, final_start_time, final_end_time)

            # Validate date is within schedule week
            schedule_id = UUID(existing_shift["schedule_id"])
            self.validate_date_in_schedule_week(schedule_id, final_shift_date)

            # Check for overlapping shifts (exclude current shift from check)
            overlapping = self.check_for_overlapping_shifts(
                employee_id=final_employee_id,
                shift_date=final_shift_date,
                start_time=final_start_time,
                end_time=final_end_time,
                exclude_shift_id=shift_id,
            )

            if overlapping:
                raise OverlappingShiftError(overlapping)

        if employee_id is not None:
            update_data["employee_id"] = str(employee_id)

        if shift_date is not None:
            update_data["shift_date"] = shift_date.isoformat()

        if start_time is not None:
            update_data["start_time"] = start_time.isoformat()

        if end_time is not None:
            update_data["end_time"] = end_time.isoformat()

        if notes is not None:
            update_data["notes"] = notes

        if not update_data:
            logger.info("No changes to shift id=%s", shift_id)
            return existing_shift

        update_data["updated_at"] = datetime.utcnow().isoformat()
        logger.info(
            "Updating shift id=%s fields=%s", shift_id, list(update_data.keys())
        )

        response = (
            self.supabase.table(self.table_name)
            .update(update_data)
            .eq("id", str(shift_id))
            .execute()
        )

        logger.info("Shift updated id=%s", shift_id)
        return response.data[0]

    # === DELETE ===

    def delete_shift(self, shift_id: UUID) -> Dict[str, Any]:
        """Delete a shift."""
        pass


shifts_service = ShiftsService(supabase)
