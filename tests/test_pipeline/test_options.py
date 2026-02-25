from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.models.policy_option import PolicyOptionCreate
from src.pipeline.llm import LLMResponse
from src.pipeline.options import (
    _build_submissions_block,
    _fallback_options,
    _parse_options_json,
    generate_policy_options,
)


def _make_cluster(n_candidates: int = 3) -> MagicMock:
    cluster = MagicMock()
    cluster.id = uuid4()
    cluster.summary = "بهداشت عمومی"
    cluster.summary_en = "Public healthcare"
    cluster.domain = "rights"
    cluster.candidate_ids = [uuid4() for _ in range(n_candidates)]
    return cluster


def _make_candidate(cid: object, stance: str = "support") -> MagicMock:
    c = MagicMock()
    c.id = cid
    c.title = "Healthcare access"
    c.summary = "Everyone should have access to healthcare."
    c.stance = stance
    return c


# ---------------------------------------------------------------------------
# PolicyOptionCreate schema validation
# ---------------------------------------------------------------------------

def test_policy_option_create_valid() -> None:
    data = PolicyOptionCreate(
        cluster_id=uuid4(),
        position=1,
        label="Support",
        description="Support this policy",
        model_version="test-model",
    )
    assert data.position == 1
    assert data.label_en is None


def test_policy_option_create_rejects_empty_label() -> None:
    with pytest.raises(ValidationError):
        PolicyOptionCreate(
            cluster_id=uuid4(),
            position=1,
            label="",
            description="desc",
            model_version="m",
        )


def test_policy_option_create_rejects_zero_position() -> None:
    with pytest.raises(ValidationError):
        PolicyOptionCreate(
            cluster_id=uuid4(),
            position=0,
            label="Label",
            description="desc",
            model_version="m",
        )


# ---------------------------------------------------------------------------
# _parse_options_json
# ---------------------------------------------------------------------------

def test_parse_valid_json() -> None:
    raw = json.dumps([
        {
            "label": "گزینه الف",
            "label_en": "Option A",
            "description": "توضیح الف",
            "description_en": "Description A",
        },
        {
            "label": "گزینه ب",
            "label_en": "Option B",
            "description": "توضیح ب",
            "description_en": "Description B",
        },
    ])
    result = _parse_options_json(raw)
    assert len(result) == 2
    assert result[0]["label"] == "گزینه الف"
    assert result[1]["label_en"] == "Option B"


def test_parse_json_with_markdown_fences() -> None:
    items = json.dumps([
        {"label": "A", "label_en": "A", "description": "d", "description_en": "d"},
        {"label": "B", "label_en": "B", "description": "d", "description_en": "d"},
    ])
    raw = f"```json\n{items}\n```"
    result = _parse_options_json(raw)
    assert len(result) == 2


def test_parse_truncates_to_four() -> None:
    items = [
        {"label": f"L{i}", "label_en": f"L{i}", "description": f"D{i}", "description_en": f"D{i}"}
        for i in range(6)
    ]
    raw = json.dumps(items)
    result = _parse_options_json(raw)
    assert len(result) == 4


def test_parse_rejects_single_option() -> None:
    raw = json.dumps([{"label": "only one", "label_en": "x", "description": "d", "description_en": "d"}])
    with pytest.raises(ValueError, match="2-4"):
        _parse_options_json(raw)


def test_parse_rejects_non_array() -> None:
    with pytest.raises((ValueError, json.JSONDecodeError)):
        _parse_options_json('{"not": "an array"}')


# ---------------------------------------------------------------------------
# _build_submissions_block
# ---------------------------------------------------------------------------

def test_submissions_block_formats_candidates() -> None:
    cluster = _make_cluster(2)
    c1 = _make_candidate(cluster.candidate_ids[0], "support")
    c2 = _make_candidate(cluster.candidate_ids[1], "oppose")
    candidates_by_id = {c1.id: c1, c2.id: c2}

    block = _build_submissions_block(cluster, candidates_by_id)
    assert "[support]" in block
    assert "[oppose]" in block


def test_submissions_block_missing_candidates() -> None:
    cluster = _make_cluster(2)
    block = _build_submissions_block(cluster, {})
    assert "no submissions" in block


# ---------------------------------------------------------------------------
# _fallback_options
# ---------------------------------------------------------------------------

def test_fallback_produces_two_options() -> None:
    cluster = _make_cluster()
    result = _fallback_options(cluster)
    assert len(result) == 2
    assert result[0]["label_en"] == "Support this policy"
    assert result[1]["label_en"] == "Oppose this policy"


# ---------------------------------------------------------------------------
# generate_policy_options (integration)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@patch("src.pipeline.options.append_evidence", new_callable=AsyncMock)
async def test_generate_policy_options_creates_records(mock_evidence: AsyncMock) -> None:
    cluster = _make_cluster(2)
    c1 = _make_candidate(cluster.candidate_ids[0])
    c2 = _make_candidate(cluster.candidate_ids[1])
    candidates_by_id = {c1.id: c1, c2.id: c2}

    llm_output = json.dumps([
        {"label": "حمایت", "label_en": "Support", "description": "توضیح", "description_en": "Desc"},
        {"label": "مخالفت", "label_en": "Oppose", "description": "توضیح", "description_en": "Desc"},
    ])
    router = MagicMock()
    router.complete = AsyncMock(return_value=LLMResponse(
        text=llm_output, model="test-model", input_tokens=10, output_tokens=20, cost_usd=0.001,
    ))

    session = AsyncMock()
    options = await generate_policy_options(
        session=session,
        clusters=[cluster],
        candidates_by_id=candidates_by_id,
        llm_router=router,
    )

    assert len(options) == 2
    assert options[0].label == "حمایت"
    assert options[0].position == 1
    assert options[1].label == "مخالفت"
    assert options[1].position == 2
    assert options[0].model_version == "test-model"
    session.add.assert_called()
    session.flush.assert_called()
    mock_evidence.assert_called_once()


@pytest.mark.asyncio
@patch("src.pipeline.options.append_evidence", new_callable=AsyncMock)
async def test_generate_policy_options_uses_fallback_on_error(mock_evidence: AsyncMock) -> None:
    cluster = _make_cluster(1)
    c1 = _make_candidate(cluster.candidate_ids[0])
    candidates_by_id = {c1.id: c1}

    router = MagicMock()
    router.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

    session = AsyncMock()
    options = await generate_policy_options(
        session=session,
        clusters=[cluster],
        candidates_by_id=candidates_by_id,
        llm_router=router,
    )

    assert len(options) == 2
    assert options[0].model_version == "fallback"
