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
    candidate.actor_scope = "public-governance"
    candidate.action_mechanism = "governance-design"
    candidate.target_scope = "public-governance"
    candidate.ballot_readiness = "needs-refinement"
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
