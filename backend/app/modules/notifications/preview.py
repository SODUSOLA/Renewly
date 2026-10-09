"""Render every email with sample data, so the designs can be looked at without sending anything.

    python -m app.modules.notifications.preview [output_dir]

Writes `<name>.html` and `<name>.txt` for each template plus an `index.html` linking them
(default folder: ./email-previews). Open index.html in a browser. The sample data is also what
the tests use to prove every template renders, so a template that breaks fails the build.
"""
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from app.modules.notifications.templating import available_templates, render_email

_DIGEST_ITEMS = [
    {"title": "Licence", "kind": "Driver's license", "vehicle_label": None, "expiry_date": date(2026, 10, 10), "days_left": 1},
    {"title": "Car insurance", "kind": "Insurance", "vehicle_label": "Corolla (ABC123XY)", "expiry_date": date(2026, 10, 16), "days_left": 7},
    {"title": "Parking permit", "kind": "Permit", "vehicle_label": None, "expiry_date": date(2026, 10, 23), "days_left": 14},
]

SAMPLES: dict[str, dict] = {
    "welcome": {"full_name": "Ada Obi", "timezone": "Africa/Lagos"},
    "password_reset": {"reset_url": "https://renewly.example.com/reset-password?token=abc123", "token": "abc123", "ttl_minutes": 60},
    "password_changed": {"full_name": "Ada Obi"},
    "expiry_reminder": {
        **_DIGEST_ITEMS[1],
        "full_name": "Ada Obi",
        "document_url": "https://renewly.example.com/documents/1",
    },
    "expiry_digest": {"full_name": "Ada Obi", "items": _DIGEST_ITEMS},
    "cost_report": {
        "full_name": "Ada Obi",
        "period_label": "January – June 2026",
        "total": Decimal("207501.25"),
        "previous_total": Decimal("100000.00"),
        "change_pct": 108,
        "renewals": 7,
        "missing_cost_count": 1,
        "by_type": [
            {"label": "Insurance", "total": Decimal("185001.00"), "renewals": 3},
            {"label": "Permit", "total": Decimal("12500.25"), "renewals": 2},
            {"label": "Driver's license", "total": Decimal("10000.00"), "renewals": 1},
        ],
        "by_vehicle": [
            {"label": "Corolla (ABC123XY)", "total": Decimal("185001.00"), "renewals": 3},
            {"label": "No vehicle", "total": Decimal("22500.25"), "renewals": 3},
        ],
        "upcoming": [
            {**_DIGEST_ITEMS[0], "estimated_cost": None},
            {**_DIGEST_ITEMS[1], "estimated_cost": Decimal("150000.50")},
            {**_DIGEST_ITEMS[2], "estimated_cost": Decimal("7500.00")},
        ],
        "estimate_total": Decimal("157500.50"),
        "estimate_count": 2,
        "reports_url": "https://renewly.example.com/reports",
    },
}


# Links a configured deployment would have (FRONTEND_URL); the preview shows them so buttons appear.
PREVIEW_LINKS = {
    "app_url": "https://renewly.example.com",
    "settings_url": "https://renewly.example.com/settings",
}


# func to get the sample values for one email
def sample_context(name: str) -> dict:
    """A complete context for template `name` (raises KeyError for an unknown template)."""
    return SAMPLES[name]


# func to write every email to disk
def write_previews(directory: Path) -> list[Path]:
    """Render all templates into `directory` as .html/.txt plus an index page; return the files."""
    directory.mkdir(parents=True, exist_ok=True)
    written, rows = [], []
    for name in available_templates():
        email = render_email(name, **{**PREVIEW_LINKS, **sample_context(name)})
        (directory / f"{name}.html").write_text(email.html)
        (directory / f"{name}.txt").write_text(email.text)
        written += [directory / f"{name}.html", directory / f"{name}.txt"]
        rows.append(f'<li><a href="{name}.html">{name}</a> · <a href="{name}.txt">text</a> · subject: <em>{email.subject}</em></li>')
    index = directory / "index.html"
    index.write_text("<!doctype html><title>Email previews</title><h1>Email previews</h1><ul>" + "".join(rows) + "</ul>")
    return written + [index]


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "email-previews")
    files = write_previews(out)
    print(f"Wrote {len(files)} files to {out.resolve()}. Open {out.resolve() / 'index.html'}")
