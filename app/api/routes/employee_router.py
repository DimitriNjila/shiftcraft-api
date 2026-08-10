import logging

from ...models.employee_model import EmployeeCreate, EmployeeModel, EmployeeUpdate
from ...models.availability_model import AvailabilityCreate, AvailabilityModel
from ...services.employee_service import (
    employee_service,
    EmployeeHasShiftsError,
    EmployeeNotFoundError,
)
from ...services.availability_service import (
    availability_service,
    AvailabilityConflictError,
    AvailabilityNotFoundError,
)
from ...core.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID

logger = logging.getLogger(__name__)

employee_router = APIRouter(
    prefix="/api/v1/employees",
    tags=["employees"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
)


@employee_router.get("", response_model=list[EmployeeModel])
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
        logger.exception("GET /employees failed: %s", e)
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
    "", response_model=EmployeeModel, status_code=status.HTTP_201_CREATED
)
def create_employee(employee: EmployeeCreate):
    try:
        new_employee = employee_service.create_employee(
            name=employee.name,
            role=employee.role,
            is_active=employee.is_active,
            restaurant_id=employee.restaurant_id,
            salary=employee.salary,
            max_hours_per_week=employee.max_hours_per_week,
        )
        return new_employee
    except ValueError as e:
        logger.warning("Create employee failed validation: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@employee_router.patch("/{employee_id}", response_model=EmployeeModel)
def update_employee(employee_id: UUID, employee: EmployeeUpdate):
    try:
        updated_employee = employee_service.update_employee(
            employee_id=employee_id,
            name=employee.name,
            role=employee.role,
            is_active=employee.is_active,
            email=employee.email,
            deleted_at=employee.deleted_at,
            salary=employee.salary,
            max_hours_per_week=employee.max_hours_per_week,
        )
        return updated_employee
    except EmployeeNotFoundError:
        logger.warning("Update employee failed: employee %s not found", employee_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found",
        )
    except ValueError as e:
        logger.warning("Update employee %s failed validation: %s", employee_id, e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@employee_router.post("/{employee_id}/deactivate", response_model=EmployeeModel)
def deactivate_employee(employee_id: UUID):
    """Disable an employee (soft delete: is_active=False). Reversible via PATCH."""
    try:
        return employee_service.deactivate_employee(employee_id)
    except EmployeeNotFoundError:
        logger.warning("Deactivate employee failed: employee %s not found", employee_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found",
        )


@employee_router.delete("/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(employee_id: UUID):
    """
    Permanently delete an employee. Blocked (409) if they have any shift
    history — deactivate instead for anyone who's actually worked a shift.
    """
    try:
        employee_service.delete_employee(employee_id)
    except EmployeeNotFoundError:
        logger.warning("Delete employee failed: employee %s not found", employee_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found",
        )
    except EmployeeHasShiftsError as e:
        logger.warning("Delete employee blocked: %s", e)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


# --- Availability ---


@employee_router.get(
    "/{employee_id}/availability",
    response_model=list[AvailabilityModel],
)
def get_employee_availability(employee_id: UUID):
    """List all availability windows for an employee."""
    employee = employee_service.get_employee_by_id(employee_id)
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found",
        )
    return availability_service.get_availability(employee_id)


@employee_router.post(
    "/{employee_id}/availability",
    response_model=AvailabilityModel,
    status_code=status.HTTP_201_CREATED,
)
def add_employee_availability(employee_id: UUID, body: AvailabilityCreate):
    """Add an availability window for an employee."""
    try:
        return availability_service.add_availability(
            employee_id=employee_id,
            day_of_week=body.day_of_week,
            start_time=body.start_time,
            end_time=body.end_time,
        )
    except EmployeeNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee with ID {employee_id} not found",
        )
    except AvailabilityConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@employee_router.delete(
    "/{employee_id}/availability/{availability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_employee_availability(employee_id: UUID, availability_id: UUID):
    """Remove an availability window."""
    try:
        availability_service.delete_availability(employee_id, availability_id)
    except AvailabilityNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Availability window {availability_id} not found",
        )
