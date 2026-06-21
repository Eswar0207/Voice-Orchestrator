"""Tests for webhook signature verification and payload routing."""
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.webhook_security import verify_signature


def _sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def test_verify_signature_accepts_valid_signature(monkeypatch):
    monkeypatch.setattr("app.webhook_security.settings.VAPI_WEBHOOK_SECRET", "my-secret")
    body = b'{"hello":"world"}'
    sig = _sign(body, "my-secret")
    assert verify_signature(body, sig) is True


def test_verify_signature_rejects_invalid_signature(monkeypatch):
    monkeypatch.setattr("app.webhook_security.settings.VAPI_WEBHOOK_SECRET", "my-secret")
    body = b'{"hello":"world"}'
    assert verify_signature(body, "deadbeef") is False


def test_verify_signature_rejects_missing_header(monkeypatch):
    monkeypatch.setattr("app.webhook_security.settings.VAPI_WEBHOOK_SECRET", "my-secret")
    body = b'{"hello":"world"}'
    assert verify_signature(body, None) is False


def test_verify_signature_fails_closed_when_no_secret_configured(monkeypatch):
    monkeypatch.setattr("app.webhook_security.settings.VAPI_WEBHOOK_SECRET", "")
    body = b'{"hello":"world"}'
    sig = _sign(body, "anything")
    assert verify_signature(body, sig) is False


def test_webhook_endpoint_rejects_unsigned_request(_isolated_test_db):
    from app.main import app

    client = TestClient(app)
    payload = {"message": {"type": "end-of-call-report"}}
    resp = client.post("/api/webhooks/vapi", json=payload)
    assert resp.status_code == 401


def test_webhook_endpoint_rejects_malformed_payload(_isolated_test_db, monkeypatch):
    monkeypatch.setattr("app.webhook_security.settings.VAPI_WEBHOOK_SECRET", "test-secret")
    from app.main import app

    client = TestClient(app)
    body = json.dumps({"message": {"type": "end-of-call-report"}}).encode()
    sig = _sign(body, "test-secret")
    resp = client.post(
        "/api/webhooks/vapi",
        content=body,
        headers={"x-vapi-signature": sig, "Content-Type": "application/json"},
    )
    # Valid signature, but missing metadata.customer_id -> 400
    assert resp.status_code == 400


def test_webhook_endpoint_ignores_non_end_of_call_events(_isolated_test_db, monkeypatch):
    monkeypatch.setattr("app.webhook_security.settings.VAPI_WEBHOOK_SECRET", "test-secret")
    from app.main import app

    client = TestClient(app)
    body = json.dumps({"message": {"type": "status-update"}}).encode()
    sig = _sign(body, "test-secret")
    resp = client.post(
        "/api/webhooks/vapi",
        content=body,
        headers={"x-vapi-signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
