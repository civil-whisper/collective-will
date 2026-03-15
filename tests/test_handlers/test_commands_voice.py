"""Tests for voice gate in route_message and voice-related command flows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.channels.types import UnifiedMessage
from src.config import get_settings
from src.handlers.commands import route_message

# Committed fixture so tests run without gitignored voice-phrases.json (CI/local)
_VOICE_PHRASES_FIXTURE = (Path(__file__).resolve().parent.parent / "fixtures" / "voice-phrases.json")


def _voice_phrases_settings():
    """Real settings with voice_phrases_file pointing at the test fixture. Call once before patching."""
    return get_settings().model_copy(update={"voice_phrases_file": str(_VOICE_PHRASES_FIXTURE)})


def _make_user(
    *,
    enrolled: bool = False,
    session_active: bool = False,
    bot_state: str | None = None,
    bot_state_data: dict | None = None,
) -> MagicMock:
    user = MagicMock()
    user.id = uuid4()
    user.locale = "en"
    user.messaging_account_ref = "ref-test"
    user.bot_state = bot_state
    user.bot_state_data = bot_state_data
    user.is_voice_enrolled = enrolled
    user.is_voice_session_active = session_active
    user.voice_embedding = b"\x00" * 768 if enrolled else None
    user.voice_enrolled_at = datetime.now(UTC) if enrolled else None
    user.voice_verified_at = datetime.now(UTC) if session_active else None
    return user


def _make_text_message(text: str = "hello") -> UnifiedMessage:
    return UnifiedMessage(
        text=text,
        sender_ref="ref-test",
        platform="telegram",
        message_id="msg-1",
    )


def _make_voice_message(file_id: str = "voice-123", duration: int = 5) -> UnifiedMessage:
    return UnifiedMessage(
        text="",
        sender_ref="ref-test",
        platform="telegram",
        message_id="msg-2",
        voice_file_id=file_id,
        voice_duration=duration,
    )


class TestVoiceGateNotEnrolled:
    """User exists but is not voice-enrolled."""

    @pytest.mark.asyncio
    async def test_text_message_prompts_language_choice(self) -> None:
        """Non-enrolled user sending text gets language choice before enrollment."""
        user = _make_user(enrolled=False)
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_text_message()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with patch("src.config.get_settings", return_value=settings_with_fixture):
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_language_choice_prompted"
        assert user.bot_state == "choosing_voice_lang"
        channel.send_message.assert_called_once()
        sent = channel.send_message.call_args[0][0]
        # Should have language choice keyboard
        assert sent.reply_markup is not None
        buttons = sent.reply_markup["inline_keyboard"][0]
        callback_values = {b["callback_data"] for b in buttons}
        assert callback_values == {"vlang_en", "vlang_fa"}

    @pytest.mark.asyncio
    async def test_voice_message_starts_enrollment(self) -> None:
        user = _make_user(enrolled=False)
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_voice_message()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with (
            patch("src.config.get_settings", return_value=settings_with_fixture),
            patch("src.handlers.commands.start_enrollment", new_callable=AsyncMock) as mock_enroll,
        ):
            mock_enroll.return_value = {
                "enrollment": True, "step": 0, "phrase_ids": [1, 2, 3],
                "collected_embeddings": [], "attempt": 0, "failures": 0,
                "failed_phrase_ids": [],
            }
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_enrollment_started"

    @pytest.mark.asyncio
    async def test_voice_service_failure_during_enrollment_sends_error_message(self) -> None:
        """When voice-service fails (500, timeout, etc.), user gets voice_enroll_error not 500."""
        state = {
            "enrollment": True,
            "step": 0,
            "phrase_ids": [0, 1, 2],
            "collected_embeddings": [],
            "attempt": 0,
            "failures": 0,
            "failed_phrase_ids": [],
        }
        user = _make_user(enrolled=False, bot_state="enrolling_voice", bot_state_data=state)
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_voice_message()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with (
            patch("src.config.get_settings", return_value=settings_with_fixture),
            patch(
                "src.handlers.commands.process_enrollment_audio",
                new_callable=AsyncMock,
                return_value=("service_error", state),
            ),
        ):
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_service_error"
        # First call is the processing notice, second is the error message
        assert channel.send_message.call_count == 2
        sent_text = channel.send_message.call_args_list[-1][0][0].text
        assert "Error processing audio" in sent_text or "error" in sent_text.lower()

    @pytest.mark.asyncio
    async def test_phrases_file_unreadable_sends_error_message(self) -> None:
        """When phrases file cannot be read (e.g. PermissionError), user gets voice_enroll_error not 500."""
        user = _make_user(enrolled=False)
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_voice_message()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with (
            patch("src.config.get_settings", return_value=settings_with_fixture),
            patch(
                "src.handlers.commands.start_enrollment",
                new_callable=AsyncMock,
                side_effect=OSError(13, "Permission denied"),
            ),
        ):
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_enrollment_error"
        channel.send_message.assert_called_once()
        sent_text = channel.send_message.call_args[0][0].text
        assert "Error processing audio" in sent_text or "error" in sent_text.lower()


class TestVoiceGateExpiredSession:
    """User is enrolled but session expired."""

    @pytest.mark.asyncio
    async def test_text_triggers_verification_prompt(self) -> None:
        user = _make_user(enrolled=True, session_active=False)
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_text_message()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with (
            patch("src.config.get_settings", return_value=settings_with_fixture),
            patch("src.handlers.commands.check_voice_rate_limit", return_value=True),
        ):
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_verification_prompted"


class TestVoiceGateActiveSession:
    """User is enrolled and session is active — should pass through."""

    @pytest.mark.asyncio
    async def test_text_message_shows_menu(self) -> None:
        user = _make_user(enrolled=True, session_active=True)
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_text_message()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        result = await route_message(session=session, message=msg, channel=channel)
        assert result == "menu_resent"


class TestVoiceRateLimiting:
    @pytest.mark.asyncio
    async def test_rate_limited_verification(self) -> None:
        user = _make_user(enrolled=True, session_active=False)
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_text_message()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        with patch("src.handlers.commands.check_voice_rate_limit", return_value=False):
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_rate_limited"


class TestEnrollmentCooldown:
    """After enrollment_blocked, user must wait 24 hours before re-enrolling."""

    @pytest.mark.asyncio
    async def test_cooldown_blocks_re_enrollment(self) -> None:
        """Voice message within 24h of block should be rejected."""
        blocked_at = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        user = _make_user(
            enrolled=False,
            bot_state_data={"enrollment_blocked_at": blocked_at},
        )
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_voice_message()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        result = await route_message(session=session, message=msg, channel=channel)
        assert result == "voice_enrollment_cooldown"

    @pytest.mark.asyncio
    async def test_cooldown_expires_after_24h(self) -> None:
        """Voice message after 24h cooldown should start enrollment."""
        blocked_at = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
        user = _make_user(
            enrolled=False,
            bot_state_data={"enrollment_blocked_at": blocked_at},
        )
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_voice_message()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with (
            patch("src.config.get_settings", return_value=settings_with_fixture),
            patch("src.handlers.commands.start_enrollment", new_callable=AsyncMock) as mock_enroll,
        ):
            mock_enroll.return_value = {
                "enrollment": True, "step": 0, "phrase_ids": [1, 2, 3],
                "collected_embeddings": [], "attempt": 0, "failures": 0,
                "failed_phrase_ids": [],
            }
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_enrollment_started"


class TestVoiceRateLimiterConfig:
    """Voice rate limiter should read values from config, not hardcode."""

    def test_limiter_uses_config_values(self) -> None:
        import src.api.rate_limit as rl_mod

        # Reset the cached limiter
        rl_mod._voice_verify_limiter = None

        with patch("src.config.get_settings") as mock_settings:
            mock_settings.return_value.voice_verification_rate_limit_count = 2
            mock_settings.return_value.voice_verification_rate_limit_window_seconds = 60

            limiter = rl_mod._get_voice_limiter()
            assert limiter.max_requests == 2
            assert limiter.window_seconds == 60

        # Clean up
        rl_mod._voice_verify_limiter = None


def _make_callback_message(callback_data: str, callback_query_id: str = "cq-1") -> UnifiedMessage:
    return UnifiedMessage(
        text="",
        sender_ref="ref-test",
        platform="telegram",
        message_id="msg-cb",
        callback_data=callback_data,
        callback_query_id=callback_query_id,
    )


class TestVoiceLanguageChoice:
    """Language choice before enrollment and language switch during enrollment/verification."""

    @pytest.mark.asyncio
    async def test_language_choice_starts_enrollment(self) -> None:
        """Pressing vlang_en while in choosing_voice_lang starts enrollment."""
        user = _make_user(enrolled=False, bot_state="choosing_voice_lang")
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_callback_message("vlang_en")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with (
            patch("src.config.get_settings", return_value=settings_with_fixture),
            patch("src.handlers.commands.start_enrollment", new_callable=AsyncMock) as mock_enroll,
        ):
            mock_enroll.return_value = {
                "enrollment": True, "step": 0, "phrase_ids": [1, 2, 3],
                "collected_embeddings": [], "attempt": 0, "failures": 0,
                "failed_phrase_ids": [],
            }
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_enrollment_started"
        assert user.locale == "en"

    @pytest.mark.asyncio
    async def test_language_choice_fa_sets_locale(self) -> None:
        """Pressing vlang_fa sets locale to fa."""
        user = _make_user(enrolled=False, bot_state="choosing_voice_lang")
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_callback_message("vlang_fa")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with (
            patch("src.config.get_settings", return_value=settings_with_fixture),
            patch("src.handlers.commands.start_enrollment", new_callable=AsyncMock) as mock_enroll,
        ):
            mock_enroll.return_value = {
                "enrollment": True, "step": 0, "phrase_ids": [1, 2, 3],
                "collected_embeddings": [], "attempt": 0, "failures": 0,
                "failed_phrase_ids": [],
            }
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_enrollment_started"
        assert user.locale == "fa"

    @pytest.mark.asyncio
    async def test_language_switch_during_enrollment_restarts(self) -> None:
        """Pressing vlang_fa mid-enrollment resets and restarts with new language."""
        state = {
            "enrollment": True, "step": 1, "phrase_ids": [1, 2, 3],
            "collected_embeddings": [b"\x00"], "attempt": 0, "failures": 0,
            "failed_phrase_ids": [],
        }
        user = _make_user(enrolled=False, bot_state="enrolling_voice", bot_state_data=state)
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_callback_message("vlang_fa")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with (
            patch("src.config.get_settings", return_value=settings_with_fixture),
            patch("src.handlers.commands.start_enrollment", new_callable=AsyncMock) as mock_enroll,
        ):
            mock_enroll.return_value = {
                "enrollment": True, "step": 0, "phrase_ids": [1, 2, 3],
                "collected_embeddings": [], "attempt": 0, "failures": 0,
                "failed_phrase_ids": [],
            }
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_enrollment_started"
        assert user.locale == "fa"

    @pytest.mark.asyncio
    async def test_language_switch_during_verification(self) -> None:
        """Pressing vlang_en during verification starts new verification with English phrase."""
        user = _make_user(enrolled=True, session_active=False, bot_state="awaiting_voice")
        user.locale = "fa"
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_callback_message("vlang_en")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with (
            patch("src.config.get_settings", return_value=settings_with_fixture),
            patch("src.handlers.commands.check_voice_rate_limit", return_value=True),
        ):
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_verification_prompted"
        assert user.locale == "en"

    @pytest.mark.asyncio
    async def test_text_during_language_choice_reprompts(self) -> None:
        """Text message while choosing_voice_lang re-prompts language choice."""
        user = _make_user(enrolled=False, bot_state="choosing_voice_lang")
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_text_message("hello")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with patch("src.config.get_settings", return_value=settings_with_fixture):
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_language_choice_prompted"
        channel.send_message.assert_called_once()
        sent = channel.send_message.call_args[0][0]
        assert sent.reply_markup is not None

    @pytest.mark.asyncio
    async def test_callback_during_language_choice_reprompts(self) -> None:
        """Non-vlang callback while choosing_voice_lang re-prompts."""
        user = _make_user(enrolled=False, bot_state="choosing_voice_lang")
        session = AsyncMock()
        channel = AsyncMock()
        msg = _make_callback_message("submit")

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        session.execute = AsyncMock(return_value=mock_result)

        settings_with_fixture = _voice_phrases_settings()
        with patch("src.config.get_settings", return_value=settings_with_fixture):
            result = await route_message(session=session, message=msg, channel=channel)

        assert result == "voice_language_choice_prompted"
