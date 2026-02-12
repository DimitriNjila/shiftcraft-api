from pydantic import BaseModel


class ShiftsModel(BaseModel):
    id: int
    employee: dict
    shift_date: str
    start_time: str
    end_time: str
    duration_hours: float
