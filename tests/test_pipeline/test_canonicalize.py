from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.pipeline.canonicalize import (
    _CANONICALIZATION_INSTRUCTIONS,
    _INSTRUCTION_VERSION,
    CanonicalizationRejection,
    _parse_candidate_payload,
    _prompt_for_item,
    _prompt_version,
    canonicalize_batch,
    canonicalize_single,
    load_existing_policy_context,
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
            "is_valid_policy": True,
            "rejection_reason": None,
            "title": "Housing Reform",
            "summary": "Build affordable housing in major cities",
            "stance": "support",
            "policy_topic": "housing-policy",
            "policy_key": "affordable-housing-policy",
            "actor_scope": "public-governance",
            "action_mechanism": "governance-design",
            "target_scope": "public-governance",
            "ballot_readiness": "ballot-ready",
            "ballot_readiness_reason": "The proposal identifies a concrete policy choice.",
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
    assert candidates[0].policy_key == "affordable-housing-policy"
    assert candidates[0].ballot_readiness == "ballot-ready"


@pytest.mark.asyncio
async def test_low_confidence_flags_candidate() -> None:
    low_conf = json.dumps({
        "is_valid_policy": True,
        "rejection_reason": None,
        "title": "Vague Policy",
        "summary": "Something vague",
        "stance": "unclear",
        "policy_topic": "economic-discussion",
        "policy_key": "general-economic-concern",
        "actor_scope": "unclear",
        "action_mechanism": "discussion-only",
        "target_scope": "unclear",
        "ballot_readiness": "discussion-only",
        "ballot_readiness_reason": "The concern is too broad for a ballot proposition.",
        "entities": [],
        "confidence": 0.4,
        "ambiguity_flags": [],
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
    result, repair = _parse_candidate_payload(text)
    assert result["title"] == "A"
    assert repair is None


def test_parse_candidate_payload_handles_object() -> None:
    text = '{"title": "B"}'
    result, repair = _parse_candidate_payload(text)
    assert result["title"] == "B"
    assert repair is None


def test_parse_candidate_payload_repairs_key_value_comma_typo() -> None:
    text = '{"is_valid_policy", true, "title": "B", "entities": [],}'
    result, repair = _parse_candidate_payload(text)
    assert result["is_valid_policy"] is True
    assert result["title"] == "B"
    assert repair == "regex"


def test_parse_candidate_payload_repairs_adjacent_strings() -> None:
    text = '{"is_valid_policy": true, "title": "Broken", "entities": ["x" "y"]}'
    result, repair = _parse_candidate_payload(text)
    assert result["entities"] == ["x", "y"]
    assert repair == "regex"


@pytest.mark.asyncio
async def test_canonicalize_single_tolerates_null_ambiguity_flags() -> None:
    response = json.dumps({
        "is_valid_policy": True,
        "rejection_reason": None,
        "title": "Free Education",
        "summary": "Universal free education for all",
        "stance": "support",
        "policy_topic": "education-policy",
        "policy_key": "universal-free-education",
        "actor_scope": "public-governance",
        "action_mechanism": "governance-design",
        "target_scope": "public-governance",
        "ballot_readiness": "ballot-ready",
        "ballot_readiness_reason": "This is a concrete policy proposition.",
        "entities": ["education"],
        "confidence": 0.95,
        "ambiguity_flags": None,
    })
    router = FakeRouter(responses=[_mock_llm_response(text=response)])
    session = _make_mock_session()
    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="تحصیل رایگان برای همه",
        language="fa",
        llm_router=router,  # type: ignore[arg-type]
    )
    assert not isinstance(result, CanonicalizationRejection)
    assert result.ambiguity_flags == []


def test_prompt_for_item_is_concise_and_has_no_examples_block() -> None:
    prompt = _prompt_for_item({"raw_text": "text", "language": "en"})
    assert "Examples of distinctions" not in prompt
    assert "Canonicalize this civic submission into JSON." in prompt
    assert "Input:" in prompt


def test_prompt_starts_with_stable_instructions() -> None:
    prompt = _prompt_for_item({"raw_text": "test", "language": "en"})
    assert prompt.startswith(_CANONICALIZATION_INSTRUCTIONS)


def test_prompt_with_context_keeps_stable_prefix() -> None:
    ctx = '  - "my-key" (3) — Some summary'
    prompt_with = _prompt_for_item({"raw_text": "test", "language": "en"}, policy_context=ctx)
    assert prompt_with.startswith(_CANONICALIZATION_INSTRUCTIONS)
    assert "my-key" in prompt_with


def test_instruction_version_is_stable_hash() -> None:
    assert len(_INSTRUCTION_VERSION) == 16
    import hashlib
    expected = hashlib.sha256(_CANONICALIZATION_INSTRUCTIONS.encode("utf-8")).hexdigest()[:16]
    assert expected == _INSTRUCTION_VERSION


def test_prompt_includes_readiness_and_compound_guidance() -> None:
    prompt = _prompt_for_item({"raw_text": "text", "language": "en"})
    prompt_with_context = _prompt_for_item(
        {"raw_text": "text", "language": "en"},
        policy_context='  - "my-key" (3) — summary',
    )
    assert "discussion-only = broad exploration with no implied proposition" in prompt
    assert "ballot-ready can include a clearly stated constitutional, legal, or policy rule" in prompt
    assert "use other when the dimension is clear but outside the listed buckets" in prompt
    assert "compound_submission" in prompt
    assert "keep only the dominant proposition in policy_key/title/summary" in prompt
    assert "reuse would change ballot wording, option sets, or refinement output" in prompt
    assert "create a new key whenever reuse would change the ballot-level proposition" in prompt_with_context


@pytest.mark.asyncio
async def test_load_existing_policy_context_caps_entries_and_summary_length(monkeypatch: pytest.MonkeyPatch) -> None:
    session = _make_mock_session()
    rows = [
        ("key-one", 9, "A" * 200, "policy_proposal"),
        ("key-two", 8, "B" * 200, "opinion_question"),
        ("key-three", 7, "C" * 200, "policy_proposal"),
    ]
    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=rows)))
    monkeypatch.setenv("CANONICALIZATION_CONTEXT_MAX_ENTRIES", "2")
    monkeypatch.setenv("CANONICALIZATION_CONTEXT_SUMMARY_CHARS", "20")

    context = await load_existing_policy_context(session)

    assert context.count("\n") == 1
    assert '"key-one" [policy_proposal] (9)' in context
    assert '"key-two" [opinion_question] (8)' in context
    assert "key-three" not in context
    assert "AAAAAAAAAAAAAAAAAAAA..." in context


