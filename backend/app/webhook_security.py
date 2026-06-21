"""
Vapi webhook signature verification.

Vapi signs webhook payloads using an HMAC-SHA256 of the raw request body with
a shared secret (configured both in the Vapi dashboard and as
VAPI_WEBHOOK_SECRET here). We verify using a constant-time comparison to
avoid timing attacks, and reject BEFORE any payload parsing or DB write.
"""
import hashlib
import hmac

from app.config import get_settings

settings = get_settings()


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """
    Returns True if the signature header matches the HMAC-SHA256 of raw_body
    computed with VAPI_WEBHOOK_SECRET. Returns False on any mismatch, missing
    header, or missing secret configuration.
    """
    if not settings.VAPI_WEBHOOK_SECRET:
        # Fail closed: if no secret is configured, never treat a request as verified.
        return False

    if not signature_header:
        return False

    expected = hmac.new(
        settings.VAPI_WEBHOOK_SECRET.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    # Vapi may prefix the header (e.g. "sha256=...") depending on dashboard config;
    # normalize before comparing.
    received = signature_header.removeprefix("sha256=").strip()

    return hmac.compare_digest(expected, received)
