"""Request and response shapes for the auth endpoints."""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.common.enums import ReminderStyle

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


# body of POST /auth/register
class RegisterRequest(BaseModel):
    """Body of POST /auth/register."""

    email: EmailStr
    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)
    full_name: str = Field(min_length=1, max_length=150)
    # Optional: the server falls back to DEFAULT_TIMEZONE when omitted.
    timezone: str | None = Field(default=None, max_length=64)

    # method: reject names that are not real IANA timezones (e.g. 'Africa/Lagos')
    @field_validator("timezone")
    @classmethod
    def timezone_must_be_valid(cls, value: str | None) -> str | None:
        """Reject names that are not real IANA timezones (e.g. 'Africa/Lagos')."""
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown timezone. Use an IANA name like 'Africa/Lagos'.")
        return value


# body of POST /auth/login
class LoginRequest(BaseModel):
    """Body of POST /auth/login."""

    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


# returned by login - a bearer token to send in the Authorization header
class TokenResponse(BaseModel):
    """Returned by login: a bearer token to send in the Authorization header."""

    access_token: str
    token_type: str = "bearer"
    # Seconds until the access token expires (the refresh token is in a cookie, not here).
    expires_in: int


# public view of a user. Never includes the hashed password
class UserRead(BaseModel):
    """Public view of a user. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    timezone: str
    reminder_style: ReminderStyle
    report_emails: bool
    created_at: datetime


# body of POST /auth/forgot-password
class ForgotPasswordRequest(BaseModel):
    """Body of POST /auth/forgot-password."""

    email: EmailStr


# body of POST /auth/reset-password
class ResetPasswordRequest(BaseModel):
    """Body of POST /auth/reset-password."""

    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(
        min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )


# a plain human-readable confirmation message
class MessageResponse(BaseModel):
    """A plain human-readable confirmation message."""

    message: str


# class for the body of PATCH /auth/me
class ProfileUpdate(BaseModel):
    """Body of PATCH /auth/me: only the fields sent are changed. Email cannot be changed here."""

    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    timezone: str | None = Field(default=None, max_length=64)
    reminder_style: ReminderStyle | None = None
    report_emails: bool | None = None

    # func to reject names that are not real IANA timezones
    @field_validator("timezone")
    @classmethod
    def timezone_must_be_valid(cls, value: str | None) -> str | None:
        """Same check as at sign-up: an IANA name like 'Africa/Lagos'."""
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown timezone. Use an IANA name like 'Africa/Lagos'.")
        return value

    # func to block explicit nulls (omit a field to leave it unchanged)
    @model_validator(mode="after")
    def no_explicit_nulls(self) -> "ProfileUpdate":
        """Reject `{"timezone": null}` and friends: omit the field instead."""
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self
