"""Generate LLM-powered multi-angle stance options for each policy cluster.

For each cluster, the LLM examines the member submissions and produces 2-4
distinct stance options (perspectives / policy approaches), each with a short
label and a description covering pros & cons.  Output is bilingual (Farsi +
English).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.cluster import Cluster
from src.models.policy_option import PolicyOption, PolicyOptionCreate
from src.models.submission import PolicyCandidate
from src.pipeline.llm import LLMRouter

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a nonpartisan policy analyst. Given a policy topic and real citizen \
submissions, generate distinct stance options that cover the realistic \
spectrum of approaches. Each option should be a genuine, defensible position \
with clear reasoning.

Rules:
- Generate 2-4 options (never fewer than 2).
- Each option must represent a meaningfully different approach, not just \
different wording of the same idea.
- Describe concrete trade-offs: what you gain AND what you give up.
- Use accessible language — avoid jargon.
- Be balanced: do NOT editorialize or favor one option.
- Output valid JSON only — no markdown fences, no commentary.
"""

_USER_PROMPT_TEMPLATE = """\
Policy topic summary (Farsi): {summary_fa}
Policy topic summary (English): {summary_en}
Domain: {domain}

Citizen submissions on this topic (sample):
{submissions_block}

Generate distinct stance options. Return a JSON array:
[
  {{
    "label": "<short Farsi label, max 60 chars>",
    "label_en": "<short English label, max 60 chars>",
    "description": "<Farsi description — 2-4 sentences covering pros/cons>",
    "description_en": "<English description — 2-4 sentences covering pros/cons>"
  }},
  ...
]
"""


def _build_submissions_block(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
    max_samples: int = 15,
) -> str:
    lines: list[str] = []
    for cid in cluster.candidate_ids[:max_samples]:
        candidate = candidates_by_id.get(cid)
        if candidate is None:
            continue
        stance = candidate.stance
        title = candidate.title
        summary = candidate.summary[:200]
        lines.append(f"- [{stance}] {title}: {summary}")
    return "\n".join(lines) if lines else "(no submissions available)"


def _parse_options_json(raw: str) -> list[dict[str, str]]:
    """Best-effort parse of the LLM JSON output."""
    text = raw.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        last_fence = text.rfind("```")
        text = text[first_newline + 1 : last_fence].strip()

    parsed = json.loads(text)
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


async def generate_policy_options(
    *,
    session: AsyncSession,
    clusters: list[Cluster],
    candidates_by_id: Mapping[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> list[PolicyOption]:
    """Generate and persist stance options for each cluster.

    Returns all created PolicyOption rows.
    """
    all_options: list[PolicyOption] = []

    for cluster in clusters:
        summary_en = cluster.summary_en or cluster.summary
        submissions_block = _build_submissions_block(cluster, candidates_by_id)
        prompt = _USER_PROMPT_TEMPLATE.format(
            summary_fa=cluster.summary,
            summary_en=summary_en,
            domain=cluster.domain if isinstance(cluster.domain, str) else cluster.domain.value,
            submissions_block=submissions_block,
        )

        model_version = "fallback"
        try:
            completion = await llm_router.complete(
                tier="english_reasoning",
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                max_tokens=2048,
                temperature=0.3,
            )
            parsed = _parse_options_json(completion.text)
            model_version = completion.model
        except Exception:
            logger.exception("Failed to generate options for cluster %s", cluster.id)
            parsed = _fallback_options(cluster)

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
            },
        )

    await session.flush()
    return all_options


def _fallback_options(cluster: Cluster) -> list[dict[str, str]]:
    """Minimal two-option fallback when LLM generation fails."""
    summary_en = cluster.summary_en or cluster.summary
    return [
        {
            "label": "حمایت از این سیاست",
            "label_en": "Support this policy",
            "description": f"حمایت از اجرای این سیاست: {cluster.summary[:150]}",
            "description_en": f"Support implementing this policy: {summary_en[:150]}",
        },
        {
            "label": "مخالفت با این سیاست",
            "label_en": "Oppose this policy",
            "description": f"مخالفت با اجرای این سیاست به دلیل هزینه یا عواقب ناخواسته: {cluster.summary[:100]}",
            "description_en": f"Oppose this policy due to costs or unintended consequences: {summary_en[:100]}",
        },
    ]
