"""The six-monthly spending report email.

When: in the first week of January (covering July to December) and of July (covering January
to June), from 08:00 in each user's own timezone. A week-long window means a day of downtime
does not cost anyone their report; the claim record below stops it being sent twice.

Who: active users who have not turned report emails off. A user with no renewals in the period
and nothing expiring in the next six months gets nothing (that period is recorded as skipped).

Exactly once: before sending, a row in `email_dispatch` for (user, "cost_report", period) is
claimed with one atomic INSERT ... ON CONFLICT. A `sent` or `skipped` row is never claimed
again; a `failed` row (or a `pending` row left by a crashed worker) can be retried.
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

from app.common.enums import ReminderStatus
from app.modules.auth.models import User
from app.modules.notifications.email import EmailMessage, send_email
from app.modules.notifications.models import EmailDispatch
from app.modules.notifications.service import build_cost_report_email
from app.modules.reminders.service import PENDING_TIMEOUT
from app.modules.reports.service import build_period_summary, upcoming_expiries

logger = logging.getLogger(__name__)

KIND = "cost_report"
REPORT_HOUR = 8
# The report can go out on any of the first this-many days of January/July (catch-up window).
WINDOW_DAYS = 7

SendFunction = Callable[[EmailMessage], None]


# class for the outcome of one job run
@dataclass
class ReportRunSummary:
    """Reports sent, failed, skipped as already handled, and skipped because there was nothing to say."""

    sent: int = 0
    failed: int = 0
    skipped: int = 0
    empty: int = 0


# func to decide which half-year a local date should report on
def report_period(local_date: date) -> tuple[str, date, date] | None:
    """Return `(period_key, first_day, last_day)` to report on, or None if it is not report season.

    Jan 1-7 reports on the previous year's July-December ("2025-H2"); Jul 1-7 on that year's
    January-June ("2026-H1").
    """
    if local_date.day > WINDOW_DAYS:
        return None
    if local_date.month == 1:
        year = local_date.year - 1
        return f"{year}-H2", date(year, 7, 1), date(year, 12, 31)
    if local_date.month == 7:
        year = local_date.year
        return f"{year}-H1", date(year, 1, 1), date(year, 6, 30)
    return None


# func to claim the right to send one user's report for a period
def claim_dispatch(db: Session, user_id: uuid.UUID, period: str, now: datetime) -> uuid.UUID | None:
    """Try to claim; return the dispatch id, or None if it was already sent/skipped/claimed.

    One atomic INSERT ... ON CONFLICT DO UPDATE: a new (user, kind, period) is inserted as pending;
    an existing row is taken over only if it `failed` or is a stale `pending`.
    """
    statement = pg_insert(EmailDispatch).values(
        user_id=user_id, kind=KIND, period=period, status=ReminderStatus.PENDING, sent_at=now
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_email_dispatch_dedup",
        set_={"status": ReminderStatus.PENDING, "sent_at": now, "error": None},
        where=or_(
            EmailDispatch.status == ReminderStatus.FAILED,
            and_(EmailDispatch.status == ReminderStatus.PENDING, EmailDispatch.sent_at < now - PENDING_TIMEOUT),
        ),
    ).returning(EmailDispatch.id)
    dispatch_id = db.execute(statement).scalar_one_or_none()
    db.commit()
    return dispatch_id


# func to record how a claimed dispatch ended
def _finish(db: Session, dispatch_id: uuid.UUID, status: ReminderStatus, now: datetime, error: str | None = None) -> None:
    """Mark the claimed row sent, failed or skipped, and commit."""
    db.execute(update(EmailDispatch).where(EmailDispatch.id == dispatch_id).values(status=status, sent_at=now, error=error))
    db.commit()


# func to cheaply rule out most of the year
def _near_report_season(now: datetime) -> bool:
    """True if any timezone could be inside a report window right now (UTC date +/- 1 day)."""
    return any(report_period(now.date() + timedelta(days=d)) for d in (-1, 0, 1))


# func to run the report job once
def run_semiannual_reports(db: Session, now: datetime, send: SendFunction = send_email) -> ReportRunSummary:
    """Send every six-monthly report that is due at `now` and has not been handled yet.

    Safe to run hourly: outside the first week of January/July it returns immediately, and inside
    it each user is claimed at most once per period. One failure never stops the others.
    """
    summary = ReportRunSummary()
    if not _near_report_season(now):
        return summary

    candidate_periods = {p[0] for d in (-1, 0, 1) if (p := report_period(now.date() + timedelta(days=d)))}
    done = set(
        db.scalars(
            select(EmailDispatch.user_id).where(
                EmailDispatch.kind == KIND,
                EmailDispatch.period.in_(candidate_periods),
                EmailDispatch.status.in_([ReminderStatus.SENT, ReminderStatus.SKIPPED]),
            )
        )
    )
    users = db.scalars(select(User).where(User.is_active.is_(True), User.report_emails.is_(True)).order_by(User.created_at))
    for user in users:
        if user.id in done:
            continue
        local = now.astimezone(ZoneInfo(user.timezone))
        period = report_period(local.date())
        if period is None or local.hour < REPORT_HOUR:
            continue
        key, start, end = period
        dispatch_id = claim_dispatch(db, user.id, key, now)
        if dispatch_id is None:
            summary.skipped += 1
            continue
        try:
            report = build_period_summary(db, user, start, end)
            upcoming = upcoming_expiries(db, user, local.date())
            if report.renewals == 0 and not upcoming:
                _finish(db, dispatch_id, ReminderStatus.SKIPPED, now)
                summary.empty += 1
                continue
            send(build_cost_report_email(user.email, user.full_name, report, upcoming, idempotency_key=f"report-{dispatch_id}"))
        except Exception as error:  # noqa: BLE001 - any failure must be recorded
            logger.warning("Six-monthly report for user %s failed: %s", user.id, error)
            db.rollback()
            _finish(db, dispatch_id, ReminderStatus.FAILED, now, str(error)[:1000])
            summary.failed += 1
        else:
            _finish(db, dispatch_id, ReminderStatus.SENT, now)
            summary.sent += 1
    return summary
