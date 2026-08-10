import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from uuid import UUID

from ...core.auth import get_current_user_or_share_token
from ...services.export_service import export_service
from ...services.schedule_service import ScheduleNotFoundError

logger = logging.getLogger(__name__)

# Separate from schedule_router (which requires a JWT for every route) because
# this endpoint must also work for an employee following a share link with no
# account — see get_current_user_or_share_token.
schedule_export_router = APIRouter(
    prefix="/api/v1/schedules",
    tags=["schedules"],
    responses={404: {"description": "Not found"}},
)


@schedule_export_router.get(
    "/{schedule_id}/export/ical",
    dependencies=[Depends(get_current_user_or_share_token)],
)
def export_schedule_ical(schedule_id: UUID, token: str | None = None):
    """
    Download a schedule as an .ics file.

    Accepts either a normal Authorization: Bearer JWT, or a `?token=` query
    param matching this schedule's active share link.
    """
    try:
        ical_content = export_service.generate_ical(schedule_id)
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Schedule {schedule_id} not found",
        )
    except Exception as e:
        logger.exception("GET /schedules/%s/export/ical failed: %s", schedule_id, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        )

    return Response(
        content=ical_content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="schedule_{schedule_id}.ics"'
        },
    )
