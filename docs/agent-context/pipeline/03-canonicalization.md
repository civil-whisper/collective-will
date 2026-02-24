# Task: Canonicalization Agent

## Depends on
- `pipeline/01-llm-abstraction` (complete() with canonicalization tier)
- `pipeline/02-privacy-strip-metadata` (prepare_batch_for_llm)
- `database/03-core-models` (Submission, PolicyCandidate models)
- `database/04-evidence-store` (append_evidence)

## Goal
Implement the canonicalization agent that turns freeform text (any language) into structured English PolicyCandidate records using Claude Sonnet. Supports both inline (single-item) and batch processing. Detects and rejects garbage/non-policy submissions with user-language feedback.

## Files to create

- `src/pipeline/canonicalize.py` — canonicalization agent

## Specification

### Language rules

- **Canonical output** (`title`, `summary`, `entities`): always English, regardless of input language. Translate if necessary.
- **Rejection reason** (`rejection_reason`): always in the same language as the input, so the user can understand it.
- The LLM prompt instructs automatic input language detection.

### Validity assessment

Each canonicalization call evaluates whether the input is a valid civic/policy proposal:
- **Valid**: expresses a position, suggestion, or demand about governance, laws, rights, economy, or public affairs.
- **Invalid**: random text, greetings, personal questions, spam, platform questions, off-topic content.

The LLM returns `is_valid_policy` (bool) and `rejection_reason` (str or null) alongside canonical fields.

### canonicalize_single()

```python
async def canonicalize_single(
    submission: Submission,
    db: AsyncSession,
) -> PolicyCandidateCreate | CanonicalizationRejection:
```

Used by the intake handler for inline processing at submission time.

Steps:
1. Prepare the submission text (strip metadata/PII)
2. Call `complete()` with `tier="canonicalization"` and the canonicalization prompt
3. Parse LLM JSON response
4. If `is_valid_policy` is false: return `CanonicalizationRejection(rejection_reason=...)`
5. If valid: build and return `PolicyCandidateCreate` with all canonical fields
6. Set `model_version` and `prompt_version` on the result

### CanonicalizationRejection

```python
@dataclass
class CanonicalizationRejection:
    rejection_reason: str  # In the user's input language
```

### canonicalize_batch()

```python
async def canonicalize_batch(
    submissions: list[Submission],
    db: AsyncSession,
) -> list[PolicyCandidate]:
```

Used by the batch scheduler as a fallback for submissions that failed inline processing (`status="pending"`).

Steps:
1. Call `prepare_batch_for_llm(submissions)` to get anonymous texts + index map
2. For each text, call `complete()` with `tier="canonicalization"` and the canonicalization prompt
3. Parse LLM JSON response into PolicyCandidate fields
4. Filter out submissions where `is_valid_policy` is false (mark as `"rejected"`)
5. Handle multi-issue splitting: one submission may produce multiple candidates
6. Re-link results to submissions via index map
7. For each valid candidate:
   - Set `model_version` to the model name from LLMResponse
   - Set `prompt_version` to a hash of the prompt template
   - If `confidence < 0.7`, set submission status to `"flagged"`
8. Save PolicyCandidate records to database
9. Log `candidate_created` event to evidence store for each candidate
10. Return list of created candidates

### Prompt template

```
You are processing civic policy proposals for a democratic deliberation platform.
Citizens submit policy ideas in any language (often Farsi or English). Your job is
to determine whether the input is a valid civic/policy proposal and, if so, convert
it into canonical structured form. All canonical output (title, summary, entities)
must be in English regardless of the input language.

LANGUAGE RULES:
- Detect the input language automatically.
- title, summary, and entities MUST always be in English (translate if needed).
- rejection_reason MUST be in the SAME LANGUAGE as the input.

VALIDITY: A valid proposal expresses a position, suggestion, or demand about
governance, laws, rights, economy, or public affairs. Invalid inputs include:
random text, greetings, personal questions, spam, platform questions, or
off-topic content.

Required JSON fields:
  is_valid_policy (bool): true if valid civic/policy proposal, false otherwise,
  rejection_reason (str or null): if invalid, explain in the INPUT language,
  title (str, ENGLISH), domain (one of: ...domains...),
  summary (str, ENGLISH), stance (one of: ...stances...),
  entities (list of strings, ENGLISH), confidence (float 0-1),
  ambiguity_flags (list of strings).

If is_valid_policy is false, still fill title/summary/domain with best-effort
English values but set confidence to 0.
Return ONLY the raw JSON object, no markdown wrapping.
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
- For `canonicalize_single`: raise exception on failure so the intake handler can fall back to `status="pending"` for batch retry.

## Constraints

- NEVER send user IDs or metadata to the LLM. Only the anonymous text from `prepare_batch_for_llm()`.
- The prompt must NOT editorialize. It structures user input, it does not rewrite or reframe.
- Every candidate must have `model_version` and `prompt_version` set. These are required for audit reproducibility.
- Candidates with `confidence < 0.7` must be flagged. Do not silently accept low-confidence results.
- Validate output against a strict JSON schema before creating candidates; schema failures are treated as flagged responses.
- Canonicalization must request `tier="canonicalization"` only; do not reference provider-specific model IDs in this module.
- All canonical fields (`title`, `summary`, `entities`) must be in English regardless of input language.
- `rejection_reason` must be in the input language so user-facing rejection messages are understandable.

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
- `canonicalize_single` with valid submission returns `PolicyCandidateCreate`
- `canonicalize_single` with garbage submission returns `CanonicalizationRejection` with input-language reason
- `canonicalize_batch` filters out invalid submissions (marks them `"rejected"`)
