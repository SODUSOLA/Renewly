"""Tests for the reminder engine: due calculation, exactly-once sending and retries."""
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.common.enums import ReminderChannel, ReminderStatus
from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.notifications.email import EmailMessage
from app.modules.reminders.models import ReminderLog
from app.modules.reminders.service import run_due_reminders
from tests.helpers import auth_headers

# 12:00 UTC is 13:00 in Lagos (UTC+1), so "today" there is 2026-10-08.
NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
LAGOS_TODAY = date(2026, 10, 8)


# class for a fake email sender that records messages
class Outbox:
    """Stand-in for the email provider: records messages, can be told to fail."""

    # func to start with nothing sent
    def __init__(self) -> None:
        """Create an empty outbox that sends successfully."""
        self.sent: list[EmailMessage] = []
        self.fail_with: str | None = None

    # func to act like EmailSender.send
    def __call__(self, message: EmailMessage) -> None:
        """Record the message, or raise if `fail_with` is set."""
        if self.fail_with:
            raise RuntimeError(self.fail_with)
        self.sent.append(message)


@pytest.fixture
def outbox() -> Outbox:
    """A fresh fake outbox."""
    return Outbox()


# func to create a document through the API
def add_doc(client, headers, expiry: date, **overrides) -> dict:
    """Create a document expiring on `expiry` and return its JSON."""
    body = {"type": "insurance", "title": "Car insurance", "expiry_date": expiry.isoformat(), **overrides}
    res = client.post("/documents", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


# func to run the job against the test database
def run(now: datetime, outbox: Outbox):
    """Run the reminder job at `now` with the fake outbox and return the summary."""
    with SessionLocal() as db:
        return run_due_reminders(db, now, send=outbox)


# func to read all reminder log rows
def logs() -> list[ReminderLog]:
    """Return every reminder_log row."""
    with SessionLocal() as db:
        return list(db.scalars(select(ReminderLog)))


def test_sends_only_when_days_left_matches_an_offset(client, ada, outbox):
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=7), title="Seven")
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=8), title="Eight")
    summary = run(NOW, outbox)
    assert (summary.sent, summary.failed) == (1, 0)
    assert [m.subject for m in outbox.sent] == ["Seven expires in 7 days"]
    assert outbox.sent[0].to == "ada@example.com"


def test_running_twice_sends_once(client, ada, outbox):
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=7))
    run(NOW, outbox)
    second = run(NOW + timedelta(hours=1), outbox)
    assert len(outbox.sent) == 1
    assert (second.sent, second.skipped) == (0, 1)
    rows = logs()
    assert len(rows) == 1 and rows[0].status == ReminderStatus.SENT


def test_failed_send_is_recorded_then_retried_and_never_resent(client, ada, outbox):
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=1))
    outbox.fail_with = "provider down"
    first = run(NOW, outbox)
    assert first.failed == 1 and outbox.sent == []
    row = logs()[0]
    assert row.status == ReminderStatus.FAILED and "provider down" in row.error

    outbox.fail_with = None
    retry = run(NOW + timedelta(hours=1), outbox)
    assert retry.sent == 1 and len(outbox.sent) == 1
    rows = logs()
    assert len(rows) == 1 and rows[0].status == ReminderStatus.SENT and rows[0].error is None

    assert run(NOW + timedelta(hours=2), outbox).sent == 0
    assert len(outbox.sent) == 1


def test_one_failure_does_not_block_other_reminders(client, ada, outbox):
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=7), title="A")
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=14), title="B")
    calls = []

    def flaky(message: EmailMessage) -> None:
        calls.append(message.subject)
        if message.subject.startswith("A"):
            raise RuntimeError("boom")
        outbox.sent.append(message)

    with SessionLocal() as db:
        summary = run_due_reminders(db, NOW, send=flaky)
    assert (summary.sent, summary.failed) == (1, 1)
    assert len(calls) == 2


def test_nothing_is_sent_before_8am_local_time(client, ada, outbox):
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=7))
    assert run(datetime(2026, 10, 8, 6, 0, tzinfo=UTC), outbox).sent == 0  # 07:00 Lagos
    assert run(datetime(2026, 10, 8, 7, 30, tzinfo=UTC), outbox).sent == 1  # 08:30 Lagos


