from ...models.schedule_model import (
    GenerateScheduleRequest,
    ScheduleModel,
    ScheduleCreate,
    ScheduleResponse,
)
from datetime import date
from ...services.schedule_service import schedule_service
from ...services.schedule_generator_service import schedule_generator
from ...core.constants import BELLAGIOS_SHIFT_TEMPLATES
from fastapi import APIRouter, HTTPException, status
from uuid import UUID

schedule_router = APIRouter(
    prefix="/schedules",
    tags=["schedules"],
    responses={404: {"description": "Not found"}},
)


@schedule_router.get("/", response_model=list[ScheduleModel])
def get_schedules(
    restaurant_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    try:
        schedules = schedule_service.get_schedules(restaurant_id, start_date, end_date)
        return schedules
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again later.",
        )


@schedule_router.get("/{schedule_id}", response_model=ScheduleResponse)
def get_schedule(schedule_id: UUID):
    try:
        schedule = schedule_service.get_schedule_with_shifts(schedule_id)
        return schedule
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@schedule_router.post("/", response_model=ScheduleModel)
def create_schedule(schedule: ScheduleCreate):
    try:
        schedule = schedule_service.create_schedule(
            restaurant_id=schedule.restaurant_id, week_start=schedule.week_start
        )
        return schedule
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@schedule_router.post("/generate")
def generate_schedule(request: GenerateScheduleRequest):
    try:
        schedule = schedule_generator.generate_schedule(
            restaurant_id=request.restaurant_id, week_start=request.week_start
        )
        return schedule
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate schedule: {str(e)}",
        )
