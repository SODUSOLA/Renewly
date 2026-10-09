"""Tests for the email templates and the per-email service functions."""
import re
from datetime import date
from decimal import Decimal

import pytest
from jinja2 import UndefinedError

from app.modules.notifications import service
from app.modules.notifications.preview import sample_context, write_previews
from app.modules.notifications.templating import TEMPLATE_DIR, available_templates, date_long, naira, render_email, when
from tests.test_auth import USER, register

EXPECTED = ["cost_report", "expiry_digest", "expiry_reminder", "password_changed", "password_reset", "welcome"]


# func to give every template realistic values
def sample(name: str) -> dict:
    """A complete, valid context for `name` (shared with the preview tool)."""
    return sample_context(name)


# ------------------------------------------------------------- the templates folder
def test_every_email_lives_in_the_templates_folder_as_subject_html_and_text():
    assert available_templates() == EXPECTED
    for name in EXPECTED:
        for extension in ("subject", "html", "txt"):
            assert (TEMPLATE_DIR / f"{name}.{extension}").is_file(), f"{name}.{extension} is missing"


def test_no_stray_files_in_the_templates_folder():
    allowed = {"base.html", "_macros.html", "_footer.txt"} | {f"{n}.{e}" for n in EXPECTED for e in ("subject", "html", "txt")}
    assert {p.name for p in TEMPLATE_DIR.iterdir()} == allowed


@pytest.mark.parametrize("name", EXPECTED)
def test_every_template_renders_all_three_parts(name):
    email = render_email(name, **sample(name))
    assert email.subject and "\n" not in email.subject
    assert email.html.lstrip().lower().startswith("<!doctype html>") and "</html>" in email.html
    assert email.text.strip()
    assert "Renewly" in email.html and "{{" not in email.html and "{%" not in email.html
    assert "{{" not in email.text and "{%" not in email.text


@pytest.mark.parametrize("name", EXPECTED)
def test_a_missing_variable_is_an_error_not_a_blank(name):
    with pytest.raises(UndefinedError):
        render_email(name)  # no context at all


def test_html_is_escaped_and_text_is_not():
    context = {**sample("expiry_reminder"), "title": "<script>alert(1)</script>", "full_name": "A & B"}
    email = render_email("expiry_reminder", **context)
    assert "<script>" not in email.html and "&lt;script&gt;" in email.html and "A &amp; B" in email.html
    assert "<script>" in email.text and "A & B" in email.text


def test_a_line_break_in_a_value_cannot_inject_extra_subject_headers():
    email = render_email("expiry_reminder", **{**sample("expiry_reminder"), "title": "Licence\nBcc: attacker@example.com"})
    assert "\n" not in email.subject and "\r" not in email.subject


def test_footer_links_to_settings_only_when_the_web_app_url_is_known(frontend_url):
    frontend_url("")
    assert "href" not in render_email("welcome", **sample("welcome")).html
    frontend_url("https://app.example.com")
    assert 'href="https://app.example.com/settings"' in render_email("welcome", **sample("welcome")).html


def test_formatting_filters():
    assert naira("15000.5") == "₦15,000.50" and naira(Decimal("0")) == "₦0.00" and naira(None) == ""
    assert date_long(date(2026, 10, 15)) == "Thursday, 15 October 2026"
    assert [when(n) for n in (0, 1, 7, -1, -4)] == ["today", "tomorrow", "in 7 days", "yesterday", "4 days ago"]


# ------------------------------------------------------------------------ welcome
def test_welcome_email_content_and_link(frontend_url):
    frontend_url("https://app.example.com")
    message = service.build_welcome_email("ada@example.com", "Ada Obi", "Africa/Lagos")
    assert message.to == "ada@example.com" and message.subject == "Welcome to Renewly, Ada Obi"
    assert "8am in your timezone (Africa/Lagos)" in message.text
    assert 'href="https://app.example.com/documents?new=1"' in message.html and "Add your first document" in message.html


def test_welcome_email_without_a_web_app_url_has_no_links(frontend_url):
    frontend_url("")
    message = service.build_welcome_email("ada@example.com", "Ada", "Africa/Lagos")
    assert "href" not in message.html and "http" not in message.text


