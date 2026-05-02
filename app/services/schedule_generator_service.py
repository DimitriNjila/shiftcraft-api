import logging

from collections import defaultdict
from datetime import date, time, timedelta, datetime
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
from supabase import Client
from ..core.db import supabase
from .employee_service import EmployeeService
from .shifts_service import shifts_service
from .schedule_service import ScheduleService
from .shift_template_service import ShiftTemplateService

from ..core.constants import BELLAGIOS_SHIFT_TEMPLATES

logger = logging.getLogger(__name__)

MIN_REST_HOURS = 10.0


class ScheduleGenerator:
    """
    Schedule Generator algorithm which handles shifts creation and assignment

    Optimized for:
    - Speed: Generates typical week in < 1 second
    - Fairness: Distributes hours evenly across employees while respecting availability and roles

    Constraints enforced:
    - Minimum rest between shifts: 10 hours
    - Weekly hours cap: respects employee.max_hours_per_week when set

    shift_templates: List of shift patterns to create
                Example: [
                    {
                        "day_of_week": 1,  # Monday
                        "start_time": "09:00:00",
                        "end_time": "17:00:00",
                        "role": "Server",
                        "count": 2  # Need 2 servers
                    }
                ]
    """

    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client
        self.schedule_service = ScheduleService(supabase_client)
        self.employee_service = EmployeeService(supabase_client)
        self.shift_service = shifts_service
        self.shift_template_service = ShiftTemplateService(supabase_client)

    def generate_schedule(
        self,
        restaurant_id: UUID,
        week_start: date,
        shift_templates: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate a schedule for a given restaurant and week.

        Template resolution order:
            1. Explicitly passed shift_templates argument
            2. Saved templates in the database for this restaurant
            3. Hardcoded BELLAGIOS_SHIFT_TEMPLATES constant (fallback)

        Args:
            restaurant_id: Restaurant ID
            week_start: Monday of the week to generate
            shift_templates: Override templates (optional)
        """
        logger.info(
            "Generating schedule: restaurant_id=%s week_start=%s", restaurant_id, week_start
        )

        if shift_templates is None:
            saved = self.shift_template_service.get_templates(str(restaurant_id))
            if saved:
                shift_templates = saved["templates"]
                logger.info(
                    "Using %d saved shift templates for restaurant_id=%s",
                    len(shift_templates),
                    restaurant_id,
                )
            else:
                shift_templates = BELLAGIOS_SHIFT_TEMPLATES
                logger.info(
                    "No saved templates found, using default BELLAGIOS templates (%d)",
                    len(BELLAGIOS_SHIFT_TEMPLATES),
                )

        normalized_week_start = self.schedule_service.get_week_start(week_start)
        existing_schedule = self.schedule_service.get_schedule_by_week(
            normalized_week_start, str(restaurant_id)
        )

        if existing_schedule:
            logger.info(
                "Schedule already exists for week %s, appending shifts to id=%s",
                normalized_week_start,
                existing_schedule["id"],
            )
            schedule = existing_schedule
        else:
            schedule = self.schedule_service.create_schedule(restaurant_id, week_start)

        employees = self.employee_service.get_employees(restaurant_id, is_active=True)

        if not employees:
            raise ValueError("No active employees found")

        logger.info("Loaded %d active employees", len(employees))

        employees_by_role = defaultdict(list)
        for employee in employees:
            employees_by_role[employee["role"]].append(employee)

        employee_hours: Dict[str, float] = {emp["id"]: 0.0 for emp in employees}
        last_shift_end: Dict[str, Optional[datetime]] = {emp["id"]: None for emp in employees}

        # When appending to an existing schedule, preload already-assigned hours and
        # last shift end times so constraints apply across both old and new shifts.
        if existing_schedule:
            self._preload_existing_shifts(schedule["id"], employee_hours, last_shift_end)

        created_shifts = []

        for template in shift_templates:
            day_of_week = template["day_of_week"]
            start_time = self.parse_time(template["start_time"])
            end_time = self.parse_time(template["end_time"])
            role = template["role"]
            count = template.get("count", 1)

            shift_date = week_start + timedelta(days=day_of_week - 1)

            if not (week_start <= shift_date < week_start + timedelta(days=7)):
                continue

            eligible_employees = employees_by_role.get(role, [])

            if not eligible_employees:
                logger.warning(
                    "No employees with role '%s' available for template on %s",
                    role,
                    shift_date,
                )
                continue

            shift_start_dt = datetime.combine(shift_date, start_time)
            shift_end_dt = datetime.combine(shift_date, end_time)
            duration = self.calculate_duration(start_time, end_time)

            for _ in range(count):
                available = [
                    emp for emp in eligible_employees
                    if self._has_sufficient_rest(last_shift_end[emp["id"]], shift_start_dt)
                    and not self._would_exceed_hours_cap(
                        emp, employee_hours[emp["id"]], duration
                    )
                ]

                if not available:
                    logger.warning(
                        "No available employees for role '%s' on %s (rest/cap constraints)",
                        role,
                        shift_date,
                    )
                    break

                employee = self.select_employee_with_least_hours(available, employee_hours)

                logger.info(
                    "Assigning %s: selected %s (current hours: %.1f)",
                    role,
                    employee.get("name"),
                    employee_hours[employee["id"]],
                )

                shift_data = {
                    "id": str(uuid4()),
                    "schedule_id": str(schedule["id"]),
                    "employee_id": str(employee["id"]),
                    "shift_date": shift_date.isoformat(),
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "notes": f"{role}",
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                }

                created_shifts.append(shift_data)

                employee_hours[employee["id"]] += duration
                last_shift_end[employee["id"]] = shift_end_dt

        if created_shifts:
            self.supabase.table("shifts").insert(created_shifts).execute()

        logger.info("Schedule generated: %d total shifts", len(created_shifts))

        return {
            "id": schedule["id"],
            "restaurant_id": schedule["restaurant_id"],
            "week_start": schedule["week_start"],
            "total_shifts": len(created_shifts),
            "status": "Completed",
        }

    def _preload_existing_shifts(
        self,
        schedule_id: str,
        employee_hours: Dict[str, float],
        last_shift_end: Dict[str, Optional[datetime]],
    ) -> None:
        """
        Load existing shifts for a schedule into the tracking dicts so that
        rest and hours-cap constraints apply correctly when appending new shifts.
        """
        response = (
            self.supabase.table("shifts")
            .select("*")
            .eq("schedule_id", str(schedule_id))
            .execute()
        )
        for shift in response.data:
            emp_id = shift["employee_id"]
            if emp_id not in employee_hours:
                continue
            start = self.parse_time(shift["start_time"])
            end = self.parse_time(shift["end_time"])
            duration = self.calculate_duration(start, end)
            employee_hours[emp_id] = employee_hours.get(emp_id, 0.0) + duration

            shift_end_dt = datetime.combine(
                date.fromisoformat(shift["shift_date"]), end
            )
            current_last = last_shift_end.get(emp_id)
            if current_last is None or shift_end_dt > current_last:
                last_shift_end[emp_id] = shift_end_dt

        logger.info("Preloaded existing shifts for schedule_id=%s", schedule_id)

    @staticmethod
    def _has_sufficient_rest(
        last_end: Optional[datetime], next_start: datetime
    ) -> bool:
        """Return True if at least MIN_REST_HOURS have passed since the employee's last shift."""
        if last_end is None:
            return True
        gap_hours = (next_start - last_end).total_seconds() / 3600
        return gap_hours >= MIN_REST_HOURS

    @staticmethod
    def _would_exceed_hours_cap(
        employee: Dict[str, Any], current_hours: float, additional_hours: float
    ) -> bool:
        """Return True if adding this shift would exceed the employee's weekly hours cap."""
        cap = employee.get("max_hours_per_week")
        if cap is None:
            return False
        return current_hours + additional_hours > cap

    @staticmethod
    def select_employee_with_least_hours(
        employees: List[Dict], employee_hours: Dict[str, float]
    ) -> Optional[Dict]:
        """
        Select employee with fewest hours assigned.

        This ensures fair distribution of work.
        """
        if not employees:
            return None

        return min(employees, key=lambda e: employee_hours[e["id"]])

    @staticmethod
    def parse_time(time_str: str) -> time:
        """Parse time string to time object."""
        return datetime.strptime(time_str, "%H:%M:%S").time()

    @staticmethod
    def calculate_duration(start_time: time, end_time: time) -> float:
        """Calculate duration in hours."""
        start_dt = datetime.combine(date.today(), start_time)
        end_dt = datetime.combine(date.today(), end_time)
        return (end_dt - start_dt).total_seconds() / 3600


schedule_generator = ScheduleGenerator(supabase)
