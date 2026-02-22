# Task: Canonicalization Agent

## Depends on
- `pipeline/01-llm-abstraction` (complete() with canonicalization tier)
- `pipeline/02-privacy-strip-metadata` (prepare_batch_for_llm)
- `database/03-core-models` (Submission, PolicyCandidate models)
- `database/04-evidence-store` (append_evidence)

## Goal
Implement the canonicalization agent that turns freeform Farsi text into structured PolicyCandidate records using Claude Sonnet.

## Files to create

- `src/pipeline/canonicalize.py` — canonicalization agent

## Specification

### canonicalize_batch()

```python
async def canonicalize_batch(
    submissions: list[Submission],
    db: AsyncSession,
) -> list[PolicyCandidate]:
```

Steps:
1. Call `prepare_batch_for_llm(submissions)` to get anonymous texts + index map
2. For each text, call `complete()` with `tier="canonicalization"` and the canonicalization prompt
3. Parse LLM JSON response into PolicyCandidate fields
4. Handle multi-issue splitting: one submission may produce multiple candidates
5. Re-link results to submissions via index map
6. For each candidate:
   - Set `model_version` to the model name from LLMResponse
   - Set `prompt_version` to a hash of the prompt template (version the prompt)
   - If `confidence < 0.7`, set submission status to `"flagged"`
7. Save PolicyCandidate records to database
8. Log `candidate_created` event to evidence store for each candidate
9. Return list of created candidates

### Prompt template

```
You are a policy structuring assistant. Given a user's freeform concern,
extract structured policy positions WITHOUT editorializing.

Rules:
- Preserve the user's intent exactly
- Do not add opinions or framing
- If the message contains multiple distinct concerns, output multiple candidates
- Flag uncertainty rather than guessing
- Output in English (translate from Farsi if needed)

Output JSON array, each element:
{
  "title": "5-15 word title",
  "domain": "governance|economy|rights|foreign_policy|religion|ethnic|justice|other",
  "summary": "1-3 sentence summary in English",
  "stance": "support|oppose|neutral|unclear",
  "entities": ["named entities mentioned"],
  "confidence": 0.0-1.0,
  "ambiguity_flags": ["sarcasm_possible", "multi_issue", etc.]
}
```

### Prompt versioning

Hash the prompt template to create a version string:

```python
PROMPT_TEMPLATE = "..."  # The full prompt above
PROMPT_VERSION = hashlib.sha256(PROMPT_TEMPLATE.encode()).hexdigest()[:12]
```

Store this with every candidate for reproducibility.

### Error handling

- If LLM returns unparseable JSON: flag submission as `"flagged"`, log error, continue with next
- If LLM returns empty result: flag submission, log
- Do not let one bad response stop the entire batch
- If Sonnet is unavailable after retries, use the canonicalization fallback model configured in the LLM abstraction (`canonicalization_fallback_model`); mark these candidates with a fallback flag for later review.

## Constraints

- NEVER send user IDs or metadata to the LLM. Only the anonymous text from `prepare_batch_for_llm()`.
- The prompt must NOT editorialize. It structures user input, it does not rewrite or reframe.
- Every candidate must have `model_version` and `prompt_version` set. These are required for audit reproducibility.
- Candidates with `confidence < 0.7` must be flagged. Do not silently accept low-confidence results.
- Validate output against a strict JSON schema before creating candidates; schema failures are treated as flagged responses.
- Canonicalization must request `tier="canonicalization"` only; do not reference provider-specific model IDs in this module.

## Tests

Write tests in `tests/test_pipeline/test_canonicalize.py` covering:
- Single-issue input produces one PolicyCandidate with correct fields (mock LLM response)
- Multi-issue input produces multiple candidates (mock LLM returning array of 2+)
- Low-confidence candidate (< 0.7) flags the submission
- LLM returning invalid JSON: submission flagged, no crash, batch continues
- LLM returning empty result: submission flagged
- `model_version` and `prompt_version` are set on every candidate
- `prompt_version` changes when prompt template changes
- Evidence logged for each candidate_created event
- Privacy: verify that the text sent to LLM (mock) contains no UUIDs or user references
- PolicyDomain enum: valid domain strings accepted, invalid rejected
