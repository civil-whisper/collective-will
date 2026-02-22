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


def test_telegram_webhook_returns_404_when_token_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    from src.config import get_settings

    get_settings.cache_clear()
    client = TestClient(app)
    payload = {"update_id": 1, "message": {"message_id": 1, "chat": {"id": 123}, "text": "hi"}}
    response = client.post("/webhooks/telegram", json=payload)
    assert response.status_code == 404


@patch("src.api.routes.webhooks.route_message", new_callable=AsyncMock)
def test_telegram_webhook_accepts_valid_message(mock_route: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-bot-token")
    from src.config import get_settings

    get_settings.cache_clear()
    client = TestClient(app)
    payload = {
        "update_id": 123,
        "message": {
            "message_id": 42,
            "from": {"id": 987654321, "is_bot": False, "first_name": "Test"},
            "chat": {"id": 987654321, "type": "private"},
            "date": 1707000000,
            "text": "سلام",
        },
    }
    response = client.post("/webhooks/telegram", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_telegram_webhook_ignores_non_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-bot-token")
    from src.config import get_settings

    get_settings.cache_clear()
    client = TestClient(app)
    payload = {
        "update_id": 124,
        "message": {
            "message_id": 43,
            "chat": {"id": 987654321, "type": "private"},
            "date": 1707000000,
            "photo": [{"file_id": "ABC"}],
        },
    }
    response = client.post("/webhooks/telegram", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
