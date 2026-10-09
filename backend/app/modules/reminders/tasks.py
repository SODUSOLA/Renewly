"""Celery tasks for reminders."""
import logging
from dataclasses import asdict
from datetime import UTC, datetime

import app.models_registry  # noqa: F401  (make sure every model is registered in a worker)
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.modules.reminders.service import run_due_reminders

logger = logging.getLogger(__name__)


# func to run the reminder job (scheduled hourly by Celery Beat)
@celery_app.task(name="reminders.send_due_reminders")
def send_due_reminders() -> dict[str, int]:
    """Send all due reminders now and return the counts (sent / failed / skipped)."""
    with SessionLocal() as db:
        summary = run_due_reminders(db, now=datetime.now(UTC))
    logger.info("Reminder run finished: %s", summary)
    return asdict(summary)