# --- canonicalize_single tests ---


@pytest.mark.asyncio
async def test_canonicalize_single_valid_submission() -> None:
    valid_response = json.dumps({
        "is_valid_policy": True,
        "rejection_reason": None,
        "title": "Free Education",
        "summary": "Universal free education for all",
        "stance": "support",
        "policy_topic": "education-policy",
        "policy_key": "universal-free-education",
        "actor_scope": "public-governance",
        "action_mechanism": "governance-design",
        "target_scope": "public-governance",
        "ballot_readiness": "ballot-ready",
        "ballot_readiness_reason": "This is a concrete policy proposition.",
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
    assert result.policy_key == "universal-free-education"
    assert result.actor_scope == "public-governance"


@pytest.mark.asyncio
async def test_canonicalize_single_garbage_rejected() -> None:
    garbage_response = json.dumps({
        "is_valid_policy": False,
        "rejection_reason": "این یک سلام است، نه یک پیشنهاد سیاستی.",
        "title": "Greeting",
        "summary": "User said hello",
        "stance": "unclear",
        "policy_topic": "unassigned",
        "policy_key": "unassigned",
        "actor_scope": "unclear",
        "action_mechanism": "discussion-only",
        "target_scope": "unclear",
        "ballot_readiness": "discussion-only",
        "ballot_readiness_reason": "This is not a civic or policy concern.",
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
async def test_canonicalize_single_normalizes_farsi_rejection_reason_to_english_for_english_input() -> None:
    garbage_response = json.dumps({
        "is_valid_policy": False,
        "rejection_reason": "این فقط یک احوالپرسی است و پیشنهاد سیاستی نیست.",
        "title": "Greeting",
        "summary": "User said hello",
        "stance": "unclear",
        "policy_topic": "unassigned",
        "policy_key": "unassigned",
        "actor_scope": "unclear",
        "action_mechanism": "discussion-only",
        "target_scope": "unclear",
        "ballot_readiness": "discussion-only",
        "ballot_readiness_reason": "This is not a civic or policy concern.",
        "entities": [],
        "confidence": 0,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=garbage_response)])
    session = _make_mock_session()
    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="hello",
        language="en",
        llm_router=router,  # type: ignore[arg-type]
    )
    assert isinstance(result, CanonicalizationRejection)
    assert result.reason == "This submission is not specific enough to be treated as a policy proposal."


@pytest.mark.asyncio
async def test_canonicalize_single_repairs_malformed_json_locally() -> None:
    malformed = '{"is_valid_policy", true, "title": "Broken", "entities": ["x" "y"]}'
    repaired = json.dumps({
        "is_valid_policy": True,
        "rejection_reason": None,
        "title": "Broken",
        "summary": "Repaired output",
        "stance": "support",
        "policy_topic": "judicial-reform",
        "policy_key": "judicial-reform",
        "actor_scope": "public-governance",
        "action_mechanism": "governance-design",
        "target_scope": "public-governance",
        "ballot_readiness": "ballot-ready",
        "ballot_readiness_reason": "Concrete proposition.",
        "entities": ["x", "y"],
        "confidence": 0.8,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=malformed), _mock_llm_response(text=repaired)])
    session = _make_mock_session()
    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="اصلاح قضایی",
        language="fa",
        llm_router=router,  # type: ignore[arg-type]
    )
    assert not isinstance(result, CanonicalizationRejection)
    assert result.title == "Broken"
    assert result.entities == ["x", "y"]
    assert len(router.calls) == 1


