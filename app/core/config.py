from pydantic_settings import BaseSettings
from typing import List
from datetime import time


class Settings(BaseSettings):
    # Restaurant Configuration (MVP - Single Restaurant)
    RESTAURANT_ID: str = "550e8400-e29b-41d4-a716-446655440000"  # Default UUID

    # Operating Hours
    OPERATING_DAYS: List[int] = [1, 2, 3, 4, 5, 6]  # Monday=1 to Sunday=6 (ISO weekday)
    OPENING_TIME: time = time(11, 0)  # 11:00 AM
    CLOSING_TIME: time = time(21, 0)  # 09:00 PM

    # Shift Configuration
    MIN_SHIFT_DURATION_MINUTES: int = 240  # 4 hours minimum
    MAX_SHIFT_DURATION_MINUTES: int = 600  # 10 hours maximum
    MIN_BREAK_BETWEEN_SHIFTS_MINUTES: int = 0  # Back-to-back allowed for now

    # Schedule Settings
    SCHEDULE_WEEKS_AHEAD: int = 4  # How far in advance to allow scheduling
    SCHEDULE_WEEKS_BEHIND: int = 2  # How far back to keep schedules

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
