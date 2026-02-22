from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


def test_webhook_rejects_invalid_api_key() -> None:
    client = TestClient(app)
    response = client.post("/webhooks/evolution", json={}, headers={"x-api-key": "bad"})
    assert response.status_code == 401


def test_webhook_rejects_missing_api_key() -> None:
    client = TestClient(app)
    response = client.post("/webhooks/evolution", json={})
    assert response.status_code == 401


def test_webhook_ignores_non_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLUTION_API_KEY", "good")
    from src.config import get_settings

    get_settings.cache_clear()
    client = TestClient(app)
    response = client.post(
        "/webhooks/evolution",
        json={"data": {"x": "y"}},
        headers={"x-api-key": "good"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


@patch("src.api.routes.webhooks.route_message", new_callable=AsyncMock)
def test_valid_text_message_triggers_route(mock_route: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLUTION_API_KEY", "good")
    from src.config import get_settings

    get_settings.cache_clear()
    client = TestClient(app)
    payload = {
        "data": {
            "key": {"remoteJid": "989123456789@s.whatsapp.net", "id": "MSG1"},
            "message": {"conversation": "hello world"},
            "messageTimestamp": 1707000000,
        }
    }
    response = client.post("/webhooks/evolution", json=payload, headers={"x-api-key": "good"})
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_webhook_returns_200_for_status_update(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVOLUTION_API_KEY", "testkey")
    from src.config import get_settings

    get_settings.cache_clear()
    client = TestClient(app)
    payload = {"event": "status.update", "data": {"status": "delivered"}}
    response = client.post("/webhooks/evolution", json=payload, headers={"x-api-key": "testkey"})
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
