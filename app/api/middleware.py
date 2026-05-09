import json
import logging
import time
import traceback
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class JsonFormatter(logging.Formatter):
    """
    Emit every log record as a single-line JSON object.
    Preserves all standard LogRecord fields plus any extras passed via extra={}.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Carry through any extra fields attached by the caller
        _skip = {
            "args", "created", "exc_info", "exc_text", "filename", "funcName",
            "levelname", "levelno", "lineno", "message", "module", "msecs",
            "msg", "name", "pathname", "process", "processName", "relativeCreated",
            "stack_info", "thread", "threadName",
        }
        for key, value in record.__dict__.items():
            if key not in _skip:
                payload[key] = value

        if record.exc_info:
            payload["stack_trace"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_json_logging() -> None:
    """
    Replace the root logger's handlers with a single JSON-emitting StreamHandler.
    Call this once at application startup before any loggers are created.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    # Suppress noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Per-request middleware that:
    - Generates a unique request_id (UUID4)
    - Attaches it to request.state so route handlers can read it
    - Returns it in the X-Request-ID response header
    - Logs incoming requests and outgoing responses as structured JSON
    - Logs unhandled exceptions with full stack trace before re-raising
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid4())
        request.state.request_id = request_id

        client_ip = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )

        logger.info(
            "Request started: %s %s",
            request.method,
            request.url.path,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": client_ip,
            },
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error(
                "Unhandled exception: %s %s",
                request.method,
                request.url.path,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": client_ip,
                    "duration_ms": duration_ms,
                    "error_type": type(exc).__name__,
                    "stack_trace": traceback.format_exc(),
                },
                exc_info=True,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        level = logging.WARNING if response.status_code >= 400 else logging.INFO
        logger.log(
            level,
            "Request completed: %s %s → %d (%.2fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        response.headers["X-Request-ID"] = request_id
        return response
