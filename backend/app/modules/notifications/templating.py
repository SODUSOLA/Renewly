"""Renders emails from the files in `templates/`.

Every email is three small files that share a name:

    templates/<name>.subject   one line: the subject
    templates/<name>.html      the HTML body (extends base.html)
    templates/<name>.txt       the plain-text body (for clients that don't show HTML)

Keeping them in one folder means wording and layout can be changed without touching code.
HTML is escaped automatically, so a document titled `<script>` is shown as text. A template
that uses a variable the code did not provide is an error, never a silent blank.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.core.config import get_settings

TEMPLATE_DIR = Path(__file__).parent / "templates"
APP_NAME = "Renewly"
# Reminders and digests are sent once the user's local clock reaches this hour.
SEND_HOUR = 8

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


# func to format money for people
def naira(amount: Decimal | str | int | float | None) -> str:
    """15000.5 -> '₦15,000.50'. None becomes an empty string."""
    if amount is None:
        return ""
    return f"₦{Decimal(str(amount)):,.2f}"


# func to format a date in full
def date_long(value: date) -> str:
    """date(2026, 10, 15) -> 'Thursday, 15 October 2026'."""
    return f"{_WEEKDAYS[value.weekday()]}, {value.day} {_MONTHS[value.month - 1]} {value.year}"


# func to format a date briefly
def date_short(value: date) -> str:
    """date(2026, 10, 15) -> '15 Oct 2026'."""
    return f"{value.day} {_MONTHS[value.month - 1][:3]} {value.year}"


# func to describe days left inside a sentence
def when(days_left: int) -> str:
    """0 -> 'today', 1 -> 'tomorrow', 7 -> 'in 7 days', -3 -> '3 days ago'."""
    if days_left == 0:
        return "today"
    if days_left == 1:
        return "tomorrow"
    if days_left == -1:
        return "yesterday"
    return f"in {days_left} days" if days_left > 0 else f"{-days_left} days ago"


# func to choose how urgent something looks in an email
def urgency_colour(days_left: int) -> str:
    """Red for today/tomorrow (or overdue), amber within a week, green otherwise.

    Colour only reinforces the wording next to it; nothing relies on it alone.
    """
    if days_left <= 1:
        return "#b42318"
    if days_left <= 7:
        return "#b54708"
    return "#067647"


# func to build a Jinja environment over the templates folder
def _environment(*, html: bool) -> Environment:
    """One environment for HTML (auto-escaping on) and one for text and subjects (off)."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=html,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(naira=naira, date_long=date_long, date_short=date_short, when=when)
    env.globals["urgency_colour"] = urgency_colour
    return env


_HTML = _environment(html=True)
_TEXT = _environment(html=False)


# class for a finished email, ready to hand to the sender
@dataclass(frozen=True)
class RenderedEmail:
    """The three parts of an email produced from one template name."""

    subject: str
    html: str
    text: str


# func to supply the variables every template can use
def base_context() -> dict[str, object]:
    """App name and links shared by all emails (`app_url` is None when FRONTEND_URL is unset)."""
    frontend = get_settings().frontend_url.rstrip("/")
    return {
        "app_name": APP_NAME,
        "app_url": frontend or None,
        "settings_url": f"{frontend}/settings" if frontend else None,
        "send_hour": SEND_HOUR,
    }


# func to render one email
def render_email(name: str, **context: object) -> RenderedEmail:
    """Render `templates/<name>.{subject,html,txt}` with `context`.

    The subject is collapsed to a single line, which also rules out header injection through
    a value that contains a line break.
    """
    values = {**base_context(), **context}
    subject = " ".join(_TEXT.get_template(f"{name}.subject").render(**values).split())
    html = _HTML.get_template(f"{name}.html").render(**values)
    text = _TEXT.get_template(f"{name}.txt").render(**values)
    return RenderedEmail(subject=subject, html=html, text=text)


# func to list the emails the app can send
def available_templates() -> list[str]:
    """Names of every email that has a subject file (used by tests and the preview tool)."""
    return sorted(p.stem for p in TEMPLATE_DIR.glob("*.subject"))
