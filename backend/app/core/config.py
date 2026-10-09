from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# class: application settings, loaded from environment variables or the `.env` file
class Settings(BaseSettings):
    """Application settings, loaded from environment variables or the `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Expiry Tracker"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str
    # Access tokens are short-lived on purpose: the refresh cookie renews them silently.
    access_token_expire_minutes: int = 15
    # A refresh token lasts this long after its last use (each use issues a new one)...
    refresh_token_expire_days: int = 30
    # ...but a login can never be extended past this many days; then the user signs in again.
    refresh_token_max_days: int = 90
    # The refresh token travels in an HttpOnly cookie (invisible to JavaScript).
    refresh_cookie_name: str = "renewly_refresh"
    # "lax" or "strict" when the web app and API share a site (e.g. app.x.com + api.x.com).
    # "none" is needed only when they are on unrelated sites, and many browsers block it.
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    # Leave unset: Secure is on in production and off in development. Never disable it in production.
    cookie_secure: bool | None = None
    # Must match the path the BROWSER sees. "/auth" normally; "/api/auth" behind a /api proxy.
    cookie_path: str = "/auth"
    # Usually empty (cookie is only sent to the API's own host).
    cookie_domain: str = ""
    default_timezone: str = "Africa/Lagos"
    # "production" makes a missing RESEND_API_KEY a hard error instead of a log line.
    app_env: str = "development"
    # "redis" in normal use; "memory" keeps counters in-process (tests, single process).
    rate_limit_backend: str = "redis"
    # "text" is readable in a terminal; "json" is one object per line for log tools.
    log_format: str = "text"
    log_level: str = "INFO"
    # Browser origins allowed to call the API (comma separated), e.g. the frontend's
    # public URL. The Vite dev server is allowed by default.
    cors_origins: str = "http://localhost:5173"
    # How many reverse proxies sit between the internet and the API (Railway's edge = 1).
    # Used to find the real client IP in X-Forwarded-For. 0 means "ignore the header".
    # Never set this higher than the real number: that lets callers spoof their IP.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)
    # Public URL of the web app, used for links in emails (e.g. password reset).
    # Empty means emails carry the bare token instead of a link.
    frontend_url: str = ""
    # Error tracking. Empty disables Sentry entirely.
    sentry_dsn: str = ""
    # Fraction of requests to trace for performance (0 = errors only).
    sentry_traces_sample_rate: float = 0.0
    resend_api_key: str = ""
    # Must be on a domain verified in Resend (onboarding@resend.dev only reaches
    # the Resend account owner, which is fine for first tests).
    email_from: str = "Expiry Tracker <onboarding@resend.dev>"


    # func to decide whether the refresh cookie is marked Secure
    @property
    def cookie_secure_effective(self) -> bool:
        """`cookie_secure` if set, else True in production (HTTPS) and False in development."""
        return self.app_env == "production" if self.cookie_secure is None else self.cookie_secure

    # func to get the allowed origins as a list
    @property
    def cors_origin_list(self) -> list[str]:
        """`cors_origins` split on commas, trimmed, ignoring blanks and trailing slashes."""
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    # func to accept the URL forms hosting providers hand out
    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Rewrite `postgres://` / `postgresql://` to `postgresql+psycopg://`.

        Railway, Heroku and friends supply the short forms, but SQLAlchemy would
        then look for the older psycopg2 driver, which this project does not use.
        """
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix):]
        return value

    # func to refuse unsafe cookie settings
    @model_validator(mode="after")
    def cookie_settings_are_safe(self) -> "Settings":
        """SameSite=None needs Secure, and Secure may not be turned off in production."""
        if self.cookie_samesite == "none" and not self.cookie_secure_effective:
            raise ValueError("COOKIE_SAMESITE=none requires a Secure cookie (HTTPS)")
        if self.app_env == "production" and not self.cookie_secure_effective:
            raise ValueError("COOKIE_SECURE must not be disabled in production")
        return self

    # func to refuse weak secrets in production
    @model_validator(mode="after")
    def production_needs_strong_secret(self) -> "Settings":
        """In production SECRET_KEY must be long and not the .env.example placeholder."""
        if self.app_env == "production" and (
            len(self.secret_key) < 32 or self.secret_key.startswith("change-me")
        ):
            raise ValueError(
                "SECRET_KEY must be a random string of at least 32 characters in production"
            )
        return self

# func: return the process-wide Settings instance (built once, then cached)
@lru_cache
def get_settings() -> Settings:
    """Return the process-wide Settings instance (built once, then cached)."""
    return Settings()
