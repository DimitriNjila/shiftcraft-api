from ...models.schedule_model import ScheduleModel, ScheduleCreate
from datetime import date
from ...services.schedule_service import (
    schedule_service,
    ScheduleAlreadyExistsError,
    ScheduleNotFoundError,
)
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
