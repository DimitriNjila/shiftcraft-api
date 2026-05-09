import logging

from ...models.schedule_model import (
    GenerateScheduleRequest,
    ScheduleModel,
    ScheduleCreate,
    ScheduleResponse,
)
from datetime import date
from ...services.schedule_service import schedule_service
from ...services.schedule_generator_service import schedule_generator
from ...core.auth import get_current_user
from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID

logger = logging.getLogger(__name__)

schedule_router = APIRouter(
    prefix="/api/v1/schedules",
    tags=["schedules"],
    dependencies=[Depends(get_current_user)],
    responses={404: {"description": "Not found"}},
)


@schedule_router.get("", response_model=list[ScheduleModel])
def get_schedules(
    restaurant_id: UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    try:
        schedules = schedule_service.get_schedules(restaurant_id, start_date, end_date)
        return schedules
    except Exception as e:
        logger.exception("GET /schedules failed: %s", e)
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
        logger.exception("GET /schedules/%s failed: %s", schedule_id, e)
        raise HTTPException(status_code=500, detail=str(e))


@schedule_router.post("", response_model=ScheduleModel)
def create_schedule(schedule: ScheduleCreate):
    try:
        schedule = schedule_service.create_schedule(
            restaurant_id=schedule.restaurant_id, week_start=schedule.week_start
        )
        return schedule
    except Exception as e:
        logger.exception("POST /schedules failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@schedule_router.post("/generate")
def generate_schedule(request: GenerateScheduleRequest):
    logger.info(
        "Generate schedule request: restaurant_id=%s week_start=%s",
        request.restaurant_id,
        request.week_start,
    )
    try:
        schedule = schedule_generator.generate_schedule(
            restaurant_id=request.restaurant_id, week_start=request.week_start
        )
        return schedule
    except ValueError as e:
        logger.warning(
            "Generate schedule rejected (400): restaurant_id=%s week_start=%s reason=%s",
            request.restaurant_id,
            request.week_start,
            e,
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.exception(
            "Generate schedule failed (500): restaurant_id=%s week_start=%s",
            request.restaurant_id,
            request.week_start,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate schedule: {str(e)}",
        )
