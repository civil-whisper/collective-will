from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from src.pipeline.embeddings import compute_and_store_embeddings, prepare_text_for_embedding
from src.pipeline.llm import EmbeddingResult


@dataclass
class FakeCandidate:
    id: UUID
    title: str
    summary: str
    embedding: list[float] | None = None


class FakeRouter:
    def __init__(self, *, fail_primary: bool = False) -> None:
        self.call_count = 0
        self._fail_primary = fail_primary

    async def embed(self, texts: list[str], timeout_s: float = 60.0) -> EmbeddingResult:
        self.call_count += 1
        if self._fail_primary and self.call_count == 1:
            raise RuntimeError("primary down")
        return EmbeddingResult(vectors=[[0.1] * 10 for _ in texts], model="text-embedding-3-large", provider="openai")


def test_prepare_text_for_embedding() -> None:
    result = prepare_text_for_embedding(title="Housing Reform", summary="Build affordable housing.")
    assert "Housing Reform" in result
    assert "Build affordable housing." in result


@pytest.mark.asyncio
async def test_candidates_without_embeddings_get_computed() -> None:
    class AsyncSession:
        async def flush(self) -> None:
            pass

    candidates = [FakeCandidate(id=uuid4(), title="A", summary="B")]
    router = FakeRouter()
    count = await compute_and_store_embeddings(
        session=AsyncSession(), candidates=candidates, llm_router=router  # type: ignore[arg-type]
    )
    assert count == 1
    assert candidates[0].embedding is not None
    assert len(candidates[0].embedding) == 10


@pytest.mark.asyncio
async def test_candidates_with_existing_embeddings_skipped() -> None:
    class AsyncSession:
        async def flush(self) -> None:
            pass

    candidates = [FakeCandidate(id=uuid4(), title="A", summary="B", embedding=[1.0] * 10)]
    router = FakeRouter()
    count = await compute_and_store_embeddings(
        session=AsyncSession(), candidates=candidates, llm_router=router  # type: ignore[arg-type]
    )
    assert count == 0
    assert router.call_count == 0


@pytest.mark.asyncio
async def test_empty_candidate_list() -> None:
    class AsyncSession:
        async def flush(self) -> None:
            pass

    router = FakeRouter()
    count = await compute_and_store_embeddings(
        session=AsyncSession(), candidates=[], llm_router=router  # type: ignore[arg-type]
    )
    assert count == 0


@pytest.mark.asyncio
async def test_batch_splitting() -> None:
    class AsyncSession:
        async def flush(self) -> None:
            pass

    candidates = [FakeCandidate(id=uuid4(), title=f"T{i}", summary=f"S{i}") for i in range(100)]
    router = FakeRouter()
    count = await compute_and_store_embeddings(
        session=AsyncSession(), candidates=candidates, llm_router=router, batch_size=30  # type: ignore[arg-type]
    )
    assert count == 100
    assert router.call_count == 4  # ceil(100/30) = 4
