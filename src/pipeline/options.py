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
You are a nonpartisan policy analyst. Given a specific civic proposition and \
real citizen submissions, generate distinct stance options that answer the \
same underlying ballot question. Each option should be a genuine, defensible \
position with clear reasoning.

Draw on real-world policy precedents, existing implementations, and \
established frameworks from around the world. Ground your options in both \
the citizen submissions AND real-world context.

Rules:
- Generate 2-4 options (never fewer than 2).
- Each option must represent a meaningfully different approach, not just \
different wording of the same idea.
- Every option must address the SAME proposition. Do not broaden the issue \
into unrelated geopolitical or ideological debates.
- Incorporate real-world examples, precedents, or established policy \
frameworks where relevant.
- Describe concrete trade-offs: what you gain AND what you give up.
- Use accessible language — avoid jargon.
- Be balanced: do NOT editorialize or favor one option.
- Output valid JSON only — no markdown fences, no commentary.
- Do NOT attempt to call tools, functions, or APIs. Produce the JSON array directly.
"""

_USER_PROMPT_TEMPLATE = """\
Proposition: {proposition}
Concern summary: {summary}

Citizen submissions related to this proposition:
{submissions_block}

Generate distinct ballot options that answer this proposition. Return a JSON array:
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
) -> str:
    lines: list[str] = []
    for cid in cluster.candidate_ids:
        candidate = candidates_by_id.get(cid)
        if candidate is None:
            continue
        lines.append(
            "- "
            f"[{candidate.stance}; actor={candidate.actor_scope}; mechanism={candidate.action_mechanism}; "
            f"target={candidate.target_scope}; readiness={candidate.ballot_readiness}] "
            f"{candidate.title}: {candidate.summary}"
        )
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


async def _generate_options_for_cluster(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> tuple[list[dict[str, str]], str]:
    """Try primary model, then fallback on parse failure, then generic options.

    Returns (parsed_options, model_version).
    """
    submissions_block = _build_submissions_block(cluster, candidates_by_id)
    prompt = _USER_PROMPT_TEMPLATE.format(
        proposition=cluster.ballot_question or cluster.summary,
        summary=cluster.summary,
        submissions_block=submissions_block,
    )

    completion = await llm_router.complete(
        tier="option_generation",
        prompt=prompt,
        system_prompt=_SYSTEM_PROMPT,
        max_tokens=2048,
        temperature=0.3,
        grounding=True,
    )
    try:
        return _parse_options_json(completion.text), completion.model
    except (json.JSONDecodeError, ValueError) as parse_exc:
        logger.warning(
            "Primary model %s returned unparseable options for cluster %s (%s), retrying with explicit fallback model",
            completion.model, cluster.id, parse_exc,
        )
        _, fallback_model = llm_router._resolve_tier_models("option_generation")
        retry_model = fallback_model if fallback_model and fallback_model != completion.model else completion.model
        retry = await llm_router.complete_with_model(
            model=retry_model,
            prompt=prompt,
            system_prompt=_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.2,
        )
        return _parse_options_json(retry.text), retry.model


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
        model_version = "fallback"
        try:
            parsed, model_version = await _generate_options_for_cluster(
                cluster, candidates_by_id, llm_router,
            )
        except Exception as exc:
            logger.exception("Failed to generate options for cluster %s", cluster.id)
            parsed = _fallback_options(cluster)
            await append_evidence(
                session=session,
                event_type="policy_options_fallback_used",
                entity_type="cluster",
                entity_id=cluster.id,
                payload={
                    "cluster_id": str(cluster.id),
                    "policy_key": cluster.policy_key,
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
            },
        )

    await session.flush()
    return all_options


def _fallback_options(cluster: Cluster) -> list[dict[str, str]]:
    """Minimal two-option fallback when LLM generation fails.

    Only used for infrastructure unavailability (provider down / timeouts).
    Descriptions are fully bilingual using the cluster's own language fields.
    """
    fa_desc = cluster.ballot_question_fa or "این سیاست"
    en_desc = cluster.ballot_question or cluster.summary
    return [
        {
            "label": "حمایت از این سیاست",
            "label_en": "Support this policy",
            "description": f"حمایت از: {fa_desc}",
            "description_en": f"Support implementing: {en_desc}",
        },
        {
            "label": "مخالفت با این سیاست",
            "label_en": "Oppose this policy",
            "description": f"مخالفت با: {fa_desc}",
            "description_en": f"Oppose due to costs or unintended consequences: {en_desc}",
        },
    ]
