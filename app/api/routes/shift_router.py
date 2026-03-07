from ...models.shifts_model import ShiftCreate, ShiftResponse, ShiftUpdate
from datetime import date
from ...services.shifts_service import (
    shifts_service,
    ShiftNotFoundError,
    ShiftValidationError,
    OverlappingShiftError,
)
from ...services.employee_service import EmployeeNotFoundError
from fastapi import APIRouter, HTTPException, status
from uuid import UUID

shifts_router = APIRouter(
    prefix="/shifts",
    tags=["shifts"],
    responses={404: {"description": "Not found"}},
)


@shifts_router.post("/", response_model=ShiftCreate)
def create_shift(shift: ShiftCreate):
    try:
        created_shift = shifts_service.create_shift(
            employee_id=shift.employee_id,
            shift_date=shift.shift_date,
            start_time=shift.start_time,
            end_time=shift.end_time,
            notes=shift.notes,
        )
        return created_shift
    except EmployeeNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee {e.employee_id} not found",
        )
    except OverlappingShiftError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e), "overlapping_shifts": e.overlapping_shifts},
        )
    except ShiftValidationError as e:
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Shift {shift_id} not found"
        )

    except EmployeeNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Employee {e.employee_id} not found",
        )

    except OverlappingShiftError as e:
        # Return detailed overlap information
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": str(e), "overlapping_shifts": e.overlapping_shifts},
        )

    except ShiftValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
