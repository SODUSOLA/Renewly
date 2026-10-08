"""Celery application and the Beat schedule.

Run locally (worker and scheduler in one process):
    celery -A app.core.celery_app worker --beat --loglevel=info
In production run `worker` and `beat` as separate processes (exactly one beat).
"""
from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.observability import init_sentry

init_sentry()

celery_app = Celery(
    "expiry_tracker",
    broker=get_settings().redis_url,
    include=["app.modules.reminders.tasks"],
)

celery_app.conf.update(
    worker_hijack_root_logger=False,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        # Hourly so every timezone gets its 08:00 reminders; the dedup key in
        # reminder_log makes repeated runs harmless.
        "send-due-reminders-hourly": {
            "task": "reminders.send_due_reminders",
            "schedule": crontab(minute=5),
        }
    },
)


# func to use our logging format inside Celery workers
@setup_logging.connect
def _configure_worker_logging(**kwargs) -> None:
    """Replace Celery's own logging setup so workers log like the API does."""
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
