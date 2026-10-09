"""Tests for the six-monthly spending report: when it goes out, to whom, and exactly once."""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from app.common.enums import ReminderStatus
from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.notifications.models import EmailDispatch
from app.modules.reports import periodic
from app.modules.reports.periodic import report_period, run_semiannual_reports
from app.modules.reports.service import build_period_summary, upcoming_expiries
from tests.helpers import auth_headers
from tests.test_reminders import Outbox, add_doc
from tests.test_reports import add_renewal, new_doc

# 12:00 UTC on 2 July 2026 is 13:00 in Lagos (UTC+1): inside the January-to-June report window.
JULY = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)


@pytest.fixture
def outbox() -> Outbox:
    """A fresh fake outbox."""
    return Outbox()


# func to run the job against the test database
def run(now: datetime, outbox: Outbox):
    """Run the six-monthly report job at `now` with the fake outbox; return its summary."""
    with SessionLocal() as db:
        return run_semiannual_reports(db, now, send=outbox)


# func to read the dispatch log
def dispatches() -> list[EmailDispatch]:
    """Every email_dispatch row."""
    with SessionLocal() as db:
        return list(db.scalars(select(EmailDispatch)))


# func to give a user something to report on
def with_history(client, headers) -> str:
    """Create a document with two renewals in H1 2026 and return its id."""
    doc = new_doc(client, headers, title="Car insurance", expiry_date="2026-09-01")
    add_renewal(doc, date(2026, 2, 1), "100000")
    add_renewal(doc, date(2026, 5, 1), "50000.50")
    return doc


# ------------------------------------------------------------------ the calendar
@pytest.mark.parametrize(
    "day, expected",
    [
        (date(2026, 1, 1), ("2025-H2", date(2025, 7, 1), date(2025, 12, 31))),
        (date(2026, 1, 7), ("2025-H2", date(2025, 7, 1), date(2025, 12, 31))),
        (date(2026, 7, 1), ("2026-H1", date(2026, 1, 1), date(2026, 6, 30))),
        (date(2026, 7, 7), ("2026-H1", date(2026, 1, 1), date(2026, 6, 30))),
        (date(2026, 1, 8), None),
        (date(2026, 7, 8), None),
        (date(2026, 6, 30), None),
        (date(2026, 12, 31), None),
        (date(2026, 3, 3), None),
    ],
)
def test_which_half_year_is_reported_and_when(day, expected):
    assert report_period(day) == expected


# ---------------------------------------------------------------------- summaries
def test_period_summary_totals_and_comparison_are_hand_computed(client, ada):
    doc = with_history(client, ada)
    add_renewal(doc, date(2025, 11, 1), "80000")  # the six months before
    add_renewal(doc, date(2026, 3, 1), None)
    with SessionLocal() as db:
        user = db.scalar(select(User))
        summary = build_period_summary(db, user, date(2026, 1, 1), date(2026, 6, 30))
    assert summary.total == Decimal("150000.50") and summary.previous_total == Decimal("80000.00")
    assert (summary.renewals, summary.renewals_with_cost, summary.missing_cost_count) == (3, 2, 1)
    assert [(b.label, b.total) for b in summary.by_type] == [("Insurance", Decimal("150000.50"))]


def test_period_boundaries_are_inclusive_of_the_last_day(client, ada):
    doc = new_doc(client, ada)
    add_renewal(doc, date(2026, 6, 30), "10")
    add_renewal(doc, date(2026, 7, 1), "1000")
    with SessionLocal() as db:
        summary = build_period_summary(db, db.scalar(select(User)), date(2026, 1, 1), date(2026, 6, 30))
    assert summary.total == Decimal("10.00")


def test_upcoming_expiries_estimate_from_the_last_recorded_cost(client, ada):
    renewed = new_doc(client, ada, title="Insurance", expiry_date="2026-08-15")
    add_renewal(renewed, date(2025, 8, 1), "90000")
    add_renewal(renewed, date(2026, 1, 1), None)  # a newer renewal with no cost: skip it
    add_renewal(renewed, date(2025, 12, 1), "120000")
    new_doc(client, ada, title="Never renewed", expiry_date="2026-09-01")
    new_doc(client, ada, title="Too far away", expiry_date="2027-06-01")
    new_doc(client, ada, title="Already expired", expiry_date="2026-06-01")
    gone = new_doc(client, ada, title="Deleted", expiry_date="2026-08-01")
    client.delete(f"/documents/{gone}", headers=ada)
    with SessionLocal() as db:
        items = upcoming_expiries(db, db.scalar(select(User)), date(2026, 7, 2))
    assert [(i.title, i.estimated_cost, i.days_left) for i in items] == [
        ("Insurance", Decimal("120000.00"), 44),
        ("Never renewed", None, 61),
    ]


