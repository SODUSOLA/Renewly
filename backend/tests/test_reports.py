"""Tests for cost reports: totals, breakdowns, CSV export and editing a renewal's cost."""
import csv
import io
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.common.dates import today_for
from app.core.database import SessionLocal
from app.modules.documents.models import RenewalHistory
from tests.helpers import auth_headers
from tests.test_documents import in_days, make_doc, make_vehicle_id

THIS_YEAR = today_for(SimpleNamespace(timezone="Africa/Lagos")).year


# func to record a past renewal directly (the API can only record "today")
def add_renewal(doc_id: str, renewed_on: date, cost: str | None, notes: str | None = None) -> str:
    """Insert a renewal_history row with a chosen date and cost; return its id."""
    with SessionLocal() as db:
        row = RenewalHistory(
            document_id=doc_id,
            previous_expiry=date(renewed_on.year, 1, 1),
            new_expiry=date(renewed_on.year + 1, 1, 1),
            renewed_on=renewed_on,
            cost=Decimal(cost) if cost is not None else None,
            notes=notes,
        )
        db.add(row)
        db.commit()
        return str(row.id)


# func to create a document and return its id
def new_doc(client, headers, **overrides) -> str:
    """Create a document through the API and return its id."""
    res = make_doc(client, headers, **overrides)
    assert res.status_code == 201, res.text
    return res.json()["id"]


