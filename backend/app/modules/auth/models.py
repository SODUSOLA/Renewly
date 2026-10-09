import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Uuid, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.common.enums import ReminderStyle, enum_values
from app.core.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.modules.documents.models import Document
    from app.modules.vehicles.models import Vehicle


# an account holder. for who owns vehicles and documents; deleting a user cascades to both
class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An account holder. Owns vehicles and documents; deleting a user cascades to both.

    `timezone` decides what "today" means for this user when reminders are computed.
    """

    __tablename__ = "users"

    # Always store emails lowercased (normalize in the service layer).
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(150))
    timezone: Mapped[str] = mapped_column(
        String(64), default="Africa/Lagos", server_default="Africa/Lagos"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true()
    )
    # One email per reminder ("each") or one combined email a day ("digest").
    reminder_style: Mapped[ReminderStyle] = mapped_column(
        Enum(ReminderStyle, native_enum=False, length=10, values_callable=enum_values),
        default=ReminderStyle.EACH,
        server_default=ReminderStyle.EACH.value,
    )

    vehicles: Mapped[list["Vehicle"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    reset_tokens: Mapped[list["PasswordResetToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# a single-use expiring password reset request class
class PasswordResetToken(UUIDPrimaryKeyMixin, Base):
    """A single-use, expiring password reset request.

    Only the SHA-256 hash of the emailed token is stored, so a database leak
    does not expose usable reset links. `used_at` marks the token as spent.
    """

    __tablename__ = "password_reset_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 hex of the emailed token. The raw token is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="reset_tokens")


# class for a long-lived login that can be exchanged for new access tokens
class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """One link in a login's chain of refresh tokens.

    Each use of a token ("rotation") marks it `rotated_at` and issues a new one in the
    same `family_id`. Presenting an already-rotated token again means a copy was stolen,
    so the whole family is revoked. Only the SHA-256 of the cookie value is stored.
    """

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # All tokens descended from one login share a family.
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # When the login began; caps the family's total lifetime.
    family_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    rotated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
