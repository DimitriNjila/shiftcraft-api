import logging

import sentry_sdk
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from typing import Optional
from .db import supabase

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
        response = supabase.auth.get_user(token)

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
