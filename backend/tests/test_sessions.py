"""Tests for refresh-token sessions: the cookie, rotation, theft detection and logout."""
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select, update

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.core.security import hash_token
from app.modules.auth import cookies, service
from app.modules.auth.models import RefreshToken, User
from tests.helpers import auth_headers

COOKIE = "renewly_refresh"
EMAIL = "ada@example.com"
PASSWORD = "correct-horse"


@pytest.fixture
def clock(monkeypatch):
    """A controllable clock for the session logic: `clock.advance(days=3)` moves it forward."""

    class Clock:
        offset = timedelta(0)

        def advance(self, **kwargs) -> None:
            self.offset += timedelta(**kwargs)

    fake = Clock()
    monkeypatch.setattr(service, "_now", lambda: datetime.now(UTC) + fake.offset)
    return fake


# func to sign in and return the response
def sign_in(client, email=EMAIL):
    """Register `email` (once) and log in, leaving the refresh cookie in the client."""
    client.post("/auth/register", json={"email": email, "password": PASSWORD, "full_name": "Ada"})
    res = client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert res.status_code == 200, res.text
    return res


# func to send a specific refresh token, as a browser holding that cookie would
def refresh_with(client, token: str | None, **headers):
    """POST /auth/refresh carrying exactly `token` as the cookie (None = no cookie)."""
    client.cookies.clear()
    if token is not None:
        headers["Cookie"] = f"{COOKIE}={token}"
    return client.post("/auth/refresh", headers=headers)


# func to read the refresh token the client currently holds
def cookie_value(client) -> str:
    """The refresh token in the client's cookie jar."""
    value = client.cookies.get(COOKIE)
    assert value, "no refresh cookie was set"
    return value


def test_login_sets_an_httponly_refresh_cookie_and_keeps_it_out_of_the_body(client):
    res = sign_in(client)
    header = res.headers["set-cookie"]
    assert header.startswith(f"{COOKIE}=")
    for part in ("HttpOnly", "Path=/auth", "SameSite=lax"):
        assert part in header, header
    max_age = int(header.split("Max-Age=")[1].split(";")[0])
    assert abs(max_age - 30 * 24 * 3600) <= 2
    assert "Secure" not in header  # development: plain http
    body = res.json()
    assert set(body) == {"access_token", "token_type", "expires_in"}
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60
    assert cookie_value(client) not in res.text


def test_only_a_hash_of_the_refresh_token_is_stored(client):
    sign_in(client)
    raw = cookie_value(client)
    with SessionLocal() as db:
        rows = list(db.scalars(select(RefreshToken)))
    assert [r.token_hash for r in rows] == [hash_token(raw)]
    assert raw not in rows[0].token_hash


