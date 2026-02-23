from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.email.sender import (
    _build_magic_link_html,
    _build_plain_text,
    send_magic_link_email,
)

LINK = "https://example.com/verify?token=abc123"


class TestBuildMagicLinkHtml:
    def test_english_template_contains_link(self) -> None:
        subject, html = _build_magic_link_html(LINK, "en", expiry_minutes=15)
        assert LINK in html
        assert "Verify your email" in subject
        assert "Verify Email" in html
        assert 'dir="ltr"' in html

    def test_farsi_template_contains_link(self) -> None:
        subject, html = _build_magic_link_html(LINK, "fa", expiry_minutes=15)
        assert LINK in html
        assert "تأیید ایمیل" in subject
        assert 'dir="rtl"' in html

    def test_template_has_expiry_notice_en(self) -> None:
        _, html = _build_magic_link_html(LINK, "en", expiry_minutes=15)
        assert "15 minutes" in html

    def test_template_has_expiry_notice_fa(self) -> None:
        _, html = _build_magic_link_html(LINK, "fa", expiry_minutes=15)
        assert "۱۵ دقیقه" in html


class TestBuildPlainText:
    def test_english_plain_text(self) -> None:
        text = _build_plain_text(LINK, "en", expiry_minutes=15)
        assert LINK in text
        assert "15 minutes" in text

    def test_farsi_plain_text(self) -> None:
        text = _build_plain_text(LINK, "fa", expiry_minutes=15)
        assert LINK in text
        assert "۱۵ دقیقه" in text


class TestSendMagicLinkEmail:
    @pytest.mark.asyncio
    async def test_logs_when_no_api_key(self) -> None:
        with patch("src.email.sender.logger") as mock_logger:
            result = await send_magic_link_email(
                to="user@example.com",
                magic_link_url=LINK,
                locale="en",
                resend_api_key=None,
                email_from="test@resend.dev",
                expiry_minutes=15,
                http_timeout_seconds=10.0,
            )
        assert result is True
        mock_logger.info.assert_called_once()
        assert "email sending disabled" in mock_logger.info.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_logs_when_empty_api_key(self) -> None:
        with patch("src.email.sender.logger") as mock_logger:
            result = await send_magic_link_email(
                to="user@example.com",
                magic_link_url=LINK,
                locale="en",
                resend_api_key="",
                email_from="test@resend.dev",
                expiry_minutes=15,
                http_timeout_seconds=10.0,
            )
        assert result is True
        mock_logger.info.assert_called_once()
        assert "email sending disabled" in mock_logger.info.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_calls_resend_api(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "email_123"}

        with patch("src.email.sender.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await send_magic_link_email(
                to="user@example.com",
                magic_link_url=LINK,
                locale="en",
                resend_api_key="re_test_key",
                email_from="noreply@example.com",
                expiry_minutes=15,
                http_timeout_seconds=10.0,
            )

        assert result is True
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "https://api.resend.com/emails"
        payload = call_args[1]["json"]
        assert payload["to"] == ["user@example.com"]
        assert payload["from"] == "noreply@example.com"
        assert LINK in payload["html"]
        assert LINK in payload["text"]
        headers = call_args[1]["headers"]
        assert "re_test_key" in headers["Authorization"]

    @pytest.mark.asyncio
    async def test_returns_false_on_api_error(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "Invalid email"

        with patch("src.email.sender.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await send_magic_link_email(
                to="bad-email",
                magic_link_url=LINK,
                locale="en",
                resend_api_key="re_test_key",
                email_from="noreply@example.com",
                expiry_minutes=15,
                http_timeout_seconds=10.0,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_network_error(self) -> None:
        with patch("src.email.sender.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = httpx.ConnectError("connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await send_magic_link_email(
                to="user@example.com",
                magic_link_url=LINK,
                locale="en",
                resend_api_key="re_test_key",
                email_from="noreply@example.com",
                expiry_minutes=15,
                http_timeout_seconds=10.0,
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_farsi_locale_sends_farsi_email(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": "email_456"}

        with patch("src.email.sender.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            await send_magic_link_email(
                to="user@example.com",
                magic_link_url=LINK,
                locale="fa",
                resend_api_key="re_test_key",
                email_from="noreply@example.com",
                expiry_minutes=15,
                http_timeout_seconds=10.0,
            )

        payload = mock_client.post.call_args[1]["json"]
        assert "تأیید ایمیل" in payload["subject"]
        assert 'dir="rtl"' in payload["html"]
