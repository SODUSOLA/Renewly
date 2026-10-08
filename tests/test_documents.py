"""Tests for documents: CRUD, derived status, soft delete, renewal and isolation."""
import uuid
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from app.common.dates import today_for
from app.modules.documents.service import compute_status

# Both test users use the default timezone, so "today" is the same for them.
TODAY = today_for(SimpleNamespace(timezone="Africa/Lagos"))


# func to turn "days from today" into an ISO date string
def in_days(days: int) -> str:
    """Return the ISO date `days` from today (negative = in the past)."""
    return (TODAY + timedelta(days=days)).isoformat()


# func to create a document and return the response
def make_doc(client, headers, **overrides):
    """POST a document (defaults overridable) and return the response."""
    body = {
        "type": "insurance",
        "title": "Car insurance",
        "expiry_date": in_days(100),
        **overrides,
    }
    return client.post("/documents", json=body, headers=headers)


# func to create a vehicle and return its id
def make_vehicle_id(client, headers, plate="ABC123") -> str:
    """Create a vehicle and return its id."""
    res = client.post(
        "/vehicles", json={"nickname": "Car", "plate_number": plate}, headers=headers
    )
    return res.json()["id"]


def test_create_uses_default_offsets_and_derives_status(client, ada):
    res = make_doc(client, ada)
    assert res.status_code == 201
    body = res.json()
    assert body["reminder_offsets"] == [90, 30, 14, 7, 1]
    assert body["days_left"] == 100
    assert body["status"] == "valid"


@pytest.mark.parametrize(
    "days, expected",
    [(-1, "expired"), (0, "expiring_soon"), (30, "expiring_soon"), (31, "valid")],
)
def test_status_boundaries(client, ada, days, expected):
    body = make_doc(client, ada, expiry_date=in_days(days)).json()
    assert body["status"] == expected
    assert body["days_left"] == days


def test_compute_status_is_pure():
    assert compute_status(-5).value == "expired"
    assert compute_status(10).value == "expiring_soon"
    assert compute_status(500).value == "valid"


def test_custom_type_requires_label_and_other_types_drop_it(client, ada):
    assert make_doc(client, ada, type="custom").status_code == 422
    ok = make_doc(client, ada, type="custom", custom_type_label="Gym card")
    assert ok.status_code == 201
    assert ok.json()["custom_type_label"] == "Gym card"
    stray = make_doc(client, ada, type="permit", custom_type_label="ignored")
    assert stray.json()["custom_type_label"] is None


def test_expiry_before_issue_is_rejected(client, ada):
    res = make_doc(client, ada, issue_date=in_days(10), expiry_date=in_days(5))
    assert res.status_code == 422


def test_offsets_are_validated_sorted_and_deduplicated(client, ada):
    ok = make_doc(client, ada, reminder_offsets=[7, 30, 7, 0])
    assert ok.json()["reminder_offsets"] == [30, 7, 0]
    assert make_doc(client, ada, reminder_offsets=[-1]).status_code == 422
    assert make_doc(client, ada, reminder_offsets=[400]).status_code == 422
    assert make_doc(client, ada, reminder_offsets=list(range(11))).status_code == 422
    assert make_doc(client, ada, reminder_offsets=[]).json()["reminder_offsets"] == []


def test_vehicle_must_belong_to_the_user(client, ada, bola):
    bola_vehicle = make_vehicle_id(client, bola)
    assert make_doc(client, ada, vehicle_id=bola_vehicle).status_code == 422
    ada_vehicle = make_vehicle_id(client, ada)
    assert make_doc(client, ada, vehicle_id=ada_vehicle).status_code == 201


def test_list_is_sorted_and_filterable(client, ada):
    vehicle = make_vehicle_id(client, ada)
    make_doc(client, ada, title="Far", expiry_date=in_days(200))
    make_doc(client, ada, title="Soon", expiry_date=in_days(5), vehicle_id=vehicle)
    make_doc(client, ada, title="Old", expiry_date=in_days(-3), type="permit")

    titles = lambda params="": [  # noqa: E731
        d["title"] for d in client.get(f"/documents{params}", headers=ada).json()
    ]
    assert titles() == ["Old", "Soon", "Far"]
    assert titles("?status=expired") == ["Old"]
    assert titles("?status=expiring_soon") == ["Soon"]
    assert titles("?status=valid") == ["Far"]
    assert titles("?type=permit") == ["Old"]
    assert titles(f"?vehicle_id={vehicle}") == ["Soon"]


