"""Phase 3: Generate stance-neutral ballot questions per policy_key cluster.

For each cluster that needs summarization, gathers all member submissions
and asks the LLM to produce a neutral ballot question suitable for the
endorsement step ("Should this topic appear on the ballot?").
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate
from src.pipeline.llm import LLMRouter

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a nonpartisan democratic process analyst. "
    "Your job is to write plain-language, impartial civic wording that resembles "
    "a real democratic process. Preserve the difference between a broad concern "
    "that needs more refinement and a concrete proposition that voters could actually decide. "
    "Do not invent a new actor, jurisdiction, or target that is not grounded in the source submissions."
)

_PROMPT_TEMPLATE = """\
Policy discussion: "{policy_key}"
Number of submissions: {member_count}

Citizen submissions on this issue:
{submissions_block}

Generate two pieces of neutral wording:
1. ballot_question:
   - If the issue is concrete and ballot-ready, write neutral proposition language
     describing what voters would actually be deciding.
   - If the issue needs refinement but has a clear direction, write a concise public-facing
     civic prompt around the concrete proposition under debate. Mention missing scope only briefly.
   - If the issue is discussion-only, write a concise civic discussion prompt about the public issue itself.
2. summary:
   - Write a short neutral summary suitable for a concerns/discussion list.

IMPORTANT formatting rules for the Farsi version (ballot_question_fa):
- Write as a STATEMENT, not a question. Do NOT start with «آیا» or end with «؟».
- Use casual, plain Farsi suitable for people in their early 20s — direct and friendly, not formal or bureaucratic.
- Plain-language civic style is more important than rhetoric.

Ballot-language requirements:
- Use concise, impartial language.
- Avoid "one citizen raised a concern" narration and avoid internal workflow language.
- Avoid starting with "This concern" or "This topic" unless no cleaner wording is possible.
- Do not say "move forward", "structured discussion", "public consideration", "further refinement",
  "agenda-setting", or similar meta-process phrases.
- For needs-refinement items, focus on the core policy dispute and keep the wording civic and public-facing.
- For needs-refinement items, prefer deliberative civic wording such as "debate over whether..." or
  "discussion of whether..." rather than bare advocacy slogans like "support X" or "use X".
- For discussion-only items, frame the issue as a public discussion topic, not as an internal process decision.
- Make clear whether the item is a concrete proposition, a draftable concern, or a broad discussion topic.
- Do not invent an option set or political spectrum in this step.
- Do not introduce a new actor, institution, city, country, or jurisdiction unless it is explicit in the submissions.
- If the actor is unclear, keep the wording actor-neutral.
- Do not turn a broad war/conflict/intervention submission into a specific
  country-led action unless the source submissions say so.

