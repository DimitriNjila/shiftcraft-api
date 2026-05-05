import logging

from fastapi import FastAPI, APIRouter, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from .routes import employee_router, schedule_router, shift_router, shift_template_router
from .routes.ai_router import ai_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


app = FastAPI(
    title="Shiftcraft API",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    redirect_slashes=True,
)

# CORS - Allow frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Local development
        "https://shiftcraft-6apf.vercel.app",  # Production frontend
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Log every 422 with the full breakdown of which fields failed and why.
    FastAPI's default handler returns the right response but logs nothing,
    making 422s invisible until now.
    """
    errors = exc.errors()
    logger.warning(
        "422 Unprocessable Entity | %s %s | %d error(s)",
        request.method,
        request.url.path,
        len(errors),
    )
    for err in errors:
        location = " -> ".join(str(loc) for loc in err.get("loc", []))
        logger.warning("  field: %s | type: %s | msg: %s", location, err.get("type"), err.get("msg"))
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors},
    )


app.include_router(employee_router.employee_router)
app.include_router(schedule_router.schedule_router)
app.include_router(shift_router.shifts_router)
app.include_router(shift_template_router.shift_template_router)
app.include_router(ai_router)


@app.get("/")
async def read_root():
    return {"Hello": "World"}
