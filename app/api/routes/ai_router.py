import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...core.auth import get_current_user
from ...core.db import get_supabase
from ...services.ai_service import AIService, AIServiceUnavailableError
from ...services.schedule_service import ScheduleService, ScheduleNotFoundError

logger = logging.getLogger(__name__)

ai_router = APIRouter(
    prefix="/api/v1",
    tags=["ai"],
    dependencies=[Depends(get_current_user)],
)


class ScheduleAnalysisResponse(BaseModel):
    schedule_id: str
    week_start: str
    analysis: str


@ai_router.post(
    "/schedules/{schedule_id}/analyze",
    response_model=ScheduleAnalysisResponse,
)
def analyze_schedule(schedule_id: UUID):
    """
    Run an AI-powered analysis of a weekly schedule.

    Returns a plain-text report covering fairness, coverage, workload,
    patterns, and concrete recommendations.
    """
    schedule_service = ScheduleService(get_supabase())

    try:
        schedule_with_shifts = schedule_service.get_schedule_with_shifts(schedule_id)
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found",
        )

    shifts = schedule_with_shifts.get("shifts", [])

    # Flatten employee name/role from the nested join onto each shift
    flat_shifts = []
    for shift in shifts:
        employee = shift.get("employee") or {}
        flat_shifts.append({
            **shift,
            "employee_name": employee.get("name"),
            "role": employee.get("role"),
        })

    try:
        ai = AIService()
    except AIServiceUnavailableError as e:
        logger.error("AI service unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    try:
        analysis = ai.analyze_schedule(schedule_with_shifts, flat_shifts)
    except Exception as e:
        logger.error("AI analysis failed for schedule_id=%s: %s", schedule_id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI analysis failed. Please try again later.",
        )

    return ScheduleAnalysisResponse(
        schedule_id=str(schedule_with_shifts["id"]),
        week_start=schedule_with_shifts["week_start"],
        analysis=analysis,
    )
