from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate, PolicyDomain
from src.pipeline.llm import LLMRouter


def determine_cluster_domain(candidates: list[PolicyCandidate]) -> PolicyDomain:
    if not candidates:
        return PolicyDomain.OTHER
    return Counter([candidate.domain for candidate in candidates]).most_common(1)[0][0]


async def summarize_clusters(
    *,
    session: AsyncSession,
    clusters: list[Cluster],
    candidates_by_id: Mapping[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> list[Cluster]:
    for cluster in clusters:
        candidates = [
            candidates_by_id[candidate_id]
            for candidate_id in cluster.candidate_ids
            if candidate_id in candidates_by_id
        ]
        prompt = (
            "Summarize these policy statements into concise Farsi and English JSON with keys "
            "summary and summary_en.\n"
            + "\n".join(f"- {candidate.title}: {candidate.summary}" for candidate in candidates[:20])
        )
        completion = await llm_router.complete(tier="english_reasoning", prompt=prompt)
        text = completion.text.strip()
        if '"summary"' in text and '"summary_en"' in text:
            cluster.summary = text
            cluster.summary_en = text
        else:
            cluster.summary = text[:500]
            cluster.summary_en = text[:500]
        cluster.domain = determine_cluster_domain(candidates)
        await append_evidence(
            session=session,
            event_type="cluster_updated",
            entity_type="cluster",
            entity_id=cluster.id,
            payload={"summary": cluster.summary, "model_version": completion.model},
        )
    await session.flush()
    return clusters
