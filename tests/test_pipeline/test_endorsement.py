"""Tests for ballot question response parsing."""
from __future__ import annotations

from src.pipeline.endorsement import _parse_ballot_response


class TestParseBallotResponse:
    def test_clean_json(self) -> None:
        raw = (
            '{"ballot_question": "Should political internet censorship be reformed?",'
            '"ballot_question_fa": "آیا سانسور اینترنت سیاسی باید اصلاح شود؟",'
            '"summary": "Citizens debate internet filtering"}'
        )
        result = _parse_ballot_response(raw)
        assert "ballot_question" in result
        assert result["ballot_question"].startswith("Should")

    def test_markdown_wrapped(self) -> None:
        raw = (
            '```json\n'
            '{"ballot_question": "test", "ballot_question_fa": "تست",'
            '"summary": "s"}\n'
            '```'
        )
        result = _parse_ballot_response(raw)
        assert result["ballot_question"] == "test"

    def test_prose_prefix_stripped(self) -> None:
        raw = (
            'Here is the ballot question:\n'
            '{"ballot_question": "test", "ballot_question_fa": "تست",'
            '"summary": "s"}'
        )
        result = _parse_ballot_response(raw)
        assert result["ballot_question"] == "test"
