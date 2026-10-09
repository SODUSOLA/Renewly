"""The refresh-token cookie and the CSRF guard that protects the endpoints using it.

The refresh token lives only in an HttpOnly cookie, so page JavaScript (and therefore
any injected script) can never read it. The short-lived access token is kept in memory
by the web app. The cookie is only sent to the auth endpoints (`path`).
"""
from datetime import UTC, datetime

from fastapi import HTTPException, Request, Response, status

from app.core.config import get_settings


# func to put the refresh token in an HttpOnly cookie
def set_refresh_cookie(response: Response, raw_token: str, expires_at: datetime) -> None:
    """Set the refresh cookie; it expires when the token does."""
    settings = get_settings()
    max_age = max(0, round((expires_at - datetime.now(UTC)).total_seconds()))
    response.set_cookie(
        key=settings.refresh_cookie_name,
        value=raw_token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure_effective,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
        domain=settings.cookie_domain or None,
    )


# func to remove the refresh cookie from the browser
def clear_refresh_cookie(response: Response) -> None:
    """Tell the browser to delete the refresh cookie (attributes must match those it was set with)."""
    settings = get_settings()
    response.delete_cookie(
        key=settings.refresh_cookie_name,
        httponly=True,
        secure=settings.cookie_secure_effective,
        samesite=settings.cookie_samesite,
        path=settings.cookie_path,
        domain=settings.cookie_domain or None,
    )


# func to read the refresh cookie from a request
def read_refresh_cookie(request: Request) -> str | None:
    """Return the refresh token the browser sent, if any."""
    return request.cookies.get(get_settings().refresh_cookie_name)


# func to reject cookie-using requests that come from another website (CSRF guard)
def require_trusted_origin(request: Request) -> None:
    """Allow the request only if its `Origin` header is one of our web app origins.

    Browsers always send `Origin` on cross-site POSTs, so a malicious page cannot use a
    victim's cookie here. Requests without the header (curl, mobile apps, server code)
    are not browsers acting for a victim, so they pass. This backs up SameSite cookies.
    """
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin.rstrip("/") not in get_settings().cors_origin_list:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Origin not allowed")
