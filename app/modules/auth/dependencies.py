"""FastAPI dependencies shared by every protected endpoint."""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import decode_access_token
from app.modules.auth.models import User

# auto_error=False so we return our own consistent 401 instead of FastAPI's 403.
bearer_scheme = HTTPBearer(auto_error=False)

# func to return current logged in user
def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the `Authorization: Bearer <jwt>` header to an active User.

    Raises 401 if the header is missing, the token is invalid/expired, or the
    user no longer exists or has been deactivated.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user
