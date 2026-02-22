from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.submission import PolicyCandidate
from src.pipeline.llm import LLMRouter


def prepare_text_for_embedding(*, title: str, summary: str) -> str:
    return f"{title.strip()}\n\n{summary.strip()}"


async def compute_and_store_embeddings(
    *,
    session: AsyncSession,
    candidates: list[PolicyCandidate],
    llm_router: LLMRouter,
    batch_size: int = 64,
) -> int:
    pending = [candidate for candidate in candidates if candidate.embedding is None]
    updated = 0
    for idx in range(0, len(pending), batch_size):
        batch = pending[idx : idx + batch_size]
        texts = [prepare_text_for_embedding(title=item.title, summary=item.summary) for item in batch]
        result = await llm_router.embed(texts)
        for candidate, vector in zip(batch, result.vectors, strict=True):
            candidate.embedding = vector
            updated += 1
    await session.flush()
    return updated
