"""Tests for the getting-started journey's backend: saved flags and progress counts."""
from datetime import date

import pytest

from tests.test_documents import make_doc, make_vehicle_id
from tests.test_reports import add_renewal, new_doc


# ------------------------------------------------------------------ saved flags
def test_a_new_user_has_no_onboarding_flags(client, ada):
    assert client.get("/auth/me", headers=ada).json()["onboarding"] == {}


def test_flags_are_merged_not_replaced_and_survive_other_profile_changes(client, ada):
    first = client.patch("/auth/me/onboarding", json={"tour_done": True}, headers=ada)
    assert first.status_code == 200 and first.json()["onboarding"] == {"tour_done": True}
    second = client.patch("/auth/me/onboarding", json={"checklist_dismissed": True}, headers=ada)
    assert second.json()["onboarding"] == {"tour_done": True, "checklist_dismissed": True}
    client.patch("/auth/me", json={"full_name": "Ada O."}, headers=ada)
    assert client.get("/auth/me", headers=ada).json()["onboarding"] == {"tour_done": True, "checklist_dismissed": True}


def test_a_flag_can_be_turned_back_off_to_show_the_checklist_again(client, ada):
    client.patch("/auth/me/onboarding", json={"checklist_dismissed": True}, headers=ada)
    res = client.patch("/auth/me/onboarding", json={"checklist_dismissed": False}, headers=ada)
    assert res.json()["onboarding"] == {"checklist_dismissed": False}


@pytest.mark.parametrize(
    "bad",
    [{"made_up_flag": True}, {"tour_done": None}, {"tour_done": "yes please"}, {"tour_done": [1]}, {"tour_done": True, "extra": 1}],
)
def test_unknown_keys_and_non_booleans_are_rejected(client, ada, bad):
    assert client.patch("/auth/me/onboarding", json=bad, headers=ada).status_code == 422
    assert client.get("/auth/me", headers=ada).json()["onboarding"] == {}


def test_an_empty_update_changes_nothing(client, ada):
    assert client.patch("/auth/me/onboarding", json={}, headers=ada).json()["onboarding"] == {}


def test_flags_belong_to_one_user_and_need_a_login(client, ada, bola):
    client.patch("/auth/me/onboarding", json={"tour_done": True}, headers=ada)
    assert client.get("/auth/me", headers=bola).json()["onboarding"] == {}
    assert client.patch("/auth/me/onboarding", json={"tour_done": True}).status_code == 401


# --------------------------------------------------------------------- progress
def test_progress_starts_at_zero(client, ada):
    res = client.get("/onboarding/progress", headers=ada)
    assert res.status_code == 200
    assert res.json() == {"documents": 0, "vehicles": 0, "renewals": 0, "renewals_with_cost": 0}


def test_progress_counts_real_data(client, ada):
    make_vehicle_id(client, ada, "ABC123")
    doc = new_doc(client, ada, title="Insurance")
    new_doc(client, ada, title="Licence", type="driver_license")
    add_renewal(doc, date(2026, 3, 1), "20000")
    add_renewal(doc, date(2026, 4, 1), None)
    assert client.get("/onboarding/progress", headers=ada).json() == {
        "documents": 2, "vehicles": 1, "renewals": 2, "renewals_with_cost": 1,
    }


def test_progress_follows_the_data_as_it_changes(client, ada):
    doc = new_doc(client, ada)
    assert client.get("/onboarding/progress", headers=ada).json()["documents"] == 1
    client.post(f"/documents/{doc}/renew", json={"new_expiry": "2090-01-01", "cost": "500"}, headers=ada)
    progress = client.get("/onboarding/progress", headers=ada).json()
    assert (progress["renewals"], progress["renewals_with_cost"]) == (1, 1)
    client.delete(f"/documents/{doc}", headers=ada)  # deleting hides its renewals too
    assert client.get("/onboarding/progress", headers=ada).json() == {"documents": 0, "vehicles": 0, "renewals": 0, "renewals_with_cost": 0}


def test_progress_is_per_user_and_needs_a_login(client, ada, bola):
    make_doc(client, ada)
    assert client.get("/onboarding/progress", headers=bola).json()["documents"] == 0
    assert client.get("/onboarding/progress").status_code == 401
