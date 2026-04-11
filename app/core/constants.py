from enum import Enum
from datetime import time

BELLAGIOS_SHIFT_TEMPLATES = [
    {
        "day_of_week": 2,
        "start_time": "16:00:00",
        "end_time": "20:00:00",
        "role": "Server",
        "count": 1,
    },
    {
        "day_of_week": 2,
        "start_time": "11:00:00",
        "end_time": "20:00:00",
        "role": "Cook",
        "count": 1,
    },
    {
        "day_of_week": 3,
        "start_time": "11:00:00",
        "end_time": "20:00:00",
        "role": "Server",
        "count": 1,
    },
    {
        "day_of_week": 3,
        "start_time": "11:00:00",
        "end_time": "16:00:00",
        "role": "Cook",
        "count": 2,
    },
    {
        "day_of_week": 3,
        "start_time": "16:00:00",
        "end_time": "20:00:00",
        "role": "Cook",
        "count": 2,
    },
    {
        "day_of_week": 4,
        "start_time": "11:00:00",
        "end_time": "16:00:00",
        "role": "Server",
        "count": 1,
    },
    {
        "day_of_week": 4,
        "start_time": "11:00:00",
        "end_time": "16:00:00",
        "role": "Cook",
        "count": 1,
    },
    {
        "day_of_week": 4,
        "start_time": "16:00:00",
        "end_time": "20:00:00",
        "role": "Cook",
        "count": 2,
    },
    {
        "day_of_week": 5,
        "start_time": "11:00:00",
        "end_time": "16:00:00",
        "role": "Server",
        "count": 1,
    },
    {
        "day_of_week": 5,
        "start_time": "16:00:00",
        "end_time": "21:00:00",
        "role": "Server",
        "count": 1,
    },
    {
        "day_of_week": 5,
        "start_time": "11:00:00",
        "end_time": "16:00:00",
        "role": "Cook",
        "count": 1,
    },
    {
        "day_of_week": 5,
        "start_time": "16:00:00",
        "end_time": "21:00:00",
        "role": "Cook",
        "count": 2,
    },
    {
        "day_of_week": 6,
        "start_time": "11:00:00",
        "end_time": "16:00:00",
        "role": "Server",
        "count": 1,
    },
    {
        "day_of_week": 6,
        "start_time": "11:00:00",
        "end_time": "16:00:00",
        "role": "Cook",
        "count": 1,
    },
    {
        "day_of_week": 6,
        "start_time": "16:00:00",
        "end_time": "21:00:00",
        "role": "Server",
        "count": 1,
    },
    {
        "day_of_week": 6,
        "start_time": "16:00:00",
        "end_time": "21:00:00",
        "role": "Cook",
        "count": 2,
    },
    {
        "day_of_week": 7,
        "start_time": "12:00:00",
        "end_time": "18:00:00",
        "role": "Server",
        "count": 1,
    },
    {
        "day_of_week": 7,
        "start_time": "12:00:00",
        "end_time": "18:00:00",
        "role": "Cook",
        "count": 1,
    },
]


class DayOfWeek(int, Enum):
    """ISO 8601 weekdays (Monday=1, Sunday=7)."""

    MONDAY = 1
    TUESDAY = 2
    WEDNESDAY = 3
    THURSDAY = 4
    FRIDAY = 5
    SATURDAY = 6
    SUNDAY = 7

    @classmethod
    def from_date(cls, date):
        """Get DayOfWeek from a date object."""
        return cls(date.isoweekday())

    @property
    def display_name(self) -> str:
        """Human-readable name."""
        return self.name.capitalize()


class EmployeeRole(str, Enum):
    """Valid employee roles."""

    SERVER = "Server"
    COOK = "Cook"
    MANAGER = "Manager"


class ShiftType(str, Enum):
    """Shift categories (optional - for future use)."""

    OPENING = "Opening"
    CLOSING = "Closing"
    DOUBLE = "Double"


# Bellagios Operating Hours
OPERATING_HOURS = {
    DayOfWeek.TUESDAY: {"open": time(11, 0), "close": time(20, 0)},
    DayOfWeek.WEDNESDAY: {"open": time(11, 0), "close": time(20, 0)},
    DayOfWeek.THURSDAY: {"open": time(11, 0), "close": time(21, 0)},
    DayOfWeek.FRIDAY: {"open": time(11, 0), "close": time(21, 0)},
    DayOfWeek.SATURDAY: {"open": time(11, 0), "close": time(20, 0)},
    DayOfWeek.SUNDAY: {"open": time(12, 0), "close": time(18, 0)},
}


def is_restaurant_open(day_of_week: DayOfWeek) -> bool:
    """Check if restaurant is open on a given day."""
    return day_of_week in OPERATING_HOURS


def get_operating_hours(day_of_week: DayOfWeek) -> dict | None:
    """Get opening/closing times for a day, or None if closed."""
    return OPERATING_HOURS.get(day_of_week)
