from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from src.config import get_settings


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _sign(payload_b64: str, secret: str) -> str:
    signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("ascii"), hashlib.sha256).digest()
    return _base64url_encode(signature)


def create_web_access_token(*, email: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(hours=settings.web_access_token_expiry_hours)
    payload = {
        "email": email,
        "exp": int(expires_at.timestamp()),
        "v": 1,
    }
    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _base64url_encode(payload_json)
    signature_b64 = _sign(payload_b64, settings.web_access_token_secret)
    return f"{payload_b64}.{signature_b64}"


def verify_web_access_token(*, token: str) -> str | None:
    settings = get_settings()
    parts = token.split(".", maxsplit=1)
    if len(parts) != 2:
        return None
    payload_b64, signature_b64 = parts
    expected_signature = _sign(payload_b64, settings.web_access_token_secret)
    if not hmac.compare_digest(signature_b64, expected_signature):
        return None

    try:
        payload_raw = _base64url_decode(payload_b64)
        payload = json.loads(payload_raw)
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None
    email = payload.get("email")
    exp = payload.get("exp")
    if not isinstance(email, str) or not isinstance(exp, int):
        return None
    if int(datetime.now(UTC).timestamp()) >= exp:
        return None
    return email