# func to fetch the report
def report(client, headers, year: int | None = None) -> dict:
    """GET /reports/costs (optionally for a year) and return the JSON."""
    res = client.get("/reports/costs", params={"year": year} if year else {}, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def populated(client, ada):
    """Two vehicles' worth of 2026 renewals with hand-computable numbers, plus 2025 history.

    2026: insurance Corolla 150000.50 (Jan 10) and 20000 (Mar 5); registration Corolla 12000 (Mar 20);
    permit with no vehicle 5000.25 (Mar 30); gym (custom, no vehicle) with no cost recorded (Jul 1).
    2025: insurance Corolla 100000.
    """
    corolla = make_vehicle_id(client, ada, "ABC123")
    insurance = new_doc(client, ada, title="Car insurance", type="insurance", vehicle_id=corolla)
    registration = new_doc(client, ada, title="Road tax", type="vehicle_registration", vehicle_id=corolla)
    permit = new_doc(client, ada, title="Parking permit", type="permit")
    gym = new_doc(client, ada, title="Gym", type="custom", custom_type_label="Gym membership")
    ids = {"insurance": insurance, "registration": registration, "permit": permit, "gym": gym, "vehicle": corolla}
    add_renewal(insurance, date(2026, 1, 10), "150000.50")
    add_renewal(insurance, date(2026, 3, 5), "20000")
    add_renewal(registration, date(2026, 3, 20), "12000")
    add_renewal(permit, date(2026, 3, 30), "5000.25")
    add_renewal(gym, date(2026, 7, 1), None)
    add_renewal(insurance, date(2025, 2, 1), "100000")
    return ids


# ------------------------------------------------------------------- the report
def test_an_empty_report_is_all_zeros_and_always_offers_the_current_year(client, ada):
    body = report(client, ada)
    assert body["year"] == THIS_YEAR and body["currency"] == "NGN"
    assert body["available_years"] == [THIS_YEAR]
    assert body["totals"] == {"total": "0.00", "previous_year_total": "0.00", "renewals": 0, "renewals_with_cost": 0}
    assert [m["month"] for m in body["by_month"]] == list(range(1, 13))
    assert all(m["total"] == "0.00" and m["renewals"] == 0 for m in body["by_month"])
    assert body["by_type"] == [] and body["by_vehicle"] == [] and body["missing_cost"] == []


def test_totals_are_hand_computed_exactly(client, ada, populated):
    totals = report(client, ada, 2026)["totals"]
    # 150000.50 + 20000 + 12000 + 5000.25 = 187000.75; the gym renewal has no cost.
    assert totals == {"total": "187000.75", "previous_year_total": "100000.00", "renewals": 5, "renewals_with_cost": 4}


def test_months_are_bucketed_and_empty_months_are_zero(client, ada, populated):
    by_month = {m["month"]: m for m in report(client, ada, 2026)["by_month"]}
    assert by_month[1] == {"month": 1, "total": "150000.50", "renewals": 1}
    assert by_month[3] == {"month": 3, "total": "37000.25", "renewals": 3}  # 20000 + 12000 + 5000.25
    assert by_month[7] == {"month": 7, "total": "0.00", "renewals": 1}  # a renewal with no cost
    assert by_month[2]["total"] == "0.00" and by_month[2]["renewals"] == 0


def test_spending_by_type_uses_custom_labels_and_is_sorted_biggest_first(client, ada, populated):
    by_type = report(client, ada, 2026)["by_type"]
    assert by_type == [
        {"label": "Insurance", "total": "170000.50", "renewals": 2},
        {"label": "Vehicle registration", "total": "12000.00", "renewals": 1},
        {"label": "Permit", "total": "5000.25", "renewals": 1},
        {"label": "Gym membership", "total": "0.00", "renewals": 1},
    ]


def test_spending_by_vehicle_includes_documents_with_no_vehicle(client, ada, populated):
    by_vehicle = report(client, ada, 2026)["by_vehicle"]
    assert by_vehicle[0] == {"label": "Car (ABC123)", "total": "182000.50", "renewals": 3, "vehicle_id": populated["vehicle"]}
    assert by_vehicle[1] == {"label": "No vehicle", "total": "5000.25", "renewals": 2, "vehicle_id": None}


def test_renewals_without_a_cost_are_listed_so_they_can_be_fixed(client, ada, populated):
    body = report(client, ada, 2026)
    assert body["missing_cost_count"] == 1
    assert body["missing_cost"] == [
        {"renewal_id": body["missing_cost"][0]["renewal_id"], "document_id": populated["gym"], "title": "Gym", "renewed_on": "2026-07-01"}
    ]


def test_years_are_offered_newest_first_and_other_years_can_be_chosen(client, ada, populated):
    assert report(client, ada, 2026)["available_years"] == sorted({THIS_YEAR, 2026, 2025}, reverse=True)
    previous = report(client, ada, 2025)
    assert previous["totals"]["total"] == "100000.00" and previous["totals"]["previous_year_total"] == "0.00"


def test_year_boundaries_are_respected(client, ada):
    doc = new_doc(client, ada)
    add_renewal(doc, date(2026, 12, 31), "10")
    add_renewal(doc, date(2027, 1, 1), "20")
    assert report(client, ada, 2026)["totals"]["total"] == "10.00"
    assert report(client, ada, 2027)["totals"]["total"] == "20.00"
    assert report(client, ada, 2027)["totals"]["previous_year_total"] == "10.00"


def test_pennies_add_up_exactly(client, ada):
    doc = new_doc(client, ada)
    add_renewal(doc, date(2026, 5, 1), "0.10")
    add_renewal(doc, date(2026, 5, 2), "0.20")
    assert report(client, ada, 2026)["totals"]["total"] == "0.30"


def test_deleted_documents_are_left_out(client, ada, populated):
    client.delete(f"/documents/{populated['insurance']}", headers=ada)
    totals = report(client, ada, 2026)["totals"]
    assert totals["total"] == "17000.25" and totals["renewals"] == 3
    assert report(client, ada, 2025)["totals"]["total"] == "0.00"


def test_users_only_see_their_own_spending(client, ada, bola, populated):
    assert report(client, bola, 2026)["totals"]["total"] == "0.00"
    assert report(client, bola, 2026)["by_type"] == []


@pytest.mark.parametrize("year", ["1999", "2101", "abc"])
def test_invalid_years_are_rejected(client, ada, year):
    assert client.get("/reports/costs", params={"year": year}, headers=ada).status_code == 422


def test_reports_require_authentication(client):
    assert client.get("/reports/costs").status_code == 401
    assert client.get("/reports/costs.csv").status_code == 401


def test_the_missing_cost_list_is_capped_but_the_count_is_exact(client, ada):
    doc = new_doc(client, ada)
    for day in range(1, 26):
        add_renewal(doc, date(2026, 6, day), None)
    body = report(client, ada, 2026)
    assert body["missing_cost_count"] == 25 and len(body["missing_cost"]) == 20
    assert body["missing_cost"][0]["renewed_on"] == "2026-06-25"  # newest first


# ------------------------------------------------------------------------- CSV
def test_csv_lists_every_renewal_of_the_year_oldest_first(client, ada, populated):
    res = client.get("/reports/costs.csv", params={"year": 2026}, headers=ada)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert res.headers["content-disposition"] == 'attachment; filename="renewly-renewals-2026.csv"'
    assert res.text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(res.text.lstrip("﻿"))))
    assert rows[0] == ["Renewed on", "Document", "Type", "Vehicle", "Previous expiry", "New expiry", "Cost (NGN)", "Notes"]
    assert [r[0] for r in rows[1:]] == ["2026-01-10", "2026-03-05", "2026-03-20", "2026-03-30", "2026-07-01"]
    assert rows[1][1:4] == ["Car insurance", "Insurance", "Car (ABC123)"]
    assert rows[1][6] == "150000.50" and rows[5][6] == ""  # the gym renewal has no cost
    assert rows[5][2] == "Gym membership" and rows[4][3] == ""  # custom label; no vehicle


