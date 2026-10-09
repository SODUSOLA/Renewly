"""Password hashing, JWT access tokens and password-reset token helpers.

Pure functions only: nothing here touches the database, so it is easy to test.
"""
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"

_hasher = PasswordHasher()

# A real argon2 hash of a random value. Used to burn the same CPU time when a
# login email does not exist, so response timing does not reveal which emails
# are registered.
DUMMY_PASSWORD_HASH = _hasher.hash(secrets.token_urlsafe(16))


# func: return the argon2 hash of `password` (salt and parameters are embedded)
def hash_password(password: str) -> str:
    """Return the argon2 hash of `password` (salt and parameters are embedded)."""
    return _hasher.hash(password)


# func: return True if `password` matches `password_hash`, False otherwise
def verify_password(password: str, password_hash: str) -> bool:
    """Return True if `password` matches `password_hash`, False otherwise.

    Never raises on a bad password or a malformed stored hash.
    """
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


# func: create a signed JWT whose subject is `user_id` and which expires per settings
def create_access_token(user_id: uuid.UUID) -> str:
    """Create a signed JWT whose subject is `user_id` and which expires per settings."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


# func: return the user id inside a valid token, or None if it is invalid or expired
def decode_access_token(token: str) -> uuid.UUID | None:
    """Return the user id inside a valid token, or None if it is invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            get_settings().secret_key,
            algorithms=[JWT_ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None


# func: return the SHA-256 hex digest of a token (what we store instead of the token)
def hash_token(raw_token: str) -> str:
    """Return the SHA-256 hex digest of a token (what we store instead of the token)."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


# func: create a password-reset token
def generate_reset_token() -> tuple[str, str]:
    """Create a password-reset token.

    Returns `(raw_token, token_hash)`: email the raw token, store only the hash.
    """
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_token(raw_token)


# func to create a refresh token
def generate_refresh_token() -> tuple[str, str]:
    """Create a refresh token.

    Returns `(raw_token, token_hash)`: put the raw token in the cookie, store only the hash.
    """
    raw_token = secrets.token_urlsafe(48)
    return raw_token, hash_token(raw_token)