def test_each_user_is_judged_in_their_own_timezone(client, outbox):
    la = auth_headers(client, "la@example.com", "America/Los_Angeles")
    auckland = auth_headers(client, "nz@example.com", "Pacific/Auckland")
    add_doc(client, la, date(2026, 10, 15), title="LA doc")
    # Oct 15 is 7 days away in UTC terms, but only 6 for someone already on Oct 9.
    add_doc(client, auckland, date(2026, 10, 15), title="NZ six")
    add_doc(client, auckland, date(2026, 10, 16), title="NZ seven")

    # 12:00 UTC: LA is 05:00 (too early); Auckland is Oct 9, 01:00 (too early).
    assert run(NOW, outbox).sent == 0
    # 16:00 UTC: LA is 09:00 on Oct 8 -> 7 days; Auckland is Oct 9, 05:00 (still early).
    run(datetime(2026, 10, 8, 16, 0, tzinfo=UTC), outbox)
    assert [m.subject for m in outbox.sent] == ["LA doc expires in 7 days"]
    # 20:00 UTC: Auckland is Oct 9, 09:00 -> "NZ seven" is 7 days, "NZ six" is 6.
    run(datetime(2026, 10, 8, 20, 0, tzinfo=UTC), outbox)
    assert [m.subject for m in outbox.sent][1:] == ["NZ seven expires in 7 days"]


def test_deleted_documents_and_inactive_users_are_ignored(client, ada, bola, outbox):
    doc = add_doc(client, ada, LAGOS_TODAY + timedelta(days=7))
    client.delete(f"/documents/{doc['id']}", headers=ada)
    add_doc(client, bola, LAGOS_TODAY + timedelta(days=7))
    with SessionLocal() as db:
        db.execute(update(User).where(User.email == "bola@example.com").values(is_active=False))
        db.commit()
    assert run(NOW, outbox).sent == 0


def test_renewal_rearms_the_same_offsets(client, ada, outbox):
    doc = add_doc(client, ada, LAGOS_TODAY + timedelta(days=7))
    assert run(NOW, outbox).sent == 1
    client.post(f"/documents/{doc['id']}/renew", json={"new_expiry": "2026-11-20"}, headers=ada)
    later = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)  # exactly 7 days before Nov 20
    assert run(later, outbox).sent == 1
    assert len(logs()) == 2


def test_custom_offsets_are_respected(client, ada, outbox):
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=7), reminder_offsets=[3])
    assert run(NOW, outbox).sent == 0
    assert run(NOW + timedelta(days=4), outbox).sent == 1  # 3 days left


def test_stale_pending_claims_are_reclaimed_but_fresh_ones_are_not(client, ada, outbox):
    doc = add_doc(client, ada, LAGOS_TODAY + timedelta(days=7))

    def seed(age: timedelta) -> None:
        with SessionLocal() as db:
            db.query(ReminderLog).delete()
            db.add(ReminderLog(
                document_id=doc["id"], offset_days=7, expiry_date=LAGOS_TODAY + timedelta(days=7),
                channel=ReminderChannel.EMAIL, status=ReminderStatus.PENDING, sent_at=NOW - age,
            ))
            db.commit()

    seed(timedelta(minutes=1))
    assert run(NOW, outbox).sent == 0
    seed(timedelta(hours=1))
    assert run(NOW, outbox).sent == 1


def test_email_names_the_vehicle_and_uses_an_idempotency_key(client, ada, outbox):
    vehicle = client.post("/vehicles", json={"nickname": "Corolla", "plate_number": "abc 1"}, headers=ada).json()
    add_doc(client, ada, LAGOS_TODAY + timedelta(days=1), vehicle_id=vehicle["id"])
    run(NOW, outbox)
    message = outbox.sent[0]
    assert "Corolla (ABC1)" in message.text and "Corolla (ABC1)" in message.html
    assert message.subject == "Car insurance expires tomorrow"
    assert message.idempotency_key == f"reminder-{logs()[0].id}"
