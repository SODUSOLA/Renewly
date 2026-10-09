"""Celery tasks for the auth module."""
import logging

import app.models_registry  # noqa: F401  (make sure every model is registered in a worker)
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.modules.auth.service import purge_expired_refresh_tokens

logger = logging.getLogger(__name__)


# func to delete expired refresh tokens (scheduled daily by Celery Beat)
@celery_app.task(name="auth.purge_expired_refresh_tokens")
def purge_expired_refresh_tokens_task() -> int:
    """Delete refresh tokens that expired over a day ago and return how many were removed."""
    with SessionLocal() as db:
        removed = purge_expired_refresh_tokens(db)
    logger.info("Purged %s expired refresh tokens", removed)
    return removed
