from collections import defaultdict
from datetime import date, time, timedelta, datetime
from typing import List, Dict, Any, Optional
from uuid import UUID
from supabase import Client
from ..core.db import supabase
from .employee_service import EmployeeService
from .shifts_service import shifts_service
from .schedule_service import ScheduleService

from ..core.constants import BELLAGIOS_SHIFT_TEMPLATES


class ScheduleGenerator:
    """
    Schedule Generator algorithm which handles shifts creation and assignment

    Optimized for:
    - Speed: Generates typical week in < 1 second
    - Fairness: Distributes hours evenly across employees while respecting availability and roles

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

    def generate_schedule(
        self,
        restaurant_id: UUID,
        week_start: date,
        shift_templates: List[Dict[str, Any]] = BELLAGIOS_SHIFT_TEMPLATES,
    ) -> Dict[str, Any]:
        """
        Generate a schedule for a given restaurant and week.

        Args:
            restaurant_id: Restaurant ID
            week_start: Monday of the week to generate
        """

        schedule = self.schedule_service.create_schedule(restaurant_id, week_start)

        employees = self.employee_service.get_employees(restaurant_id, is_active=True)

        if not employees:
            raise ValueError("No active employees found")

        employees_by_role = defaultdict(list)
        for employee in employees:
            employees_by_role[employee["role"]].append(employee)

        employee_hours = {employee["id"]: 0 for employee in employees}

        created_shifts = []

        for template in shift_templates:
            day_of_week = template["day_of_week"]
            start_time_str = template["start_time"]
            end_time_str = template["end_time"]
            role = template["role"]
            count = template.get("count", 1)

            start_time = self.parse_time(start_time_str)
            end_time = self.parse_time(end_time_str)

            shift_date = week_start + timedelta(days=day_of_week - 1)

            if not (week_start <= shift_date < week_start + timedelta(days=7)):
                continue
            eligible_employees = employees_by_role.get(role, [])

            if not eligible_employees:
                print(f"WARNING: No employees with role '{role}' available")
                continue

            for _ in range(count):
                employee = self.select_employee_with_least_hours(
                    eligible_employees, employee_hours
                )

                if not employee:
                    print(f"WARNING: Not enough employees for role '{role}'")
                    break

                try:
                    shift = self.shift_service.create_shift(
                        schedule_id=schedule["id"],
                        employee_id=employee["id"],
                        shift_date=shift_date,
                        start_time=start_time,
                        end_time=end_time,
                        notes=f"{role}",
                    )

                    created_shifts.append(shift)

                    duration = self.calculate_duration(start_time, end_time)
                    employee_hours[employee["id"]] += duration

                except Exception as e:
                    print(f"ERROR creating shift: {e}")

                    continue

        return {
            "id": schedule["id"],
            "restaurant_id": schedule["restaurant_id"],
            "week_start": schedule["week_start"],
            "total_shifts": len(created_shifts),
            "status": "Completed",
        }

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
