import logging

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from .middleware import RequestLoggingMiddleware, configure_json_logging
from .routes import employee_router, schedule_router, shift_router, shift_template_router
from .routes.ai_router import ai_router
from app.core.config import settings

# ── Logging ───────────────────────────────────────────────────────────────────
# Must run before any logger is created so all loggers inherit the JSON handler.
configure_json_logging()
logger = logging.getLogger(__name__)

# ── Sentry ────────────────────────────────────────────────────────────────────
if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
        environment=settings.ENVIRONMENT,
        traces_sample_rate=0.1,
        profiles_sample_rate=0.1,
        send_default_pii=False,
    )
    logger.info("Sentry initialised for environment=%s", settings.ENVIRONMENT)
else:
    logger.info("SENTRY_DSN not set — Sentry disabled")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Shiftcraft API",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    redirect_slashes=True,
)

# Middleware order matters — outermost wrapper runs first on the way in and
# last on the way out. CORS must be outermost so preflight responses are sent
# before any auth/logging work happens.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[allow_origins=settings.cors_origins_list],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

# ── Exception handlers ────────────────────────────────────────────────────────

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Log every 422 with the full field-level breakdown.
    FastAPI's default handler returns the right response but never logs, so
    validation failures were invisible. Now each failing field is logged with
    its location, error type, and human-readable message.
    """
    request_id = getattr(request.state, "request_id", None)
    errors = exc.errors()

    logger.warning(
        "422 Unprocessable Entity | %s %s | %d error(s)",
        request.method,
        request.url.path,
        len(errors),
        extra={"request_id": request_id},
    )
    for err in errors:
        location = " -> ".join(str(loc) for loc in err.get("loc", []))
        logger.warning(
            "  field: %s | type: %s | msg: %s",
            location,
            err.get("type"),
            err.get("msg"),
            extra={"request_id": request_id},
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors},
        headers={"X-Request-ID": request_id} if request_id else {},
    )


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(employee_router.employee_router)
app.include_router(schedule_router.schedule_router)
app.include_router(shift_router.shifts_router)
app.include_router(shift_template_router.shift_template_router)
app.include_router(ai_router)


@app.on_event("startup")
async def startup_event():
    """
    Warm up the Supabase client on startup so the first real request isn't
    slower due to cold-start connection overhead.
    """
    from app.core.db import get_supabase
    get_supabase()
    logger.info("Supabase client initialised")


@app.get("/")
async def read_root():
    return {"Hello": "World"}
