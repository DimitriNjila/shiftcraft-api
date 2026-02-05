from pydantic import BaseModel, EmailStr


class EmployeeCreate(BaseModel):
    name: str
    role: str
    is_active: bool = True


class EmployeeModel(EmployeeCreate):
    id: int
    restaurant_id: int
    email: EmailStr
    created_at: str
    deleted_at: str
