"""HTTP endpoints for registration, login, the current user and password reset."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import RateLimiter
from app.core.security import create_access_token
from app.modules.auth import service
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserRead,
)
from app.modules.notifications.email import send_password_reset_email

router = APIRouter(prefix="/auth", tags=["auth"])

# Limits: per client IP (Depends) and, for credential-guessing and email spam,
# also per email address (checked inside the endpoint).
register_limit = RateLimiter("register-ip", limit=10, window_seconds=3600)
login_ip_limit = RateLimiter("login-ip", limit=30, window_seconds=60)
login_email_limit = RateLimiter("login-email", limit=10, window_seconds=900)
forgot_ip_limit = RateLimiter("forgot-ip", limit=5, window_seconds=3600)
forgot_email_limit = RateLimiter("forgot-email", limit=3, window_seconds=3600)
reset_ip_limit = RateLimiter("reset-ip", limit=10, window_seconds=3600)


# func: create an account. Returns 409 if the email is already registered
@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_limit)],
)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> User:
    """Create an account. Returns 409 if the email is already registered."""
    try:
        return service.register_user(
            db,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            timezone=body.timezone,
        )
    except service.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")


# func: exchange email and password for a bearer token. Returns 401 on any failure
@router.post(
    "/login", response_model=TokenResponse, dependencies=[Depends(login_ip_limit)]
)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Exchange email and password for a bearer token.

    Returns 401 on any failure and 429 after too many attempts for the same email.
    """
    login_email_limit.check(body.email)
    try:
        user = service.authenticate(db, email=body.email, password=body.password)
    except service.InvalidCredentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=create_access_token(user.id))


# func: return the profile of the authenticated user
@router.get("/me", response_model=UserRead)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the profile of the authenticated user."""
    return current_user


# func: email a reset link if the account exists
@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(forgot_ip_limit)],
)
def forgot_password(
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Email a reset link if the account exists.

    Always answers the same way so the endpoint cannot be used to discover
    which emails are registered. The email is sent after the response.
    """
    forgot_email_limit.check(body.email)
    result = service.create_password_reset(db, email=body.email)
    if result is not None:
        user, raw_token = result
        background_tasks.add_task(send_password_reset_email, user.email, raw_token)
    return MessageResponse(
        message="If that email is registered, a reset link has been sent."
    )


# func: set a new password using the emailed token. Returns 400 if the token is bad
@router.post(
    "/reset-password",
    response_model=MessageResponse,
    dependencies=[Depends(reset_ip_limit)],
)
def reset_password(
    body: ResetPasswordRequest, db: Session = Depends(get_db)
) -> MessageResponse:
    """Set a new password using the emailed token. Returns 400 if the token is bad."""
    try:
        service.reset_password(
            db, raw_token=body.token, new_password=body.new_password
        )
    except service.InvalidResetToken:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token")
    return MessageResponse(message="Password updated.")
