from pydantic import BaseModel
from uuid import UUID
from typing import List
from datetime import datetime
from .schedule_model import ShiftTemplate


class ShiftTemplateSave(BaseModel):
    restaurant_id: str
    templates: List[ShiftTemplate]


class ShiftTemplateResponse(BaseModel):
    id: UUID
    restaurant_id: str
    templates: List[ShiftTemplate]
    updated_at: datetime
