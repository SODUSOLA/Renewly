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
import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.common.enums import ReminderChannel, ReminderStatus, ReminderStyle
from app.core.config import get_settings
from app.modules.auth.models import User
from app.modules.documents.models import Document
from app.modules.notifications.email import EmailMessage, send_email
from app.modules.notifications.rendering import DigestItem, render_expiry_digest, render_expiry_reminder
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


# func to record how a send attempt ended for several reminders at once
def _finish_many(
    db: Session, log_ids: list[uuid.UUID], status: ReminderStatus, now: datetime, error: str | None
) -> None:
    """Mark all the given log rows sent or failed in one statement and commit."""
    db.execute(
        update(ReminderLog)
        .where(ReminderLog.id.in_(log_ids))
        .values(status=status, sent_at=now, error=error)
    )
    db.commit()


# func to build the key that stops a digest being delivered twice
def digest_idempotency_key(log_ids: list[uuid.UUID]) -> str:
    """A key that depends only on WHICH reminders the digest covers, not their order.

    If a send is retried (a timeout after the provider already accepted it), the same
    reminders produce the same key, so the provider drops the duplicate.
    """
    joined = ",".join(sorted(str(i) for i in log_ids))
    return "digest-" + hashlib.sha256(joined.encode()).hexdigest()[:32]


# func to build one email covering several claimed reminders
def build_digest_message(user: User, claimed: list[tuple[DueReminder, uuid.UUID]]) -> EmailMessage:
    """Render the digest for `user`, most urgent document first.

    Ties on urgency are ordered by title so the email is stable between runs.
    """
    ordered = sorted(claimed, key=lambda c: (c[0].days_left, c[0].document.title.lower()))
    items = []
    for due, _ in ordered:
        vehicle = due.document.vehicle
        items.append(
            DigestItem(
                title=due.document.title,
                doc_type=due.document.type,
                custom_type_label=due.document.custom_type_label,
                expiry_date=due.document.expiry_date,
                days_left=due.days_left,
                vehicle_label=f"{vehicle.nickname} ({vehicle.plate_number})" if vehicle else None,
            )
        )
    frontend = get_settings().frontend_url.rstrip("/")
    subject, html, text = render_expiry_digest(
        full_name=user.full_name, items=items, settings_url=f"{frontend}/settings" if frontend else None
    )
    return EmailMessage(
        to=user.email,
        subject=subject,
        html=html,
        text=text,
        idempotency_key=digest_idempotency_key([log_id for _, log_id in claimed]),
    )


# func to send one email per due reminder
def _send_each(
    db: Session, dues: list[DueReminder], now: datetime, send: SendFunction, summary: ReminderRunSummary
) -> None:
    """Claim, send and record each reminder on its own; one failure never stops the rest."""
    for due in dues:
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


# func to send one combined email for all of a user's due reminders
def _send_digest(
    db: Session, user: User, dues: list[DueReminder], now: datetime, send: SendFunction, summary: ReminderRunSummary
) -> None:
    """Claim every due reminder, send ONE email covering the ones we won, record them together.

    Reminders already sent or claimed elsewhere are left out (and counted as skipped), so
    switching styles mid-day or a retry never repeats a reminder. If the single send fails,
    every reminder in it is marked failed and retried on the next run.
    """
    claimed: list[tuple[DueReminder, uuid.UUID]] = []
    for due in dues:
        log_id = claim_reminder(db, due, now)
        if log_id is None:
            summary.skipped += 1
        else:
            claimed.append((due, log_id))
    if not claimed:
        return
    log_ids = [log_id for _, log_id in claimed]
    try:
        send(build_digest_message(user, claimed))
    except Exception as error:  # noqa: BLE001 - any failure must be recorded
        logger.warning("Digest for user %s failed: %s", user.id, error)
        _finish_many(db, log_ids, ReminderStatus.FAILED, now, str(error)[:1000])
        summary.failed += len(claimed)
    else:
        _finish_many(db, log_ids, ReminderStatus.SENT, now, None)
        summary.sent += len(claimed)


# func to run the whole reminder job once
def run_due_reminders(
    db: Session, now: datetime, send: SendFunction = send_email
) -> ReminderRunSummary:
    """Send every reminder that is due at `now` and has not been sent yet.

    Safe to run as often as you like (the Beat schedule runs it hourly): the
    claim step guarantees each reminder is delivered once, and failed sends are
    retried on later runs while the reminder is still due. Reminders are grouped by
    user: users on the "digest" style get one email for the group, everyone else gets
    one email per reminder. A failure for one user never stops the others. `send` is
    injectable so tests can use a fake.
    """
    summary = ReminderRunSummary()
    by_user: dict[uuid.UUID, list[DueReminder]] = {}
    for due in find_due_reminders(db, now):
        by_user.setdefault(due.user.id, []).append(due)
    for dues in by_user.values():
        user = dues[0].user
        if user.reminder_style == ReminderStyle.DIGEST:
            _send_digest(db, user, dues, now, send, summary)
        else:
            _send_each(db, dues, now, send, summary)
    return summary
