from pydantic import BaseModel, Field, field_validator
from typing import List


class RestaurantRolesResponse(BaseModel):
    restaurant_id: str
    roles: List[str]


class RestaurantRolesUpdate(BaseModel):
    roles: List[str] = Field(..., min_length=1)

    @field_validator("roles")
    @classmethod
    def clean_and_dedupe(cls, v: List[str]) -> List[str]:
        cleaned = []
        seen = set()
        for raw in v:
            role = (raw or "").strip()
            if not role:
                continue
            # Case-insensitive dedupe, but preserve the owner's chosen casing
            # for display ("BOH" vs "boh" is the same role, keep first form).
            key = role.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(role)
        if not cleaned:
            raise ValueError("roles must contain at least one non-empty entry")
        return cleaned
