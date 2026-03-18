from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from src.ops.monitor import (
    _fingerprint,
    _format_alert_text,
    _format_heartbeat_text,
    _load_state,
    _save_state,
    check_and_alert,
)


@pytest.fixture(autouse=True)
def _tmp_state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("src.ops.monitor.STATE_DIR", tmp_path)


def _ok_health(generated_at: str | None = None) -> dict:
    return {
        "generated_at": generated_at or datetime.now(UTC).isoformat(),
        "overall_status": "ok",
        "services": [
            {"name": "api", "status": "ok", "detail": None},
            {"name": "database", "status": "ok", "detail": None},
            {"name": "telegram_webhook", "status": "ok", "detail": "webhook healthy"},
            {"name": "scheduler", "status": "ok", "detail": "ok"},
        ],
        "recent_error_count": 0,
        "recent_warning_count": 0,
        "pipeline_degradation_count": 0,
    }


def _error_health() -> dict:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "overall_status": "error",
        "services": [
            {"name": "api", "status": "ok", "detail": None},
            {"name": "database", "status": "error", "detail": "database health check failed"},
            {"name": "telegram_webhook", "status": "error", "detail": "webhook URL not set"},
        ],
        "recent_error_count": 5,
        "recent_warning_count": 2,
        "pipeline_degradation_count": 1,
    }


class TestFingerprint:
    def test_consistent(self) -> None:
        fp1 = _fingerprint("database", "health check failed")
        fp2 = _fingerprint("database", "health check failed")
        assert fp1 == fp2

    def test_differs_for_different_input(self) -> None:
        fp1 = _fingerprint("database", "health check failed")
        fp2 = _fingerprint("telegram", "webhook URL not set")
        assert fp1 != fp2


class TestStateManagement:
    def test_load_empty_state(self) -> None:
        state = _load_state("staging")
        assert state["active_fingerprints"] == {}
        assert state["last_heartbeat_date"] is None

    def test_save_and_load_round_trip(self) -> None:
        state = {
            "active_fingerprints": {"abc123": "2026-03-18T10:00:00"},
            "last_heartbeat_date": "2026-03-18",
            "last_check_at": "2026-03-18T10:00:00",
        }
        _save_state("staging", state)
        loaded = _load_state("staging")
        assert loaded == state


class TestFormatting:
    def test_alert_text_includes_failures(self) -> None:
        failures = [{"service": "database", "status": "error", "detail": "unreachable"}]
        health = _error_health()
        text = _format_alert_text("staging", failures, health)
        assert "STAGING" in text
        assert "database" in text
        assert "unreachable" in text

    def test_heartbeat_text_includes_services(self) -> None:
        health = _ok_health()
        text = _format_heartbeat_text("production", health)
        assert "PRODUCTION" in text
        assert "all services OK" in text


def _make_mock_httpx(health_data: dict):
    """Build a mock httpx.AsyncClient that returns the given health JSON."""

    class _FakeResp:
        status_code = 200

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return health_data

    class _Client:
        def __init__(self, **kw: object) -> None:
            pass

        async def get(self, url: str) -> _FakeResp:
            return _FakeResp()

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a: object) -> None:
            pass

    return _Client


class TestCheckAndAlert:
    @pytest.mark.asyncio
    async def test_sends_alert_on_error(self) -> None:
        health = _error_health()

        with (
            patch("src.ops.monitor.httpx.AsyncClient", _make_mock_httpx(health)),
            patch("src.ops.monitor.send_operator_email", new_callable=AsyncMock, return_value=True) as mock_email,
        ):
            result = await check_and_alert(
                env="staging",
                backend_url="http://127.0.0.1:8100",
                alert_emails=["ops@example.com"],
                resend_api_key="re_test",
                email_from="ops@resend.dev",
                heartbeat_hour_utc=8,
                dedup_minutes=60,
            )

        assert result["action"] == "alert_sent"
        mock_email.assert_called_once()
        call_kwargs = mock_email.call_args[1]
        assert "STAGING" in call_kwargs["subject"]
        assert call_kwargs["to"] == ["ops@example.com"]

    @pytest.mark.asyncio
    async def test_deduplicates_repeated_alerts(self) -> None:
        health = _error_health()

        with (
            patch("src.ops.monitor.httpx.AsyncClient", _make_mock_httpx(health)),
            patch("src.ops.monitor.send_operator_email", new_callable=AsyncMock, return_value=True),
        ):
            kwargs = dict(
                env="staging",
                backend_url="http://127.0.0.1:8100",
                alert_emails=["ops@example.com"],
                resend_api_key="re_test",
                email_from="ops@resend.dev",
                heartbeat_hour_utc=8,
                dedup_minutes=60,
            )
            r1 = await check_and_alert(**kwargs)
            r2 = await check_and_alert(**kwargs)

        assert r1["action"] == "alert_sent"
        assert r2["action"] == "alert_suppressed_dedup"

    @pytest.mark.asyncio
    async def test_sends_heartbeat_when_all_ok(self, monkeypatch) -> None:
        health = _ok_health()

        fixed_time = datetime(2026, 3, 18, 10, 0, 0, tzinfo=UTC)

        with (
            patch("src.ops.monitor.httpx.AsyncClient", _make_mock_httpx(health)),
            patch("src.ops.monitor.send_operator_email", new_callable=AsyncMock, return_value=True) as mock_email,
            patch("src.ops.monitor.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            result = await check_and_alert(
                env="staging",
                backend_url="http://127.0.0.1:8100",
                alert_emails=["ops@example.com"],
                resend_api_key="re_test",
                email_from="ops@resend.dev",
                heartbeat_hour_utc=8,
                dedup_minutes=60,
            )

        assert result["action"] == "heartbeat_sent"
        mock_email.assert_called_once()
        assert "heartbeat" in mock_email.call_args[1]["subject"].lower()

    @pytest.mark.asyncio
    async def test_no_email_when_no_recipients(self) -> None:
        health = _error_health()

        with (
            patch("src.ops.monitor.httpx.AsyncClient", _make_mock_httpx(health)),
            patch("src.ops.monitor.send_operator_email", new_callable=AsyncMock) as mock_email,
        ):
            result = await check_and_alert(
                env="staging",
                backend_url="http://127.0.0.1:8100",
                alert_emails=[],
                resend_api_key="re_test",
                email_from="ops@resend.dev",
                heartbeat_hour_utc=8,
                dedup_minutes=60,
            )

        assert result["action"] == "none"
        mock_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_unreachable_backend(self) -> None:
        class _FailClient:
            def __init__(self, **kw: object) -> None:
                pass

            async def get(self, url: str):
                raise httpx.ConnectError("refused")

            async def __aenter__(self) -> _FailClient:
                return self

            async def __aexit__(self, *a: object) -> None:
                pass

        with (
            patch("src.ops.monitor.httpx.AsyncClient", _FailClient),
            patch("src.ops.monitor.send_operator_email", new_callable=AsyncMock, return_value=True) as mock_email,
        ):
            result = await check_and_alert(
                env="staging",
                backend_url="http://127.0.0.1:9999",
                alert_emails=["ops@example.com"],
                resend_api_key="re_test",
                email_from="ops@resend.dev",
                heartbeat_hour_utc=8,
                dedup_minutes=60,
            )

        assert result["action"] == "alert_sent"
        mock_email.assert_called_once()
