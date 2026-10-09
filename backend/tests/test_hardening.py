"""Tests for rate limiting, request ids, error shape, logging and config safety."""
import json
import logging
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core import rate_limit
from app.core.config import Settings
from app.core.database import get_db
from app.core.logging import JsonFormatter, request_id_var
from app.main import app
from app.modules.auth.router import forgot_email_limit
from tests.helpers import auth_headers

BAD_LOGIN = {"email": "ghost@example.com", "password": "wrong-password"}


# ------------------------------------------------------------ rate limiting
def test_login_is_limited_per_email_with_retry_after(client):
    for _ in range(10):
        assert client.post("/auth/login", json=BAD_LOGIN).status_code == 401
    blocked = client.post("/auth/login", json=BAD_LOGIN)
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0
    assert blocked.json()["code"] == "rate_limited"
    # A different email is not affected.
    other = {**BAD_LOGIN, "email": "other@example.com"}
    assert client.post("/auth/login", json=other).status_code == 401


def test_correct_password_is_also_blocked_once_limit_is_hit(client, ada):
    body = {"email": "ada@example.com", "password": "wrong-password"}
    for _ in range(10):
        client.post("/auth/login", json=body)
    good = {"email": "ada@example.com", "password": "correct-horse"}
    assert client.post("/auth/login", json=good).status_code == 429


def test_register_is_limited_per_ip(client):
    codes = [
        client.post(
            "/auth/register",
            json={"email": f"u{i}@example.com", "password": "correct-horse", "full_name": "U"},
        ).status_code
        for i in range(12)
    ]
    assert codes[:10] == [201] * 10 and codes[10:] == [429, 429]


def test_forgot_password_is_limited_per_email_without_revealing_existence(client):
    results = [
        client.post("/auth/forgot-password", json={"email": "ghost@example.com"}).status_code
        for _ in range(4)
    ]
    assert results == [202, 202, 202, 429]


def test_reset_password_is_limited_per_ip(client):
    body = {"token": "nope", "new_password": "brand-new-pass"}
    codes = [client.post("/auth/reset-password", json=body).status_code for _ in range(11)]
    assert codes == [400] * 10 + [429]


def test_limiter_fails_open_when_the_backend_is_down(monkeypatch):
    class Broken:
        def hit(self, key, window):
            raise ConnectionError("redis down")

    monkeypatch.setattr(rate_limit, "get_backend", lambda: Broken())
    for _ in range(50):  # far over the limit of 3, yet never blocked
        forgot_email_limit.check("a@example.com")


def test_memory_backend_window_expires(monkeypatch):
    backend = rate_limit.MemoryBackend()
    clock = [1000.0]
    monkeypatch.setattr(rate_limit.time, "monotonic", lambda: clock[0])
    assert backend.hit("k", 60) == (1, 60)
    assert backend.hit("k", 60)[0] == 2
    clock[0] += 61
    assert backend.hit("k", 60)[0] == 1


def test_redis_backend_counts_and_sets_expiry():
    from app.core.config import get_settings

    backend = rate_limit.RedisBackend(get_settings().redis_url)
    key = f"rl:test:{uuid.uuid4().hex}"
    try:
        first = backend.hit(key, 30)
    except Exception:
        pytest.skip("Redis is not reachable")
    assert first == (1, 30)
    count, ttl = backend.hit(key, 30)
    assert count == 2 and 0 < ttl <= 30
    backend._client.delete(key)


# -------------------------------------------------------------- request ids
def test_every_response_has_a_request_id_and_valid_incoming_ids_are_kept(client):
    assert len(client.get("/health").headers["X-Request-ID"]) == 32
    kept = client.get("/health", headers={"X-Request-ID": "trace-abc.123"})
    assert kept.headers["X-Request-ID"] == "trace-abc.123"
    replaced = client.get("/health", headers={"X-Request-ID": "bad id\twith spaces!"})
    assert replaced.headers["X-Request-ID"] != "bad id\twith spaces!"


def test_requests_are_logged_with_status_and_duration(client, caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/dashboard")
    record = next(r for r in caplog.records if r.name == "app.request")
    assert (record.method, record.path, record.status) == ("GET", "/dashboard", 401)
    assert record.duration_ms >= 0


# -------------------------------------------------------------- error shape
def test_errors_share_one_shape_with_the_request_id(client, ada):
    not_found = client.get("/no-such-route", headers={"X-Request-ID": "rid-1"})
    assert not_found.status_code == 404
    assert not_found.json() == {"detail": "Not Found", "code": "not_found", "request_id": "rid-1"}

    unauthorized = client.get("/auth/me")
    assert unauthorized.json()["code"] == "unauthorized"
    assert unauthorized.headers["WWW-Authenticate"] == "Bearer"

    invalid = client.post("/vehicles", json={}, headers=ada)
    body = invalid.json()
    assert invalid.status_code == 422 and body["code"] == "validation_error"
    assert isinstance(body["detail"], list) and body["request_id"]

    assert client.get("/vehicles/not-a-uuid", headers=ada).json()["code"] == "validation_error"
    assert client.post("/health").json()["code"] == "method_not_allowed"


@pytest.fixture
def boom_route():
    """Temporarily add a route that crashes, to test the 500 handler."""

    def boom():
        raise RuntimeError("secret database password is hunter2")

    app.add_api_route("/__boom", boom)
    yield
    app.router.routes = [r for r in app.router.routes if getattr(r, "path", "") != "/__boom"]


def test_unexpected_errors_become_a_clean_500_without_leaking_details(boom_route, caplog):
    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR):
        res = client.get("/__boom")
    assert res.status_code == 500
    body = res.json()
    assert body["detail"] == "Internal server error" and body["code"] == "internal_error"
    assert "hunter2" not in res.text
    assert body["request_id"] == res.headers["X-Request-ID"]
    # The real cause is logged for operators, with the stack trace.
    assert any("hunter2" in (r.exc_text or str(r.exc_info)) for r in caplog.records if r.exc_info)


