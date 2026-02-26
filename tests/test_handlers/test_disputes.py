from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.handlers.disputes import _record_dispute_metrics, resolve_submission_dispute
from src.pipeline.llm import LLMResponse


def _select_result(first_value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value = MagicMock(first=MagicMock(return_value=first_value))
    return result


def _router_with_primary(text: str) -> MagicMock:
    router = MagicMock()
    router.complete = AsyncMock(
        return_value=LLMResponse(
            text=text,
            model="claude-sonnet-4-20250514",
            input_tokens=10,
            output_tokens=8,
            cost_usd=0.0,
        )
    )
    router.complete_with_model = AsyncMock()
    return router


def _count_result(value: int) -> MagicMock:
    result = MagicMock()
    result.scalar_one.return_value = value
    return result


def _payload_rows_result(payloads: list[dict[str, object]]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value = MagicMock(all=MagicMock(return_value=payloads))
    return result


@pytest.mark.asyncio
async def test_resolve_submission_dispute_updates_existing_candidate() -> None:
    submission = MagicMock()
    submission.id = uuid4()
    submission.raw_text = "کمبود آب"

    candidate = MagicMock()
    candidate.id = uuid4()
    candidate.title = "Old title"
    candidate.summary = "Old summary"
    candidate.stance = "unclear"
    candidate.entities = []
    candidate.confidence = 0.1
    candidate.ambiguity_flags = []
    candidate.model_version = "old"
    candidate.prompt_version = "old"

    session = AsyncMock()
    session.execute.side_effect = [_select_result(candidate), _select_result(None)]
    router = _router_with_primary(
        '{"title":"Water Access Policy","domain":"rights","summary":"Ensure water access",'
        '"stance":"support","entities":["water"],"confidence":0.9,"ambiguity_flags":[]}'
    )

    with (
        patch("src.handlers.disputes.append_evidence", new_callable=AsyncMock) as mock_evidence,
        patch("src.handlers.disputes._record_dispute_metrics", new_callable=AsyncMock) as mock_metrics,
    ):
        result = await resolve_submission_dispute(session=session, submission=submission, llm_router=router)

    assert result["status"] == "resolved"
    assert result["escalated"] is False
    assert candidate.title == "Water Access Policy"
    assert candidate.summary == "Ensure water access"
    assert candidate.stance == "support"
    assert candidate.confidence == 0.9
    assert router.complete.call_count == 1
    assert router.complete_with_model.call_count == 0
    assert mock_evidence.call_count == 1
    assert mock_evidence.call_args.kwargs["event_type"] == "dispute_resolved"
    mock_metrics.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_submission_dispute_escalates_low_confidence_and_creates_candidate() -> None:
    submission = MagicMock()
    submission.id = uuid4()
    submission.raw_text = "تورم بالا"

    created_candidate = MagicMock()
    created_candidate.id = uuid4()

    session = AsyncMock()
    session.execute.side_effect = [_select_result(None), _select_result(None)]

    router = _router_with_primary(
        '{"title":"Inflation policy","domain":"economy","summary":"Lower inflation",'
        '"stance":"support","entities":["inflation"],"confidence":0.3,"ambiguity_flags":[]}'
    )
    router.complete_with_model.side_effect = [
        LLMResponse(
            text='{"title":"Inflation relief","domain":"economy","summary":"Relief policy",'
            '"stance":"support","entities":["inflation"],"confidence":0.6,"ambiguity_flags":[]}',
            model="claude-opus-4-20250514",
            input_tokens=10,
            output_tokens=8,
            cost_usd=0.0,
        ),
        LLMResponse(
            text='{"title":"Inflation stabilization","domain":"economy","summary":"Stabilize prices",'
            '"stance":"support","entities":["inflation"],"confidence":0.8,"ambiguity_flags":[]}',
            model="deepseek-chat",
            input_tokens=10,
            output_tokens=8,
            cost_usd=0.0,
        ),
    ]

    with (
        patch("src.handlers.disputes.append_evidence", new_callable=AsyncMock) as mock_evidence,
        patch("src.handlers.disputes.create_policy_candidate", new_callable=AsyncMock, return_value=created_candidate),
        patch("src.handlers.disputes._record_dispute_metrics", new_callable=AsyncMock) as mock_metrics,
    ):
        result = await resolve_submission_dispute(session=session, submission=submission, llm_router=router)

    assert result["status"] == "resolved"
    assert result["escalated"] is True
    assert result["candidate_id"] == str(created_candidate.id)
    assert router.complete.call_count == 1
    assert router.complete_with_model.call_count >= 1
    event_types = [call.kwargs["event_type"] for call in mock_evidence.call_args_list]
    assert "dispute_escalated" in event_types
    assert "dispute_resolved" in event_types
    mock_metrics.assert_called_once()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_record_dispute_metrics_recommends_tuning_on_high_rate() -> None:
    session = AsyncMock()
    session.execute.side_effect = [
        _count_result(100),
        _payload_rows_result([
            {"escalated": True}, {"escalated": True}, {"escalated": True},
            {"escalated": True}, {"escalated": True}, {"escalated": True},
            {"escalated": True}, {"escalated": True},
        ]),
    ]

    with patch("src.handlers.disputes.append_evidence", new_callable=AsyncMock) as mock_evidence:
        await _record_dispute_metrics(
            session=session,
            submission_id=uuid4(),
            resolution_seconds=120.0,
            escalated=True,
            confidence=0.55,
        )

    assert mock_evidence.call_count == 2
    event_types = [call.kwargs["event_type"] for call in mock_evidence.call_args_list]
    assert event_types == ["dispute_metrics_recorded", "dispute_tuning_recommended"]
