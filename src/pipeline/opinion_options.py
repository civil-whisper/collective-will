"""Generate LLM-powered answer options for opinion-question clusters.

Unlike policy proposals (which get stance options on a specific proposition),
opinion questions get neutral answer choices that capture the real positions
expressed in the cluster submissions.  Output is bilingual (Farsi + English).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.cluster import Cluster
from src.models.policy_option import PolicyOption, PolicyOptionCreate
from src.models.submission import PolicyCandidate
from src.pipeline.llm import LLMRouter

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a nonpartisan public-opinion analyst. Given a civic question and real \
citizen submissions, generate distinct answer options that capture the range \
of genuine positions people hold on this issue.

Rules:
- Generate 2-4 answer options (never fewer than 2).
- Each option must represent a meaningfully different viewpoint or position, \
not just different wording of the same idea.
- Options must be neutral and non-leading — do NOT editorialize or favor one \
answer.
- Frame each option as a genuine position someone might hold, with concrete \
reasoning.
- Use accessible language — avoid jargon.
- Output valid JSON only — no markdown fences, no commentary.
- Do NOT attempt to call tools, functions, or APIs. Produce the JSON array \
directly.
"""

_USER_PROMPT_TEMPLATE = """\
Opinion question: {question}
Context summary: {summary}

Citizen submissions related to this question:
{submissions_block}

Generate distinct answer options that capture the real positions people hold \
on this question. Return a JSON array:
[
  {{
    "label": "<short Farsi label, max 60 chars>",
    "label_en": "<short English label, max 60 chars>",
    "description": "<Farsi description — 2-3 sentences explaining this position>",
    "description_en": "<English description — 2-3 sentences explaining this position>"
  }},
  ...
]
"""


def _build_submissions_block(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
) -> str:
    lines: list[str] = []
    for cid in cluster.candidate_ids:
        candidate = candidates_by_id.get(cid)
        if candidate is None:
            continue
        lines.append(
            f"- [{candidate.stance}] {candidate.title}: {candidate.summary}"
        )
    return "\n".join(lines) if lines else "(no submissions available)"


def _coerce_options(parsed: Any) -> list[dict[str, str]]:
    if not isinstance(parsed, list) or len(parsed) < 2:
        n = len(parsed) if isinstance(parsed, list) else "N/A"
        raise ValueError(
            f"Expected array of 2-4 items, got {type(parsed).__name__} len={n}"
        )

    options: list[dict[str, str]] = []
    for item in parsed[:4]:
        options.append({
            "label": str(item.get("label", "")),
            "label_en": str(item.get("label_en", "")),
            "description": str(item.get("description", "")),
            "description_en": str(item.get("description_en", "")),
        })
    return options


def _extract_first_json_array(text: str) -> str | None:
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\[", text):
        try:
            parsed, end_idx = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return text[match.start(): match.start() + end_idx]
    return None


def _parse_options_json(raw: str) -> list[dict[str, str]]:
    text = raw.strip()
    candidate_texts = [text]

    for match in re.finditer(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL):
        block = match.group(1).strip()
        if block:
            candidate_texts.append(block)

    extracted = _extract_first_json_array(text)
    if extracted:
        candidate_texts.append(extracted)

    seen: set[str] = set()
    last_error: Exception | None = None
    for candidate in candidate_texts:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return _coerce_options(json.loads(normalized))
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise ValueError("No JSON array found in opinion option generation response")


def _fallback_options(cluster: Cluster) -> list[dict[str, str]]:
    fa_desc = cluster.ballot_question_fa or "این سؤال"
    en_desc = cluster.ballot_question or cluster.summary
    return [
        {
            "label": "موافقم",
            "label_en": "Agree",
            "description": f"موافقت با: {fa_desc}",
            "description_en": f"Agree with the position implied by: {en_desc}",
        },
        {
            "label": "مخالفم",
            "label_en": "Disagree",
            "description": f"مخالفت با: {fa_desc}",
            "description_en": f"Disagree with the position implied by: {en_desc}",
        },
    ]


async def generate_opinion_options(
    *,
    session: AsyncSession,
    clusters: list[Cluster],
    candidates_by_id: Mapping[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> list[PolicyOption]:
    """Generate and persist answer options for opinion-question clusters."""
    all_options: list[PolicyOption] = []

    for cluster in clusters:
        model_version = "fallback"
        try:
            submissions_block = _build_submissions_block(cluster, candidates_by_id)
            prompt = _USER_PROMPT_TEMPLATE.format(
                question=cluster.ballot_question or cluster.summary,
                summary=cluster.summary,
                submissions_block=submissions_block,
            )
            completion = await llm_router.complete(
                tier="option_generation",
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.3,
            )
            parsed = _parse_options_json(completion.text)
            model_version = completion.model
        except Exception as exc:
            logger.exception("Failed to generate opinion options for cluster %s", cluster.id)
            parsed = _fallback_options(cluster)
            await append_evidence(
                session=session,
                event_type="policy_options_fallback_used",
                entity_type="cluster",
                entity_id=cluster.id,
                payload={
                    "cluster_id": str(cluster.id),
                    "policy_key": cluster.policy_key,
                    "submission_lane": "opinion_question",
                    "error_type": type(exc).__name__,
                },
            )

        for position, item in enumerate(parsed, 1):
            option_data = PolicyOptionCreate(
                cluster_id=cluster.id,
                position=position,
                label=item["label"],
                label_en=item.get("label_en"),
                description=item["description"],
                description_en=item.get("description_en"),
                model_version=model_version,
            )
            db_option = PolicyOption(
                cluster_id=option_data.cluster_id,
                position=option_data.position,
                label=option_data.label,
                label_en=option_data.label_en,
                description=option_data.description,
                description_en=option_data.description_en,
                model_version=option_data.model_version,
            )
            session.add(db_option)
            all_options.append(db_option)

        await session.flush()

        await append_evidence(
            session=session,
            event_type="policy_options_generated",
            entity_type="cluster",
            entity_id=cluster.id,
            payload={
                "cluster_id": str(cluster.id),
                "option_count": len(parsed),
                "labels": [item["label"] for item in parsed],
                "model_version": model_version,
                "submission_lane": "opinion_question",
            },
        )

    await session.flush()
    return all_options
