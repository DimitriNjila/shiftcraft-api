from collections import defaultdict
from datetime import date, time, timedelta, datetime
from typing import List, Dict, Any, Optional
from uuid import UUID, uuid4
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
            start_time = self.parse_time(template["start_time"])
            end_time = self.parse_time(template["end_time"])
            role = template["role"]
            count = template.get("count", 1)


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

                shift_data = {
                "id": str(uuid4()),  
                "schedule_id": str(schedule['id']),
                "employee_id": str(employee['id']),
                "shift_date": shift_date.isoformat(),
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "notes": f"{role}",
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat(),
            }

                created_shifts.append(shift_data)

                duration = self.calculate_duration(start_time, end_time)
                employee_hours[employee["id"]] += duration
                    
        if created_shifts:
            self.supabase.table("shifts").insert(created_shifts).execute()



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

# // example request:
# curl -X 'POST' \
#   'http://localhost:8000/schedules/generate' \
#   -H 'accept: application/json' \
#   -H 'Content-Type: application/json' \
#   -d '{
#   "week_start": "2026-04-20",
#   "restaurant_id": "4fadbd49-40ab-4105-a670-f7906722beac",
#   "shift_templates": [
#     {
#         "day_of_week": 2,
#         "start_time": "16:00:00",
#         "end_time": "20:00:00",
#         "role": "Server",
#         "count": 1
#     },
#     {
#         "day_of_week": 2,
#         "start_time": "11:00:00",
#         "end_time": "20:00:00",
#         "role": "Cook",
#         "count": 1
#     },
#     {
#         "day_of_week": 3,
#         "start_time": "11:00:00",
#         "end_time": "20:00:00",
#         "role": "Server",
#         "count": 1
#     },
#     {
#         "day_of_week": 3,
#         "start_time": "11:00:00",
#         "end_time": "16:00:00",
#         "role": "Cook",
#         "count": 2
#     },
#     {
#         "day_of_week": 3,
#         "start_time": "16:00:00",
#         "end_time": "20:00:00",
#         "role": "Cook",
#         "count": 2
#     },
#     {
#         "day_of_week": 4,
#         "start_time": "11:00:00",
#         "end_time": "16:00:00",
#         "role": "Server",
#         "count": 1
#     },
#     {
#         "day_of_week": 4,
#         "start_time": "11:00:00",
#         "end_time": "16:00:00",
#         "role": "Cook",
#         "count": 1
#     },
#     {
#         "day_of_week": 4,
#         "start_time": "16:00:00",
#         "end_time": "20:00:00",
#         "role": "Cook",
#         "count": 2
#     },
#     {
#         "day_of_week": 5,
#         "start_time": "11:00:00",
#         "end_time": "16:00:00",
#         "role": "Server",
#         "count": 1
#     },
#     {
#         "day_of_week": 5,
#         "start_time": "16:00:00",
#         "end_time": "21:00:00",
#         "role": "Server",
#         "count": 1
#     },
#     {
#         "day_of_week": 5,
#         "start_time": "11:00:00",
#         "end_time": "16:00:00",
#         "role": "Cook",
#         "count": 1
#     },
#     {
#         "day_of_week": 5,
#         "start_time": "16:00:00",
#         "end_time": "21:00:00",
#         "role": "Cook",
#         "count": 2
#     },
#     {
#         "day_of_week": 6,
#         "start_time": "11:00:00",
#         "end_time": "16:00:00",
#         "role": "Server",
#         "count": 1
#     },
#     {
#         "day_of_week": 6,
#         "start_time": "11:00:00",
#         "end_time": "16:00:00",
#         "role": "Cook",
#         "count": 1
#     },
#     {
#         "day_of_week": 6,
#         "start_time": "16:00:00",
#         "end_time": "21:00:00",
#         "role": "Server",
#         "count": 1
#     },
#     {
#         "day_of_week": 6,
#         "start_time": "16:00:00",
#         "end_time": "21:00:00",
#         "role": "Cook",
#         "count": 2
#     },
#     {
#         "day_of_week": 7,
#         "start_time": "12:00:00",
#         "end_time": "18:00:00",
#         "role": "Server",
#         "count": 1
#     },
#     {
#         "day_of_week": 7,
#         "start_time": "12:00:00",
#         "end_time": "18:00:00",
#         "role": "Cook",
#         "count": 1
#     }
#   ]
# }'
