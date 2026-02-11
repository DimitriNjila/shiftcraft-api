from ...models.employee_model import EmployeeCreate, EmployeeModel, EmployeeUpdate
from ...services.employee_service import employee_service, EmployeeNotFoundError
from fastapi import APIRouter, HTTPException, status
from uuid import UUID

employee_router = APIRouter(
    prefix="/employees",
    tags=["employees"],
    responses={404: {"description": "Not found"}},
)


@employee_router.get("/", response_model=list[EmployeeModel])
def get_employees(
    restaurant_id: str | None = None,
    is_active: bool | None = None,
):
    try:
        employees = employee_service.get_employees(
            restaurant_id=restaurant_id, is_active=is_active
        )
        return employees
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@employee_router.get("/{employee_id}", response_model=EmployeeModel)
def get_employee(employee_id: UUID):
    """Get a single employee by ID. Returns 404 if not found."""
    employee = employee_service.get_employee_by_id(employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found",
        )
    return employee


@employee_router.post(
    "/", response_model=EmployeeModel, status_code=status.HTTP_201_CREATED
)
def create_employee(employee: EmployeeCreate):
    try:
        new_employee = employee_service.create_employee(
            name=employee.name,
            role=employee.role,
            is_active=employee.is_active,
            restaurant_id=employee.restaurant_id,
        )
        return new_employee
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@employee_router.put("/{employee_id}", response_model=EmployeeModel)
def update_employee(employee_id: UUID, employee: EmployeeUpdate):
    try:
        updated_employee = employee_service.update_employee(
            employee_id=employee_id,
            name=employee.name,
            role=employee.role,
            is_active=employee.is_active,
            email=employee.email,
            deleted_at=employee.deleted_at,
        )
        return updated_employee
    except EmployeeNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found",
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@employee_router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(employee_id: UUID):
    try:
        employee_service.deactivate_employee(employee_id)
    except EmployeeNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found",
        )
