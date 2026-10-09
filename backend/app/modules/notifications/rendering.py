"""Builds the subject, HTML and plain-text bodies of reminder emails."""
from dataclasses import dataclass
from datetime import date
from html import escape
from pathlib import Path
from string import Template

from app.common.enums import DocumentType

TEMPLATE_PATH = Path(__file__).parent / "templates" / "expiry_reminder.html"
DIGEST_TEMPLATE_PATH = Path(__file__).parent / "templates" / "expiry_digest.html"

_TYPE_LABELS = {
    DocumentType.DRIVER_LICENSE: "Driver's license",
    DocumentType.INSURANCE: "Insurance",
    DocumentType.VEHICLE_REGISTRATION: "Vehicle registration",
    DocumentType.PERMIT: "Permit",
}


# func to describe days left in words
def describe_days(days_left: int) -> str:
    """Return 'today', 'tomorrow' or 'in N days' for use inside a sentence."""
    if days_left == 0:
        return "today"
    if days_left == 1:
        return "tomorrow"
    return f"in {days_left} days"


# func to render one expiry reminder
def render_expiry_reminder(
    *,
    full_name: str,
    title: str,
    doc_type: DocumentType,
    custom_type_label: str | None,
    expiry_date: date,
    days_left: int,
    vehicle_label: str | None,
) -> tuple[str, str, str]:
    """Return `(subject, html, text)` for a reminder.

    Every user-supplied value is HTML-escaped in the HTML version, so a title
    like `<script>` cannot inject markup into the email.
    """
    when = describe_days(days_left)
    headline = f"{title} expires {when}."
    kind = custom_type_label or _TYPE_LABELS.get(doc_type, doc_type.value)
    expiry = expiry_date.strftime("%A, %d %B %Y")

    vehicle_row = ""
    if vehicle_label:
        vehicle_row = (
            '<tr><td style="padding: 4px 16px 4px 0; color: #52606d;">Vehicle</td>'
            f"<td>{escape(vehicle_label)}</td></tr>"
        )
    html = Template(TEMPLATE_PATH.read_text()).substitute(
        name=escape(full_name),
        headline=escape(headline),
        title=escape(title),
        kind=escape(kind),
        vehicle_row=vehicle_row,
        expiry=escape(expiry),
    )

    lines = [f"Hi {full_name},", "", headline, "", f"Document: {title}", f"Type: {kind}"]
    if vehicle_label:
        lines.append(f"Vehicle: {vehicle_label}")
    lines += [f"Expires on: {expiry}", "", "Mark it as renewed in Expiry Tracker once done."]
    return f"{title} expires {when}", html, "\n".join(lines)


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


# func to colour a row by urgency (the wording carries the meaning too, colour only helps)
def _urgency_colour(days_left: int) -> str:
    """Red for today/tomorrow, amber within a week, calm green otherwise."""
    if days_left <= 1:
        return "#b42318"
    if days_left <= 7:
        return "#b54708"
    return "#067647"


# func to render one email covering several documents
def render_expiry_digest(
    *, full_name: str, items: list[DigestItem], settings_url: str | None
) -> tuple[str, str, str]:
    """Return `(subject, html, text)` for a digest of `items` (already in the order to show).

    One item reads like an ordinary reminder; several share a count headline. Every
    user-supplied value is HTML-escaped in the HTML version. `settings_url`, when given,
    adds a "change how you get reminders" link to the footer.
    """
    count = len(items)
    first = items[0]
    if count == 1:
        subject = f"{first.title} expires {describe_days(first.days_left)}"
        headline = f"{first.title} expires {describe_days(first.days_left)}."
    else:
        subject = f"{count} documents need your attention"
        headline = f"{count} documents need your attention. The most urgent expires {describe_days(first.days_left)}."

    rows = []
    lines = [f"Hi {full_name},", "", headline, ""]
    for item in items:
        kind = item.custom_type_label or _TYPE_LABELS.get(item.doc_type, item.doc_type.value)
        detail = kind + (f" · {item.vehicle_label}" if item.vehicle_label else "")
        when = describe_days(item.days_left)
        on = item.expiry_date.strftime("%A, %d %B %Y")
        rows.append(
            '<tr><td style="padding: 10px 0; border-bottom: 1px solid #e4e7eb;">'
            f"<strong>{escape(item.title)}</strong><br>"
            f'<span style="color: #52606d; font-size: 14px;">{escape(detail)}</span></td>'
            '<td style="padding: 10px 0 10px 16px; border-bottom: 1px solid #e4e7eb; text-align: right; white-space: nowrap;">'
            f'<strong style="color: {_urgency_colour(item.days_left)};">Expires {escape(when)}</strong><br>'
            f'<span style="color: #52606d; font-size: 14px;">{escape(on)}</span></td></tr>'
        )
        lines.append(f"- {item.title} ({detail}): expires {when}, on {on}")

    footer = "You are receiving this once a day because you chose a daily digest."
    text_footer = footer
    if settings_url:
        footer += f' <a href="{escape(settings_url)}">Change how you get reminders</a>.'
        text_footer += f" Change it here: {settings_url}"
    html = Template(DIGEST_TEMPLATE_PATH.read_text()).substitute(
        name=escape(full_name), headline=escape(headline), rows="".join(rows), footer=footer
    )
    lines += ["", "Mark each one as renewed in Renewly once done.", "", text_footer]
    return subject, html, "\n".join(lines)
