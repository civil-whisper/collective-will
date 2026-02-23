from __future__ import annotations

import base64
import json
from unittest.mock import patch

from src.security.web_auth import _sign, create_web_access_token, verify_web_access_token


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@patch("src.security.web_auth.get_settings")
def test_create_and_verify_token(mock_settings) -> None:
    mock_settings.return_value.web_access_token_secret = "test-secret"
    mock_settings.return_value.web_access_token_expiry_hours = 1

    token = create_web_access_token(email="user@example.com")
    verified_email = verify_web_access_token(token=token)

    assert verified_email == "user@example.com"


@patch("src.security.web_auth.get_settings")
def test_verify_rejects_modified_signature(mock_settings) -> None:
    mock_settings.return_value.web_access_token_secret = "test-secret"
    mock_settings.return_value.web_access_token_expiry_hours = 1

    token = create_web_access_token(email="user@example.com")
    payload_part, _ = token.split(".", maxsplit=1)
    tampered = f"{payload_part}.invalid-signature"

    assert verify_web_access_token(token=tampered) is None


@patch("src.security.web_auth.get_settings")
def test_verify_rejects_expired_token(mock_settings) -> None:
    mock_settings.return_value.web_access_token_secret = "test-secret"
    mock_settings.return_value.web_access_token_expiry_hours = 1

    expired_payload = {
        "email": "user@example.com",
        "exp": 1,
        "v": 1,
    }
    payload_b64 = _b64url(json.dumps(expired_payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _sign(payload_b64, "test-secret")
    token = f"{payload_b64}.{signature}"

    assert verify_web_access_token(token=token) is None
