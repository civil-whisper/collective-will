from __future__ import annotations

from src.pipeline.privacy import prepare_batch_for_llm, re_link_results, redact_pii, validate_no_metadata


def test_prepare_batch_strips_metadata_and_redacts_pii() -> None:
    items = [
        {"id": "1", "raw_text": "email is a@b.com", "user_id": "u1"},
        {"id": "2", "raw_text": "normal text", "wa_id": "123"},
    ]
    sanitized, index_map = prepare_batch_for_llm(items)
    assert len(sanitized) == 2
    assert len(index_map) == 2
    assert validate_no_metadata(sanitized) is True
    assert "[REDACTED]" in sanitized[0]["raw_text"] or "[REDACTED]" in sanitized[1]["raw_text"]


def test_shuffled_output_order() -> None:
    items = [{"raw_text": f"text-{i}"} for i in range(50)]
    sanitized, index_map = prepare_batch_for_llm(items)
    original_order = [f"text-{i}" for i in range(50)]
    result_order = [item["raw_text"] for item in sanitized]
    assert result_order != original_order  # statistically certain with 50 items


def test_index_map_round_trip() -> None:
    items = [{"raw_text": f"item-{i}"} for i in range(10)]
    sanitized, index_map = prepare_batch_for_llm(items)
    relinked = re_link_results(sanitized, index_map)
    for idx, item in enumerate(relinked):
        assert item["raw_text"] == f"item-{idx}"


def test_relink_results_correct() -> None:
    results = [{"v": "a"}, {"v": "b"}]
    index_map = [1, 0]
    relinked = re_link_results(results, index_map)
    assert relinked == [{"v": "b"}, {"v": "a"}]


def test_validate_no_metadata_clean() -> None:
    items = [{"raw_text": "clean text here"}]
    assert validate_no_metadata(items) is True


def test_validate_no_metadata_detects_numeric_patterns() -> None:
    items = [{"raw_text": "user id is 12345678-1234-1234-1234-123456789abc"}]
    assert validate_no_metadata(items) is False  # phone-like patterns in UUIDs flagged conservatively


def test_validate_no_metadata_detects_metadata_keys() -> None:
    items = [{"user_id": "some-id", "raw_text": "text"}]
    assert validate_no_metadata(items) is False


def test_validate_no_metadata_detects_email() -> None:
    items = [{"raw_text": "contact me at user@example.com for info"}]
    assert validate_no_metadata(items) is False


def test_pii_redaction_masks_email() -> None:
    text = "My email is test@example.com and phone is +1-555-123-4567"
    redacted = redact_pii(text)
    assert "test@example.com" not in redacted
    assert "[REDACTED]" in redacted


def test_empty_input() -> None:
    sanitized, index_map = prepare_batch_for_llm([])
    assert sanitized == []
    assert index_map == []


def test_single_item() -> None:
    items = [{"raw_text": "single item text", "user_id": "u1"}]
    sanitized, index_map = prepare_batch_for_llm(items)
    assert len(sanitized) == 1
    assert "user_id" not in sanitized[0]
    assert sanitized[0]["raw_text"] == "single item text"
