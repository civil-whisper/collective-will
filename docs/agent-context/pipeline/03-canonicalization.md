# Task: Canonicalization Agent

## Depends on
- `pipeline/01-llm-abstraction` (complete() with canonicalization tier)
- `pipeline/02-privacy-strip-metadata` (prepare_batch_for_llm)
- `database/03-core-models` (Submission, PolicyCandidate models)
- `database/04-evidence-store` (append_evidence)

## Goal
Implement the canonicalization agent that turns freeform text (any language) into structured English `PolicyCandidate` records using the `canonicalization` tier. Supports both inline (single-item) and batch processing. Detects and rejects garbage/non-policy submissions with user-language feedback. Canonicalization must also preserve semantic identity so different actors/mechanisms do not collapse into the same ballot proposition.

## Files to create

- `src/pipeline/canonicalize.py` — canonicalization agent

## Specification

### Language rules

- **Canonical output** (`title`, `summary`, `entities`, `policy_key`, semantic fields): always English, regardless of input language. Translate if necessary.
- **Rejection reason** (`rejection_reason`): always in the same language as the input, so the user can understand it.
- The LLM prompt instructs automatic input language detection.

### Semantic identity fields

Each valid candidate must include:

- `policy_key`: ballot-level proposition identity. This is the main grouping key.
- `policy_topic`: optional browsing/UI label only. It must not drive grouping/merge logic.
- `actor_scope`: who primarily acts or applies pressure.
- `action_mechanism`: how the policy works.
- `target_scope`: what the action primarily targets.
- `ballot_readiness`: one of `ballot-ready`, `needs-refinement`, `discussion-only`.
- `ballot_readiness_reason`: short explanation for the readiness classification.

These fields exist to preserve distinctions like domestic strikes vs foreign sanctions vs military intervention even when they share a broad political goal.

### Validity assessment

Each canonicalization call evaluates whether the input relates to a civic/policy topic:
- **Valid**: anything relating to governance, laws, rights, economy, foreign policy, or public affairs. This includes direct positions ("We should do X"), questions about policy topics ("What should happen with X?"), and expressions of concern or interest ("I'm worried about X"). All of these identify a policy topic citizens care about and will cluster together.
- **Invalid**: random text, greetings, purely personal matters unrelated to public policy, spam, platform questions ("how does this bot work?"), off-topic content.

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
4. If parsing fails, attempt local repair for common malformed JSON patterns (for example key/value comma typos or trailing commas)
5. If local repair still fails, make one JSON-repair pass through the `canonicalization` tier and parse that result
6. If parsing still fails after repair: raise so the intake handler can fall back to pending/batch retry
7. If `is_valid_policy` is false: return `CanonicalizationRejection(rejection_reason=...)`
8. If valid: build and return `PolicyCandidateCreate` with all canonical fields
9. Set `model_version` and `prompt_version` on the result

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
3. Parse LLM JSON response into PolicyCandidate fields, with the same local-repair then one-shot JSON-repair fallback used by `canonicalize_single()`
4. Filter out submissions where `is_valid_policy` is false (mark as `"rejected"`)
5. Handle multi-issue splitting: one submission may produce multiple candidates
6. Re-link results to submissions via index map
7. For each valid candidate:
   - Set `model_version` to the model name from LLMResponse
   - Set `prompt_version` to a hash of the prompt template
   - If `confidence < 0.7`, set submission status to `"flagged"`
8. Save `PolicyCandidate` records to database
9. Log `candidate_created` and `candidate_classified` evidence for each candidate
10. Return list of created candidates

### Prompt template

```
You are processing civic submissions for a democratic deliberation platform.
Citizens submit policy ideas, concerns, or questions in any language (often Farsi
or English). Your job is to determine whether the input relates to a civic or
policy topic and, if so, convert it into canonical structured form. All canonical
output (title, summary, entities) must be in English regardless of the input language.

LANGUAGE RULES:
- Detect the input language automatically.
- title, summary, entities, policy_key, policy_topic, actor_scope, action_mechanism, target_scope, ballot_readiness, and ballot_readiness_reason MUST always be in English (translate if needed).
- rejection_reason MUST be in the SAME LANGUAGE as the input.

VALIDITY: A valid submission is anything that relates to governance, laws,
rights, economy, foreign policy, or public affairs. This includes:
- Direct positions, suggestions, or demands ('We should do X')
- Questions or concerns about a policy topic ('What should happen with X?')
- Expressions of worry or interest in a public issue ('I'm concerned about X')
All of these are valid because they identify a policy topic citizens care about.
Invalid inputs include: random text, greetings, purely personal matters unrelated
to public policy, spam, platform questions ('how does this bot work?'), or
completely off-topic content.

Required JSON fields:
  is_valid_policy (bool): true if valid civic/policy proposal, false otherwise,
  rejection_reason (str or null): if invalid, explain in the INPUT language,
  title (str, ENGLISH),
  summary (str, ENGLISH), stance (one of: ...stances...),
  policy_key (str, ENGLISH, lowercase-with-hyphens),
  policy_topic (str, ENGLISH, lowercase-with-hyphens, UI/browsing label only),
  actor_scope (str, ENGLISH),
  action_mechanism (str, ENGLISH),
  target_scope (str, ENGLISH),
  ballot_readiness (str, ENGLISH),
  ballot_readiness_reason (str, ENGLISH),
  entities (list of strings, ENGLISH), confidence (float 0-1),
  ambiguity_flags (list of strings).

If is_valid_policy is false, still fill title/summary with best-effort
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

- If LLM returns malformed JSON: first try local parser repair, then one strict JSON-repair LLM pass. Both repair methods emit a `candidate_parse_repaired` evidence event with the repair method (`regex` or `llm`).
- If the repaired payload is still unparseable: flag submission as `"flagged"` in batch mode, or raise in `canonicalize_single()` so intake can fall back to pending processing
- If LLM returns empty result: flag submission, log
- Do not let one bad response stop the entire batch
- If Sonnet is unavailable after retries, use the canonicalization fallback model configured in the LLM abstraction (`canonicalization_fallback_model`); mark these candidates with a fallback flag for later review.
- For `canonicalize_single`: raise exception on failure so the intake handler can fall back to `status="pending"` for batch retry.

## Constraints

- NEVER send user IDs or metadata to the LLM. Only the anonymous text from `prepare_batch_for_llm()`.
- The prompt must NOT editorialize. It structures user input, it does not rewrite or reframe.
- Reuse an existing `policy_key` only when actor, mechanism, and target materially match.
- `policy_topic` is display metadata only. Do not rely on it for algorithmic identity.
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
- LLM returning invalid JSON: common syntax errors are repaired locally when possible; otherwise the repair pass is used and batch continues
- LLM returning empty result: submission flagged
- `model_version` and `prompt_version` are set on every candidate
- `prompt_version` changes when prompt template changes
- Evidence logged for each `candidate_created` / `candidate_classified` event
- Privacy: verify that the text sent to LLM (mock) contains no UUIDs or user references
- `policy_topic`, `policy_key`, semantic fields, and ballot readiness are assigned from LLM output
- `canonicalize_single` with valid submission returns `PolicyCandidateCreate`
- `canonicalize_single` with garbage submission returns `CanonicalizationRejection` with input-language reason
- `canonicalize_batch` filters out invalid submissions (marks them `"rejected"`)
