"""Tests for the auth endpoints: register, login, /me and password reset."""
import pytest

USER = {
    "email": "Ada@Example.com",
    "password": "correct-horse",
    "full_name": "Ada Obi",
}


# func: register a user (defaults to USER) and return the response
def register(client, **overrides):
    """Register a user (defaults to USER) and return the response."""
    return client.post("/auth/register", json={**USER, **overrides})


# func: log in and return the access token
def login_token(client, email="ada@example.com", password=USER["password"]) -> str:
    """Log in and return the access token."""
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


# func: test register creates user with normalized email
def test_register_creates_user_with_normalized_email(client):
    res = register(client)
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "ada@example.com"
    assert body["timezone"] == "Africa/Lagos"
    assert "password" not in body and "password_hash" not in body


# func: test register duplicate email is rejected case insensitively
def test_register_duplicate_email_is_rejected_case_insensitively(client):
    assert register(client).status_code == 201
    assert register(client, email="ADA@example.com").status_code == 409


# func: test register rejects bad timezone and short password
def test_register_rejects_bad_timezone_and_short_password(client):
    assert register(client, timezone="Mars/Olympus").status_code == 422
    assert register(client, password="short").status_code == 422


# func: test login succeeds and me returns profile
def test_login_succeeds_and_me_returns_profile(client):
    register(client)
    token = login_token(client)
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    assert res.json()["full_name"] == "Ada Obi"


# func: test login with wrong password is rejected
def test_login_with_wrong_password_is_rejected(client):
    register(client)
    res = client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "wrong-password"}
    )
    assert res.status_code == 401


# func: test login with unknown email gets same error
def test_login_with_unknown_email_gets_same_error(client):
    res = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever123"}
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect email or password"


# func: test me requires a valid token
@pytest.mark.parametrize("header", [None, "Bearer not-a-jwt", "Basic abc"])
def test_me_requires_a_valid_token(client, header):
    headers = {"Authorization": header} if header else {}
    assert client.get("/auth/me", headers=headers).status_code == 401


# func: capture reset emails instead of sending them: a list of (email, token)
@pytest.fixture
def sent_emails(monkeypatch):
    """Capture reset emails instead of sending them: a list of (email, token)."""
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "app.modules.auth.router.send_password_reset_email",
        lambda email, token: sent.append((email, token)),
    )
    return sent


# func: test password reset full flow
def test_password_reset_full_flow(client, sent_emails):
    register(client)
    res = client.post("/auth/forgot-password", json={"email": "ada@example.com"})
    assert res.status_code == 202
    assert len(sent_emails) == 1
    _, token = sent_emails[0]

    res = client.post(
        "/auth/reset-password", json={"token": token, "new_password": "brand-new-pass"}
    )
    assert res.status_code == 200

    # Old password no longer works, new one does.
    old = client.post(
        "/auth/login", json={"email": "ada@example.com", "password": USER["password"]}
    )
    assert old.status_code == 401
    assert login_token(client, password="brand-new-pass")


# func: test reset token is single use
def test_reset_token_is_single_use(client, sent_emails):
    register(client)
    client.post("/auth/forgot-password", json={"email": "ada@example.com"})
    _, token = sent_emails[0]
    body = {"token": token, "new_password": "brand-new-pass"}
    assert client.post("/auth/reset-password", json=body).status_code == 200
    assert client.post("/auth/reset-password", json=body).status_code == 400


# func: test forgot password for unknown email looks identical
def test_forgot_password_for_unknown_email_looks_identical(client, sent_emails):
    res = client.post("/auth/forgot-password", json={"email": "ghost@example.com"})
    assert res.status_code == 202
    assert sent_emails == []


# func: test reset with garbage token is rejected
def test_reset_with_garbage_token_is_rejected(client):
    res = client.post(
        "/auth/reset-password", json={"token": "nope", "new_password": "brand-new-pass"}
    )
    assert res.status_code == 400


# func to deactivate a user directly in the database
def deactivate(email: str) -> None:
    """Mark the user inactive, as an admin or a future 'delete account' would."""
    from sqlalchemy import update

    from app.core.database import SessionLocal
    from app.modules.auth.models import User

    with SessionLocal() as db:
        db.execute(update(User).where(User.email == email).values(is_active=False))
        db.commit()


def test_deactivated_user_cannot_log_in_and_existing_tokens_stop_working(client):
    register(client)
    token = login_token(client)
    deactivate("ada@example.com")
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    res = client.post(
        "/auth/login", json={"email": "ada@example.com", "password": USER["password"]}
    )
    assert res.status_code == 401


def test_deactivated_user_gets_no_reset_email(client, sent_emails):
    register(client)
    deactivate("ada@example.com")
    assert client.post("/auth/forgot-password", json={"email": "ada@example.com"}).status_code == 202
    assert sent_emails == []


def test_expired_reset_token_is_rejected(client, sent_emails):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import update

    from app.core.database import SessionLocal
    from app.modules.auth.models import PasswordResetToken

    register(client)
    client.post("/auth/forgot-password", json={"email": "ada@example.com"})
    _, token = sent_emails[0]
    with SessionLocal() as db:
        db.execute(update(PasswordResetToken).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        db.commit()
    res = client.post("/auth/reset-password", json={"token": token, "new_password": "brand-new-pass"})
    assert res.status_code == 400


def test_new_reset_request_does_not_break_older_unused_links_until_one_is_used(client, sent_emails):
    register(client)
    client.post("/auth/forgot-password", json={"email": "ada@example.com"})
    client.post("/auth/forgot-password", json={"email": "ada@example.com"})
    (_, first), (_, second) = sent_emails
    body = {"new_password": "brand-new-pass"}
    assert client.post("/auth/reset-password", json={"token": second, **body}).status_code == 200
    # Using one link spends every outstanding link.
    assert client.post("/auth/reset-password", json={"token": first, **body}).status_code == 400
