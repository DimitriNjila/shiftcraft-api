from pydantic import BaseModel
from typing import Dict, List, Optional

from .schedule_model import ShiftTemplate


class ParsedTemplateRow(BaseModel):
    """A single parsed + validated row from an imported CSV/Excel/image file."""

    row_number: int
    name: Optional[str] = None
    day_of_week: Optional[int] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    role: Optional[str] = None
    count: Optional[int] = None
    confidence: Optional[str] = None  # "high" | "low" — set by image import, unset for file import
    errors: List[str] = []
    warnings: List[str] = []
    is_valid: bool


class TemplateImportPreviewResponse(BaseModel):
    """Preview returned by parse endpoints — never saved yet."""

    column_mapping: Dict[str, str]
    rows: List[ParsedTemplateRow]
    valid_count: int
    error_count: int


class TemplateImportConfirmRequest(BaseModel):
    """Confirmed rows to actually save, after the user has reviewed the preview."""

    restaurant_id: str
    rows: List[ShiftTemplate]
