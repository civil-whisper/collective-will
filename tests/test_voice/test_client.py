"""Tests for VoiceCloudClient (orchestrates transcription + embedding + scoring)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.voice.client import VoiceCloudClient, VoiceProviderError


class TestVoiceCloudClient:
    @pytest.mark.asyncio
    async def test_process_audio_success(self) -> None:
        with (
            patch("src.voice.client.transcribe_audio", new_callable=AsyncMock) as mock_transcribe,
            patch("src.voice.client.get_speaker_embedding", new_callable=AsyncMock) as mock_embed,
        ):
            mock_transcribe.return_value = "hello world"
            mock_embed.return_value = ([0.1] * 192, "Jenthe/ECAPA2")

            client = VoiceCloudClient()
            result = await client.process_audio(b"fake-audio", "hello world", language="en")

        assert result.transcription == "hello world"
        assert result.transcription_score == 1.0
        assert len(result.embedding) == 192
        assert result.model_version == "Jenthe/ECAPA2"

    @pytest.mark.asyncio
    async def test_parallel_calls(self) -> None:
        """Transcription and embedding should be called (both invoked)."""
        with (
            patch("src.voice.client.transcribe_audio", new_callable=AsyncMock) as mock_transcribe,
            patch("src.voice.client.get_speaker_embedding", new_callable=AsyncMock) as mock_embed,
        ):
            mock_transcribe.return_value = "test phrase"
            mock_embed.return_value = ([0.5] * 192, "Jenthe/ECAPA2")

            client = VoiceCloudClient()
            result = await client.process_audio(b"audio", "test phrase", language="en")

        mock_transcribe.assert_called_once_with(b"audio", language="en")
        mock_embed.assert_called_once_with(b"audio")
        assert result.transcription == "test phrase"

    @pytest.mark.asyncio
    async def test_farsi_scoring(self) -> None:
        with (
            patch("src.voice.client.transcribe_audio", new_callable=AsyncMock) as mock_transcribe,
            patch("src.voice.client.get_speaker_embedding", new_callable=AsyncMock) as mock_embed,
        ):
            mock_transcribe.return_value = "لطفا کمی آرام‌تر حرف بزن"
            mock_embed.return_value = ([0.1] * 192, "Jenthe/ECAPA2")

            client = VoiceCloudClient()
            result = await client.process_audio(
                b"audio", "لطفا کمی آرام‌تر حرف بزن", language="fa"
            )

        assert result.transcription_score == 1.0

    @pytest.mark.asyncio
    async def test_transcription_error_propagates(self) -> None:
        with (
            patch("src.voice.client.transcribe_audio", new_callable=AsyncMock) as mock_transcribe,
            patch("src.voice.client.get_speaker_embedding", new_callable=AsyncMock) as mock_embed,
        ):
            mock_transcribe.side_effect = Exception("API error")
            mock_embed.return_value = ([0.1] * 192, "Jenthe/ECAPA2")

            client = VoiceCloudClient()
            with pytest.raises(VoiceProviderError, match="openai_transcription failed"):
                await client.process_audio(b"audio", "hello", language="en")

    @pytest.mark.asyncio
    async def test_embedding_error_propagates(self) -> None:
        with (
            patch("src.voice.client.transcribe_audio", new_callable=AsyncMock) as mock_transcribe,
            patch("src.voice.client.get_speaker_embedding", new_callable=AsyncMock) as mock_embed,
        ):
            mock_transcribe.return_value = "hello"
            mock_embed.side_effect = Exception("Modal down")

            client = VoiceCloudClient()
            with pytest.raises(VoiceProviderError, match="modal_embedding failed"):
                await client.process_audio(b"audio", "hello", language="en")

    @pytest.mark.asyncio
    async def test_both_upstreams_error_propagates_multiple_provider_context(self) -> None:
        with (
            patch("src.voice.client.transcribe_audio", new_callable=AsyncMock) as mock_transcribe,
            patch("src.voice.client.get_speaker_embedding", new_callable=AsyncMock) as mock_embed,
        ):
            mock_transcribe.side_effect = TimeoutError("OpenAI timeout")
            mock_embed.side_effect = TimeoutError("Modal timeout")

            client = VoiceCloudClient()
            with pytest.raises(VoiceProviderError, match="multiple failed"):
                await client.process_audio(b"audio", "hello", language="en")
