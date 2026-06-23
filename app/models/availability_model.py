from pydantic import BaseModel, field_validator
from uuid import UUID
from typing import Optional


class AvailabilityCreate(BaseModel):
    day_of_week: int
    start_time: str  # HH:MM:SS
    end_time: str    # HH:MM:SS

    @field_validator("day_of_week")
    @classmethod
    def validate_day(cls, v: int) -> int:
        if v < 1 or v > 7:
            raise ValueError("day_of_week must be between 1 (Monday) and 7 (Sunday)")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        from datetime import datetime
        try:
            datetime.strptime(v, "%H:%M:%S")
        except ValueError:
            raise ValueError("time must be in HH:MM:SS format")
        return v


class AvailabilityModel(AvailabilityCreate):
    id: UUID
    employee_id: UUID
    restaurant_id: UUID
    created_at: str
    updated_at: str
