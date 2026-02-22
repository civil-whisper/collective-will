from __future__ import annotations

import re
import secrets
from typing import Any

PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\+?\d[\d\-\s]{7,}\d"),
]
METADATA_KEYS = {"id", "user_id", "email", "messaging_account_ref", "wa_id", "ip"}


def redact_pii(text: str) -> str:
    clean = text
    for pattern in PII_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def prepare_batch_for_llm(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[int]]:
    index_pairs = list(enumerate(items))
    secrets.SystemRandom().shuffle(index_pairs)

    sanitized: list[dict[str, Any]] = []
    index_map: list[int] = []
    for original_index, item in index_pairs:
        sanitized_item = {
            key: value
            for key, value in item.items()
            if key not in METADATA_KEYS and not key.endswith("_id")
        }
        if "raw_text" in sanitized_item and isinstance(sanitized_item["raw_text"], str):
            sanitized_item["raw_text"] = redact_pii(sanitized_item["raw_text"])
        sanitized.append(sanitized_item)
        index_map.append(original_index)
    return sanitized, index_map


def validate_no_metadata(items: list[dict[str, Any]]) -> bool:
    for item in items:
        for key, value in item.items():
            if key in METADATA_KEYS or key.endswith("_id"):
                return False
            if isinstance(value, str) and any(pattern.search(value) for pattern in PII_PATTERNS):
                return False
    return True


def re_link_results(results: list[dict[str, Any]], index_map: list[int]) -> list[dict[str, Any]]:
    if len(results) != len(index_map):
        raise ValueError("results and index_map length mismatch")
    output: list[dict[str, Any] | None] = [None] * len(results)
    for idx, original_index in enumerate(index_map):
        output[original_index] = results[idx]
    return [item for item in output if item is not None]
