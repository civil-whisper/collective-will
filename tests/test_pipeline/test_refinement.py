from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.pipeline.llm import LLMResponse
from src.pipeline.refinement import generate_refinement_drafts


def _make_cluster() -> MagicMock:
    cluster = MagicMock()
    cluster.id = uuid4()
    cluster.policy_key = "public-transport-access"
    cluster.policy_topic = "transport-policy"
    cluster.summary = "Citizens want more reliable public transport."
    cluster.candidate_ids = [uuid4()]
    return cluster


def _make_candidate(candidate_id: object) -> MagicMock:
    candidate = MagicMock()
    candidate.id = candidate_id
    candidate.title = "Improve Public Transport"
    candidate.summary = "Expand routes and increase reliability."
    candidate.stance = "support"
    candidate.actor_scope = "public-governance"
    candidate.action_mechanism = "governance-design"
    candidate.target_scope = "public-governance"
    candidate.ballot_readiness = "needs-refinement"
    candidate.ballot_readiness_reason = "The direction is clear but details still need to be narrowed."
    candidate.ambiguity_flags = []
    candidate.entities = ["public transport"]
    return candidate


@pytest.mark.asyncio
async def test_generate_refinement_drafts_updates_cluster_and_logs_evidence() -> None:
    cluster = _make_cluster()
    candidate = _make_candidate(cluster.candidate_ids[0])
    router = MagicMock()
    router.complete = AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "refinement_draft": "The government should expand bus routes and service frequency in underserved areas.",
            "refinement_draft_fa": "دولت باید مسیرها و تعداد سرویس اتوبوس را در مناطق کم‌برخوردار افزایش دهد.",
            "refinement_confidence": 0.82,
            "requires_clarification": False,
            "notes": "Multiple submissions point toward a concrete transit expansion proposal.",
        }),
        model="test-model",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
    ))
    session = AsyncMock()

    from unittest.mock import patch

    with patch("src.pipeline.refinement.append_evidence", new_callable=AsyncMock) as mock_evidence:
        await generate_refinement_drafts(
            session=session,
            clusters=[cluster],
            candidates_by_id={candidate.id: candidate},
            llm_router=router,
        )

    assert cluster.refinement_draft is not None
    assert "bus routes" in cluster.refinement_draft
    assert cluster.refinement_confidence == 0.82
    assert cluster.refinement_requires_clarification is False
    mock_evidence.assert_called_once()
    assert mock_evidence.call_args.kwargs["event_type"] == "refinement_draft_generated"


@pytest.mark.asyncio
async def test_generate_refinement_drafts_softens_blunt_needs_refinement_tone() -> None:
    cluster = _make_cluster()
    cluster.policy_key = "support-strike-for-iran-regime-change"
    cluster.policy_topic = "foreign-policy"
    cluster.summary = "Support for a strike to help Iranians pursue regime change."
    candidate = _make_candidate(cluster.candidate_ids[0])
    candidate.title = "Support a strike to help Iranians pursue regime change"
    candidate.summary = "Calls for a strike as a means of supporting Iranians in achieving regime change."
    candidate.action_mechanism = "labor-strike"
    candidate.target_scope = "iranian-regime"
    router = MagicMock()
    router.complete = AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "refinement_draft": "Support a labor strike to help Iranians pursue regime change in Iran.",
            "refinement_draft_fa": "از یک اعتصاب کارگری برای کمک به ایرانیان در پیگیری تغییر رژیم در ایران حمایت کنید.",
            "refinement_confidence": 0.78,
            "requires_clarification": True,
            "notes": "The exact scope and coordination are still unclear.",
        }),
        model="test-model",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
    ))
    session = AsyncMock()

    from unittest.mock import patch

    with patch("src.pipeline.refinement.append_evidence", new_callable=AsyncMock):
        await generate_refinement_drafts(
            session=session,
            clusters=[cluster],
            candidates_by_id={candidate.id: candidate},
            llm_router=router,
        )

    assert cluster.refinement_draft == "A labor strike to help Iranians pursue regime change in Iran should be supported."
    assert cluster.refinement_draft_fa == "از یک اعتصاب کارگری برای کمک به ایرانیان در پیگیری تغییر رژیم در ایران حمایت شود."
    assert cluster.refinement_requires_clarification is True


@pytest.mark.asyncio
async def test_generate_refinement_drafts_normalizes_question_form_to_statement() -> None:
    cluster = _make_cluster()
    cluster.policy_key = "economic-pressure-on-iran-regime-regime-change"
    cluster.policy_topic = "foreign-policy"
    cluster.summary = "Economic pressure against the regime in support of regime change."
    candidate = _make_candidate(cluster.candidate_ids[0])
    candidate.title = "Apply financial pressure on the regime to support regime change"
    candidate.summary = "Calls for using financial pressure against the regime as a means of advancing regime change."
    candidate.action_mechanism = "economic-pressure"
    candidate.target_scope = "iranian-regime"
    router = MagicMock()
    router.complete = AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "refinement_draft": "Should economic and financial pressure be applied against the Iranian regime to support regime change?",
            "refinement_draft_fa": "آیا باید فشار اقتصادی و مالی علیه رژیم ایران برای حمایت از تغییر رژیم اعمال شود؟",
            "refinement_confidence": 0.84,
            "requires_clarification": False,
            "notes": "The exact measures and actor remain unclear.",
        }),
        model="test-model",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
    ))
    session = AsyncMock()

    from unittest.mock import patch

    with patch("src.pipeline.refinement.append_evidence", new_callable=AsyncMock):
        await generate_refinement_drafts(
            session=session,
            clusters=[cluster],
            candidates_by_id={candidate.id: candidate},
            llm_router=router,
        )

    assert cluster.refinement_draft == (
        "Economic and financial pressure should be applied against the Iranian regime to support regime change."
    )
    assert cluster.refinement_draft_fa == "فشار اقتصادی و مالی علیه رژیم ایران برای حمایت از تغییر رژیم اعمال شود."
    assert cluster.refinement_requires_clarification is False


