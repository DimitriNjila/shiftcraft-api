from datetime import date, time, datetime, timedelta
from uuid import UUID
from typing import Optional
from pydantic import BaseModel, field_validator


class ShiftCreate(BaseModel):
    schedule_id: UUID
    employee_id: UUID
    shift_date: date
    start_time: time
    end_time: time
    notes: Optional[str] = None

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, v, info):
        """Ensure end_time is after start_time."""
        if "start_time" in info.data and v <= info.data["start_time"]:
            raise ValueError("End time must be after start time")
        return v


class ShiftUpdate(BaseModel):
    employee_id: Optional[UUID] = None
    shift_date: Optional[date] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    notes: Optional[str] = None


class ShiftResponse(BaseModel):
    id: UUID
    schedule_id: UUID
    employee_id: UUID
    shift_date: date
    start_time: time
    end_time: time
    notes: Optional[str]
    duration_hours: float
    created_at: datetime
    updated_at: datetime

    # employee: Optional[dict] = None
    # schedule: Optional[dict] = None
