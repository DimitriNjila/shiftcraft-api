from pydantic import BaseModel


class ScheduleModel(BaseModel):
    id: int
    week_start: str
    restaurant_id: str


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
