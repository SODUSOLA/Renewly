"""Business logic for accounts: register, authenticate, password reset.

Functions raise the domain errors below; the router turns them into HTTP responses.
"""
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    generate_refresh_token,
    generate_reset_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.modules.auth.models import PasswordResetToken, RefreshToken, User
from app.modules.auth.schemas import ProfileUpdate

RESET_TOKEN_TTL = timedelta(hours=1)
# Two tabs can refresh at the same instant with the same cookie. A token rotated this
# recently is treated as that race, not as theft.
REFRESH_GRACE = timedelta(seconds=10)


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
    # A password change signs the account out everywhere.
    revoke_all_sessions(db, user.id, now)
    db.commit()


# ---------------------------------------------------------------- refresh sessions


# raised when a refresh token is missing, unknown, expired, revoked or reused
class InvalidRefreshToken(Exception):
    """Raised when a refresh token cannot be used (the caller answers 401)."""


# func to get the current time (one place to fake in tests)
def _now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


# func to create the next refresh token in a family
def _issue_refresh_token(
    db: Session, user_id: uuid.UUID, family_id: uuid.UUID, family_started_at: datetime, now: datetime
) -> tuple[str, datetime]:
    """Add a new refresh token row and return `(raw_token, expires_at)`.

    The expiry slides forward by `refresh_token_expire_days` on every use but never
    passes `refresh_token_max_days` after the login began.
    """
    settings = get_settings()
    expires_at = min(
        now + timedelta(days=settings.refresh_token_expire_days),
        family_started_at + timedelta(days=settings.refresh_token_max_days),
    )
    raw_token, token_hash = generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user_id,
            family_id=family_id,
            token_hash=token_hash,
            family_started_at=family_started_at,
            expires_at=expires_at,
        )
    )
    return raw_token, expires_at


# func to begin a login session
def start_session(db: Session, user: User) -> tuple[str, datetime]:
    """Start a new login for `user`; return `(raw_refresh_token, expires_at)` for the cookie."""
    now = _now()
    raw_token, expires_at = _issue_refresh_token(db, user.id, uuid.uuid4(), now, now)
    db.commit()
    return raw_token, expires_at


# func to revoke every token of one login
def revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    """Mark every still-active token in the family revoked (does not commit)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


# func to revoke all of a user's logins
def revoke_all_sessions(db: Session, user_id: uuid.UUID, now: datetime) -> None:
    """Sign the user out everywhere by revoking every active refresh token (does not commit)."""
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )


# func to swap a refresh token for a new one
def rotate_session(db: Session, raw_token: str) -> tuple[User, str | None, datetime | None]:
    """Use a refresh token; return `(user, new_raw_token, new_expires_at)`.

    - Normal use: the old token is marked rotated and a new one is issued.
    - Same token again within REFRESH_GRACE (two tabs racing): the user is returned
      with `None, None`: the caller issues an access token but sets no new cookie,
      because the winning request already did.
    - Same token again after the grace period: it was copied, so the whole family is
      revoked and InvalidRefreshToken is raised.
    The token row is locked, so two simultaneous requests cannot both rotate it.
    """
    now = _now()
    token = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    if token is None or token.revoked_at is not None or token.expires_at <= now:
        raise InvalidRefreshToken
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        revoke_family(db, token.family_id, now)
        db.commit()
        raise InvalidRefreshToken
    if token.rotated_at is not None:
        if now - token.rotated_at <= REFRESH_GRACE:
            db.rollback()
            return user, None, None
        revoke_family(db, token.family_id, now)
        db.commit()
        raise InvalidRefreshToken
    token.rotated_at = now
    new_raw, expires_at = _issue_refresh_token(
        db, user.id, token.family_id, token.family_started_at, now
    )
    db.commit()
    return user, new_raw, expires_at


# func to end the login that owns a refresh token
def end_session(db: Session, raw_token: str) -> None:
    """Log out: revoke the whole family of this token. Unknown tokens are ignored."""
    token = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if token is not None:
        revoke_family(db, token.family_id, _now())
        db.commit()


# func to delete old refresh tokens
def purge_expired_refresh_tokens(db: Session) -> int:
    """Delete tokens that expired more than a day ago; return how many.

    Rotated and revoked tokens are kept until they expire, because reuse detection
    needs to recognise them.
    """
    result = db.execute(
        delete(RefreshToken).where(RefreshToken.expires_at < _now() - timedelta(days=1))
    )
    db.commit()
    return result.rowcount


# ------------------------------------------------------------------- profile


# func to change the user's own settings
def update_profile(db: Session, user: User, data: ProfileUpdate) -> User:
    """Apply the fields the client sent (name, timezone, reminder style) and return the user."""
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value.strip() if isinstance(value, str) else value)
    db.commit()
    return user