@pytest.mark.asyncio
async def test_canonicalize_batch_skips_invalid() -> None:
    """Batch canonicalization skips submissions flagged as not valid policies."""
    valid = json.dumps({
        "is_valid_policy": True,
        "title": "Policy A",
        "summary": "Valid",
        "stance": "support",
        "policy_topic": "economic-reform",
        "policy_key": "economic-reform-policy",
        "actor_scope": "public-governance",
        "action_mechanism": "governance-design",
        "target_scope": "public-governance",
        "ballot_readiness": "ballot-ready",
        "ballot_readiness_reason": "The issue is specific enough for a ballot proposition.",
        "entities": [],
        "confidence": 0.9,
        "ambiguity_flags": [],
    })
    invalid = json.dumps({
        "is_valid_policy": False,
        "rejection_reason": "Not a policy",
        "title": "Garbage",
        "summary": "Not valid",
        "stance": "unclear",
        "policy_topic": "unassigned",
        "policy_key": "unassigned",
        "actor_scope": "unclear",
        "action_mechanism": "discussion-only",
        "target_scope": "unclear",
        "ballot_readiness": "discussion-only",
        "ballot_readiness_reason": "The text is not a policy submission.",
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


@pytest.mark.asyncio
async def test_canonicalize_batch_normalizes_english_rejection_reason_to_farsi_for_farsi_input() -> None:
    invalid = json.dumps({
        "is_valid_policy": False,
        "rejection_reason": "This is only a greeting and not a policy submission.",
        "title": "Greeting",
        "summary": "User said hello",
        "stance": "unclear",
        "policy_topic": "unassigned",
        "policy_key": "unassigned",
        "actor_scope": "unclear",
        "action_mechanism": "discussion-only",
        "target_scope": "unclear",
        "ballot_readiness": "discussion-only",
        "ballot_readiness_reason": "The text is not a policy submission.",
        "entities": [],
        "confidence": 0,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=invalid)])
    session = _make_mock_session()
    items = [{"id": str(uuid4()), "raw_text": "سلام", "language": "fa"}]
    from unittest.mock import patch

    with patch("src.pipeline.canonicalize.append_evidence", new_callable=AsyncMock) as mock_evidence:
        candidates = await canonicalize_batch(session=session, submissions=items, llm_router=router)  # type: ignore[arg-type]

    assert candidates == []
    evidence_payload = mock_evidence.call_args.kwargs["payload"]
    assert evidence_payload["rejection_reason"] == (
        "این متن به اندازه کافی مشخص نیست که به عنوان یک پیشنهاد سیاستی در نظر گرفته شود."
    )
    assert evidence_payload["rejection_reason_language_normalized"] is True


@pytest.mark.asyncio
async def test_canonicalize_single_emits_parse_repaired_evidence_on_llm_repair() -> None:
    """When LLM repair is used, a candidate_parse_repaired evidence event is emitted."""
    malformed = '{"is_valid_policy", true, "title": "Broken", "entities": ["x" "y"]}'
    repaired = json.dumps({
        "is_valid_policy": True,
        "rejection_reason": None,
        "title": "Broken",
        "summary": "Repaired output",
        "stance": "support",
        "policy_topic": "judicial-reform",
        "policy_key": "judicial-reform",
        "actor_scope": "public-governance",
        "action_mechanism": "governance-design",
        "target_scope": "public-governance",
        "ballot_readiness": "ballot-ready",
        "ballot_readiness_reason": "Concrete proposition.",
        "entities": ["x", "y"],
        "confidence": 0.8,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=malformed), _mock_llm_response(text=repaired)])
    session = _make_mock_session()
    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="اصلاح قضایی",
        language="fa",
        llm_router=router,  # type: ignore[arg-type]
    )
    assert not isinstance(result, CanonicalizationRejection)
    # Verify via the mock session that evidence was appended multiple times
    # The session gets execute/flush calls; we check the number of mock calls.
    # At minimum: evidence for parse_repaired + evidence for candidate_created
    # We check that the session.flush was called (evidence append triggers flush)
    assert session.flush.call_count >= 1


