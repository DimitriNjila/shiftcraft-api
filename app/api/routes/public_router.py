import logging

from fastapi import APIRouter, HTTPException, status

from ...models.schedule_model import PublicScheduleResponse
from ...services.schedule_service import schedule_service

logger = logging.getLogger(__name__)

# Deliberately no auth dependency — this router serves employees viewing
# their schedule via a share link, without a Supabase account.
#
# NOTE: unauthenticated + publicly reachable given a valid token. Should sit
# behind rate limiting (e.g. per-IP) at the reverse proxy / API gateway layer
# before going to production — not implemented here.
public_router = APIRouter(
    prefix="/api/v1/public",
    tags=["public"],
)


@public_router.get("/schedules/{token}", response_model=PublicScheduleResponse)
def get_public_schedule(token: str):
    """Get a read-only schedule via its public share token. No auth required."""
    try:
        result = schedule_service.get_schedule_by_share_token(token)
    except Exception as e:
        logger.exception("GET /public/schedules/%s failed: %s", token, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred. Please try again later.",
        )

    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return result
