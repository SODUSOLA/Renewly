"""Tests for the daily digest: batching, exactly-once delivery, retries and the profile setting."""
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.common.enums import DocumentType, ReminderStatus
from app.core.database import SessionLocal
from app.modules.notifications.rendering import DigestItem, render_expiry_digest
from app.modules.reminders import service as reminders
from app.modules.reminders.models import ReminderLog
from tests.helpers import auth_headers
from tests.test_reminders import LAGOS_TODAY, NOW, Outbox, add_doc, logs, run


@pytest.fixture
def outbox() -> Outbox:
    """A fresh fake outbox."""
    return Outbox()


# func to switch a user to the digest style through the API
def use_digest(client, headers) -> None:
    """PATCH /auth/me so this user receives a daily digest."""
    res = client.patch("/auth/me", json={"reminder_style": "digest"}, headers=headers)
    assert res.status_code == 200, res.text


# func to create several documents that are all due on the same day
def add_three_due_docs(client, headers) -> None:
    """Create documents due in 7, 1 and 14 days (all hit a default reminder offset)."""
    add_doc(client, headers, LAGOS_TODAY + timedelta(days=7), title="Insurance")
    add_doc(client, headers, LAGOS_TODAY + timedelta(days=1), title="Licence")
    add_doc(client, headers, LAGOS_TODAY + timedelta(days=14), title="Permit", type="permit")


# ------------------------------------------------------------------ batching
def test_a_digest_user_gets_one_email_for_everything_due(client, ada, outbox):
    use_digest(client, ada)
    add_three_due_docs(client, ada)
    summary = run(NOW, outbox)
    assert len(outbox.sent) == 1
    assert (summary.sent, summary.failed) == (3, 0)  # counts reminders delivered
    message = outbox.sent[0]
    assert message.to == "ada@example.com"
    assert message.subject == "3 documents need your attention"
    # Most urgent first.
    assert message.text.index("Licence") < message.text.index("Insurance") < message.text.index("Permit")
    assert {r.status for r in logs()} == {ReminderStatus.SENT} and len(logs()) == 3


def test_the_default_style_still_sends_one_email_per_reminder(client, ada, outbox):
    add_three_due_docs(client, ada)
    run(NOW, outbox)
    assert len(outbox.sent) == 3


def test_a_single_due_document_reads_like_a_normal_reminder(client, ada, outbox):
    use_digest(client, ada)
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=7), title="Insurance")
    run(NOW, outbox)
    assert [m.subject for m in outbox.sent] == ["Insurance expires in 7 days"]


def test_users_are_handled_independently(client, ada, bola, outbox):
    use_digest(client, ada)
    add_three_due_docs(client, ada)
    add_doc(client, bola, LAGOS_TODAY + timedelta(days=7), title="B1")
    add_doc(client, bola, LAGOS_TODAY + timedelta(days=14), title="B2")
    run(NOW, outbox)
    by_recipient = {}
    for message in outbox.sent:
        by_recipient.setdefault(message.to, []).append(message)
    assert len(by_recipient["ada@example.com"]) == 1  # digest
    assert len(by_recipient["bola@example.com"]) == 2  # one each


def test_nothing_is_sent_when_nothing_is_due(client, ada, outbox):
    use_digest(client, ada)
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=9))
    assert run(NOW, outbox).sent == 0 and outbox.sent == []


def test_the_digest_waits_for_8am_local_time(client, ada, outbox):
    use_digest(client, ada)
    add_three_due_docs(client, ada)
    assert run(datetime(2026, 10, 8, 6, 0, tzinfo=UTC), outbox).sent == 0  # 07:00 Lagos
    assert run(datetime(2026, 10, 8, 7, 30, tzinfo=UTC), outbox).sent == 3  # 08:30 Lagos
    assert len(outbox.sent) == 1


# ----------------------------------------------------------- exactly once / retries
def test_running_again_never_repeats_a_digest(client, ada, outbox):
    use_digest(client, ada)
    add_three_due_docs(client, ada)
    run(NOW, outbox)
    second = run(NOW + timedelta(hours=1), outbox)
    assert len(outbox.sent) == 1
    assert (second.sent, second.skipped) == (0, 3)


def test_a_failed_digest_is_retried_as_one_email_and_not_resent_afterwards(client, ada, outbox):
    use_digest(client, ada)
    add_three_due_docs(client, ada)
    outbox.fail_with = "provider down"
    first = run(NOW, outbox)
    assert (first.sent, first.failed) == (0, 3) and outbox.sent == []
    assert {r.status for r in logs()} == {ReminderStatus.FAILED}
    assert all("provider down" in r.error for r in logs())

    outbox.fail_with = None
    retry = run(NOW + timedelta(hours=1), outbox)
    assert (retry.sent, retry.failed) == (3, 0) and len(outbox.sent) == 1
    assert {r.status for r in logs()} == {ReminderStatus.SENT} and len(logs()) == 3
    assert run(NOW + timedelta(hours=2), outbox).sent == 0 and len(outbox.sent) == 1