@pytest.mark.asyncio
async def test_generate_refinement_drafts_skips_discussion_only_clusters() -> None:
    cluster = _make_cluster()
    candidate = _make_candidate(cluster.candidate_ids[0])
    candidate.ballot_readiness = "discussion-only"
    router = MagicMock()
    router.complete = AsyncMock()
    session = AsyncMock()

    from unittest.mock import patch

    with patch("src.pipeline.refinement.append_evidence", new_callable=AsyncMock) as mock_evidence:
        await generate_refinement_drafts(
            session=session,
            clusters=[cluster],
            candidates_by_id={candidate.id: candidate},
            llm_router=router,
        )

    router.complete.assert_not_called()
    mock_evidence.assert_not_called()
    assert cluster.refinement_draft is None
    assert cluster.refinement_requires_clarification is True


@pytest.mark.asyncio
async def test_generate_refinement_drafts_rejects_unanchored_local_actor() -> None:
    cluster = _make_cluster()
    cluster.policy_key = "oppose-american-intervention-in-iran-regime-change"
    cluster.policy_topic = "foreign-policy"
    cluster.summary = "Discussion about U.S. intervention in efforts to change Iran's government."
    candidate = _make_candidate(cluster.candidate_ids[0])
    candidate.title = "Oppose American intervention in Iran regime change"
    candidate.summary = "Opposes U.S. intervention in efforts to change the Iranian regime."
    candidate.stance = "oppose"
    candidate.actor_scope = "foreign-state"
    candidate.action_mechanism = "other"
    candidate.target_scope = "iranian-regime"
    router = MagicMock()
    router.complete = AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "refinement_draft": "The city should oppose U.S. intervention aimed at changing Iran's government.",
            "refinement_draft_fa": "این شهر باید با مداخله آمریکا برای تغییر حکومت ایران مخالفت کند.",
            "refinement_confidence": 0.76,
            "requires_clarification": False,
            "notes": "The cluster consistently opposes intervention.",
        }),
        model="test-model",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
    ))
    session = AsyncMock()

    from unittest.mock import patch

    with patch("src.pipeline.refinement.append_evidence", new_callable=AsyncMock):
        await generate_refinement_drafts(
            session=session,
            clusters=[cluster],
            candidates_by_id={candidate.id: candidate},
            llm_router=router,
        )

    assert cluster.refinement_draft is None
    assert cluster.refinement_draft_fa is None
    assert cluster.refinement_requires_clarification is True
    assert cluster.refinement_notes is not None
    assert "city-level actor" in cluster.refinement_notes


@pytest.mark.asyncio
async def test_generate_refinement_drafts_rejects_unanchored_specific_target() -> None:
    cluster = _make_cluster()
    cluster.policy_key = "support-war-in-iran-with-time-limit"
    cluster.policy_topic = "foreign-policy"
    cluster.summary = "Conditional support for war in Iran with a short duration."
    candidate = _make_candidate(cluster.candidate_ids[0])
    candidate.title = "Support for war in Iran, with support conditional on a short duration"
    candidate.summary = "Supports war in Iran, but only if it does not continue beyond one month."
    candidate.stance = "support"
    candidate.actor_scope = "unclear"
    candidate.action_mechanism = "military-action"
    candidate.target_scope = "unclear"
    router = MagicMock()
    router.complete = AsyncMock(return_value=LLMResponse(
        text=json.dumps({
            "refinement_draft": "Support military action against Iran, but only for a limited period of no more than one month.",
            "refinement_draft_fa": "از اقدام نظامی علیه ایران حمایت شود، اما فقط برای مدت محدودی که از یک ماه بیشتر نباشد.",
            "refinement_confidence": 0.8,
            "requires_clarification": False,
            "notes": "The submission supports war with a time limit.",
        }),
        model="test-model",
        input_tokens=10,
        output_tokens=20,
        cost_usd=0.001,
    ))
    session = AsyncMock()

    from unittest.mock import patch

    with patch("src.pipeline.refinement.append_evidence", new_callable=AsyncMock):
        await generate_refinement_drafts(
            session=session,
            clusters=[cluster],
            candidates_by_id={candidate.id: candidate},
            llm_router=router,
        )

    assert cluster.refinement_draft is None
    assert cluster.refinement_draft_fa is None
    assert cluster.refinement_requires_clarification is True
    assert cluster.refinement_notes is not None
    assert "specific target" in cluster.refinement_notes
