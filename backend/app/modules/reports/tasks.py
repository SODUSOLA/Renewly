"""Celery tasks for reports."""
import logging
from dataclasses import asdict
from datetime import UTC, datetime

import app.models_registry  # noqa: F401  (make sure every model is registered in a worker)
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.modules.reports.periodic import run_semiannual_reports

logger = logging.getLogger(__name__)


# func to send any six-monthly reports that are due (scheduled hourly by Celery Beat)
@celery_app.task(name="reports.send_semiannual_reports")
def send_semiannual_reports() -> dict[str, int]:
    """Send due six-monthly reports and return the counts. Does almost nothing outside report season."""
    with SessionLocal() as db:
        summary = run_semiannual_reports(db, now=datetime.now(UTC))
    logger.info("Six-monthly report run finished: %s", summary)
    return asdict(summary)
