"""Tests for the dashboard grouping, counts and isolation."""
from tests.test_documents import in_days, make_doc, TODAY


# func to fetch the dashboard JSON
def dashboard(client, headers) -> dict:
    """GET /dashboard and return the parsed body."""
    res = client.get("/dashboard", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def test_empty_dashboard(client, ada):
    body = dashboard(client, ada)
    assert body["today"] == TODAY.isoformat()
    assert body["counts"] == {"expired": 0, "expiring_soon": 0, "valid": 0, "total": 0}
    assert body["expired"] == body["expiring_soon"] == body["valid"] == []


def test_documents_are_grouped_counted_and_ordered(client, ada):
    # Hand-computed: days left -> expected group.
    cases = {"gone-10": -10, "gone-1": -1, "today": 0, "edge30": 30,
             "edge31": 31, "far": 400}
    for title, days in cases.items():
        make_doc(client, ada, title=title, expiry_date=in_days(days))

    body = dashboard(client, ada)
    titles = lambda key: [d["title"] for d in body[key]]  # noqa: E731
    assert titles("expired") == ["gone-10", "gone-1"]  # most overdue first
    assert titles("expiring_soon") == ["today", "edge30"]
    assert titles("valid") == ["edge31", "far"]
    assert body["counts"] == {"expired": 2, "expiring_soon": 2, "valid": 2, "total": 6}
    assert body["expired"][0]["days_left"] == -10


def test_soft_deleted_documents_are_excluded(client, ada):
    doc_id = make_doc(client, ada, expiry_date=in_days(-5)).json()["id"]
    client.delete(f"/documents/{doc_id}", headers=ada)
    assert dashboard(client, ada)["counts"]["total"] == 0


def test_renewal_moves_a_document_to_valid(client, ada):
    doc_id = make_doc(client, ada, expiry_date=in_days(-5)).json()["id"]
    assert dashboard(client, ada)["counts"]["expired"] == 1
    client.post(f"/documents/{doc_id}/renew", json={"new_expiry": in_days(365)}, headers=ada)
    counts = dashboard(client, ada)["counts"]
    assert counts["expired"] == 0 and counts["valid"] == 1


def test_dashboard_only_shows_own_documents(client, ada, bola):
    make_doc(client, ada)
    assert dashboard(client, bola)["counts"]["total"] == 0


def test_dashboard_requires_authentication(client):
    assert client.get("/dashboard").status_code == 401
