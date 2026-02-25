"""Tests for LLM-based key normalization merge response parsing."""
from __future__ import annotations

from src.pipeline.normalize import _parse_merge_response


class TestParseMergeResponse:
    def test_simple_merge(self) -> None:
        raw = '{"merges": [{"keys": ["key-a", "key-b"], "survivor": "key-a"}]}'
        result = _parse_merge_response(raw)
        assert len(result) == 1
        assert result[0]["survivor"] == "key-a"
        assert set(result[0]["keys"]) == {"key-a", "key-b"}

    def test_no_merges(self) -> None:
        raw = '{"merges": []}'
        result = _parse_merge_response(raw)
        assert result == []

    def test_markdown_wrapped(self) -> None:
        raw = '```json\n{"merges": [{"keys": ["a", "b"], "survivor": "a"}]}\n```'
        result = _parse_merge_response(raw)
        assert len(result) == 1

    def test_multiple_merges(self) -> None:
        raw = '{"merges": [{"keys": ["a", "b"], "survivor": "a"}, {"keys": ["c", "d"], "survivor": "d"}]}'
        result = _parse_merge_response(raw)
        assert len(result) == 2
        assert result[0]["survivor"] == "a"
        assert result[1]["survivor"] == "d"
