from pydantic import BaseModel
from uuid import UUID
from datetime import date


class ScheduleCreate(BaseModel):
    restaurant_id: str
    week_start: date


class ScheduleModel(ScheduleCreate):
    id: UUID


{
    "id": 1,
    "week_start": "2025-01-06",
    "shifts": [
        {
            "id": 101,
            "employee": {"id": 5, "name": "Alice"},
            "shift_date": "2025-01-06",
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "duration_hours": 8.0,
        }
    ],
}
