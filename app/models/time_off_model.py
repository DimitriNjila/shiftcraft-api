from datetime import date
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator


class TimeOffCreate(BaseModel):
    start_date: date
    end_date: date
    reason: Optional[str] = None

    @model_validator(mode="after")
    def check_date_order(self) -> "TimeOffCreate":
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned or None


class TimeOffModel(BaseModel):
    id: UUID
    employee_id: UUID
    restaurant_id: UUID
    start_date: date
    end_date: date
    reason: Optional[str] = None
    created_at: str
    updated_at: str
