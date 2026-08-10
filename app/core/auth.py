import logging

import sentry_sdk
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional
from uuid import UUID
from .db import get_supabase
from ..services.schedule_service import schedule_service

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
):
    """
    FastAPI dependency that validates a Supabase JWT from the Authorization header.

    Usage:
        @router.get("/", dependencies=[Depends(get_current_user)])   # router-level
        def get_something(current_user = Depends(get_current_user))  # endpoint-level (with user object)

    Raises:
        401 if the header is missing, the token is invalid, or the token is expired.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        response = get_supabase().auth.get_user(token)

        if not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = response.user
        # Set Sentry user context so every error on this request is linked to
        # the authenticated user — no PII beyond the opaque user ID.
        sentry_sdk.set_user({"id": user.id})
        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Token validation failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_or_share_token(
    schedule_id: UUID,
    token: Optional[str] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
):
    """
    FastAPI dependency for schedule sub-resources (e.g. iCal export) that must
    work both for an authenticated manager and for an employee following a
    share link with no account of their own.

    Tries JWT auth first (same validation as get_current_user); falls back to
    checking `token` (query param) against the given schedule's active,
    unexpired share link.

    Usage:
        @router.get("/{schedule_id}/export/ical")
        def export(schedule_id: UUID, _=Depends(get_current_user_or_share_token)):

    Raises:
        401 if neither a valid JWT nor a valid share token is presented.
    """
    if credentials:
        return get_current_user(credentials)

    if token and schedule_service.is_valid_share_token(schedule_id, token):
        return None

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required: provide a Bearer token or a valid ?token= share link",
        headers={"WWW-Authenticate": "Bearer"},
    )
