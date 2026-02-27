from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.api.main import app
from src.api.routes.auth import _get_client_ip
from src.db.connection import get_db
from src.models.user import User


def _mock_session() -> AsyncMock:
    return AsyncMock()


class TestGetClientIp:
    def test_xff_single_ip(self) -> None:
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "203.0.113.50"}
        assert _get_client_ip(request) == "203.0.113.50"

    def test_xff_chain_returns_first(self) -> None:
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "203.0.113.50, 70.41.3.18, 150.172.238.178"}
        assert _get_client_ip(request) == "203.0.113.50"

    def test_no_xff_falls_back_to_client_host(self) -> None:
        request = MagicMock()
        request.headers = {}
        request.client.host = "192.168.1.1"
        assert _get_client_ip(request) == "192.168.1.1"

    def test_no_xff_no_client_returns_empty(self) -> None:
        request = MagicMock()
        request.headers = {}
        request.client = None
        assert _get_client_ip(request) == ""


class TestSubscribe:
    def test_successful_subscribe(self) -> None:
        user = AsyncMock(spec=User)
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch(
                "src.api.routes.auth.subscribe_email",
                new_callable=AsyncMock,
                return_value=(user, "test-token-123"),
            ):
                client = TestClient(app)
                response = client.post(
                    "/auth/subscribe",
                    json={
                        "email": "user@example.com",
                        "locale": "fa",
                        "messaging_account_ref": "web-signup",
                    },
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "pending_verification"
                assert data["token"] == "test-token-123"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_subscribe_blocked_returns_429(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch(
                "src.api.routes.auth.subscribe_email",
                new_callable=AsyncMock,
                return_value=(None, "rate limit exceeded"),
            ):
                client = TestClient(app)
                response = client.post(
                    "/auth/subscribe",
                    json={
                        "email": "user@example.com",
                        "locale": "fa",
                        "messaging_account_ref": "web-signup",
                    },
                )
                assert response.status_code == 429
                assert "rate limit" in response.json()["detail"]
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_subscribe_blocked_default_message(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch(
                "src.api.routes.auth.subscribe_email",
                new_callable=AsyncMock,
                return_value=(None, None),
            ):
                client = TestClient(app)
                response = client.post(
                    "/auth/subscribe",
                    json={
                        "email": "user@example.com",
                        "locale": "fa",
                        "messaging_account_ref": "web-signup",
                    },
                )
                assert response.status_code == 429
                assert response.json()["detail"] == "signup blocked"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_subscribe_rejects_invalid_email(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.post(
                "/auth/subscribe",
                json={
                    "email": "not-an-email",
                    "locale": "fa",
                    "messaging_account_ref": "web-signup",
                },
            )
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_subscribe_rejects_missing_fields(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            client = TestClient(app)
            response = client.post("/auth/subscribe", json={"email": "a@b.com"})
            assert response.status_code == 422
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_subscribe_passes_correct_arguments(self) -> None:
        user = AsyncMock(spec=User)
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            mock_subscribe = AsyncMock(return_value=(user, "tok"))
            with patch("src.api.routes.auth.subscribe_email", mock_subscribe):
                client = TestClient(app)
                client.post(
                    "/auth/subscribe",
                    json={
                        "email": "test@example.org",
                        "locale": "en",
                        "messaging_account_ref": "ref-abc",
                    },
                    headers={"X-Forwarded-For": "10.0.0.1"},
                )
                mock_subscribe.assert_called_once()
                call_kwargs = mock_subscribe.call_args.kwargs
                assert call_kwargs["email"] == "test@example.org"
                assert call_kwargs["locale"] == "en"
                assert call_kwargs["requester_ip"] == "10.0.0.1"
                assert call_kwargs["messaging_account_ref"] == "ref-abc"
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestVerify:
    def test_successful_verification(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch(
                "src.api.routes.auth.verify_magic_link",
                new_callable=AsyncMock,
                return_value=(True, "linking-code-xyz", "user@example.com", "web-session-code"),
            ):
                client = TestClient(app)
                response = client.post("/auth/verify/test-token-123")
                assert response.status_code == 200
                assert response.json()["status"] == "linking-code-xyz"
                assert response.json()["email"] == "user@example.com"
                assert response.json()["web_session_code"] == "web-session-code"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_invalid_token_returns_400(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch(
                "src.api.routes.auth.verify_magic_link",
                new_callable=AsyncMock,
                return_value=(False, "invalid_token", None, None),
            ):
                client = TestClient(app)
                response = client.post("/auth/verify/bad-token")
                assert response.status_code == 400
                assert response.json()["detail"] == "invalid_token"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_expired_token_returns_400(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch(
                "src.api.routes.auth.verify_magic_link",
                new_callable=AsyncMock,
                return_value=(False, "expired_token", None, None),
            ):
                client = TestClient(app)
                response = client.post("/auth/verify/old-token")
                assert response.status_code == 400
                assert response.json()["detail"] == "expired_token"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_verify_passes_correct_token(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            mock_verify = AsyncMock(return_value=(True, "ok", "user@example.com", "web-code"))
            with patch("src.api.routes.auth.verify_magic_link", mock_verify):
                client = TestClient(app)
                client.post("/auth/verify/my-special-token")
                mock_verify.assert_called_once()
                assert mock_verify.call_args.kwargs["token"] == "my-special-token"
        finally:
            app.dependency_overrides.pop(get_db, None)


class TestWebSession:
    def test_web_session_success(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch(
                "src.api.routes.auth.exchange_web_session_code",
                new_callable=AsyncMock,
                return_value=(True, "access-token-abc"),
            ):
                client = TestClient(app)
                response = client.post(
                    "/auth/web-session",
                    json={"email": "user@example.com", "code": "code-123"},
                )
                assert response.status_code == 200
                body = response.json()
                assert body["status"] == "ok"
                assert body["email"] == "user@example.com"
                assert body["access_token"] == "access-token-abc"
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_web_session_invalid_code(self) -> None:
        session = _mock_session()
        app.dependency_overrides[get_db] = lambda: session
        try:
            with patch(
                "src.api.routes.auth.exchange_web_session_code",
                new_callable=AsyncMock,
                return_value=(False, "invalid_code"),
            ):
                client = TestClient(app)
                response = client.post(
                    "/auth/web-session",
                    json={"email": "user@example.com", "code": "bad"},
                )
                assert response.status_code == 400
                assert response.json()["detail"] == "invalid_code"
        finally:
            app.dependency_overrides.pop(get_db, None)