# ------------------------------------------------------------------ logging
def test_json_formatter_outputs_structured_lines():
    token = request_id_var.set("rid-9")
    try:
        record = logging.LogRecord("app.x", logging.WARNING, __file__, 1, "hello %s", ("world",), None)
        record.status = 201  # an `extra=` field
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line["message"] == "hello world" and line["level"] == "WARNING"
    assert line["request_id"] == "rid-9" and line["status"] == 201 and "ts" in line


def test_json_formatter_includes_exceptions():
    try:
        raise ValueError("bad")
    except ValueError:
        import sys

        record = logging.LogRecord("app.x", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    assert "ValueError: bad" in json.loads(JsonFormatter().format(record))["exception"]


# -------------------------------------------------------------------- health
def test_readiness_reports_ok_and_503_when_the_database_is_down(client):
    assert client.get("/health/ready").json() == {"status": "ready"}

    class DeadSession:
        def execute(self, *args, **kwargs):
            raise ConnectionError("db down")

    app.dependency_overrides[get_db] = lambda: DeadSession()
    try:
        res = client.get("/health/ready")
    finally:
        app.dependency_overrides.pop(get_db)
    assert res.status_code == 503 and res.json() == {"status": "unavailable"}
    assert "db down" not in res.text  # the cause is logged, never returned


# ------------------------------------------------------------------- config
@pytest.mark.parametrize("secret", ["short", "change-me-to-a-long-random-string-xxxxxxxxxxxx"])
def test_production_rejects_weak_secrets(secret):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, database_url="postgresql://x", secret_key=secret, app_env="production")


def test_production_accepts_a_strong_secret_and_development_allows_weak_ones():
    strong = "k" * 40
    assert Settings(_env_file=None, database_url="x", secret_key=strong, app_env="production")
    assert Settings(_env_file=None, database_url="x", secret_key="dev", app_env="development")


# ------------------------------------------------------------ app start-up
def test_app_can_use_every_model_when_started_on_its_own():
    """Regression: a fresh process importing only app.main must configure all mappers.

    The test suite imports every model itself (conftest), which hides a missing
    import in the real app, so this runs the app's entry point in a clean process.
    """
    import subprocess
    import sys

    code = "import app.main; from sqlalchemy.orm import configure_mappers; configure_mappers()"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-800:]


# ------------------------------------------------------- deployment settings
@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@h:5432/d", "postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"],
)
def test_database_url_forms_from_hosting_providers_are_accepted(given):
    settings = Settings(_env_file=None, database_url=given, secret_key="k")
    assert settings.database_url == "postgresql+psycopg://u:p@h:5432/d"


def test_sentry_is_off_without_a_dsn_and_privacy_safe_with_one(monkeypatch):
    import sentry_sdk

    from app.core import observability

    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))

    off = Settings(_env_file=None, database_url="x", secret_key="k")
    monkeypatch.setattr(observability, "get_settings", lambda: off)
    assert observability.init_sentry() is False and calls == []

    on = Settings(_env_file=None, database_url="x", secret_key="k", sentry_dsn="https://k@o.ingest.sentry.io/1")
    monkeypatch.setattr(observability, "get_settings", lambda: on)
    assert observability.init_sentry() is True
    assert calls[0]["send_default_pii"] is False
    assert calls[0]["max_request_body_size"] == "never"
    assert calls[0]["environment"] == "development"


