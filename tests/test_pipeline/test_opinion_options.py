"""Tests for opinion-question option generation and lane-aware clustering."""
from __future__ import annotations

import json
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.models.submission import PolicyCandidate
from src.pipeline.cluster import group_by_policy_key
from src.pipeline.llm import LLMResponse
from src.pipeline.opinion_options import (
    _build_submissions_block,
    _coerce_options,
    _fallback_options,
    _parse_options_json,
    generate_opinion_options,
)

# ---------------------------------------------------------------------------
# Fake candidate with submission_lane
# ---------------------------------------------------------------------------

class _FakeCandidate:
    def __init__(
        self,
        *,
        policy_key: str = "test-policy",
        submission_lane: str = "policy_proposal",
        embedding: list[float] | None = None,
    ) -> None:
        self.id = uuid4()
        self.policy_key = policy_key
        self.submission_lane = submission_lane
        self.embedding = embedding
        self.policy_topic = "test-topic"


# ---------------------------------------------------------------------------
# group_by_policy_key — composite key includes submission_lane
# ---------------------------------------------------------------------------

class TestGroupByPolicyKeyLaneAware:
    def test_same_key_different_lanes_get_separate_groups(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                _FakeCandidate(policy_key="healthcare", submission_lane="policy_proposal"),
                _FakeCandidate(policy_key="healthcare", submission_lane="opinion_question"),
            ],
        )
        groups = group_by_policy_key(candidates=candidates)
        assert len(groups) == 2
        assert "healthcare|policy_proposal" in groups
        assert "healthcare|opinion_question" in groups

    def test_same_key_same_lane_grouped_together(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                _FakeCandidate(policy_key="education", submission_lane="opinion_question"),
                _FakeCandidate(policy_key="education", submission_lane="opinion_question"),
            ],
        )
        groups = group_by_policy_key(candidates=candidates)
        assert len(groups) == 1
        assert len(groups["education|opinion_question"]) == 2

    def test_unassigned_excluded_regardless_of_lane(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                _FakeCandidate(policy_key="unassigned", submission_lane="opinion_question"),
                _FakeCandidate(policy_key="real-key", submission_lane="policy_proposal"),
            ],
        )
        groups = group_by_policy_key(candidates=candidates)
        assert len(groups) == 1
        assert "real-key|policy_proposal" in groups

    def test_composite_key_includes_discussion_only(self) -> None:
        candidates = cast(
            list[PolicyCandidate],
            [
                _FakeCandidate(policy_key="economy", submission_lane="discussion_only"),
            ],
        )
        groups = group_by_policy_key(candidates=candidates)
        assert "economy|discussion_only" in groups


# ---------------------------------------------------------------------------
# _parse_options_json  (opinion variant)
# ---------------------------------------------------------------------------

class TestParseOpinionOptionsJson:
    def test_parse_valid_array(self) -> None:
        raw = json.dumps([
            {"label": "موافقم", "label_en": "Agree", "description": "d", "description_en": "d"},
            {"label": "مخالفم", "label_en": "Disagree", "description": "d", "description_en": "d"},
        ])
        result = _parse_options_json(raw)
        assert len(result) == 2

    def test_truncates_to_four(self) -> None:
        items = [
            {"label": f"L{i}", "label_en": f"L{i}", "description": f"D{i}", "description_en": f"D{i}"}
            for i in range(6)
        ]
        result = _parse_options_json(json.dumps(items))
        assert len(result) == 4

    def test_rejects_single_option(self) -> None:
        raw = json.dumps([{"label": "only", "label_en": "o", "description": "d", "description_en": "d"}])
        with pytest.raises(ValueError, match="2-4"):
            _parse_options_json(raw)

    def test_handles_markdown_fences(self) -> None:
        items = json.dumps([
            {"label": "A", "label_en": "A", "description": "d", "description_en": "d"},
            {"label": "B", "label_en": "B", "description": "d", "description_en": "d"},
        ])
        raw = f"```json\n{items}\n```"
        result = _parse_options_json(raw)
        assert len(result) == 2

    def test_extracts_array_after_prose(self) -> None:
        items = json.dumps([
            {"label": "A", "label_en": "A", "description": "d", "description_en": "d"},
            {"label": "B", "label_en": "B", "description": "d", "description_en": "d"},
        ])
        raw = f"Here is my analysis.\n\n{items}"
        result = _parse_options_json(raw)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _coerce_options
# ---------------------------------------------------------------------------

class TestCoerceOptions:
    def test_valid_list(self) -> None:
        parsed = [
            {"label": "A", "label_en": "A_en", "description": "d", "description_en": "de"},
            {"label": "B", "label_en": "B_en", "description": "d", "description_en": "de"},
        ]
        result = _coerce_options(parsed)
        assert len(result) == 2
        assert result[0]["label"] == "A"

    def test_missing_fields_default_empty(self) -> None:
        parsed = [{"label": "A"}, {"label": "B"}]
        result = _coerce_options(parsed)
        assert result[0]["label_en"] == ""
        assert result[0]["description"] == ""

    def test_rejects_single_item(self) -> None:
        with pytest.raises(ValueError, match="2-4"):
            _coerce_options([{"label": "only"}])

    def test_rejects_non_list(self) -> None:
        with pytest.raises(ValueError):
            _coerce_options({"not": "a list"})


# ---------------------------------------------------------------------------
# _fallback_options  (opinion variant)
# ---------------------------------------------------------------------------

