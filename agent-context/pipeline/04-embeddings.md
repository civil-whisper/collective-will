# Task: Embedding Computation

## Depends on
- `pipeline/01-llm-abstraction` (embed() function)
- `database/03-core-models` (PolicyCandidate model with pgvector column)

## Goal
Compute semantic embeddings for PolicyCandidates via the configured embedding model (quality-first in v0) and store them in the pgvector column.

## Files to create

- `src/pipeline/embeddings.py` — embedding computation and storage

## Specification

### compute_and_store_embeddings()

```python
async def compute_and_store_embeddings(
    candidates: list[PolicyCandidate],
    db: AsyncSession,
) -> int:  # Returns number of candidates updated
```

Steps:
1. Filter to candidates that don't have embeddings yet (`embedding IS NULL`)
2. Extract the canonicalized text for each (use `summary` or `title + summary` as the text to embed)
3. Call `embed()` from the LLM abstraction with the texts
4. Store the returned vectors in each candidate's `embedding` column
5. Save to database
6. Return count of candidates updated

### Batch handling

- Embedding providers have batch limits; use the limit for the currently selected provider/model
- Split large candidate lists into sub-batches
- Process sub-batches sequentially to respect rate limits

### Text preparation for embedding

Use the English canonicalized text (not the raw Farsi submission):

```python
def prepare_text_for_embedding(candidate: PolicyCandidate) -> str:
    """Combine title and summary for richer embedding."""
    return f"{candidate.title}. {candidate.summary}"
```

### Retry logic

- If the primary embedding provider returns an error for a batch, retry that batch (up to 3 times)
- If retries fail and `embedding_fallback_model` is configured, retry the batch once via fallback model/provider
- If a batch permanently fails, log the error and skip those candidates (don't block the rest)
- Failed candidates should be retried on the next pipeline run

## Constraints

- Only embed the canonicalized English text, NOT the raw Farsi submission. The raw text should never leave the local system.
- Embeddings are stored in the pgvector column on policy_candidates. Vector dimension must match the active embedding model; do not hardcode model-specific dimensions in this module.
- Do not re-compute embeddings for candidates that already have them.

## Tests

Write tests in `tests/test_pipeline/test_embeddings.py` covering:
- Candidates without embeddings get embeddings computed and stored (mock primary embedding API)
- Candidates with existing embeddings are skipped
- Batch splitting: 100 candidates correctly split into sub-batches
- Stored embedding dimension matches the configured model expectation
- Embedding can be retrieved from database and has correct length
- API error on one batch doesn't block processing of other batches
- Primary embedding failure triggers fallback model when configured
- Empty candidate list handled gracefully (returns 0)
- `prepare_text_for_embedding()` combines title and summary correctly
