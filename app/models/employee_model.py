from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional


class EmployeeCreate(BaseModel):
    name: str
    role: str
    restaurant_id: str
    is_active: bool = True


class EmployeeModel(EmployeeCreate):
    id: UUID
    created_at: str
    email: Optional[EmailStr] = None
    deleted_at: Optional[str] = None


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    email: Optional[EmailStr] = None
    deleted_at: Optional[str] = None
