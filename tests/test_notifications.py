"""Tests for email rendering, the Resend sender and the Celery task."""
import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.common.enums import DocumentType
from app.modules.notifications import email as email_module
from app.modules.notifications.email import EmailMessage, EmailSendError, ResendSender
from app.modules.notifications.rendering import render_expiry_reminder

MESSAGE = EmailMessage("ada@example.com", "Hello", "<p>hi</p>", "hi", idempotency_key="k-1")


# func to render a reminder with sensible defaults
def render(**overrides):
    """Render a reminder email, overriding any argument."""
    args = dict(
        full_name="Ada", title="Insurance", doc_type=DocumentType.INSURANCE,
        custom_type_label=None, expiry_date=date(2026, 10, 15), days_left=7, vehicle_label=None,
    )
    return render_expiry_reminder(**{**args, **overrides})


@pytest.mark.parametrize(
    "days, subject",
    [(0, "Insurance expires today"), (1, "Insurance expires tomorrow"), (30, "Insurance expires in 30 days")],
)
def test_subject_wording(days, subject):
    assert render(days_left=days)[0] == subject


def test_user_supplied_values_are_escaped_in_html_only():
    subject, html, text = render(title="<script>alert(1)</script>", full_name="A & B")
    assert "<script>" not in html and "&lt;script&gt;" in html and "A &amp; B" in html
    assert "<script>" in text


def test_custom_label_replaces_type_name():
    _, html, text = render(doc_type=DocumentType.CUSTOM, custom_type_label="Gym card")
    assert "Gym card" in html and "Gym card" in text


# func to build a ResendSender whose network is faked
def sender_with(handler):
    """Return a ResendSender wired to an in-memory fake of the Resend API."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ResendSender("re_test_key", "Tracker <noreply@example.com>", client=client)


def test_resend_sender_posts_the_expected_request():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(url=str(request.url), headers=request.headers, body=json.loads(request.content))
        return httpx.Response(200, json={"id": "abc"})

    sender_with(handler).send(MESSAGE)
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"]["authorization"] == "Bearer re_test_key"
    assert seen["headers"]["idempotency-key"] == "k-1"
    assert seen["body"] == {
        "from": "Tracker <noreply@example.com>", "to": ["ada@example.com"],
        "subject": "Hello", "html": "<p>hi</p>", "text": "hi",
    }


def test_resend_rejection_becomes_email_send_error():
    sender = sender_with(lambda request: httpx.Response(422, text="domain not verified"))
    with pytest.raises(EmailSendError, match="422.*domain not verified"):
        sender.send(MESSAGE)


def test_network_failure_becomes_email_send_error():
    def handler(request):
        raise httpx.ConnectError("no route")

    with pytest.raises(EmailSendError, match="Could not reach Resend"):
        sender_with(handler).send(MESSAGE)


# func to fake the settings object used by get_sender
def fake_settings(monkeypatch, **values):
    """Make email.get_settings() return the given settings values."""
    defaults = dict(resend_api_key="", app_env="development", email_from="x@example.com")
    monkeypatch.setattr(email_module, "get_settings", lambda: SimpleNamespace(**{**defaults, **values}))


def test_sender_selection(monkeypatch):
    fake_settings(monkeypatch)
    assert isinstance(email_module.get_sender(), email_module.LogSender)
    fake_settings(monkeypatch, resend_api_key="re_x")
    assert isinstance(email_module.get_sender(), ResendSender)


def test_missing_key_in_production_fails_loudly(monkeypatch):
    fake_settings(monkeypatch, app_env="production")
    with pytest.raises(EmailSendError, match="RESEND_API_KEY"):
        email_module.send_email(MESSAGE)


def test_reset_email_failure_is_swallowed(monkeypatch):
    def boom(message):
        raise EmailSendError("down")

    monkeypatch.setattr(email_module, "send_email", boom)
    email_module.send_password_reset_email("ada@example.com", "tok")  # must not raise


def test_celery_task_runs_and_reports_counts():
    from app.modules.reminders.tasks import send_due_reminders

    assert send_due_reminders() == {"sent": 0, "failed": 0, "skipped": 0}


def test_log_sender_logs_the_message_instead_of_sending(caplog):
    import logging

    with caplog.at_level(logging.INFO):
        email_module.LogSender().send(MESSAGE)
    assert "no RESEND_API_KEY" in caplog.text and "ada@example.com" in caplog.text
