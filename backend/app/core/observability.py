"""Error tracking with Sentry (optional: does nothing unless SENTRY_DSN is set)."""
import logging

import sentry_sdk

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# func to start Sentry when configured
def init_sentry() -> bool:
    """Initialise Sentry if SENTRY_DSN is set; return whether it was enabled.

    Privacy: personal data and request bodies are never sent (bodies can hold
    passwords and reset tokens). Error-level log lines, including the API's
    "unhandled_exception", become Sentry events through the logging integration.
    """
    settings = get_settings()
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.app_env,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
    )
    logger.info("Sentry error tracking enabled")
    return True
