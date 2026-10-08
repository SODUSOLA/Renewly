"""Logging setup: one place decides the format, and every line carries a request id."""
import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

# The id of the request being handled (None outside a request, e.g. in Celery).
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes every LogRecord has; anything else was passed via `extra=` and is
# included as a structured field in JSON logs.
_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "request_id",
}


# class for JSON log lines
class JsonFormatter(logging.Formatter):
    """Formats each record as a single JSON object (easy to search in log tools)."""

    # func to turn a record into a JSON line
    def format(self, record: logging.LogRecord) -> str:
        """Return the record as JSON: time, level, logger, message, request id, extras."""
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        payload.update(
            {k: v for k, v in record.__dict__.items() if k not in _STANDARD_ATTRS}
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


# class for adding the request id to text logs
class RequestIdFilter(logging.Filter):
    """Copies the current request id onto each record for the text format."""

    # func to attach the id
    def filter(self, record: logging.LogRecord) -> bool:
        """Always keeps the record; sets `record.request_id` ('-' when none)."""
        record.request_id = request_id_var.get() or "-"
        return True


# func to configure the root logger
def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    """Send all logs to stderr in the chosen format ("json" or "text").

    Safe to call more than once: it replaces only the handler it installed
    before. Uvicorn's own access log is silenced because the request
    middleware logs every request itself, with its id and duration.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "_app_handler", False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stderr)
    handler._app_handler = True  # type: ignore[attr-defined]
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        JsonFormatter()
        if fmt == "json"
        else logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    root.addHandler(handler)
    root.setLevel(level.upper())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