# ------------------------------------------------------------------------ the job
def test_a_user_with_history_gets_one_report_with_the_right_content(client, ada, outbox, frontend_url):
    frontend_url("https://app.example.com")
    with_history(client, ada)
    summary = run(JULY, outbox)
    assert (summary.sent, summary.failed, summary.empty) == (1, 0, 0)
    message = outbox.sent[0]
    assert message.to == "ada@example.com" and message.subject == "Your January – June 2026 renewals report"
    assert "₦150,000.50" in message.html and "2 renewals" in message.html
    assert "Coming up in the next six months" in message.html and "Car insurance" in message.html
    assert "https://app.example.com/reports" in message.html
    assert [(d.period, d.status) for d in dispatches()] == [("2026-H1", ReminderStatus.SENT)]
    assert message.idempotency_key == f"report-{dispatches()[0].id}"


def test_running_again_never_sends_a_second_copy(client, ada, outbox):
    with_history(client, ada)
    run(JULY, outbox)
    again = run(JULY + timedelta(hours=1), outbox)
    next_day = run(JULY + timedelta(days=1), outbox)
    assert len(outbox.sent) == 1 and again.sent == 0 and next_day.sent == 0


def test_january_reports_on_the_previous_years_second_half(client, ada, outbox):
    doc = new_doc(client, ada, expiry_date="2026-12-01")
    add_renewal(doc, date(2025, 9, 1), "25000")
    run(datetime(2026, 1, 3, 12, 0, tzinfo=UTC), outbox)
    assert outbox.sent[0].subject == "Your July – December 2025 renewals report"
    assert dispatches()[0].period == "2025-H2"


def test_nothing_is_sent_outside_the_report_window(client, ada, outbox):
    with_history(client, ada)
    for moment in (datetime(2026, 7, 9, 12, 0, tzinfo=UTC), datetime(2026, 3, 3, 12, 0, tzinfo=UTC), datetime(2026, 12, 31, 12, 0, tzinfo=UTC)):
        assert run(moment, outbox).sent == 0
    assert outbox.sent == [] and dispatches() == []


def test_the_catch_up_window_covers_the_first_seven_days(client, ada, outbox):
    with_history(client, ada)
    assert run(datetime(2026, 7, 7, 12, 0, tzinfo=UTC), outbox).sent == 1  # day 7: still inside


def test_nothing_goes_out_before_8am_local_time(client, ada, outbox):
    with_history(client, ada)
    assert run(datetime(2026, 7, 2, 6, 0, tzinfo=UTC), outbox).sent == 0  # 07:00 in Lagos
    assert run(datetime(2026, 7, 2, 7, 30, tzinfo=UTC), outbox).sent == 1  # 08:30 in Lagos


def test_each_user_is_judged_in_their_own_timezone(client, outbox):
    la = auth_headers(client, "la@example.com", "America/Los_Angeles")
    doc = new_doc(client, la, expiry_date="2026-12-01")
    add_renewal(doc, date(2026, 4, 1), "5000")
    # 12:00 UTC on July 2 is 05:00 in Los Angeles (too early) but 16:00 UTC is 09:00.
    assert run(datetime(2026, 7, 2, 12, 0, tzinfo=UTC), outbox).sent == 0
    assert run(datetime(2026, 7, 2, 16, 0, tzinfo=UTC), outbox).sent == 1
    # And at 00:30 UTC on 1 July it is still 30 June there: not report season yet.
    assert report_period(datetime(2026, 7, 1, 0, 30, tzinfo=UTC).astimezone(ZoneInfo("America/Los_Angeles")).date()) is None


def test_users_who_opted_out_or_are_inactive_get_nothing(client, ada, bola, outbox):
    with_history(client, ada)
    doc = new_doc(client, bola, expiry_date="2026-09-01")
    add_renewal(doc, date(2026, 2, 1), "1000")
    assert client.patch("/auth/me", json={"report_emails": False}, headers=ada).status_code == 200
    with SessionLocal() as db:
        db.execute(update(User).where(User.email == "bola@example.com").values(is_active=False))
        db.commit()
    assert run(JULY, outbox).sent == 0 and dispatches() == []


