import logging

from ...models.shifts_model import ShiftCreate, ShiftResponse, ShiftUpdate
from ...services.shifts_service import (
    shifts_service,
    ShiftNotFoundError,
    ShiftValidationError,
    OverlappingShiftError,
)
from ...services.employee_service import EmployeeNotFoundError
from ...core.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID

logger = logging.getLogger(__name__)

shifts_router = APIRouter(
    prefix="/api/v1/shifts",
    tags=["shifts"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
)


@shifts_router.post("", response_model=ShiftCreate)
def create_shift(shift: ShiftCreate):
    try:
        created_shift = shifts_service.create_shift(
            schedule_id=shift.schedule_id,
            employee_id=shift.employee_id,
            shift_date=shift.shift_date,
            start_time=shift.start_time,
            end_time=shift.end_time,
            notes=shift.notes,
        )
        return created_shift
    except EmployeeNotFoundError as e:
        logger.warning("Create shift failed: employee %s not found", e.employee_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee {e.employee_id} not found",
        )
    except OverlappingShiftError as e:
        logger.warning("Create shift failed: overlap detected — %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e), "overlapping_shifts": e.overlapping_shifts},
        )
    except ShiftValidationError as e:
        logger.warning("Create shift failed validation: %s", e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@shifts_router.patch("/{shift_id}", response_model=ShiftResponse)
def update_shift(shift_id: UUID, request: ShiftUpdate):
    try:
        updated_shift = shifts_service.update_shift(
            shift_id=shift_id,
            employee_id=request.employee_id,
            shift_date=request.shift_date,
            start_time=request.start_time,
            end_time=request.end_time,
            notes=request.notes,
        )
        return updated_shift

    except ShiftNotFoundError:
        logger.warning("Update shift failed: shift %s not found", shift_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Shift {shift_id} not found"
        )

    except EmployeeNotFoundError as e:
        logger.warning("Update shift %s failed: employee %s not found", shift_id, e.employee_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee {e.employee_id} not found",
        )

    except OverlappingShiftError as e:
        logger.warning("Update shift %s failed: overlap detected — %s", shift_id, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e), "overlapping_shifts": e.overlapping_shifts},
        )

    except ShiftValidationError as e:
        logger.warning("Update shift %s failed validation: %s", shift_id, e)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@shifts_router.delete("/{shift_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shift(shift_id: UUID):
    try:
        shifts_service.delete_shift(shift_id)
    except ShiftNotFoundError:
        logger.warning("Delete shift failed: shift %s not found", shift_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Shift {shift_id} not found"
        )
