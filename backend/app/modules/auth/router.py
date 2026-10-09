"""HTTP endpoints for registration, login, the current user and password reset."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.core.errors import error_response
from app.core.rate_limit import RateLimiter
from app.core.security import create_access_token
from app.modules.auth import service
from app.modules.auth.cookies import (
    clear_refresh_cookie,
    read_refresh_cookie,
    require_trusted_origin,
    set_refresh_cookie,
)
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    OnboardingUpdate,
    ProfileUpdate,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserRead,
)
from app.modules.notifications.service import (
    send_password_changed_email,
    send_password_reset_email,
    send_welcome_email,
)

router = APIRouter(prefix="/auth", tags=["auth"])

# Limits: per client IP (Depends) and, for credential-guessing and email spam,
# also per email address (checked inside the endpoint).
register_limit = RateLimiter("register-ip", limit=10, window_seconds=3600)
login_ip_limit = RateLimiter("login-ip", limit=30, window_seconds=60)
login_email_limit = RateLimiter("login-email", limit=10, window_seconds=900)
forgot_ip_limit = RateLimiter("forgot-ip", limit=5, window_seconds=3600)
forgot_email_limit = RateLimiter("forgot-email", limit=3, window_seconds=3600)
reset_ip_limit = RateLimiter("reset-ip", limit=10, window_seconds=3600)
refresh_ip_limit = RateLimiter("refresh-ip", limit=60, window_seconds=60)


# func: create an account. Returns 409 if the email is already registered
@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(register_limit)],
)
def register(
    body: RegisterRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
) -> User:
    """Create an account and email a welcome message. Returns 409 if the email is already registered."""
    try:
        user = service.register_user(
            db,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            timezone=body.timezone,
        )
    except service.EmailAlreadyRegistered:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    background_tasks.add_task(send_welcome_email, user.email, user.full_name, user.timezone)
    return user


# func to exchange email and password for an access token and a refresh cookie
@router.post(
    "/login", response_model=TokenResponse, dependencies=[Depends(login_ip_limit)]
)
def login(
    body: LoginRequest, response: Response, db: Session = Depends(get_db)
) -> TokenResponse:
    """Sign in: returns a short-lived access token and sets the HttpOnly refresh cookie.

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
    refresh_token, expires_at = service.start_session(db, user)
    set_refresh_cookie(response, refresh_token, expires_at)
    return _token_response(user)


# func to build the access-token response body
def _token_response(user: User) -> TokenResponse:
    """A fresh access token for `user` and how many seconds it lasts."""
    return TokenResponse(
        access_token=create_access_token(user.id),
        expires_in=get_settings().access_token_expire_minutes * 60,
    )


# func to trade the refresh cookie for a new access token
@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(refresh_ip_limit), Depends(require_trusted_origin)],
)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    """Exchange the refresh cookie for a new access token (and a rotated cookie).

    Returns 401 (and deletes the cookie) if there is no valid refresh token. The web app
    calls this on page load and whenever an access token expires.
    """
    raw_token = read_refresh_cookie(request)
    try:
        if raw_token is None:
            raise service.InvalidRefreshToken
        user, new_token, expires_at = service.rotate_session(db, raw_token)
    except service.InvalidRefreshToken:
        rejected = error_response(
            status.HTTP_401_UNAUTHORIZED, "Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
        clear_refresh_cookie(rejected)
        return rejected
    if new_token is not None and expires_at is not None:
        set_refresh_cookie(response, new_token, expires_at)
    return _token_response(user)


# func to log out of this device
@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_trusted_origin)],
)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    """Revoke this login's refresh tokens and delete the cookie. Safe to call when signed out."""
    raw_token = read_refresh_cookie(request)
    if raw_token:
        service.end_session(db, raw_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response)
    return response


# func: return the profile of the authenticated user
@router.get("/me", response_model=UserRead)
def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the profile of the authenticated user."""
    return current_user


# func to change the signed-in user's own settings
@router.patch("/me", response_model=UserRead)
def update_me(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Change name, timezone or reminder style (`each` or `digest`). Only fields sent change."""
    return service.update_profile(db, current_user, body)


# func to record progress through the getting-started journey
@router.patch("/me/onboarding", response_model=UserRead)
def update_my_onboarding(
    body: OnboardingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Remember what the user has seen or done in the getting-started journey (flags only)."""
    return service.update_onboarding(db, current_user, body)


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
    body: ResetPasswordRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Set a new password using the emailed token, then email a security notice.

    Returns 400 if the token is bad.
    """
    try:
        user = service.reset_password(
            db, raw_token=body.token, new_password=body.new_password
        )
    except service.InvalidResetToken:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token")
    background_tasks.add_task(send_password_changed_email, user.email, user.full_name)
    return MessageResponse(message="Password updated.")
