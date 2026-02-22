from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


def test_health_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ok() -> bool:
        return True

    monkeypatch.setattr("src.api.main.check_db_health", _ok)
    client = TestClient(app)
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fail() -> bool:
        return False

    monkeypatch.setattr("src.api.main.check_db_health", _fail)
    client = TestClient(app)
    response = client.get("/health/db")
    assert response.status_code == 503
