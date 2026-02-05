from ...models.employee_model import EmployeeCreate, EmployeeModel
from ...services import employee_service
from fastapi import APIRouter, HTTPException
from uuid import UUID

employee_router = APIRouter(
    prefix="/employees",
    tags=["employees"],
    responses={404: {"description": "Not found"}},
)


@employee_router.get("/", response_model=list[EmployeeModel])
def get_employees():
    try:
        employees = employee_service.get_employees()
        return employees
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@employee_router.get("/{employee_id}", response_model=EmployeeModel)
def get_employee(employee_id: UUID):
    try:
        employee = employee_service.get_employee_by_id(employee_id)
        if not employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        return employee
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@employee_router.post("/", response_model=EmployeeModel)
def create_employee(employee: EmployeeCreate):
    try:
        new_employee = employee_service.create_employee(
            name=employee.name,
            role=employee.role,
            is_active=employee.is_active,
        )
        return new_employee
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# @employee_router.put("/{employee_id}", response_model=EmployeeModel)
# def update_employee(employee_id: UUID):
#     try:
#         updated_employee = employee_service.update_employee(
#             employee_id=employee_id,
#             name=employee.name,
#             role=employee.role,
#             is_active=employee.is_active,
#         )
#         if not updated_employee:
#             raise HTTPException(status_code=404, detail="Employee not found")
#         return updated_employee
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


@employee_router.delete("/{employee_id}", response_model=EmployeeModel)
def delete_employee(employee_id: UUID):
    try:
        deleted_employee = employee_service.delete_employee(employee_id)
        if not deleted_employee:
            raise HTTPException(status_code=404, detail="Employee not found")
        return deleted_employee
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
