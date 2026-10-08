"""Builds the subject, HTML and plain-text bodies of reminder emails."""
from datetime import date
from html import escape
from pathlib import Path
from string import Template

from app.common.enums import DocumentType

TEMPLATE_PATH = Path(__file__).parent / "templates" / "expiry_reminder.html"

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
