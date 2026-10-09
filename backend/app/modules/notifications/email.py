"""Email delivery through Resend, behind a small interface (transport only).

What the emails say lives in `templates/` and `service.py`; this file only sends them.

Other code only calls `send_email(EmailMessage(...))`. Which sender is used is
decided by settings, so swapping providers later means adding one class here.
"""
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT_SECONDS = 10


# class for "the provider did not accept or deliver the email"
class EmailSendError(Exception):
    """Raised when an email could not be sent (network error or provider rejection)."""


# class for one outgoing email
@dataclass(frozen=True)
class EmailMessage:
    """An email to send. `idempotency_key` lets the provider drop an exact duplicate."""

    to: str
    subject: str
    html: str
    text: str
    idempotency_key: str | None = None


# class for the contract every sender follows
class EmailSender(Protocol):
    """Anything with a `send(message)` method that raises EmailSendError on failure."""

    def send(self, message: EmailMessage) -> None: ...


# class for sending through the Resend HTTP API
class ResendSender:
    """Sends email via Resend (https://resend.com)."""

    # func to store credentials and (optionally) an HTTP client to reuse
    def __init__(
        self, api_key: str, from_address: str, client: httpx.Client | None = None
    ) -> None:
        """`client` is injectable so tests can fake the network."""
        self._api_key = api_key
        self._from = from_address
        self._client = client

    # func to send one message
    def send(self, message: EmailMessage) -> None:
        """POST the message to Resend. Raises EmailSendError on any failure."""
        headers = {"Authorization": f"Bearer {self._api_key}"}
        if message.idempotency_key:
            # Resend ignores a repeat of the same key, so a retry after a crash
            # cannot deliver the same reminder twice.
            headers["Idempotency-Key"] = message.idempotency_key
        payload = {
            "from": self._from,
            "to": [message.to],
            "subject": message.subject,
            "html": message.html,
            "text": message.text,
        }
        try:
            if self._client is not None:
                response = self._client.post(RESEND_URL, json=payload, headers=headers)
            else:
                with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                    response = client.post(RESEND_URL, json=payload, headers=headers)
        except httpx.HTTPError as error:
            raise EmailSendError(f"Could not reach Resend: {error}") from error
        if response.status_code >= 400:
            raise EmailSendError(
                f"Resend rejected the email ({response.status_code}): {response.text[:300]}"
            )


# class for development: log instead of sending
class LogSender:
    """Development stand-in used when no RESEND_API_KEY is set. Sends nothing."""

    # func to log the message
    def send(self, message: EmailMessage) -> None:
        """Log the email (including the body, so reset tokens are visible in dev)."""
        logger.info(
            "[email not sent: no RESEND_API_KEY] to=%s subject=%s\n%s",
            message.to,
            message.subject,
            message.text,
        )


# func to pick the sender from settings
def get_sender() -> EmailSender:
    """Return ResendSender when a key is configured, else LogSender.

    In production a missing key is an error: silently logging reminders instead
    of sending them would defeat the whole product.
    """
    settings = get_settings()
    if settings.resend_api_key:
        return ResendSender(settings.resend_api_key, settings.email_from)
    if settings.app_env == "production":
        raise EmailSendError("RESEND_API_KEY is not set")
    return LogSender()


# func to send an email using the configured provider
def send_email(message: EmailMessage) -> None:
    """Send `message` with the configured sender. Raises EmailSendError on failure."""
    get_sender().send(message)