def test_refresh_issues_a_working_access_token_and_rotates_the_cookie(client):
    sign_in(client)
    first = cookie_value(client)
    res = client.post("/auth/refresh")
    assert res.status_code == 200
    assert cookie_value(client) != first
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {res.json()['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == EMAIL


def test_refresh_without_a_cookie_is_401_and_clears_any_stale_cookie(client):
    res = refresh_with(client, None)
    assert res.status_code == 401
    assert res.json()["code"] == "unauthorized"
    assert f'{COOKIE}=""' in res.headers["set-cookie"] or "Max-Age=0" in res.headers["set-cookie"]


def test_unknown_refresh_token_is_rejected(client):
    assert refresh_with(client, "not-a-real-token").status_code == 401


def test_reusing_a_rotated_token_after_the_grace_period_revokes_the_whole_login(client, clock):
    sign_in(client)
    stolen = cookie_value(client)
    assert client.post("/auth/refresh").status_code == 200  # the real user rotates it
    legit = cookie_value(client)

    clock.advance(seconds=30)
    assert refresh_with(client, stolen).status_code == 401  # thief replays the old token
    assert refresh_with(client, legit).status_code == 401  # ...so the real user's login died too


def test_a_simultaneous_refresh_within_the_grace_period_is_not_treated_as_theft(client):
    sign_in(client)
    old = cookie_value(client)
    assert client.post("/auth/refresh").status_code == 200
    newest = cookie_value(client)

    second = refresh_with(client, old)  # another tab raced with the same cookie
    assert second.status_code == 200
    assert "set-cookie" not in second.headers  # the winner already set the new cookie
    assert refresh_with(client, newest).status_code == 200  # the login is still alive


def test_a_refresh_token_expires_after_30_idle_days(client, clock):
    sign_in(client)
    token = cookie_value(client)
    clock.advance(days=31)
    assert refresh_with(client, token).status_code == 401


def test_using_the_token_keeps_the_login_alive_but_never_past_90_days(client, clock):
    sign_in(client)
    for _ in range(3):  # day 25, 50, 75: each use slides the expiry forward
        clock.advance(days=25)
        assert client.post("/auth/refresh").status_code == 200
    clock.advance(days=25)  # day 100 is past the 90-day cap
    assert client.post("/auth/refresh").status_code == 401


def test_logout_revokes_the_login_and_clears_the_cookie(client):
    sign_in(client)
    token = cookie_value(client)
    res = client.post("/auth/logout")
    assert res.status_code == 204
    assert "Max-Age=0" in res.headers["set-cookie"]
    assert refresh_with(client, token).status_code == 401


def test_logout_is_harmless_when_already_signed_out(client):
    assert client.post("/auth/logout").status_code == 204


def test_each_device_has_its_own_login_and_logout_only_ends_one(client):
    sign_in(client)
    phone = cookie_value(client)
    client.cookies.clear()
    client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    laptop = cookie_value(client)
    assert phone != laptop
    client.post("/auth/logout")  # logs the laptop out
    assert refresh_with(client, laptop).status_code == 401
    assert refresh_with(client, phone).status_code == 200


def test_resetting_the_password_signs_out_every_device(client, monkeypatch):
    sent = []
    monkeypatch.setattr("app.modules.auth.router.send_password_reset_email", lambda e, t: sent.append(t))
    sign_in(client)
    old = cookie_value(client)
    client.post("/auth/forgot-password", json={"email": EMAIL})
    res = client.post("/auth/reset-password", json={"token": sent[0], "new_password": "brand-new-pass"})
    assert res.status_code == 200
    assert refresh_with(client, old).status_code == 401


def test_a_deactivated_user_cannot_refresh(client):
    sign_in(client)
    token = cookie_value(client)
    with SessionLocal() as db:
        db.execute(update(User).where(User.email == EMAIL).values(is_active=False))
        db.commit()
    assert refresh_with(client, token).status_code == 401


# ------------------------------------------------------------ CSRF / origin guard
def test_refresh_and_logout_reject_other_websites(client):
    sign_in(client)
    evil = {"Origin": "https://evil.example"}
    assert client.post("/auth/refresh", headers=evil).status_code == 403
    assert client.post("/auth/logout", headers=evil).status_code == 403
    # The rejected calls changed nothing: the real login still works.
    assert client.post("/auth/refresh", headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_requests_without_an_origin_header_are_allowed(client):
    sign_in(client)
    assert client.post("/auth/refresh").status_code == 200  # curl, mobile apps, servers


def test_cors_allows_credentials_for_the_web_app_only(client):
    ok = client.options(
        "/auth/refresh",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers["access-control-allow-credentials"] == "true"
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = client.options(
        "/auth/refresh",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


def test_refresh_is_rate_limited_per_ip(client):
    codes = [refresh_with(client, "nope").status_code for _ in range(62)]
    assert codes[:60] == [401] * 60 and codes[60:] == [429, 429]


# ------------------------------------------------------------ cookie settings
# func to build settings for the cookie tests
def make_settings(**overrides) -> Settings:
    """Settings with just enough fields to be valid."""
    return Settings(_env_file=None, database_url="x", secret_key="k" * 40, **overrides)


def test_the_cookie_is_secure_in_production_and_not_in_development():
    assert make_settings(app_env="production").cookie_secure_effective is True
    assert make_settings(app_env="development").cookie_secure_effective is False


def test_unsafe_cookie_settings_are_refused():
    with pytest.raises(ValueError, match="Secure"):
        make_settings(cookie_samesite="none")  # SameSite=None without HTTPS
    with pytest.raises(ValueError, match="production"):
        make_settings(app_env="production", cookie_secure=False)
    assert make_settings(app_env="production", cookie_samesite="none").cookie_samesite == "none"


def test_production_cookie_carries_the_secure_flag_and_custom_attributes(monkeypatch):
    from fastapi import Response

    monkeypatch.setattr(
        cookies, "get_settings",
        lambda: make_settings(app_env="production", cookie_path="/api/auth", cookie_domain="example.com", cookie_samesite="strict"),
    )
    response = Response()
    cookies.set_refresh_cookie(response, "tok", datetime.now(UTC) + timedelta(days=1))
    header = response.headers["set-cookie"]
    for part in ("Secure", "HttpOnly", "Path=/api/auth", "Domain=example.com", "SameSite=strict"):
        assert part in header, header


# ------------------------------------------------------------ housekeeping
def test_purge_removes_only_long_expired_tokens(client):
    sign_in(client)
    now = datetime.now(UTC)
    with SessionLocal() as db:
        user = db.scalar(select(User))
        for name, expires in (("old", now - timedelta(days=2)), ("recent", now - timedelta(hours=2))):
            db.add(RefreshToken(user_id=user.id, family_id=user.id, token_hash=hash_token(name),
                                family_started_at=now - timedelta(days=60), expires_at=expires))
        db.commit()
        removed = service.purge_expired_refresh_tokens(db)
        remaining = {r.token_hash for r in db.scalars(select(RefreshToken))}
    assert removed == 1
    assert hash_token("old") not in remaining and hash_token("recent") in remaining
    assert len(remaining) == 2  # the live login plus the recently expired one


def test_the_purge_task_is_registered_and_scheduled():
    from app.core.celery_app import celery_app
    from app.modules.auth.tasks import purge_expired_refresh_tokens_task

    assert purge_expired_refresh_tokens_task() == 0
    assert "auth.purge_expired_refresh_tokens" in celery_app.tasks
    assert "purge-refresh-tokens-daily" in celery_app.conf.beat_schedule


def test_auth_headers_helper_still_works_with_cookies(client):
    assert auth_headers(client, "bola@example.com")["Authorization"].startswith("Bearer ")
