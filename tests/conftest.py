"""Shared test fixtures.

Tests run against a separate `<db>_test` database on the same Postgres server,
so they never touch development data.
"""
import os

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings

# Point the app at the test database BEFORE anything imports app.core.database.
_dev_url = make_url(get_settings().database_url)
_test_url = _dev_url.set(database=f"{_dev_url.database}_test")
os.environ["DATABASE_URL"] = _test_url.render_as_string(hide_password=False)
# Keep rate-limit counters in-process so tests need no Redis.
os.environ["RATE_LIMIT_BACKEND"] = "memory"
get_settings.cache_clear()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models_registry  # noqa: E402,F401
from app.core.base import Base  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.core.rate_limit import reset_rate_limits  # noqa: E402
from app.main import app  # noqa: E402


# func: create the test database if it does not exist yet
def _ensure_test_database() -> None:
    """Create the test database if it does not exist yet."""
    admin = create_engine(_dev_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"),
            {"n": _test_url.database},
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{_test_url.database}"'))
    admin.dispose()


# func: create all tables once per test session and drop them at the end
@pytest.fixture(scope="session", autouse=True)
def _schema():
    """Create all tables once per test session and drop them at the end."""
    _ensure_test_database()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


# func: empty every table after each test so tests are independent
@pytest.fixture(autouse=True)
def _clean_tables():
    """Empty every table after each test so tests are independent."""
    yield
    with engine.begin() as conn:
        names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} CASCADE"))


# func: an HTTP client bound to the FastAPI app
@pytest.fixture
def client() -> TestClient:
    """An HTTP client bound to the FastAPI app."""
    return TestClient(app)


# func: auth headers for a first registered user
@pytest.fixture
def ada(client):
    """Auth headers for a first registered user (ada@example.com)."""
    from tests.helpers import auth_headers

    return auth_headers(client, "ada@example.com")


# func: auth headers for a second registered user
@pytest.fixture
def bola(client):
    """Auth headers for a second registered user (bola@example.com)."""
    from tests.helpers import auth_headers

    return auth_headers(client, "bola@example.com")


# func: start every test with empty rate-limit counters
@pytest.fixture(autouse=True)
def _fresh_rate_limits():
    """Reset rate-limit counters so one test's requests never count against another."""
    reset_rate_limits()
