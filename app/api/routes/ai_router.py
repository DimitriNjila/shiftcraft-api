import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ...core.auth import get_current_user
from ...core.db import get_supabase
from ...services.ai_service import AIServiceUnavailableError, get_ai_service
from ...services.employee_service import EmployeeService
from ...services.schedule_service import ScheduleService, ScheduleNotFoundError

logger = logging.getLogger(__name__)

ai_router = APIRouter(
    prefix="/api/v1",
    tags=["ai"],
    dependencies=[Depends(get_current_user)],
)


class AnalysisDimension(BaseModel):
    score: Literal["good", "fair", "poor"]
    details: str


class ScheduleAnalysisResponse(BaseModel):
    schedule_id: str
    week_start: str
    summary: str
    fairness: AnalysisDimension
    coverage: AnalysisDimension
    workload: AnalysisDimension
    patterns: list[str]
    recommendations: list[str]


@ai_router.post(
    "/schedules/{schedule_id}/analyze",
    response_model=ScheduleAnalysisResponse,
)
def analyze_schedule(schedule_id: UUID):
    """
    Run an AI-powered analysis of a weekly schedule.

    Returns a structured report covering fairness, coverage, workload,
    patterns, and concrete recommendations — each with a good/fair/poor score.
    """
    supabase = get_supabase()
    schedule_service = ScheduleService(supabase)
    employee_service = EmployeeService(supabase)

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

    # Fetch full active roster so the model can flag employees with zero shifts
    restaurant_id = schedule_with_shifts.get("restaurant_id")
    all_employees = employee_service.get_employees(
        restaurant_id=str(restaurant_id) if restaurant_id else None,
        is_active=True,
    )

    try:
        ai = get_ai_service()
    except AIServiceUnavailableError as e:
        logger.error("AI service unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )

    try:
        result = ai.analyze_schedule(schedule_with_shifts, flat_shifts, all_employees)
    except ValueError as e:
        logger.error("AI returned unexpected response for schedule_id=%s: %s", schedule_id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI analysis returned an unexpected response. Please try again.",
        )
    except Exception as e:
        logger.error("AI analysis failed for schedule_id=%s: %s", schedule_id, e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI analysis failed. Please try again later.",
        )

    return ScheduleAnalysisResponse(
        schedule_id=str(schedule_with_shifts["id"]),
        week_start=schedule_with_shifts["week_start"],
        **result,
    )