class TestOpinionFallbackOptions:
    def test_produces_agree_disagree(self) -> None:
        cluster = MagicMock()
        cluster.ballot_question = "Should we reform education?"
        cluster.ballot_question_fa = "آیا باید آموزش را اصلاح کنیم؟"
        cluster.summary = "Education reform"
        result = _fallback_options(cluster)
        assert len(result) == 2
        assert result[0]["label_en"] == "Agree"
        assert result[1]["label_en"] == "Disagree"

    def test_uses_ballot_question_fa_for_farsi(self) -> None:
        cluster = MagicMock()
        cluster.ballot_question = "Should we reform education?"
        cluster.ballot_question_fa = "آیا باید اصلاح شود؟"
        cluster.summary = "Education reform"
        result = _fallback_options(cluster)
        assert "آیا باید اصلاح شود؟" in result[0]["description"]

    def test_falls_back_to_summary_without_ballot_question(self) -> None:
        cluster = MagicMock()
        cluster.ballot_question = None
        cluster.ballot_question_fa = None
        cluster.summary = "Education reform"
        result = _fallback_options(cluster)
        assert "Education reform" in result[0]["description_en"]


# ---------------------------------------------------------------------------
# _build_submissions_block
# ---------------------------------------------------------------------------

class TestBuildOpinionSubmissionsBlock:
    def test_formats_candidate_lines(self) -> None:
        cluster = MagicMock()
        cid1, cid2 = uuid4(), uuid4()
        cluster.candidate_ids = [cid1, cid2]

        c1 = MagicMock()
        c1.id = cid1
        c1.stance = "support"
        c1.title = "Title A"
        c1.summary = "Summary A"

        c2 = MagicMock()
        c2.id = cid2
        c2.stance = "oppose"
        c2.title = "Title B"
        c2.summary = "Summary B"

        block = _build_submissions_block(cluster, {cid1: c1, cid2: c2})
        assert "[support]" in block
        assert "[oppose]" in block
        assert "Title A" in block

    def test_missing_candidates(self) -> None:
        cluster = MagicMock()
        cluster.candidate_ids = [uuid4()]
        block = _build_submissions_block(cluster, {})
        assert "no submissions" in block


# ---------------------------------------------------------------------------
# generate_opinion_options (integration)
# ---------------------------------------------------------------------------

def _make_opinion_cluster(n_candidates: int = 2) -> MagicMock:
    cluster = MagicMock()
    cluster.id = uuid4()
    cluster.summary = "Public opinion on education reform"
    cluster.ballot_question = "What should be the priority for education reform?"
    cluster.ballot_question_fa = "اولویت اصلاحات آموزشی چیست؟"
    cluster.candidate_ids = [uuid4() for _ in range(n_candidates)]
    cluster.policy_topic = "education"
    cluster.policy_key = "education-reform"
    cluster.submission_lane = "opinion_question"
    return cluster


def _make_opinion_candidate(cid: object) -> MagicMock:
    c = MagicMock()
    c.id = cid
    c.title = "Education access"
    c.summary = "Everyone should have access to quality education."
    c.stance = "support"
    return c


@pytest.mark.asyncio
@patch("src.pipeline.opinion_options.append_evidence", new_callable=AsyncMock)
async def test_generate_opinion_options_creates_records(mock_evidence: AsyncMock) -> None:
    cluster = _make_opinion_cluster(2)
    c1 = _make_opinion_candidate(cluster.candidate_ids[0])
    c2 = _make_opinion_candidate(cluster.candidate_ids[1])
    candidates_by_id = {c1.id: c1, c2.id: c2}

    llm_output = json.dumps([
        {"label": "موافقم", "label_en": "Agree", "description": "توضیح", "description_en": "Desc"},
        {"label": "مخالفم", "label_en": "Disagree", "description": "توضیح", "description_en": "Desc"},
        {"label": "بی‌طرف", "label_en": "Neutral", "description": "توضیح", "description_en": "Desc"},
    ])
    router = MagicMock()
    router.complete = AsyncMock(return_value=LLMResponse(
        text=llm_output, model="test-model", input_tokens=10, output_tokens=20, cost_usd=0.001,
    ))

    session = AsyncMock()
    session.add = MagicMock()
    options = await generate_opinion_options(
        session=session,
        clusters=[cluster],
        candidates_by_id=candidates_by_id,
        llm_router=router,
    )

    assert len(options) == 3
    assert options[0].label == "موافقم"
    assert options[2].label == "بی‌طرف"
    assert options[0].model_version == "test-model"
    session.add.assert_called()
    session.flush.assert_called()

    generated_calls = [
        c for c in mock_evidence.call_args_list
        if c.kwargs.get("event_type") == "policy_options_generated"
    ]
    assert len(generated_calls) == 1
    assert generated_calls[0].kwargs["payload"]["submission_lane"] == "opinion_question"


@pytest.mark.asyncio
@patch("src.pipeline.opinion_options.append_evidence", new_callable=AsyncMock)
async def test_generate_opinion_options_uses_fallback_on_error(mock_evidence: AsyncMock) -> None:
    cluster = _make_opinion_cluster(1)
    c1 = _make_opinion_candidate(cluster.candidate_ids[0])
    candidates_by_id = {c1.id: c1}

    router = MagicMock()
    router.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

    session = AsyncMock()
    session.add = MagicMock()
    options = await generate_opinion_options(
        session=session,
        clusters=[cluster],
        candidates_by_id=candidates_by_id,
        llm_router=router,
    )

    assert len(options) == 2
    assert options[0].model_version == "fallback"

    fallback_calls = [
        c for c in mock_evidence.call_args_list
        if c.kwargs.get("event_type") == "policy_options_fallback_used"
    ]
    assert len(fallback_calls) == 1
    assert fallback_calls[0].kwargs["payload"]["submission_lane"] == "opinion_question"
