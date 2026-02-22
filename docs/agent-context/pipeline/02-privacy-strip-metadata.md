# Task: Privacy — Strip Metadata for LLM

## Depends on
- `database/03-core-models` (Submission model)

## Goal
Implement the privacy boundary that prepares submission text for cloud LLM processing — stripping identifiers, redacting residual PII, and shuffling to prevent timing correlation.

## Files to create

- `src/pipeline/privacy.py` — metadata stripping and batch preparation

## Specification

### prepare_batch_for_llm()

```python
def prepare_batch_for_llm(
    submissions: list[Submission],
) -> tuple[list[str], dict[int, UUID]]:
    """
    Prepare submissions for cloud LLM processing.

    Returns:
        texts: list of anonymous text strings (shuffled)
        index_map: maps shuffled index -> submission_id (for re-linking results)
    """
```

Steps:
1. Extract only `raw_text` from each submission. Discard `user_id`, `created_at`, `id`, and all other metadata.
2. Apply residual PII redaction on text content (emails, phone numbers, national IDs, exact addresses where detectable).
3. Shuffle the list using `secrets.SystemRandom().shuffle()` (cryptographically secure shuffle).
4. Build an index map so results can be re-linked to submissions after LLM processing.
5. Return the shuffled texts and the index map.

### validate_no_metadata()

```python
def validate_no_metadata(texts: list[str], submissions: list[Submission]) -> bool:
    """
    Safety check: verify none of the texts contain user IDs, emails, or account refs.
    Returns True if clean, False if any identifier detected.
    """
```

Scan each text for patterns that look like:
- UUIDs (regex for UUID format)
- Email addresses
- Phone numbers (basic pattern)
- Account reference token patterns (if any app-specific prefix/pattern is used)

This is a safety net, not a guarantee. Primary protection is layered: intake PII gate (reject + resend prompt for high-risk content) plus this residual redaction pass before LLM.

### re_link_results()

```python
def re_link_results(
    results: list[T],
    index_map: dict[int, UUID],
) -> dict[UUID, T]:
    """Map LLM results back to submission IDs using the index map."""
```

## Constraints

- NEVER include `user_id`, `email`, `messaging_account_ref`, `created_at`, or `submission_id` in the text sent to cloud LLM.
- The shuffle must use a cryptographically secure random source (`secrets`), not `random.shuffle()`.
- The index map is the ONLY way to re-link results. It must be kept in memory only during processing, never persisted with the batch.
- This module is a hard privacy boundary. If in doubt, strip more rather than less.
- If residual PII cannot be safely redacted, mark for reject-and-resend workflow instead of forwarding text downstream.

## Tests

Write tests in `tests/test_pipeline/test_privacy.py` covering:
- `prepare_batch_for_llm()` returns only raw_text strings, no UUIDs in output
- Output list is shuffled (different order from input — test with large enough list that this is statistically certain)
- Index map correctly maps each shuffled position back to the original submission_id
- `re_link_results()` correctly maps results to submission IDs
- `validate_no_metadata()` returns True for clean text
- `validate_no_metadata()` returns False when text accidentally contains a UUID
- `validate_no_metadata()` returns False when text contains an email address
- Residual PII redaction masks detected PII before LLM batch output
- Unredactable high-risk PII path triggers reject-and-resend signal (no downstream forwarding)
- Empty input list handled gracefully (returns empty list and empty map)
- Single-item list works correctly
