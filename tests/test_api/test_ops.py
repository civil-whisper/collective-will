from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.config import get_settings
from src.db.connection import get_db
from src.db.evidence import EvidenceLogEntry
from src.db.heartbeat import SchedulerHeartbeat
from src.ops import events as ops_events
from src.security.web_auth import create_web_access_token


class DummySettings(SimpleNamespace):
    def ops_admin_email_list(self) -> list[str]:
        raw = getattr(self, "ops_admin_emails", "")
        return [item.strip().lower() for item in raw.split(",") if item.strip()]


def _settings(
    *,
    enabled: bool = True,
    require_admin: bool = False,
    admin_emails: str = "",
) -> DummySettings:
    return DummySettings(
        ops_console_enabled=enabled,
        ops_console_show_in_nav=True,
        ops_console_require_admin=require_admin,
        ops_admin_emails=admin_emails,
        telegram_bot_token="test-token",
        resend_api_key="resend-test-key",
        ops_event_buffer_size=500,
        pipeline_interval_hours=6.0,
        pipeline_min_interval_hours=0.01,
    )


def _mock_session(
    rows: list[EvidenceLogEntry] | None = None,
    heartbeat: SchedulerHeartbeat | None = None,
) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value = MagicMock(all=MagicMock(return_value=rows or []))
    result.scalar_one_or_none.return_value = heartbeat
    session.execute.return_value = result
    session.get.return_value = heartbeat
    return session


def _auth_headers(email: str = "test@example.com") -> dict[str, str]:
    token = create_web_access_token(email=email)
    return {"Authorization": f"Bearer {token}"}


def _make_evidence_entry(
    *,
    event_type: str = "submission_received",
    payload: dict[str, object] | None = None,
) -> MagicMock:
    entry = MagicMock(spec=EvidenceLogEntry)
    entry.id = 1
    entry.timestamp = datetime(2026, 2, 20, 10, 0, 0, tzinfo=UTC)
    entry.event_type = event_type
    entry.entity_type = "submission"
    entry.entity_id = uuid4()
    entry.payload = payload or {"state": "ok"}
    entry.hash = "abc"
    entry.prev_hash = "genesis"
    return entry


def test_ops_status_respects_admin_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db_ok() -> bool:
        return True

    monkeypatch.setattr("src.api.routes.ops.check_db_health", _db_ok)
    session = _mock_session()
    app.dependency_overrides[get_settings] = lambda: _settings(
        enabled=True,
        require_admin=True,
        admin_emails="admin@example.com",
    )
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)

        missing = client.get("/ops/status")
        assert missing.status_code == 401

        forbidden = client.get("/ops/status", headers=_auth_headers("user@example.com"))
        assert forbidden.status_code == 403

        allowed = client.get("/ops/status", headers=_auth_headers("admin@example.com"))
        assert allowed.status_code == 200
        assert allowed.json()["require_admin"] is True
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)


def test_ops_status_disabled_returns_404() -> None:
    app.dependency_overrides[get_settings] = lambda: _settings(enabled=False)
    try:
        client = TestClient(app)
        response = client.get("/ops/status")
        assert response.status_code == 404
        assert response.json()["detail"] == "ops_console_disabled"
    finally:
        app.dependency_overrides.pop(get_settings, None)


def test_ops_events_filter_and_redaction() -> None:
    ops_events.configure_ops_event_logging(max_size=500)
    ops_events.ops_event_buffer.add(
        {
            "timestamp": "2026-02-20T10:00:00.000Z",
            "level": "error",
            "component": "src.handlers.identity",
            "event_type": "identity.send_failed",
            "message": "Magic link failed for user@example.com",
            "correlation_id": None,
            "payload": {"email": "user@example.com", "status": "failed"},
        }
    )

    session = _mock_session([_make_evidence_entry()])
    app.dependency_overrides[get_settings] = lambda: _settings(enabled=True, require_admin=False)
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        response = client.get("/ops/events?limit=10&level=error", headers=_auth_headers())
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["event_type"] == "identity.send_failed"
        assert "[REDACTED]" in data[0]["message"]
        assert data[0]["payload"]["email"] == "[REDACTED]"
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)


