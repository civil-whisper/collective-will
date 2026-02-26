from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.pipeline.canonicalize import (
    CanonicalizationRejection,
    _parse_candidate_payload,
    _prompt_version,
    canonicalize_batch,
    canonicalize_single,
)
from src.pipeline.llm import LLMResponse


def _make_mock_session() -> AsyncMock:
    session = AsyncMock()

    @asynccontextmanager
    async def _begin_nested() -> AsyncIterator[None]:
        yield

    session.begin_nested = _begin_nested
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))
    # SQLAlchemy Session.add is synchronous; keep it non-async in mocks.
    session.add = MagicMock()
    return session


def _mock_llm_response(text: str = "", model: str = "claude-sonnet-4-20250514") -> LLMResponse:
    if not text:
        text = json.dumps({
            "title": "Housing Reform",
            "domain": "economy",
            "summary": "Build affordable housing in major cities",
            "stance": "support",
            "entities": ["housing"],
            "confidence": 0.9,
            "ambiguity_flags": [],
        })
    return LLMResponse(text=text, model=model, input_tokens=10, output_tokens=5, cost_usd=0.0001)


class FakeRouter:
    def __init__(self, responses: list[LLMResponse] | None = None) -> None:
        self.calls: list[dict[str, str]] = []
        self.responses = responses or [_mock_llm_response()]
        self._idx = 0

    async def complete(self, *, tier: str, prompt: str, **kwargs: object) -> LLMResponse:
        self.calls.append({"tier": tier, "prompt": prompt})
        resp = self.responses[self._idx % len(self.responses)]
        self._idx += 1
        return resp


@pytest.mark.asyncio
async def test_single_issue_produces_one_candidate() -> None:
    router = FakeRouter()
    session = _make_mock_session()
    items = [{"id": str(uuid4()), "raw_text": "مسکن ارزان", "language": "fa"}]
    candidates = await canonicalize_batch(session=session, submissions=items, llm_router=router)  # type: ignore[arg-type]
    assert len(candidates) == 1
    assert candidates[0].title == "Housing Reform"


@pytest.mark.asyncio
async def test_low_confidence_flags_candidate() -> None:
    low_conf = json.dumps({
        "title": "Vague Policy", "domain": "other", "summary": "Something vague",
        "stance": "unclear", "entities": [], "confidence": 0.4, "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=low_conf)])
    session = _make_mock_session()
    items = [{"id": str(uuid4()), "raw_text": "text", "language": "fa"}]
    candidates = await canonicalize_batch(session=session, submissions=items, llm_router=router)  # type: ignore[arg-type]
    assert "low_confidence" in candidates[0].ambiguity_flags


@pytest.mark.asyncio
async def test_model_version_and_prompt_version_set() -> None:
    router = FakeRouter()
    session = _make_mock_session()
    items = [{"id": str(uuid4()), "raw_text": "text", "language": "fa"}]
    candidates = await canonicalize_batch(session=session, submissions=items, llm_router=router)  # type: ignore[arg-type]
    assert candidates[0].model_version == "claude-sonnet-4-20250514"
    assert len(candidates[0].prompt_version) > 0


def test_prompt_version_changes_with_content() -> None:
    v1 = _prompt_version("prompt A")
    v2 = _prompt_version("prompt B")
    assert v1 != v2
    assert _prompt_version("prompt A") == v1


@pytest.mark.asyncio
async def test_canonicalization_uses_correct_tier() -> None:
    router = FakeRouter()
    session = _make_mock_session()
    items = [{"id": str(uuid4()), "raw_text": "text", "language": "fa"}]
    await canonicalize_batch(session=session, submissions=items, llm_router=router)  # type: ignore[arg-type]
    assert router.calls[0]["tier"] == "canonicalization"


@pytest.mark.asyncio
async def test_privacy_no_uuids_in_prompt() -> None:
    router = FakeRouter()
    session = _make_mock_session()
    user_id = str(uuid4())
    items = [{"id": str(uuid4()), "raw_text": "safe text", "language": "fa", "user_id": user_id}]
    await canonicalize_batch(session=session, submissions=items, llm_router=router)  # type: ignore[arg-type]
    assert user_id not in router.calls[0]["prompt"]


def test_parse_candidate_payload_handles_array() -> None:
    text = '[{"title": "A"}]'
    result = _parse_candidate_payload(text)
    assert result["title"] == "A"


def test_parse_candidate_payload_handles_object() -> None:
    text = '{"title": "B"}'
    result = _parse_candidate_payload(text)
    assert result["title"] == "B"


# --- canonicalize_single tests ---


@pytest.mark.asyncio
async def test_canonicalize_single_valid_submission() -> None:
    valid_response = json.dumps({
        "is_valid_policy": True,
        "rejection_reason": None,
        "title": "Free Education",
        "domain": "rights",
        "summary": "Universal free education for all",
        "stance": "support",
        "entities": ["education"],
        "confidence": 0.95,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=valid_response)])
    session = _make_mock_session()
    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="تحصیل رایگان برای همه",
        language="fa",
        llm_router=router,  # type: ignore[arg-type]
    )
    assert not isinstance(result, CanonicalizationRejection)
    assert result.title == "Free Education"
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_canonicalize_single_garbage_rejected() -> None:
    garbage_response = json.dumps({
        "is_valid_policy": False,
        "rejection_reason": "این یک سلام است، نه یک پیشنهاد سیاستی.",
        "title": "Greeting",
        "domain": "other",
        "summary": "User said hello",
        "stance": "unclear",
        "entities": [],
        "confidence": 0,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=garbage_response)])
    session = _make_mock_session()
    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="سلام!",
        language="fa",
        llm_router=router,  # type: ignore[arg-type]
    )
    assert isinstance(result, CanonicalizationRejection)
    assert "سلام" in result.reason


@pytest.mark.asyncio
async def test_canonicalize_batch_skips_invalid() -> None:
    """Batch canonicalization skips submissions flagged as not valid policies."""
    valid = json.dumps({
        "is_valid_policy": True,
        "title": "Policy A",
        "domain": "economy",
        "summary": "Valid",
        "stance": "support",
        "entities": [],
        "confidence": 0.9,
        "ambiguity_flags": [],
    })
    invalid = json.dumps({
        "is_valid_policy": False,
        "rejection_reason": "Not a policy",
        "title": "Garbage",
        "domain": "other",
        "summary": "Not valid",
        "stance": "unclear",
        "entities": [],
        "confidence": 0,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[
        _mock_llm_response(text=valid),
        _mock_llm_response(text=invalid),
    ])
    session = _make_mock_session()
    items = [
        {"id": str(uuid4()), "raw_text": "سیاست اقتصادی", "language": "fa"},
        {"id": str(uuid4()), "raw_text": "سلام", "language": "fa"},
    ]
    candidates = await canonicalize_batch(session=session, submissions=items, llm_router=router)  # type: ignore[arg-type]
    assert len(candidates) == 1
    assert candidates[0].title == "Policy A"