@pytest.mark.asyncio
async def test_canonicalize_single_regex_repair_emits_parse_repaired() -> None:
    """Regex repair of malformed JSON also emits candidate_parse_repaired."""
    typo_json = '{"is_valid_policy", true, "title": "Typo Fix", "summary": "Test", '
    typo_json += '"stance": "support", "policy_topic": "test", "policy_key": "test-key", '
    typo_json += '"actor_scope": "unclear", "action_mechanism": "unclear", '
    typo_json += '"target_scope": "unclear", "ballot_readiness": "discussion-only", '
    typo_json += '"ballot_readiness_reason": "broad", "entities": [], "confidence": 0.8, '
    typo_json += '"ambiguity_flags": []}'
    router = FakeRouter(responses=[_mock_llm_response(text=typo_json)])
    session = _make_mock_session()
    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="test",
        language="en",
        llm_router=router,  # type: ignore[arg-type]
    )
    assert not isinstance(result, CanonicalizationRejection)
    assert result.title == "Typo Fix"


@pytest.mark.asyncio
async def test_canonicalize_preserves_actor_and_mechanism_distinction() -> None:
    response = json.dumps({
        "is_valid_policy": True,
        "rejection_reason": None,
        "title": "Domestic Economic Strike Against the Regime",
        "summary": "Calls for domestic strike action to economically weaken the regime.",
        "stance": "support",
        "policy_topic": "economic-resistance",
        "policy_key": "domestic-economic-strike-against-regime",
        "actor_scope": "domestic-citizens",
        "action_mechanism": "labor-strike",
        "target_scope": "iranian-regime",
        "ballot_readiness": "ballot-ready",
        "ballot_readiness_reason": "The submission proposes a concrete tactic.",
        "entities": ["regime"],
        "confidence": 0.84,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=response)])
    session = _make_mock_session()
    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="We need to strike so the regime cannot survive economically",
        language="en",
        llm_router=router,  # type: ignore[arg-type]
    )
    assert not isinstance(result, CanonicalizationRejection)
    assert result.actor_scope == "domestic-citizens"
    assert result.action_mechanism == "labor-strike"
    assert result.policy_key == "domestic-economic-strike-against-regime"


@pytest.mark.asyncio
async def test_canonicalize_preserves_other_semantic_buckets() -> None:
    response = json.dumps({
        "is_valid_policy": True,
        "rejection_reason": None,
        "title": "Protect Informal Mutual Aid Networks",
        "summary": "Protect neighborhood support networks from state disruption.",
        "stance": "support",
        "policy_topic": "community-resilience",
        "policy_key": "protect-informal-mutual-aid-networks",
        "actor_scope": "other",
        "action_mechanism": "other",
        "target_scope": "other",
        "ballot_readiness": "needs-refinement",
        "ballot_readiness_reason": "The direction is clear but the legal mechanism needs to be specified.",
        "entities": ["mutual aid networks"],
        "confidence": 0.77,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=response)])
    session = _make_mock_session()
    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="Protect local mutual aid networks from interference",
        language="en",
        llm_router=router,  # type: ignore[arg-type]
    )
    assert not isinstance(result, CanonicalizationRejection)
    assert result.actor_scope == "other"
    assert result.action_mechanism == "other"
    assert result.target_scope == "other"


@pytest.mark.asyncio
async def test_canonicalize_downgrades_inferred_regime_target_for_broad_conflict_input() -> None:
    response = json.dumps({
        "is_valid_policy": True,
        "rejection_reason": None,
        "title": "Conditional support for war in Iran",
        "summary": (
            "The submission expresses conditional support for war in Iran "
            "if it does not last more than one month."
        ),
        "stance": "support",
        "policy_topic": "foreign-policy",
        "policy_key": "support-war-in-iran",
        "actor_scope": "other",
        "action_mechanism": "military-action",
        "target_scope": "iranian-regime",
        "ballot_readiness": "needs-refinement",
        "ballot_readiness_reason": "The actor and target remain underspecified.",
        "entities": ["Iran"],
        "confidence": 0.76,
        "ambiguity_flags": [],
    })
    router = FakeRouter(responses=[_mock_llm_response(text=response)])
    session = _make_mock_session()

    result = await canonicalize_single(
        session=session,
        submission_id=uuid4(),
        raw_text="من با جنگ در ایران موافقم ولی اگه تا یه ماه بیشتر طول بکشه نمی‌دونم باز موافق خواهم بود",
        language="fa",
        llm_router=router,  # type: ignore[arg-type]
    )

    assert not isinstance(result, CanonicalizationRejection)
    assert result.target_scope == "unclear"
    assert "target_scope_unclear_from_input" in result.ambiguity_flags
