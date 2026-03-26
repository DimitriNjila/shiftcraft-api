from pydantic import BaseModel, Field
from uuid import UUID
from datetime import date, time, datetime
from typing import List, Optional


class ScheduleCreate(BaseModel):
    restaurant_id: str
    week_start: date


class ScheduleModel(ScheduleCreate):
    id: UUID


class EmployeeBasic(BaseModel):
    """Embedded employee info in shift response"""

    id: UUID
    name: str
    role: str


class ShiftInSchedule(BaseModel):
    """Shift as it appears in schedule response"""

    id: UUID
    shift_date: date
    start_time: time
    end_time: time
    duration_hours: float
    notes: Optional[str]
    employee: EmployeeBasic


class ScheduleResponse(BaseModel):
    """Complete schedule with all shifts"""

    id: UUID
    restaurant_id: str
    week_start: date
    created_at: datetime
    shifts: List[ShiftInSchedule]
    total_shifts: int = 0
    total_hours: float = 0.0


class ShiftTemplate(BaseModel):
    """Template for a shift to be created."""

    day_of_week: int = Field(..., ge=1, le=7, description="1=Monday, 7=Sunday")
    start_time: str = Field(..., description="HH:MM:SS format")
    end_time: str = Field(..., description="HH:MM:SS format")
    role: str = Field(..., description="Employee role required")
    count: int = Field(default=1, ge=1, description="Number of employees needed")


class GenerateScheduleRequest(BaseModel):
    """Request to generate a schedule."""

    week_start: date = Field(..., description="Monday of the week to schedule")
    restaurant_id: str
    shift_templates: List[ShiftTemplate]