def test_signing_up_sends_exactly_one_welcome_email(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.modules.auth.router.send_welcome_email", lambda *args: sent.append(args))
    assert register(client).status_code == 201
    assert sent == [("ada@example.com", "Ada Obi", "Africa/Lagos")]


def test_no_welcome_email_when_the_email_is_already_registered_or_invalid(client, monkeypatch):
    register(client)
    sent = []
    monkeypatch.setattr("app.modules.auth.router.send_welcome_email", lambda *args: sent.append(args))
    assert register(client).status_code == 409
    assert register(client, email="bob@example.com", password="short").status_code == 422
    assert sent == []


def test_a_failing_email_provider_never_breaks_sign_up(client, monkeypatch):
    from app.modules.notifications.email import EmailSendError

    def boom(message):
        raise EmailSendError("provider down")

    monkeypatch.setattr(service, "send_email", boom)
    assert register(client).status_code == 201
    assert client.post("/auth/login", json={"email": "ada@example.com", "password": USER["password"]}).status_code == 200


# --------------------------------------------------------------- password emails
def test_password_changed_email_warns_the_owner_and_links_to_reset(frontend_url):
    frontend_url("https://app.example.com")
    message = service.build_password_changed_email("ada@example.com", "Ada")
    assert message.subject == "Your Renewly password was changed"
    assert "If it wasn't you" in message.text and "signed out on all your devices" in message.text
    assert 'href="https://app.example.com/forgot-password"' in message.html


def test_a_successful_reset_sends_the_security_notice_and_a_failed_one_does_not(client, monkeypatch):
    tokens, notices = [], []
    monkeypatch.setattr("app.modules.auth.router.send_password_reset_email", lambda e, t: tokens.append(t))
    monkeypatch.setattr("app.modules.auth.router.send_password_changed_email", lambda e, n: notices.append((e, n)))
    register(client)
    client.post("/auth/forgot-password", json={"email": "ada@example.com"})
    bad = client.post("/auth/reset-password", json={"token": "nope", "new_password": "brand-new-pass"})
    assert bad.status_code == 400 and notices == []
    good = client.post("/auth/reset-password", json={"token": tokens[0], "new_password": "brand-new-pass"})
    assert good.status_code == 200 and notices == [("ada@example.com", "Ada Obi")]


def test_reset_email_states_how_long_the_link_lasts(frontend_url):
    frontend_url("https://app.example.com")
    message = service.build_password_reset_email("ada@example.com", "tok")
    assert "expires in 60 minutes" in message.text and "expires in 60 minutes" in message.html
    assert "Your password won't change" in message.text


# ---------------------------------------------------------------------- reminders
def test_the_reminder_email_links_to_its_document(frontend_url):
    frontend_url("https://app.example.com")
    subject, html, text = service.render_expiry_reminder(
        full_name="Ada", title="Licence", doc_type=service.DocumentType.DRIVER_LICENSE, custom_type_label=None,
        expiry_date=date(2026, 10, 15), days_left=7, vehicle_label=None, document_id="abc-123",
    )
    assert subject == "Licence expires in 7 days"
    assert 'href="https://app.example.com/documents/abc-123"' in html and "https://app.example.com/documents/abc-123" in text


# ------------------------------------------------------------------- cost report
def test_cost_report_email_shows_the_numbers_a_person_would_check(frontend_url):
    frontend_url("https://app.example.com")
    email = render_email("cost_report", **sample("cost_report"))
    assert email.subject == "Your January – June 2026 renewals report"
    for expected in ("₦207,501.25", "↑ 108% more than the six months before (₦100,000.00)", "1 renewal has no cost recorded", "Insurance", "₦185,001.00", "about ₦150,000.50", "no price on record", "Roughly <strong>₦157,500.50</strong>", "2 of 3 have a past price"):
        assert expected in email.html, expected
    assert "Full report: https://renewly.example.com/reports" in email.text and "Turn it off here: https://app.example.com/settings" in email.text


def test_cost_report_email_for_a_period_with_no_renewals_says_so():
    context = {**sample("cost_report"), "renewals": 0, "change_pct": None, "by_type": [], "by_vehicle": [], "missing_cost_count": 0}
    email = render_email("cost_report", **context)
    assert "You didn't mark any renewals in this period." in email.text
    assert "Spent on renewals" not in email.html and "Coming up in the next six months" in email.html


def test_cost_report_omits_the_comparison_when_there_is_nothing_to_compare():
    email = render_email("cost_report", **{**sample("cost_report"), "change_pct": None})
    assert "more than the six months before" not in email.html


@pytest.mark.parametrize("change, wording", [(-20, "↓ 20% less than the six months before"), (0, "no change from the six months before")])
def test_cost_report_comparison_wording(change, wording):
    email = render_email("cost_report", **{**sample("cost_report"), "change_pct": change})
    assert wording in email.html


def test_period_labels_read_naturally():
    assert service.period_label(date(2026, 1, 1), date(2026, 6, 30)) == "January – June 2026"
    assert service.period_label(date(2025, 7, 1), date(2025, 12, 31)) == "July – December 2025"
    assert service.period_label(date(2025, 10, 1), date(2026, 3, 31)) == "October 2025 – March 2026"


# -------------------------------------------------------------- the preview tool
def test_the_preview_tool_writes_every_email_and_an_index(tmp_path):
    files = write_previews(tmp_path)
    names = {f.name for f in files}
    assert names == {"index.html"} | {f"{n}.{e}" for n in EXPECTED for e in ("html", "txt")}
    index = (tmp_path / "index.html").read_text()
    assert all(f'href="{n}.html"' in index for n in EXPECTED)
    assert "Welcome to Renewly, Ada Obi" in index