def test_an_account_with_nothing_to_say_is_skipped_once_and_not_retried(client, ada, outbox):
    summary = run(JULY, outbox)  # no documents, no renewals
    assert (summary.sent, summary.empty) == (0, 1) and outbox.sent == []
    assert [d.status for d in dispatches()] == [ReminderStatus.SKIPPED]
    assert run(JULY + timedelta(hours=1), outbox).empty == 0  # not re-evaluated every hour


def test_a_user_with_only_upcoming_expiries_still_gets_a_report(client, ada, outbox):
    new_doc(client, ada, title="Permit", expiry_date="2026-08-20")
    assert run(JULY, outbox).sent == 1
    assert "You didn't mark any renewals in this period." in outbox.sent[0].text
    assert "Permit" in outbox.sent[0].text


def test_a_failed_send_is_recorded_retried_and_never_duplicated(client, ada, outbox):
    with_history(client, ada)
    outbox.fail_with = "provider down"
    first = run(JULY, outbox)
    assert (first.sent, first.failed) == (0, 1)
    assert [(d.status, "provider down" in d.error) for d in dispatches()] == [(ReminderStatus.FAILED, True)]
    outbox.fail_with = None
    retry = run(JULY + timedelta(hours=1), outbox)
    assert retry.sent == 1 and len(outbox.sent) == 1
    assert [d.status for d in dispatches()] == [ReminderStatus.SENT] and dispatches()[0].error is None
    assert run(JULY + timedelta(hours=2), outbox).sent == 0


def test_one_users_failure_does_not_stop_the_others(client, ada, bola, outbox):
    for headers in (ada, bola):
        doc = new_doc(client, headers, expiry_date="2026-09-01")
        add_renewal(doc, date(2026, 2, 1), "1000")
    calls = []

    def flaky(message):
        calls.append(message.to)
        if message.to == "ada@example.com":
            raise RuntimeError("boom")
        outbox.sent.append(message)

    with SessionLocal() as db:
        summary = run_semiannual_reports(db, JULY, send=flaky)
    assert (summary.sent, summary.failed) == (1, 1) and len(calls) == 2


def test_a_stale_pending_claim_is_taken_over_but_a_fresh_one_is_left_alone(client, ada, outbox):
    with_history(client, ada)
    with SessionLocal() as db:
        user = db.scalar(select(User))
        db.add(EmailDispatch(user_id=user.id, kind=periodic.KIND, period="2026-H1", status=ReminderStatus.PENDING, sent_at=JULY - timedelta(minutes=1)))
        db.commit()
    assert run(JULY, outbox).sent == 0  # another worker is on it
    with SessionLocal() as db:
        db.execute(update(EmailDispatch).values(sent_at=JULY - timedelta(hours=1)))
        db.commit()
    assert run(JULY, outbox).sent == 1  # that worker crashed long ago


def test_the_dispatch_record_is_unique_per_user_kind_and_period(client, ada):
    from sqlalchemy.exc import IntegrityError

    with_history(client, ada)
    with SessionLocal() as db:
        user = db.scalar(select(User))
        for _ in range(2):
            db.add(EmailDispatch(user_id=user.id, kind="cost_report", period="2026-H1", status=ReminderStatus.SENT))
        with pytest.raises(IntegrityError):
            db.commit()


# ------------------------------------------------------------------- the setting
def test_report_emails_default_on_and_can_be_switched_off_and_on(client, ada):
    assert client.get("/auth/me", headers=ada).json()["report_emails"] is True
    assert client.patch("/auth/me", json={"report_emails": False}, headers=ada).json()["report_emails"] is False
    assert client.patch("/auth/me", json={"report_emails": True}, headers=ada).json()["report_emails"] is True
    assert client.patch("/auth/me", json={"report_emails": None}, headers=ada).status_code == 422
    assert client.patch("/auth/me", json={"report_emails": "maybe"}, headers=ada).status_code == 422


# ------------------------------------------------------------------------- Celery
def test_the_report_task_is_registered_scheduled_hourly_and_runs_safely_off_season():
    from app.core.celery_app import celery_app
    from app.modules.reports.tasks import send_semiannual_reports

    assert "reports.send_semiannual_reports" in celery_app.tasks
    entry = celery_app.conf.beat_schedule["send-semiannual-reports-hourly"]
    assert entry["task"] == "reports.send_semiannual_reports" and str(entry["schedule"]).startswith("<crontab: 20 *")
    result = send_semiannual_reports()
    assert set(result) == {"sent", "failed", "skipped", "empty"}