# --------------------------------------------------------------------- CORS
def test_cors_allows_the_configured_frontend_origin_only(client):
    ok = client.options(
        "/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "authorization" in ok.headers["access-control-allow-headers"].lower()

    denied = client.options(
        "/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in denied.headers


def test_cors_headers_are_present_even_on_errors_and_expose_helpful_headers(client):
    res = client.get("/auth/me", headers={"Origin": "http://localhost:5173"})
    assert res.status_code == 401
    assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "x-request-id" in res.headers["access-control-expose-headers"].lower()


def test_cors_origin_list_parsing():
    s = Settings(_env_file=None, database_url="x", secret_key="k",
                 cors_origins=" https://a.example/ , ,https://b.example ")
    assert s.cors_origin_list == ["https://a.example", "https://b.example"]


# ------------------------------------------------- client IP / proxy spoofing
# func to run a request through client_ip with chosen proxy settings
def ip_for(monkeypatch, hops: int, forwarded: str | None, peer: str = "10.0.0.7") -> str:
    """Return what client_ip() decides for a request with the given header and settings."""
    from starlette.requests import Request

    from app.core import client_ip as module

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(trusted_proxy_hops=hops))
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    scope = {"type": "http", "headers": headers, "client": (peer, 5000), "method": "GET", "path": "/"}
    return module.client_ip(Request(scope))


def test_without_trusted_proxies_the_header_is_ignored(monkeypatch):
    assert ip_for(monkeypatch, 0, "1.2.3.4") == "10.0.0.7"


def test_one_proxy_means_the_rightmost_entry_is_the_client(monkeypatch):
    # The client invented the first two values; our proxy appended the real one.
    assert ip_for(monkeypatch, 1, "6.6.6.6, 7.7.7.7, 203.0.113.9") == "203.0.113.9"
    assert ip_for(monkeypatch, 1, "203.0.113.9") == "203.0.113.9"


def test_two_proxies_means_the_second_from_the_right(monkeypatch):
    assert ip_for(monkeypatch, 2, "6.6.6.6, 203.0.113.9, 198.51.100.4") == "203.0.113.9"


def test_missing_short_or_invalid_headers_fall_back_to_the_connecting_address(monkeypatch):
    assert ip_for(monkeypatch, 1, None) == "10.0.0.7"
    assert ip_for(monkeypatch, 2, "203.0.113.9") == "10.0.0.7"  # fewer entries than proxies
    assert ip_for(monkeypatch, 1, "<script>") == "10.0.0.7"  # not an IP


def test_ipv6_clients_are_supported_and_normalised(monkeypatch):
    assert ip_for(monkeypatch, 1, "2001:0DB8:0:0:0:0:0:1") == "2001:db8::1"


# func to register users until the per-IP limit trips, forging a different leading header each time
def register_with_forged_headers(client, monkeypatch, hops: int, real_ip: str, count: int = 12) -> list[int]:
    """POST /auth/register `count` times claiming a new fake IP each time; return status codes."""
    from app.core import client_ip as module

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(trusted_proxy_hops=hops))
    codes = []
    for i in range(count):
        res = client.post(
            "/auth/register",
            json={"email": f"u{i}@example.com", "password": "correct-horse", "full_name": "U"},
            headers={"X-Forwarded-For": f"9.9.9.{i}, {real_ip}"},
        )
        codes.append(res.status_code)
    return codes


def test_forging_forwarded_for_cannot_dodge_the_ip_rate_limit_behind_a_proxy(client, monkeypatch):
    codes = register_with_forged_headers(client, monkeypatch, hops=1, real_ip="203.0.113.9")
    assert codes[:10] == [201] * 10 and codes[10:] == [429, 429]


def test_forging_forwarded_for_cannot_dodge_the_ip_rate_limit_without_a_proxy(client, monkeypatch):
    codes = register_with_forged_headers(client, monkeypatch, hops=0, real_ip="203.0.113.9")
    assert codes[:10] == [201] * 10 and codes[10:] == [429, 429]


def test_real_users_behind_the_proxy_get_separate_limits(client, monkeypatch):
    from app.core import client_ip as module

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(trusted_proxy_hops=1))

    def attempt(ip: str, n: int) -> int:
        return client.post(
            "/auth/register",
            json={"email": f"{ip.replace('.', '-')}-{n}@example.com", "password": "correct-horse", "full_name": "U"},
            headers={"X-Forwarded-For": ip},
        ).status_code

    assert [attempt("203.0.113.1", n) for n in range(11)][-1] == 429  # the noisy client is limited
    assert attempt("203.0.113.2", 0) == 201  # a different real client is unaffected


def test_request_log_records_the_client_ip(client, monkeypatch, caplog):
    from app.core import client_ip as module

    monkeypatch.setattr(module, "get_settings", lambda: SimpleNamespace(trusted_proxy_hops=1))
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/dashboard", headers={"X-Forwarded-For": "6.6.6.6, 203.0.113.9"})
    record = next(r for r in caplog.records if r.name == "app.request")
    assert record.client_ip == "203.0.113.9"


def test_startup_warns_when_production_has_no_proxy_configured(caplog):
    from app.core.client_ip import log_proxy_configuration

    with caplog.at_level(logging.INFO, logger="app.core.client_ip"):
        log_proxy_configuration(Settings(_env_file=None, database_url="x", secret_key="k" * 40, app_env="production"))
        warned = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warned and "TRUSTED_PROXY_HOPS" in warned[0].getMessage()
        caplog.clear()
        log_proxy_configuration(Settings(_env_file=None, database_url="x", secret_key="k" * 40, app_env="production", trusted_proxy_hops=1))
        log_proxy_configuration(Settings(_env_file=None, database_url="x", secret_key="k" * 40, app_env="development"))
    assert [r.levelno for r in caplog.records] == [logging.INFO]


def test_proxy_hops_setting_is_bounded():
    for bad in (-1, 6):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, database_url="x", secret_key="k", trusted_proxy_hops=bad)
