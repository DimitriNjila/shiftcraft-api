import logging

from datetime import datetime
from typing import Optional

from icalendar import Calendar, Event
from supabase import Client

from .schedule_service import ScheduleService

logger = logging.getLogger(__name__)


class ExportService:
    """Service for generating calendar/file exports of schedules."""

    def __init__(self, supabase_client: Optional[Client] = None):
        self.schedule_service = ScheduleService(supabase_client)

    def generate_ical(self, schedule_id) -> str:
        """
        Build an iCalendar (.ics) document for every shift in a schedule.

        Args:
            schedule_id: Schedule to export

        Returns:
            Raw .ics file content as a string

        Raises:
            ScheduleNotFoundError: If the schedule doesn't exist
        """
        schedule = self.schedule_service.get_schedule_with_shifts(schedule_id)
        restaurant_name = self.schedule_service.get_restaurant_name(
            schedule.get("restaurant_id")
        )

        logger.info(
            "Generating iCal export for schedule id=%s shifts=%d",
            schedule_id,
            schedule["total_shifts"],
        )

        cal = Calendar()
        cal.add("prodid", "-//Prep//Schedule Export//EN")
        cal.add("version", "2.0")

        dtstamp = datetime.utcnow()
        for shift in schedule["shifts"]:
            shift_date = datetime.strptime(shift["shift_date"], "%Y-%m-%d").date()
            start_time = datetime.strptime(shift["start_time"], "%H:%M:%S").time()
            end_time = datetime.strptime(shift["end_time"], "%H:%M:%S").time()

            employee = shift.get("employee") or {}
            role = employee.get("role", "Unknown")

            event = Event()
            event.add("summary", f"Shift - {role}")
            event.add("dtstart", datetime.combine(shift_date, start_time))
            event.add("dtend", datetime.combine(shift_date, end_time))
            event.add("dtstamp", dtstamp)
            event.add("uid", f"{shift['id']}@prep-app")
            event.add("description", restaurant_name)

            cal.add_component(event)

        logger.info("iCal export complete for schedule id=%s", schedule_id)
        return cal.to_ical().decode("utf-8")


export_service = ExportService()
