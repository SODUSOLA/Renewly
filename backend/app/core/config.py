from functools import lru_cache
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# class: application settings, loaded from environment variables or the `.env` file
class Settings(BaseSettings):
    """Application settings, loaded from environment variables or the `.env` file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Expiry Tracker"
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    secret_key: str
    access_token_expire_minutes: int = 30
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
