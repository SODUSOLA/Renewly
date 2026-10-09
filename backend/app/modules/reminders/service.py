"""The reminder engine: work out which reminders are due and send each exactly once.

How "exactly once" works
------------------------
1. A reminder is identified by (document, offset, expiry date, channel).
2. Before sending, we CLAIM it by inserting a `pending` row in `reminder_log`.
   The table's unique key means only one worker can win the claim.
3. We send, then mark the row `sent` or `failed`.
4. A `failed` row can be claimed again on a later run (retry); a `sent` row
   never can. A `pending` row left behind by a crash is claimable again after
   PENDING_TIMEOUT, and the email provider's idempotency key stops a duplicate
   if the first attempt actually went through.
"""
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.common.enums import ReminderChannel, ReminderStatus
from app.modules.auth.models import User
from app.modules.documents.models import Document
from app.modules.notifications.email import EmailMessage, send_email
from app.modules.notifications.rendering import render_expiry_reminder
from app.modules.reminders.models import ReminderLog

logger = logging.getLogger(__name__)

# Reminders go out once the user's local clock reaches this hour.
REMINDER_HOUR = 8
# A pending claim older than this is assumed to belong to a crashed worker.
PENDING_TIMEOUT = timedelta(minutes=15)
# Longest possible reminder offset (see schemas.MAX_OFFSET_DAYS), plus slack for
# the +/-1 day difference between UTC and a user's local date.
_LOOKAHEAD_DAYS = 365 + 2

SendFunction = Callable[[EmailMessage], None]


# class for a reminder that should go out now
@dataclass(frozen=True)
class DueReminder:
    """A document that hits one of its reminder offsets on the user's local today."""

    document: Document
    user: User
    days_left: int


# class for the outcome of one job run
@dataclass
class ReminderRunSummary:
    """Counts for one run: emails sent, sends that failed, reminders skipped as done."""

    sent: int = 0
    failed: int = 0
    skipped: int = 0


# func to find reminders due at a given moment
def find_due_reminders(db: Session, now: datetime) -> list[DueReminder]:
    """Return every reminder due at `now` (a timezone-aware datetime).

    A document is due when, in its owner's timezone, it is at least REMINDER_HOUR
    o'clock and the days left until expiry equal one of its reminder offsets.
    Soft-deleted documents and inactive users are ignored.
    """
    utc_today = now.date()
    candidates = db.execute(
        select(Document, User)
        .join(User, Document.user_id == User.id)
        .where(
            Document.deleted_at.is_(None),
            User.is_active.is_(True),
            Document.expiry_date >= utc_today - timedelta(days=1),
            Document.expiry_date <= utc_today + timedelta(days=_LOOKAHEAD_DAYS),
        )
        .order_by(Document.expiry_date, Document.id)
    )
    due: list[DueReminder] = []
    for document, user in candidates:
        local_now = now.astimezone(ZoneInfo(user.timezone))
        if local_now.hour < REMINDER_HOUR:
            continue
        days_left = (document.expiry_date - local_now.date()).days
        if days_left in document.reminder_offsets:
            due.append(DueReminder(document, user, days_left))
    return due


# func to claim a reminder before sending it
def claim_reminder(db: Session, due: DueReminder, now: datetime) -> uuid.UUID | None:
    """Try to claim the reminder; return its log id, or None if it is not ours.

    One atomic INSERT ... ON CONFLICT: a brand-new reminder is inserted as
    pending; an existing row is taken over only if it `failed` or is a stale
    `pending`. A `sent` (or freshly pending) row yields no row back.
    """
    statement = pg_insert(ReminderLog).values(
        document_id=due.document.id,
        offset_days=due.days_left,
        expiry_date=due.document.expiry_date,
        channel=ReminderChannel.EMAIL,
        status=ReminderStatus.PENDING,
        sent_at=now,
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_reminder_log_dedup",
        set_={"status": ReminderStatus.PENDING, "sent_at": now, "error": None},
        where=or_(
            ReminderLog.status == ReminderStatus.FAILED,
            and_(
                ReminderLog.status == ReminderStatus.PENDING,
                ReminderLog.sent_at < now - PENDING_TIMEOUT,
            ),
        ),
    ).returning(ReminderLog.id)
    log_id = db.execute(statement).scalar_one_or_none()
    db.commit()
    return log_id


# func to record how a send attempt ended
def _finish(
    db: Session, log_id: uuid.UUID, status: ReminderStatus, now: datetime, error: str | None
) -> None:
    """Mark the claimed log row as sent or failed and commit."""
    db.execute(
        update(ReminderLog)
        .where(ReminderLog.id == log_id)
        .values(status=status, sent_at=now, error=error)
    )
    db.commit()


# func to build the email for a due reminder
def build_message(due: DueReminder, log_id: uuid.UUID) -> EmailMessage:
    """Render the reminder email for the document's owner."""
    document = due.document
    vehicle = document.vehicle
    vehicle_label = f"{vehicle.nickname} ({vehicle.plate_number})" if vehicle else None
    subject, html, text = render_expiry_reminder(
        full_name=due.user.full_name,
        title=document.title,
        doc_type=document.type,
        custom_type_label=document.custom_type_label,
        expiry_date=document.expiry_date,
        days_left=due.days_left,
        vehicle_label=vehicle_label,
    )
    return EmailMessage(
        to=due.user.email,
        subject=subject,
        html=html,
        text=text,
        idempotency_key=f"reminder-{log_id}",
    )


# func to run the whole reminder job once
def run_due_reminders(
    db: Session, now: datetime, send: SendFunction = send_email
) -> ReminderRunSummary:
    """Send every reminder that is due at `now` and has not been sent yet.

    Safe to run as often as you like (the Beat schedule runs it hourly): the
    claim step guarantees one email per reminder, and failed sends are retried
    on later runs while the reminder is still due. One failure never stops the
    others. `send` is injectable so tests can use a fake.
    """
    summary = ReminderRunSummary()
    for due in find_due_reminders(db, now):
        log_id = claim_reminder(db, due, now)
        if log_id is None:
            summary.skipped += 1
            continue
        try:
            send(build_message(due, log_id))
        except Exception as error:  # noqa: BLE001 - any failure must be recorded
            logger.warning("Reminder for document %s failed: %s", due.document.id, error)
            _finish(db, log_id, ReminderStatus.FAILED, now, str(error)[:1000])
            summary.failed += 1
        else:
            _finish(db, log_id, ReminderStatus.SENT, now, None)
            summary.sent += 1
    return summary