def test_csv_neutralises_spreadsheet_formulas(client, ada):
    doc = new_doc(client, ada, title='=HYPERLINK("http://evil.example","click")')
    add_renewal(doc, date(2026, 2, 2), "50", notes="@SUM(A1)")
    rows = list(csv.reader(io.StringIO(client.get("/reports/costs.csv", params={"year": 2026}, headers=ada).text.lstrip("﻿"))))
    assert rows[1][1].startswith("'=HYPERLINK") and rows[1][7] == "'@SUM(A1)"


def test_csv_only_contains_the_users_own_data(client, ada, bola, populated):
    text = client.get("/reports/costs.csv", params={"year": 2026}, headers=bola).text.lstrip("﻿")
    assert len(list(csv.reader(io.StringIO(text)))) == 1  # header only


def test_csv_defaults_to_the_current_year_in_its_file_name(client, ada):
    res = client.get("/reports/costs.csv", headers=ada)
    assert f"renewly-renewals-{THIS_YEAR}.csv" in res.headers["content-disposition"]


# ------------------------------------------------------- editing a renewal's cost
# func to renewals URL
def renewal_url(doc_id: str, renewal_id: str) -> str:
    """Path of one renewal."""
    return f"/documents/{doc_id}/renewals/{renewal_id}"


def test_a_missing_cost_can_be_added_afterwards_and_the_report_updates(client, ada, populated):
    renewal = report(client, ada, 2026)["missing_cost"][0]["renewal_id"]
    res = client.patch(renewal_url(populated["gym"], renewal), json={"cost": "9500.50", "notes": "Annual"}, headers=ada)
    assert res.status_code == 200 and res.json()["cost"] == "9500.50" and res.json()["notes"] == "Annual"
    body = report(client, ada, 2026)
    assert body["missing_cost_count"] == 0 and body["totals"]["total"] == "196501.25"


def test_null_clears_a_cost_and_omitting_a_field_leaves_it_alone(client, ada, populated):
    renewal = add_renewal(populated["permit"], date(2026, 4, 1), "300", notes="keep me")
    url = renewal_url(populated["permit"], renewal)
    assert client.patch(url, json={"cost": None}, headers=ada).json()["cost"] is None
    result = client.get(f"/documents/{populated['permit']}/renewals", headers=ada).json()
    assert [r["notes"] for r in result if r["id"] == renewal] == ["keep me"]
    assert client.patch(url, json={}, headers=ada).status_code == 200


@pytest.mark.parametrize("bad", [{"cost": "-1"}, {"cost": "abc"}, {"cost": "1.234"}, {"cost": "10000000000"}])
def test_invalid_costs_are_rejected(client, ada, populated, bad):
    renewal = add_renewal(populated["permit"], date(2026, 4, 1), "300")
    assert client.patch(renewal_url(populated["permit"], renewal), json=bad, headers=ada).status_code == 422


def test_renewals_cannot_be_edited_across_users_documents_or_deletions(client, ada, bola, populated):
    renewal = add_renewal(populated["permit"], date(2026, 4, 1), "300")
    url = renewal_url(populated["permit"], renewal)
    assert client.patch(url, json={"cost": "1"}, headers=bola).status_code == 404  # someone else's
    assert client.patch(renewal_url(populated["gym"], renewal), json={"cost": "1"}, headers=ada).status_code == 404  # wrong document
    assert client.patch(renewal_url(populated["permit"], "00000000-0000-0000-0000-000000000000"), json={}, headers=ada).status_code == 404
    client.delete(f"/documents/{populated['permit']}", headers=ada)
    assert client.patch(url, json={"cost": "1"}, headers=ada).status_code == 404  # deleted document
    assert client.patch(url, json={"cost": "1"}).status_code == 401
