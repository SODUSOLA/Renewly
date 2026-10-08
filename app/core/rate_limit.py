"""Rate limiting for abuse-prone endpoints (login, sign-up, password reset).

Fixed-window counters keyed by client IP and, where it matters, by email. The
counters live in Redis in normal use, so every API process shares them; tests
use an in-memory backend. If Redis is unreachable we FAIL OPEN (allow the
request and log an error): a Redis outage must not lock every user out.
"""
import hashlib
import logging
import math
import threading
import time
from functools import lru_cache
from typing import Protocol

import redis
from fastapi import HTTPException, Request, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)


# class for the contract every counter store follows
class RateLimitBackend(Protocol):
    """Counts hits per key inside a window."""

    # func to record one hit
    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Record a hit; return (hits so far in this window, seconds until it resets)."""
        ...


# class for an in-process counter store (tests, single-process development)
class MemoryBackend:
    """Thread-safe in-memory counters. Not shared between processes."""

    # func to start with no counters
    def __init__(self) -> None:
        """Create an empty store."""
        self._entries: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    # func to record one hit
    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """Count a hit, starting a fresh window when the previous one has ended."""
        now = time.monotonic()
        with self._lock:
            count, reset_at = self._entries.get(key, (0, 0.0))
            if now >= reset_at:
                count, reset_at = 0, now + window_seconds
            count += 1
            self._entries[key] = (count, reset_at)
            return count, max(1, math.ceil(reset_at - now))

    # func to forget every counter
    def reset(self) -> None:
        """Clear all counters (used between tests)."""
        with self._lock:
            self._entries.clear()


# class for a Redis-backed counter store (shared by all API processes)
class RedisBackend:
    """Counters in Redis: INCR a key and let it expire when the window ends."""

    # func to connect lazily with short timeouts
    def __init__(self, url: str) -> None:
        """Short timeouts keep a slow Redis from slowing every request."""
        self._client = redis.Redis.from_url(
            url, socket_timeout=0.5, socket_connect_timeout=0.5
        )

    # func to record one hit
    def hit(self, key: str, window_seconds: int) -> tuple[int, int]:
        """INCR the key; the first hit (or a key without expiry) sets the window."""
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = pipe.execute()
        if count == 1 or ttl < 0:
            self._client.expire(key, window_seconds)
            ttl = window_seconds
        return int(count), int(ttl)


# func to choose the counter store from settings
@lru_cache
def get_backend() -> RateLimitBackend:
    """Return the shared backend: Redis by default, memory when configured."""
    settings = get_settings()
    if settings.rate_limit_backend == "memory":
        return MemoryBackend()
    return RedisBackend(settings.redis_url)


# func to clear counters between tests
def reset_rate_limits() -> None:
    """Empty the in-memory counters (no-op for Redis)."""
    backend = get_backend()
    if isinstance(backend, MemoryBackend):
        backend.reset()


# class for one named limit, e.g. "10 login attempts per 15 minutes"
class RateLimiter:
    """Allows `limit` hits per `window_seconds` per identifier, else raises 429.

    Use it as a route dependency (limits per client IP), or call `check()`
    yourself with another identifier such as an email address.
    """

    # func to define the limit
    def __init__(self, name: str, limit: int, window_seconds: int) -> None:
        """`name` namespaces the counters so different limits never share a key."""
        self.name = name
        self.limit = limit
        self.window_seconds = window_seconds

    # func to apply the limit per client IP when used with Depends()
    def __call__(self, request: Request) -> None:
        """FastAPI dependency: limit by the caller's IP address.

        Behind a reverse proxy run uvicorn with --proxy-headers so
        `request.client` is the real client, not the proxy.
        """
        self.check(request.client.host if request.client else "unknown")

    # func to count a hit for any identifier
    def check(self, identifier: str) -> None:
        """Count one hit for `identifier`; raise HTTP 429 once over the limit.

        Identifiers are hashed so emails never appear in Redis keys.
        """
        digest = hashlib.sha256(identifier.strip().lower().encode()).hexdigest()[:24]
        try:
            count, retry_after = get_backend().hit(
                f"rl:{self.name}:{digest}", self.window_seconds
            )
        except Exception:  # noqa: BLE001 - fail open on any backend problem
            logger.exception("Rate limiter backend unavailable; allowing request")
            return
        if count > self.limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"Too many requests. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
