"""Request and response shapes for the auth endpoints."""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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


# public view of a user. Never includes the hashed password
class UserRead(BaseModel):
    """Public view of a user. Never includes the password hash."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    timezone: str
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
