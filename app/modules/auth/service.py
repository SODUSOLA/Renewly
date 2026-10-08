"""Business logic for accounts: register, authenticate, password reset.

Functions raise the domain errors below; the router turns them into HTTP responses.
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    generate_reset_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.auth.models import PasswordResetToken, User

RESET_TOKEN_TTL = timedelta(hours=1)


# raised when registering an email that already has an account
class EmailAlreadyRegistered(Exception):
    """Raised when registering an email that already has an account."""


# raised for a wrong email/password or a deactivated account (deliberately vague)
class InvalidCredentials(Exception):
    """Raised for a wrong email/password or a deactivated account (deliberately vague)."""


# raised when a reset token is unknown, expired or already used
class InvalidResetToken(Exception):
    """Raised when a reset token is unknown, expired or already used."""


# func to lowercase and trim an email so lookups are case-insensitive
def normalize_email(email: str) -> str:
    """Lowercase and trim an email so lookups are case-insensitive."""
    return email.strip().lower()


# func to find a user by (normalized) email or None
def get_user_by_email(db: Session, email: str) -> User | None:
    """Find a user by (normalized) email, or None."""
    return db.scalar(select(User).where(User.email == normalize_email(email)))


# func ti create an account and return it
def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    timezone: str | None,
) -> User:
    """Create an account and return it.

    Raises EmailAlreadyRegistered if the email is taken. The unique index is the
    real guard: two simultaneous sign-ups cannot both succeed.
    """
    if get_user_by_email(db, email):
        raise EmailAlreadyRegistered
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        timezone=timezone or get_settings().default_timezone,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise EmailAlreadyRegistered
    return user


# func to return the user for a correct email/password, else raise InvalidCredentials
def authenticate(db: Session, *, email: str, password: str) -> User:
    """Return the user for a correct email/password, else raise InvalidCredentials.

    Hashes against a dummy value when the email is unknown so timing does not
    reveal which emails exist.
    """
    user = get_user_by_email(db, email)
    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)
        raise InvalidCredentials
    if not verify_password(password, user.password_hash) or not user.is_active:
        raise InvalidCredentials
    return user


# func to start a password reset flow
def create_password_reset(db: Session, *, email: str) -> tuple[User, str] | None:
    """Start a password reset.

    Returns `(user, raw_token)` for the caller to email, or None if no active
    account has that email (the caller must respond identically either way).
    """
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None
    raw_token, token_hash = generate_reset_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + RESET_TOKEN_TTL,
        )
    )
    db.commit()
    return user, raw_token


# func to set a new password using an emailed token
def reset_password(db: Session, *, raw_token: str, new_password: str) -> None:
    """Set a new password using an emailed token.

    Raises InvalidResetToken if the token is unknown, expired or used. On
    success every outstanding reset token for the user is spent, so older
    emailed links stop working.
    """
    now = datetime.now(UTC)
    token = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == hash_token(raw_token)
        )
    )
    if token is None or token.used_at is not None or token.expires_at <= now:
        raise InvalidResetToken
    user = db.get(User, token.user_id)
    user.password_hash = hash_password(new_password)
    db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    db.commit()
