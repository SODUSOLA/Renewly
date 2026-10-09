"""The emails Renewly sends, one function per email.

Each function gathers what its email needs, renders the matching template from
`templates/` (see templating.py) and returns an EmailMessage, or sends it. Wording and
layout live in the templates; this file only decides *what data* goes in. Emails that are
sent in the background never raise: a failure is logged, because the request that
triggered them has already been answered.
"""
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from app.common.enums import DocumentType, document_type_label
from app.core.config import get_settings
from app.modules.notifications.email import EmailMessage, EmailSendError, send_email
from app.modules.notifications.templating import RenderedEmail, render_email

logger = logging.getLogger(__name__)

# How long a password-reset link or token works (kept in step with auth.service.RESET_TOKEN_TTL).
RESET_TTL_MINUTES = 60

_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


# func to send a prepared message without ever raising
def _send_safely(message: EmailMessage) -> None:
    """Send `message`; log (never raise) if the provider fails. For fire-and-forget emails."""
    try:
        send_email(message)
    except EmailSendError:
        logger.exception("Could not send '%s' to %s", message.subject, message.to)


# func to wrap a rendered email for the sender
def _message(to_email: str, rendered: RenderedEmail, *, idempotency_key: str | None = None) -> EmailMessage:
    """Combine a recipient with a rendered subject/html/text."""
    return EmailMessage(to=to_email, subject=rendered.subject, html=rendered.html, text=rendered.text, idempotency_key=idempotency_key)


# ------------------------------------------------------------------ welcome
# func to build the welcome email
def build_welcome_email(to_email: str, full_name: str, timezone: str) -> EmailMessage:
    """The email a new user gets right after signing up (template: welcome)."""
    return _message(to_email, render_email("welcome", full_name=full_name, timezone=timezone))


# func to send the welcome email in the background
def send_welcome_email(to_email: str, full_name: str, timezone: str) -> None:
    """Send the welcome email. Never raises."""
    _send_safely(build_welcome_email(to_email, full_name, timezone))


# ----------------------------------------------------------- password emails
# func to build the password-reset email
def build_password_reset_email(to_email: str, raw_token: str) -> EmailMessage:
    """The reset email: a link to the web app when FRONTEND_URL is set, else the bare token."""
    frontend = get_settings().frontend_url.rstrip("/")
    reset_url = f"{frontend}/reset-password?{urlencode({'token': raw_token})}" if frontend else None
    return _message(
        to_email,
        render_email("password_reset", reset_url=reset_url, token=raw_token, ttl_minutes=RESET_TTL_MINUTES),
    )


# func to send the password-reset email
def send_password_reset_email(to_email: str, raw_token: str) -> None:
    """Email the reset link/token. Never raises: the endpoint answers the same either way."""
    _send_safely(build_password_reset_email(to_email, raw_token))


# func to build the "your password changed" security email
def build_password_changed_email(to_email: str, full_name: str) -> EmailMessage:
    """Tell the owner their password was just changed (template: password_changed)."""
    return _message(to_email, render_email("password_changed", full_name=full_name))


# func to send the "your password changed" email
def send_password_changed_email(to_email: str, full_name: str) -> None:
    """Send the security notice. Never raises."""
    _send_safely(build_password_changed_email(to_email, full_name))


# ---------------------------------------------------------------- reminders
# func to render one document reminder
def render_expiry_reminder(
    *,
    full_name: str,
    title: str,
    doc_type: DocumentType,
    custom_type_label: str | None,
    expiry_date: date,
    days_left: int,
    vehicle_label: str | None,
    document_id: str | None = None,
) -> tuple[str, str, str]:
    """Return `(subject, html, text)` for a single document reminder (template: expiry_reminder)."""
    frontend = get_settings().frontend_url.rstrip("/")
    document_url = f"{frontend}/documents/{document_id}" if frontend and document_id else (f"{frontend}/documents" if frontend else None)
    rendered = render_email(
        "expiry_reminder",
        full_name=full_name,
        title=title,
        kind=document_type_label(doc_type, custom_type_label),
        vehicle_label=vehicle_label,
        expiry_date=expiry_date,
        days_left=days_left,
        document_url=document_url,
    )
    return rendered.subject, rendered.html, rendered.text


# class for one line of a digest email
@dataclass(frozen=True)
class DigestItem:
    """One document in a digest: what it is and how soon it expires."""

    title: str
    doc_type: DocumentType
    custom_type_label: str | None
    expiry_date: date
    days_left: int
    vehicle_label: str | None


# func to render a digest of several documents
def render_expiry_digest(*, full_name: str, items: list[DigestItem], settings_url: str | None = None) -> tuple[str, str, str]:
    """Return `(subject, html, text)` for a digest (template: expiry_digest), items already ordered.

    `settings_url` is accepted for callers that know it; the template otherwise derives it
    from FRONTEND_URL like every other email.
    """
    rendered = render_email(
        "expiry_digest",
        full_name=full_name,
        items=[
            {
                "title": i.title,
                "kind": document_type_label(i.doc_type, i.custom_type_label),
                "vehicle_label": i.vehicle_label,
                "expiry_date": i.expiry_date,
                "days_left": i.days_left,
            }
            for i in items
        ],
        **({"settings_url": settings_url} if settings_url else {}),
    )
    return rendered.subject, rendered.html, rendered.text


# ---------------------------------------------------------- six-month report
# func to name a half-year in words
def period_label(start: date, end: date) -> str:
    """date(2026,1,1), date(2026,6,30) -> 'January – June 2026' (spans two years if needed)."""
    first, last = _MONTH_NAMES[start.month - 1], _MONTH_NAMES[end.month - 1]
    if start.year == end.year:
        return f"{first} – {last} {end.year}"
    return f"{first} {start.year} – {last} {end.year}"


# func to build the six-monthly report email
def build_cost_report_email(to_email: str, full_name: str, summary, upcoming: list, *, idempotency_key: str | None = None) -> EmailMessage:
    """The half-yearly spending report (template: cost_report).

    `summary` is a reports.service.PeriodSummary and `upcoming` a list of UpcomingExpiry; they are
    unpacked here so the template only sees plain values.
    """
    frontend = get_settings().frontend_url.rstrip("/")
    change_pct = None
    if summary.previous_total > 0:
        change_pct = round(((summary.total - summary.previous_total) / summary.previous_total) * 100)
    estimates = [u.estimated_cost for u in upcoming if u.estimated_cost is not None]
    rendered = render_email(
        "cost_report",
        full_name=full_name,
        period_label=period_label(summary.start, summary.end),
        total=summary.total,
        previous_total=summary.previous_total,
        change_pct=change_pct,
        renewals=summary.renewals,
        missing_cost_count=summary.missing_cost_count,
        by_type=summary.by_type,
        by_vehicle=summary.by_vehicle,
        upcoming=[
            {
                "title": u.title,
                "kind": document_type_label(u.doc_type, u.custom_type_label),
                "vehicle_label": u.vehicle_label,
                "expiry_date": u.expiry_date,
                "days_left": u.days_left,
                "estimated_cost": u.estimated_cost,
            }
            for u in upcoming
        ],
        estimate_total=sum(estimates, Decimal("0")) if estimates else None,
        estimate_count=len(estimates),
        reports_url=f"{frontend}/reports" if frontend else None,
    )
    return _message(to_email, rendered, idempotency_key=idempotency_key)
