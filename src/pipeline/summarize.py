from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.db.evidence import append_evidence
from src.models.cluster import Cluster
from src.models.submission import PolicyCandidate
from src.pipeline.llm import LLMRouter


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
            "Summarize these policy statements into a concise English summary.\n"
            + "\n".join(f"- {candidate.title}: {candidate.summary}" for candidate in candidates[:20])
        )
        completion = await llm_router.complete(tier="english_reasoning", prompt=prompt)
        text = completion.text.strip()
        cluster.summary = text[:500]
        await append_evidence(
            session=session,
            event_type="cluster_updated",
            entity_type="cluster",
            entity_id=cluster.id,
            payload={
                "summary": cluster.summary,
                "member_count": len(cluster.candidate_ids),
                "candidate_ids": [str(cid) for cid in cluster.candidate_ids],
                "model_version": completion.model,
            },
        )
    await session.flush()
    return clusters
