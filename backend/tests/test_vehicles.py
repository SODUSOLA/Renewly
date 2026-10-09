"""Tests for the vehicles endpoints, including cross-user isolation."""
import uuid


# func to create a vehicle and return the response
def make_vehicle(client, headers, **overrides):
    """POST a vehicle (defaults overridable) and return the response."""
    body = {"nickname": "Daily", "plate_number": "abc 123 xy", **overrides}
    return client.post("/vehicles", json=body, headers=headers)


# func: test create normalizes plate
def test_create_normalizes_plate(client, ada):
    res = make_vehicle(client, ada, make="Toyota", year=2018)
    assert res.status_code == 201
    assert res.json()["plate_number"] == "ABC123XY"
    assert res.json()["make"] == "Toyota"


# func: test duplicate plate same user is 409 even with different spacing
def test_duplicate_plate_same_user_is_409_even_with_different_spacing(client, ada):
    assert make_vehicle(client, ada).status_code == 201
    assert make_vehicle(client, ada, plate_number="ABC123XY").status_code == 409


# func: test same plate allowed for different users
def test_same_plate_allowed_for_different_users(client, ada, bola):
    assert make_vehicle(client, ada).status_code == 201
    assert make_vehicle(client, bola).status_code == 201


# func: test list returns only own vehicles
def test_list_returns_only_own_vehicles(client, ada, bola):
    make_vehicle(client, ada, plate_number="AAA111")
    make_vehicle(client, bola, plate_number="BBB222")
    plates = [v["plate_number"] for v in client.get("/vehicles", headers=ada).json()]
    assert plates == ["AAA111"]


# func: test user cannot read update or delete another users vehicle
def test_user_cannot_read_update_or_delete_another_users_vehicle(client, ada, bola):
    vehicle_id = make_vehicle(client, ada).json()["id"]
    url = f"/vehicles/{vehicle_id}"
    assert client.get(url, headers=bola).status_code == 404
    assert client.patch(url, json={"nickname": "Hacked"}, headers=bola).status_code == 404
    assert client.delete(url, headers=bola).status_code == 404
    # Still intact for the owner.
    assert client.get(url, headers=ada).json()["nickname"] == "Daily"


# func: test patch changes only sent fields
def test_patch_changes_only_sent_fields(client, ada):
    vehicle_id = make_vehicle(client, ada, make="Toyota").json()["id"]
    res = client.patch(
        f"/vehicles/{vehicle_id}", json={"nickname": "Work car"}, headers=ada
    )
    assert res.status_code == 200
    assert res.json()["nickname"] == "Work car"
    assert res.json()["make"] == "Toyota"
    assert res.json()["plate_number"] == "ABC123XY"


# func: test patch to existing plate is 409
def test_patch_to_existing_plate_is_409(client, ada):
    make_vehicle(client, ada, plate_number="AAA111")
    other = make_vehicle(client, ada, plate_number="BBB222").json()["id"]
    res = client.patch(f"/vehicles/{other}", json={"plate_number": "aaa 111"}, headers=ada)
    assert res.status_code == 409


# func: test patch rejects null for required fields
def test_patch_rejects_null_for_required_fields(client, ada):
    vehicle_id = make_vehicle(client, ada).json()["id"]
    res = client.patch(f"/vehicles/{vehicle_id}", json={"nickname": None}, headers=ada)
    assert res.status_code == 422


# func: test delete removes vehicle
def test_delete_removes_vehicle(client, ada):
    vehicle_id = make_vehicle(client, ada).json()["id"]
    assert client.delete(f"/vehicles/{vehicle_id}", headers=ada).status_code == 204
    assert client.get(f"/vehicles/{vehicle_id}", headers=ada).status_code == 404


# func: test unknown id is 404 and bad id is 422
def test_unknown_id_is_404_and_bad_id_is_422(client, ada):
    assert client.get(f"/vehicles/{uuid.uuid4()}", headers=ada).status_code == 404
    assert client.get("/vehicles/not-a-uuid", headers=ada).status_code == 422


# func: test endpoints require authentication
def test_endpoints_require_authentication(client):
    assert client.get("/vehicles").status_code == 401
    assert client.post("/vehicles", json={"nickname": "x", "plate_number": "y"}).status_code == 401


# func: test validation rejects blank plate and bad year
def test_validation_rejects_blank_plate_and_bad_year(client, ada):
    assert make_vehicle(client, ada, plate_number="   ").status_code == 422
    assert make_vehicle(client, ada, year=1800).status_code == 422
