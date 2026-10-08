"""One consistent JSON shape for every error the API returns.

    {"detail": "<message, or a list of field errors for 422>",
     "code": "<stable machine-readable code>",
     "request_id": "<id to quote when reporting a problem>"}

`detail` is kept (FastAPI's standard key) so clients and docs keep working.
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)

_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


# func to build an error response
def error_response(
    status_code: int,
    detail: object,
    *,
    code: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Return a JSON error in the standard shape, tagged with the current request id."""
    if code is None:
        code = _CODES.get(status_code, "server_error" if status_code >= 500 else f"http_{status_code}")
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code, "request_id": request_id_var.get()},
        headers=headers,
    )


# func to handle HTTPException (404s, 401s, 409s, 429s...)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Wrap any HTTPException in the standard shape, keeping its headers."""
    return error_response(exc.status_code, exc.detail, headers=exc.headers)


# func to handle request-body / parameter validation errors
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Return 422 with the list of field errors in the standard shape."""
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT, jsonable_encoder(exc.errors())
    )


# func to register the handlers on the app
def register_error_handlers(app: FastAPI) -> None:
    """Install the handlers above. Unexpected exceptions are caught in the middleware."""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
