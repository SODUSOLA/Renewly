"""Request middleware: request ids, request logging and the last-resort 500 handler."""
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request

from app.core.errors import error_response
from app.core.logging import request_id_var

logger = logging.getLogger("app.request")

# Only accept a client-supplied id that is short and boring, so it is safe to log.
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


# func to install the middleware
def register_middleware(app: FastAPI) -> None:
    """Attach the request-context middleware to the app."""

    # func to wrap every request
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        """Give the request an id, time it, log it, and turn crashes into clean 500s.

        The id comes from the caller's `X-Request-ID` header when it is valid
        (so it can be traced across services), otherwise a new one is made. It
        is returned in the `X-Request-ID` response header and on every log line.
        """
        supplied = request.headers.get("x-request-id", "")
        request_id = supplied if _VALID_REQUEST_ID.match(supplied) else uuid.uuid4().hex
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:  # noqa: BLE001 - last resort: never leak internals
                logger.exception("unhandled_exception", extra={"path": request.url.path})
                response = error_response(500, "Internal server error", code="internal_error")
            response.headers["X-Request-ID"] = request_id
            level = logging.DEBUG if request.url.path.startswith("/health") else logging.INFO
            logger.log(
                level,
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)