def test_ops_events_include_request_correlation_id() -> None:
    ops_events.configure_ops_event_logging(max_size=500)
    session = _mock_session([])
    app.dependency_overrides[get_settings] = lambda: _settings(enabled=True, require_admin=False)
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        health = client.get("/health", headers={"x-request-id": "trace-id-ops"})
        assert health.status_code == 200
        assert health.headers.get("x-request-id") == "trace-id-ops"

        response = client.get(
            "/ops/events?limit=25&type=api.request.completed&correlation_id=trace-id-ops",
            headers=_auth_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        health_events = [row for row in data if row["payload"].get("path") == "/health"]
        assert health_events
        assert health_events[0]["correlation_id"] == "trace-id-ops"
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)


def test_ops_jobs_returns_expected_rows() -> None:
    session = _mock_session([_make_evidence_entry(event_type="cluster_created")])
    app.dependency_overrides[get_settings] = lambda: _settings(enabled=True, require_admin=False)
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        response = client.get("/ops/jobs", headers=_auth_headers())
        assert response.status_code == 200
        names = [row["name"] for row in response.json()]
        assert "pipeline_batch" in names
        assert "cycle_management" in names
        assert "daily_merkle_anchor" in names
        assert "email_delivery" in names
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)


def _make_heartbeat(
    *,
    last_run_at: datetime | None = None,
    status: str = "ok",
    detail: str | None = "processed=3 candidates=2 clusters=1",
) -> MagicMock:
    hb = MagicMock(spec=SchedulerHeartbeat)
    hb.last_run_at = last_run_at or datetime.now(UTC)
    hb.status = status
    hb.detail = detail
    return hb


def test_ops_status_scheduler_ok_with_recent_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db_ok() -> bool:
        return True

    monkeypatch.setattr("src.api.routes.ops.check_db_health", _db_ok)
    heartbeat = _make_heartbeat(last_run_at=datetime.now(UTC) - timedelta(minutes=30))
    session = _mock_session(heartbeat=heartbeat)
    app.dependency_overrides[get_settings] = lambda: _settings(enabled=True)
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        response = client.get("/ops/status", headers=_auth_headers())
        assert response.status_code == 200
        services = {s["name"]: s for s in response.json()["services"]}
        assert services["scheduler"]["status"] == "ok"
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)


def test_ops_status_scheduler_unknown_without_heartbeat(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db_ok() -> bool:
        return True

    monkeypatch.setattr("src.api.routes.ops.check_db_health", _db_ok)
    session = _mock_session(heartbeat=None)
    app.dependency_overrides[get_settings] = lambda: _settings(enabled=True)
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        response = client.get("/ops/status", headers=_auth_headers())
        assert response.status_code == 200
        services = {s["name"]: s for s in response.json()["services"]}
        assert services["scheduler"]["status"] == "unknown"
        assert "no heartbeat" in services["scheduler"]["detail"]
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)


def test_ops_status_scheduler_degraded_when_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db_ok() -> bool:
        return True

    monkeypatch.setattr("src.api.routes.ops.check_db_health", _db_ok)
    heartbeat = _make_heartbeat(last_run_at=datetime.now(UTC) - timedelta(hours=20))
    session = _mock_session(heartbeat=heartbeat)
    app.dependency_overrides[get_settings] = lambda: _settings(enabled=True)
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        response = client.get("/ops/status", headers=_auth_headers())
        assert response.status_code == 200
        services = {s["name"]: s for s in response.json()["services"]}
        assert services["scheduler"]["status"] == "degraded"
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)


def test_ops_status_scheduler_error_when_heartbeat_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _db_ok() -> bool:
        return True

    monkeypatch.setattr("src.api.routes.ops.check_db_health", _db_ok)
    heartbeat = _make_heartbeat(status="error", detail="processed=0 candidates=0 clusters=0 errors=['DB down']")
    session = _mock_session(heartbeat=heartbeat)
    app.dependency_overrides[get_settings] = lambda: _settings(enabled=True)
    app.dependency_overrides[get_db] = lambda: session
    try:
        client = TestClient(app)
        response = client.get("/ops/status", headers=_auth_headers())
        assert response.status_code == 200
        services = {s["name"]: s for s in response.json()["services"]}
        assert services["scheduler"]["status"] == "error"
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db, None)