def test_reminders_already_sent_individually_are_left_out_of_the_digest(client, ada, outbox):
    add_three_due_docs(client, ada)
    run(NOW, outbox)  # default style: three separate emails go out
    assert len(outbox.sent) == 3
    use_digest(client, ada)  # the user switches style mid-day
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=30), title="Later")  # a new reminder falls due
    run(NOW + timedelta(hours=1), outbox)
    assert len(outbox.sent) == 4  # only the new one
    assert outbox.sent[-1].subject == "Later expires in 30 days"


def test_the_idempotency_key_depends_on_which_reminders_not_their_order():
    a, b, c = (uuid.uuid4() for _ in range(3))
    key = reminders.digest_idempotency_key
    assert key([a, b, c]) == key([c, a, b])
    assert key([a, b, c]) != key([a, b])
    assert key([a, b]).startswith("digest-")


def test_the_email_carries_that_key(client, ada, outbox):
    use_digest(client, ada)
    add_three_due_docs(client, ada)
    run(NOW, outbox)
    ids = [r.id for r in logs()]
    assert outbox.sent[0].idempotency_key == reminders.digest_idempotency_key(ids)


# ------------------------------------------------------------------ rendering
# func to build a digest item
def item(title="Insurance", days=7, label=None, vehicle=None, doc_type=DocumentType.INSURANCE) -> DigestItem:
    """A DigestItem with sensible defaults."""
    return DigestItem(title, doc_type, label, date(2026, 10, 15), days, vehicle)


def test_digest_lists_every_item_and_names_vehicles():
    subject, html, text = render_expiry_digest(
        full_name="Ada", items=[item("Insurance", 1, vehicle="Corolla (ABC1)"), item("Permit", 14, doc_type=DocumentType.PERMIT)], settings_url=None
    )
    assert subject == "2 documents need your attention"
    assert "tomorrow" in text and "in 14 days" in text and "Corolla (ABC1)" in html
    assert "Permit" in html and "Thursday, 15 October 2026" in html


def test_user_supplied_text_is_escaped_in_the_html_digest():
    _, html, text = render_expiry_digest(
        full_name="A & B", items=[item("<script>alert(1)</script>"), item("Other", 3)], settings_url=None
    )
    assert "<script>" not in html and "&lt;script&gt;" in html and "A &amp; B" in html
    assert "<script>" in text


def test_footer_links_to_settings_only_when_a_url_is_known():
    with_link = render_expiry_digest(full_name="Ada", items=[item()], settings_url="https://app.example.com/settings")
    without = render_expiry_digest(full_name="Ada", items=[item()], settings_url=None)
    assert 'href="https://app.example.com/settings"' in with_link[1] and "https://app.example.com/settings" in with_link[2]
    assert "href" not in without[1] and "http" not in without[2]


def test_the_message_builder_links_to_the_frontend_settings_page(client, ada, monkeypatch):
    monkeypatch.setattr(reminders, "get_settings", lambda: SimpleNamespace(frontend_url="https://app.example.com/"))
    use_digest(client, ada)
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=7))
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=14), title="Other")
    outbox = Outbox()
    run(NOW, outbox)
    assert "https://app.example.com/settings" in outbox.sent[0].text


# ------------------------------------------------------------- profile setting
def test_new_users_default_to_one_email_per_reminder(client, ada):
    assert client.get("/auth/me", headers=ada).json()["reminder_style"] == "each"


def test_patch_me_changes_only_the_fields_sent(client, ada):
    res = client.patch("/auth/me", json={"reminder_style": "digest"}, headers=ada)
    assert res.json()["reminder_style"] == "digest" and res.json()["timezone"] == "Africa/Lagos"
    res = client.patch("/auth/me", json={"timezone": "Europe/London", "full_name": "  Ada O.  "}, headers=ada)
    body = res.json()
    assert (body["timezone"], body["full_name"], body["reminder_style"]) == ("Europe/London", "Ada O.", "digest")
    assert client.get("/auth/me", headers=ada).json()["timezone"] == "Europe/London"


@pytest.mark.parametrize(
    "bad",
    [{"reminder_style": "weekly"}, {"timezone": "Mars/Olympus"}, {"full_name": ""}, {"timezone": None}, {"reminder_style": None}],
)
def test_patch_me_rejects_invalid_values(client, ada, bad):
    assert client.patch("/auth/me", json=bad, headers=ada).status_code == 422


def test_patch_me_cannot_change_the_email_or_other_protected_fields(client, ada):
    client.patch("/auth/me", json={"email": "evil@example.com", "is_active": False, "password_hash": "x"}, headers=ada)
    me = client.get("/auth/me", headers=ada).json()
    assert me["email"] == "ada@example.com"


def test_patch_me_requires_authentication(client):
    assert client.patch("/auth/me", json={"reminder_style": "digest"}).status_code == 401


def test_a_timezone_change_takes_effect_for_the_next_reminder_run(client, ada, outbox):
    add_doc(client, ada, date(2026, 10, 15))  # 7 days away on Oct 8 in Lagos
    client.patch("/auth/me", json={"timezone": "Pacific/Auckland"}, headers=ada)
    # 12:00 UTC is already Oct 9 in Auckland (6 days left, not due) and only 01:00 there.
    assert run(NOW, outbox).sent == 0
