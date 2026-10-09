"""Finding the real client IP behind reverse proxies, without trusting what clients claim.

Each proxy appends the address of the peer that connected to it to `X-Forwarded-For`:

    client -> edge proxy -> API        X-Forwarded-For: <anything the client sent>, <client IP>

Everything on the LEFT of the entries our own proxies added is written by the caller and
can be anything, so reading the first (leftmost) value lets anyone pick their own "IP"
and dodge per-IP rate limits. Instead we count `TRUSTED_PROXY_HOPS` entries from the
RIGHT, which are the ones our proxies wrote.
"""
import ipaddress
import logging

from fastapi import Request

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


# func to read an IP address from text
def _valid_ip(text: str) -> str | None:
    """Return `text` normalised if it is a valid IPv4/IPv6 address, else None."""
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return None


# func to work out who is really calling
def client_ip(request: Request) -> str:
    """Return the caller's IP address.

    With `TRUSTED_PROXY_HOPS=0` (default) the header is ignored and the connecting
    address is used. With N > 0 the Nth entry from the right of `X-Forwarded-For` is used.
    If the header has fewer entries than that, or the entry is not a valid IP, we fall
    back to the connecting address rather than believe an unverifiable value.
    """
    peer = request.client.host if request.client else "unknown"
    hops = get_settings().trusted_proxy_hops
    if hops <= 0:
        return peer
    entries = [e for e in request.headers.get("x-forwarded-for", "").split(",") if e.strip()]
    if len(entries) < hops:
        return peer
    return _valid_ip(entries[-hops]) or peer


# func to say at start-up how client IPs are determined
def log_proxy_configuration(settings: Settings) -> None:
    """Log how client IPs are read; warn in production when no proxy is configured.

    In production the API normally sits behind a load balancer. If TRUSTED_PROXY_HOPS is
    left at 0 every request then appears to come from the proxy, so all users would share
    one per-IP rate-limit bucket.
    """
    if settings.trusted_proxy_hops > 0:
        logger.info(
            "Client IPs are read from X-Forwarded-For, trusting %s proxy hop(s)",
            settings.trusted_proxy_hops,
        )
    elif settings.app_env == "production":
        logger.warning(
            "TRUSTED_PROXY_HOPS=0 in production: per-IP rate limits use the connecting "
            "address. Behind a load balancer set it to the number of proxies in front of the API."
        )
