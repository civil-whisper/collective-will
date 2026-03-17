"""Tests for ballot question response parsing and generation."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.pipeline.endorsement import _parse_ballot_response, generate_ballot_questions
from src.pipeline.llm import LLMResponse


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


def _make_cluster() -> MagicMock:
    cluster = MagicMock()
    cluster.id = uuid4()
    cluster.policy_key = "support-war-in-iran"
    cluster.policy_topic = "foreign-policy"
    cluster.summary = "Conditional support for war in Iran."
    cluster.candidate_ids = [uuid4()]
    cluster.member_count = 1
    cluster.needs_resummarize = True
    cluster.last_summarized_count = 0
    return cluster


def _make_candidate(candidate_id: object) -> MagicMock:
    candidate = MagicMock()
    candidate.id = candidate_id
    candidate.title = "Conditional support for war in Iran"
    candidate.summary = "Supports war in Iran, but only if it does not continue beyond one month."
    candidate.stance = "support"
    candidate.actor_scope = "other"
    candidate.action_mechanism = "military-action"
    candidate.target_scope = "unclear"
    candidate.ballot_readiness = "needs-refinement"
    candidate.ballot_readiness_reason = "The actor, target, objectives, and duration still need clarification."
    candidate.ambiguity_flags = ["conditional_support", "actor_unclear", "target_unclear"]
    candidate.entities = ["Iran"]
    return candidate


@pytest.mark.asyncio
async def test_generate_ballot_questions_rewrites_unanchored_actorful_output() -> None:
    cluster = _make_cluster()
    candidate = _make_candidate(cluster.candidate_ids[0])
    router = MagicMock()
    router.complete = AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "ballot_question": "Whether the United States should use military force against Iran, with the current proposal limited to support for war and no clear details yet on scope, objectives, or duration.",
            "ballot_question_fa": "حمایت از جنگ با ایران، با این ابهام که هنوز معلوم نیست دامنه، هدف‌ها و مدت آن دقیقاً چی باشد.",
            "summary": "A proposal to support military action against Iran, with the main details still unclear and the support described as conditional.",
        }),
        model="test-model",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
    ))
    session = AsyncMock()

    from unittest.mock import patch

    with patch("src.pipeline.endorsement.append_evidence", new_callable=AsyncMock) as mock_evidence:
        updated = await generate_ballot_questions(
            session=session,
            clusters=[cluster],
            candidates_by_id={candidate.id: candidate},
            llm_router=router,
        )

    assert updated == 1
    assert cluster.ballot_question == (
        "Debate over whether to support military action related to Iran, with the exact actor, "
        "objectives, and duration still needing definition."
    )
    assert "United States" not in cluster.ballot_question
    assert cluster.summary == "Discussion of whether to support military action related to Iran while key details remain unclear."
    evidence_payload = mock_evidence.call_args.kwargs["payload"]
    assert evidence_payload["validation_flags"] == [
        "Ballot wording introduced a U.S. actor not grounded in the source submissions.",
        "Ballot wording introduced a specific target that is not grounded in the source submissions.",
    ]


@pytest.mark.asyncio
async def test_generate_ballot_questions_softens_blunt_needs_refinement_wording() -> None:
    cluster = _make_cluster()
    cluster.policy_key = "support-strike-to-weaken-regime-economically"
    cluster.policy_topic = "governance"
    candidate = _make_candidate(cluster.candidate_ids[0])
    candidate.title = "Use strikes to economically weaken the regime"
    candidate.summary = "Calls for labor strikes to economically weaken the regime."
    candidate.actor_scope = "domestic-citizens"
    candidate.action_mechanism = "labor-strike"
    candidate.target_scope = "iranian-regime"
    router = MagicMock()
    router.complete = AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "ballot_question": "Support using labor strikes by domestic citizens to economically weaken the Iranian regime, with the exact scope and organizing details still unspecified.",
            "ballot_question_fa": "حمایت از اعتصاب‌های کارگری توسط شهروندان داخل کشور برای ضعیف کردن اقتصادیِ رژیم ایران، با این‌که جزئیات دقیقِ دامنه و سازمان‌دهی هنوز مشخص نیست.",
            "summary": "Proposal to use domestic labor strikes as a tactic to economically weaken the Iranian regime; the intended scope and organizing details are not yet defined.",
        }),
        model="test-model",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
    ))
    session = AsyncMock()

    from unittest.mock import patch

    with patch("src.pipeline.endorsement.append_evidence", new_callable=AsyncMock):
        updated = await generate_ballot_questions(
            session=session,
            clusters=[cluster],
            candidates_by_id={candidate.id: candidate},
            llm_router=router,
        )

    assert updated == 1
    assert cluster.ballot_question == (
        "Debate over whether to support using labor strikes by domestic citizens to economically weaken "
        "the Iranian regime, with the exact scope and organizing details still unspecified."
    )
    assert cluster.summary == (
        "Discussion of whether to support using labor strikes by domestic citizens to economically weaken "
        "the Iranian regime while key details remain unclear."
    )

    def test_prose_prefix_stripped(self) -> None:
        raw = (
            'Here is the ballot question:\n'
            '{"ballot_question": "test", "ballot_question_fa": "تست",'
            '"summary": "s"}'
        )
        result = _parse_ballot_response(raw)
        assert result["ballot_question"] == "test"