def test_user_cannot_touch_another_users_document(client, ada, bola):
    doc_id = make_doc(client, ada).json()["id"]
    url = f"/documents/{doc_id}"
    assert client.get(url, headers=bola).status_code == 404
    assert client.patch(url, json={"title": "x"}, headers=bola).status_code == 404
    assert client.delete(url, headers=bola).status_code == 404
    renew = {"new_expiry": in_days(400)}
    assert client.post(f"{url}/renew", json=renew, headers=bola).status_code == 404
    assert client.get(f"{url}/renewals", headers=bola).status_code == 404
    assert client.get("/documents", headers=bola).json() == []


def test_patch_updates_fields_and_rechecks_rules(client, ada):
    doc_id = make_doc(client, ada, issue_date=in_days(-10)).json()["id"]
    url = f"/documents/{doc_id}"
    res = client.patch(url, json={"title": "Renamed", "expiry_date": in_days(3)}, headers=ada)
    assert res.json()["title"] == "Renamed"
    assert res.json()["status"] == "expiring_soon"
    assert client.patch(url, json={"expiry_date": in_days(-20)}, headers=ada).status_code == 422
    assert client.patch(url, json={"type": "custom"}, headers=ada).status_code == 422
    assert client.patch(url, json={"title": None}, headers=ada).status_code == 422
    # A rejected patch must not have changed anything.
    assert client.get(url, headers=ada).json()["title"] == "Renamed"


def test_soft_delete_hides_the_document(client, ada):
    doc_id = make_doc(client, ada).json()["id"]
    assert client.delete(f"/documents/{doc_id}", headers=ada).status_code == 204
    assert client.get(f"/documents/{doc_id}", headers=ada).status_code == 404
    assert client.get("/documents", headers=ada).json() == []
    assert client.delete(f"/documents/{doc_id}", headers=ada).status_code == 404


def test_renew_updates_expiry_and_writes_history(client, ada):
    old_expiry = in_days(5)
    doc_id = make_doc(client, ada, expiry_date=old_expiry).json()["id"]
    res = client.post(
        f"/documents/{doc_id}/renew",
        json={"new_expiry": in_days(370), "cost": "15000.50", "notes": "Annual"},
        headers=ada,
    )
    assert res.status_code == 200
    assert res.json()["expiry_date"] == in_days(370)
    assert res.json()["status"] == "valid"

    history = client.get(f"/documents/{doc_id}/renewals", headers=ada).json()
    assert len(history) == 1
    assert history[0]["previous_expiry"] == old_expiry
    assert history[0]["new_expiry"] == in_days(370)
    assert history[0]["renewed_on"] == TODAY.isoformat()
    assert history[0]["cost"] == "15000.50"


def test_renew_requires_a_later_date_and_logs_nothing_on_failure(client, ada):
    doc_id = make_doc(client, ada, expiry_date=in_days(50)).json()["id"]
    for bad in (in_days(50), in_days(10)):
        res = client.post(f"/documents/{doc_id}/renew", json={"new_expiry": bad}, headers=ada)
        assert res.status_code == 422
    assert client.get(f"/documents/{doc_id}/renewals", headers=ada).json() == []
    assert client.get(f"/documents/{doc_id}", headers=ada).json()["expiry_date"] == in_days(50)


def test_renewals_are_listed_newest_first(client, ada):
    doc_id = make_doc(client, ada).json()["id"]
    for days in (200, 300):
        client.post(f"/documents/{doc_id}/renew", json={"new_expiry": in_days(days)}, headers=ada)
    history = client.get(f"/documents/{doc_id}/renewals", headers=ada).json()
    assert [h["new_expiry"] for h in history] == [in_days(300), in_days(200)]


def test_deleting_a_vehicle_keeps_its_documents(client, ada):
    vehicle = make_vehicle_id(client, ada)
    doc_id = make_doc(client, ada, vehicle_id=vehicle).json()["id"]
    assert client.delete(f"/vehicles/{vehicle}", headers=ada).status_code == 204
    doc = client.get(f"/documents/{doc_id}", headers=ada)
    assert doc.status_code == 200
    assert doc.json()["vehicle_id"] is None


def test_endpoints_require_authentication_and_valid_ids(client, ada):
    assert client.get("/documents").status_code == 401
    assert client.get(f"/documents/{uuid.uuid4()}", headers=ada).status_code == 404
    assert client.get("/documents/not-a-uuid", headers=ada).status_code == 422