Return ONLY raw JSON (no markdown):
{{
  "ballot_question": "English policy description (statement format)",
  "ballot_question_fa": "Farsi policy description (statement, casual tone, no آیا, no ؟)",
  "summary": "Short neutral English summary of the policy discussion"
}}
"""

_LOCAL_ACTOR_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bthe united states should\b", flags=re.IGNORECASE),
        "Ballot wording introduced a U.S. actor not grounded in the source submissions.",
    ),
    (
        re.compile(r"\bu\.s\. should\b", flags=re.IGNORECASE),
        "Ballot wording introduced a U.S. actor not grounded in the source submissions.",
    ),
    (
        re.compile(r"\bthe city should\b", flags=re.IGNORECASE),
        "Ballot wording introduced a city-level actor not grounded in the source submissions.",
    ),
)
_UNANCHORED_TARGET_PHRASES = (
    "against iran",
    "against the iranian regime",
    "against iran's government",
    "change iran's government",
    "change iran’s government",
)
_MECHANISM_LABELS_EN = {
    "labor-strike": "labor strikes",
    "economic-sanctions": "economic sanctions",
    "economic-pressure": "economic pressure",
    "military-action": "military action",
    "diplomatic-pressure": "diplomatic pressure",
    "civil-society-support": "civil-society support",
    "governance-design": "governance rules",
    "discussion-only": "this public issue",
    "other": "this policy direction",
    "unclear": "this policy direction",
}
_MECHANISM_LABELS_FA = {
    "labor-strike": "اعتصاب کارگری",
    "economic-sanctions": "تحریم اقتصادی",
    "economic-pressure": "فشار اقتصادی",
    "military-action": "اقدام نظامی",
    "diplomatic-pressure": "فشار دیپلماتیک",
    "civil-society-support": "حمایت مدنی",
    "governance-design": "قواعد حکمرانی",
    "discussion-only": "این موضوع عمومی",
    "other": "این جهت‌گیری سیاستی",
    "unclear": "این جهت‌گیری سیاستی",
}
_TARGET_SUFFIXES_EN = {
    "iranian-regime": " affecting the Iranian regime",
    "iranian-economy": " affecting the Iranian economy",
    "public-governance": " in public governance",
    "civil-rights": " related to civil rights",
}
_TARGET_SUFFIXES_FA = {
    "iranian-regime": " علیه رژیم ایران",
    "iranian-economy": " بر اقتصاد ایران",
    "public-governance": " در حوزه حکمرانی عمومی",
    "civil-rights": " در حوزه حقوق مدنی",
}


def _build_submissions_block(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
) -> str:
    lines: list[str] = []
    for cid in cluster.candidate_ids:
        candidate = candidates_by_id.get(cid)
        if candidate is None:
            continue
        ambiguity_flags = getattr(candidate, "ambiguity_flags", None) or []
        flags_text = ", ".join(str(flag) for flag in ambiguity_flags) if ambiguity_flags else "none"
        readiness_reason = getattr(candidate, "ballot_readiness_reason", None) or "none"
        lines.append(
            "- "
            f"[{candidate.stance}; actor={candidate.actor_scope}; mechanism={candidate.action_mechanism}; "
            f"target={candidate.target_scope}; readiness={candidate.ballot_readiness}; "
            f"reason={readiness_reason}; flags={flags_text}] "
            f"{candidate.title}: {candidate.summary}"
        )
    return "\n".join(lines) if lines else "(no submissions available)"


def _cluster_members(
    cluster: Cluster,
    candidates_by_id: Mapping[UUID, PolicyCandidate],
) -> list[PolicyCandidate]:
    return [candidates_by_id[cid] for cid in cluster.candidate_ids if cid in candidates_by_id]


def _dominant_member_value(members: list[PolicyCandidate], attr: str) -> str | None:
    counts = Counter(
        str(getattr(member, attr, "")).strip()
        for member in members
        if str(getattr(member, attr, "")).strip() not in {"", "unclear", "other", "neutral"}
    )
    if not counts:
        return None
    value, count = counts.most_common(1)[0]
    if count * 2 < len(members):
        return None
    return value


def _build_source_corpus(cluster: Cluster, members: list[PolicyCandidate]) -> str:
    parts = [cluster.policy_key, cluster.policy_topic]
    for member in members:
        parts.extend([
            str(getattr(member, "title", "")),
            str(getattr(member, "summary", "")),
            str(getattr(member, "ballot_readiness_reason", "")),
            " ".join(str(flag) for flag in (getattr(member, "ambiguity_flags", None) or [])),
            " ".join(str(entity) for entity in (getattr(member, "entities", None) or [])),
        ])
    return " ".join(part for part in parts if part).lower()


def _question_mentions_iran(source_corpus: str) -> bool:
    return " iran " in f" {source_corpus} " or "ایران" in source_corpus


def _fallback_ballot_wording(
    *,
    cluster: Cluster,
    members: list[PolicyCandidate],
) -> tuple[str, str, str]:
    dominant_mechanism = _dominant_member_value(members, "action_mechanism") or "unclear"
    dominant_target = _dominant_member_value(members, "target_scope")
    dominant_stance = _dominant_member_value(members, "stance")
    source_corpus = _build_source_corpus(cluster, members)
    mentions_iran = _question_mentions_iran(source_corpus)

    mechanism_en = _MECHANISM_LABELS_EN.get(dominant_mechanism, "this policy direction")
    mechanism_fa = _MECHANISM_LABELS_FA.get(dominant_mechanism, "این جهت‌گیری سیاستی")
    target_en = _TARGET_SUFFIXES_EN.get(dominant_target or "", "")
    target_fa = _TARGET_SUFFIXES_FA.get(dominant_target or "", "")
    if not target_en and mentions_iran:
        target_en = " related to Iran"
    if not target_fa and mentions_iran:
        target_fa = " مرتبط با ایران"

    readiness = "discussion-only"
    if any(member.ballot_readiness == "ballot-ready" for member in members):
        readiness = "ballot-ready"
    elif any(member.ballot_readiness == "needs-refinement" for member in members):
        readiness = "needs-refinement"

    if readiness == "discussion-only" or dominant_stance is None:
        return (
            f"Public discussion about {mechanism_en}{target_en}.",
            f"گفت‌وگوی عمومی درباره {mechanism_fa}{target_fa}.",
            f"Discussion about {mechanism_en}{target_en}.",
        )

    unresolved_en = ", with the exact scope still needing definition."
    unresolved_fa = "، با این‌که جزئیات دقیق آن هنوز باید روشن‌تر شود."
    if dominant_mechanism == "military-action" and (
        _dominant_member_value(members, "actor_scope") is None or dominant_target is None
    ):
        unresolved_en = (
            ", with the exact actor, objectives, and duration still needing definition."
        )
        unresolved_fa = "، با این‌که بازیگر دقیق، هدف‌ها و مدت آن هنوز باید روشن‌تر شود."

    if readiness == "needs-refinement":
        if dominant_stance == "oppose":
            return (
                f"Debate over whether to oppose {mechanism_en}{target_en}{unresolved_en}",
                f"بحث درباره مخالفت با {mechanism_fa}{target_fa}{unresolved_fa}",
                "Discussion of whether to oppose "
                f"{mechanism_en}{target_en} while key details remain unclear.",
            )
        return (
            f"Debate over whether to support {mechanism_en}{target_en}{unresolved_en}",
            f"بحث درباره حمایت از {mechanism_fa}{target_fa}{unresolved_fa}",
            "Discussion of whether to support "
            f"{mechanism_en}{target_en} while key details remain unclear.",
        )

    if dominant_stance == "oppose":
        return (
            f"Whether to oppose {mechanism_en}{target_en}.",
            f"مخالفت با {mechanism_fa}{target_fa}.",
            f"Debate over whether to oppose {mechanism_en}{target_en}.",
        )
    return (
        f"Whether to support {mechanism_en}{target_en}.",
        f"حمایت از {mechanism_fa}{target_fa}.",
        f"Debate over whether to support {mechanism_en}{target_en}.",
    )


def _tone_soften_ballot_wording(
    *,
    cluster: Cluster,
    members: list[PolicyCandidate],
    ballot_question: str,
    ballot_question_fa: str,
    summary: str,
) -> tuple[str, str, str]:
    if not any(member.ballot_readiness == "needs-refinement" for member in members):
        return ballot_question, ballot_question_fa, summary

    dominant_stance = _dominant_member_value(members, "stance")
    if dominant_stance not in {"support", "oppose"}:
        return ballot_question, ballot_question_fa, summary

    lower_question = ballot_question.lower()
    if lower_question.startswith("debate over whether") or lower_question.startswith("discussion of whether"):
        return ballot_question, ballot_question_fa, summary

    unresolved_suffix = ""
    question_parts = ballot_question.split(",", 1)
    if len(question_parts) == 2:
        unresolved_suffix = ", " + question_parts[1].strip()
    main_clause = question_parts[0].strip()

    if dominant_stance == "support":
        support_rewrites = (
            ("Whether to support ", "Debate over whether to support "),
            ("Support for ", "Debate over whether to support "),
            ("Support ", "Debate over whether to support "),
            ("Use ", "Debate over whether to use "),
            ("Apply ", "Debate over whether to apply "),
        )
        for prefix, replacement in support_rewrites:
            if main_clause.startswith(prefix):
                rewritten_core = (
                    f"{replacement[len('Debate over '):]}{main_clause[len(prefix):]}"
                ).rstrip(".")
                softened_question = f"{replacement}{main_clause[len(prefix):]}{unresolved_suffix}"
                softened_summary = (
                    f"Discussion of {rewritten_core} while key details remain unclear."
                )
                softened_fa = ballot_question_fa
                if ballot_question_fa.startswith("حمایت از"):
                    softened_fa = f"بحث درباره حمایت از {ballot_question_fa[len('حمایت از '):]}"
                elif ballot_question_fa.startswith("اعمال ") or ballot_question_fa.startswith(
                    "استفاده از"
                ):
                    softened_fa = f"بحث درباره {ballot_question_fa}"
                return softened_question, softened_fa, softened_summary
    else:
        oppose_rewrites = (
            ("Whether to oppose ", "Debate over whether to oppose "),
            ("Opposition to ", "Debate over whether to oppose "),
            ("Oppose ", "Debate over whether to oppose "),
        )
        for prefix, replacement in oppose_rewrites:
            if main_clause.startswith(prefix):
                rewritten_core = (
                    f"{replacement[len('Debate over '):]}{main_clause[len(prefix):]}"
                ).rstrip(".")
                softened_question = f"{replacement}{main_clause[len(prefix):]}{unresolved_suffix}"
                softened_summary = (
                    f"Discussion of {rewritten_core} while key details remain unclear."
                )
                softened_fa = ballot_question_fa
                if ballot_question_fa.startswith("مخالفت با"):
                    softened_fa = (
                        f"بحث درباره مخالفت با {ballot_question_fa[len('مخالفت با '):]}"
                    )
                return softened_question, softened_fa, softened_summary

    return ballot_question, ballot_question_fa, summary


def _sanitize_ballot_wording(
    *,
    cluster: Cluster,
    members: list[PolicyCandidate],
    parsed: dict[str, str],
) -> tuple[str, str, str, list[str]]:
    ballot_question = str(parsed.get("ballot_question", "")).strip()
    ballot_question_fa = str(parsed.get("ballot_question_fa", "")).strip()
    summary = str(parsed.get("summary", "")).strip() or cluster.summary
    validation_flags: list[str] = []

    source_corpus = _build_source_corpus(cluster, members)
    dominant_actor = _dominant_member_value(members, "actor_scope")
    dominant_target = _dominant_member_value(members, "target_scope")
    ballot_lower = ballot_question.lower()

    if dominant_actor is None:
        for pattern, message in _LOCAL_ACTOR_PATTERNS:
            if pattern.search(ballot_question) and not pattern.search(source_corpus):
                validation_flags.append(message)
    if dominant_target is None:
        for phrase in _UNANCHORED_TARGET_PHRASES:
            if phrase in ballot_lower and phrase not in source_corpus:
                validation_flags.append(
                    "Ballot wording introduced a specific target that is not grounded in the source submissions."
                )
                break

    if validation_flags:
        return (*_fallback_ballot_wording(cluster=cluster, members=members), validation_flags)
    softened_question, softened_question_fa, softened_summary = _tone_soften_ballot_wording(
        cluster=cluster,
        members=members,
        ballot_question=ballot_question,
        ballot_question_fa=ballot_question_fa,
        summary=summary,
    )
    return softened_question, softened_question_fa, softened_summary, validation_flags


async def generate_ballot_questions(
    *,
    session: AsyncSession,
    clusters: list[Cluster],
    candidates_by_id: Mapping[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> int:
    """Generate ballot questions for clusters that need (re-)summarization.

    Returns the number of clusters updated.
    """
    updated = 0
    for cluster in clusters:
        if not cluster.needs_resummarize:
            continue

        members = _cluster_members(cluster, candidates_by_id)
        submissions_block = _build_submissions_block(cluster, candidates_by_id)
        prompt = _PROMPT_TEMPLATE.format(
            policy_key=cluster.policy_key,
            member_count=cluster.member_count,
            submissions_block=submissions_block,
        )

        try:
            completion = await llm_router.complete(
                tier="english_reasoning",
                prompt=prompt,
                system_prompt=_SYSTEM_PROMPT,
                temperature=0.1,
            )
            parsed = _parse_ballot_response(completion.text)
        except Exception as exc:
            logger.exception(
                "Ballot question generation failed for cluster %s (%s)",
                cluster.id, cluster.policy_key,
            )
            await append_evidence(
                session=session,
                event_type="ballot_generation_failed",
                entity_type="cluster",
                entity_id=cluster.id,
                payload={
                    "cluster_id": str(cluster.id),
                    "policy_key": cluster.policy_key,
                    "error_type": type(exc).__name__,
                },
            )
            continue

        (
            cluster.ballot_question,
            cluster.ballot_question_fa,
            cluster.summary,
            validation_flags,
        ) = _sanitize_ballot_wording(cluster=cluster, members=members, parsed=parsed)
        cluster.last_summarized_count = cluster.member_count
        cluster.needs_resummarize = False

        await append_evidence(
            session=session,
            event_type="ballot_question_generated",
            entity_type="cluster",
            entity_id=cluster.id,
            payload={
                "policy_key": cluster.policy_key,
                "ballot_question": cluster.ballot_question,
                "validation_flags": validation_flags,
                "member_count": cluster.member_count,
                "model_version": completion.model,
            },
        )
        updated += 1

    await session.flush()
    return updated


def _parse_ballot_response(raw: str) -> dict[str, str]:
    text = raw.strip()
    if text.startswith("```"):
        nl = text.find("\n")
        last = text.rfind("```")
        text = text[nl + 1:last].strip()
    if text and text[0] != "{":
        start = text.find("{")
        if start != -1:
            text = text[start:]
    result: dict[str, str] = json.loads(text)
    return result
