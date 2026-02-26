# Task: Cluster Summarization and Agenda Builder

## Depends on
- `pipeline/01-llm-abstraction` (complete() with english_reasoning tier)
- `pipeline/05-hdbscan-clustering` (clusters exist with member candidates)
- `database/03-core-models` (Cluster, PolicyCandidate, PolicyEndorsement models)
- `database/04-evidence-store` (append_evidence)

## Goal
Generate human-readable summaries for each cluster using the quality-first `english_reasoning` model (v0 default: Claude Sonnet), then build the voting agenda using a multi-stage gate: size threshold first, endorsement-signature threshold second.

## Files to create

- `src/pipeline/summarize.py` — cluster summarization
- `src/pipeline/agenda.py` — agenda builder

## Specification

### summarize_clusters()

```python
async def summarize_clusters(
    clusters: list[Cluster],
    db: AsyncSession,
) -> list[Cluster]:
    """Generate summaries for clusters that don't have one yet."""
```

Steps:
1. For each cluster without a summary:
   - Load member PolicyCandidates
   - Prepare aggregated content: combine all member titles and summaries into one text block
   - Do NOT include individual submission IDs, user references, or metadata
   - Call `complete()` with `tier="english_reasoning"` and summarization prompt
   - Parse response into `summary` (English)
   - If primary `english_reasoning` model fails after retries, use mandatory fallback (`english_reasoning_fallback_model`) and mark output with fallback metadata for audit/review
2. Update cluster records with summaries
3. Return updated clusters

### Summarization prompt

```
You are summarizing a group of related policy concerns from Iranian citizens.

The following policy positions were clustered together because they address similar concerns:

{aggregated_titles_and_summaries}

Write:
1. A concise summary (2-3 sentences) in Farsi that represents what this group collectively wants
2. An English translation of the same summary
3. A brief explanation (1 sentence) of why these items were grouped together

Output JSON:
{
  "summary": "...",
  "grouping_rationale": "..."
}
```

### build_agenda()

```python
async def build_agenda(
    cycle_id: UUID,
    db: AsyncSession,
    min_size: int = 5,
    min_endorsements: int = 5,
) -> list[UUID]:
    """Select clusters for voting. Returns list of cluster IDs."""
```

Steps:
1. Load all clusters for this cycle
2. Filter to clusters with `member_count >= min_size`
3. For remaining clusters, count distinct `PolicyEndorsement.user_id` signatures on each cluster
4. Keep only clusters with endorsement_count >= `min_endorsements`
5. Include ALL qualifying clusters — no editorial selection, no ranking, no filtering by topic
6. Log agenda-preparation evidence with qualifying/disqualified counts (the actual cycle_opened event is logged by the voting service)
7. Return the list of qualifying cluster IDs

### Policy Option Generation (post-summarization)

After cluster summarization, `src/pipeline/options.py` generates 2–4 distinct stance options per cluster using the LLM. This is called in the scheduler pipeline after `summarize_clusters()`.

```python
async def generate_policy_options(
    session: AsyncSession,
    clusters: list[Cluster],
    candidates_by_id: dict[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> list[PolicyOption]:
```

Steps:
1. For each cluster, build a submissions block from ALL member candidates — full title, summary, and stance with no truncation
2. Call LLM with `tier="option_generation"` and `grounding=True` to generate 2–4 stance options with bilingual labels and descriptions. The primary model (Gemini Flash) uses Google Search to research real-world policy positions.
3. Parse JSON output, validate 2–4 options with required fields (label, label_en, description, description_en)
4. Create `PolicyOption` records linked to the cluster
5. Log `policy_options_generated` evidence event
6. On LLM failure: fall back to generic Support/Oppose binary options with `model_version="fallback"`. The fallback model (Claude Sonnet) runs without web search.

The options are used in the per-policy voting flow (see `messaging/08-message-commands`).

## Constraints

- Only aggregated/anonymized content is sent to the LLM. Never individual submissions or user data.
- Full candidate summaries are passed without truncation — the LLM sees the complete citizen input.
- Ballot inclusion requires BOTH gates: size threshold and endorsement-signature threshold. No editorial filtering beyond these gates.
- Small clusters (below threshold) are NOT deleted. They remain visible on the analytics dashboard but don't appear in the voting ballot.
- Summary generation must always have a fallback path configured for risk management (`english_reasoning_fallback_model`).
- Policy option generation must have a fallback path (generic support/oppose) so voting is never blocked by LLM failures.
- Web search grounding (`grounding=True`) is only applied when the provider supports it (currently Gemini). Non-Google fallback models run without grounding automatically.
- Keep provider/model choice behind config-backed tiers only; these modules must not hardcode provider model IDs.

## Tests

Tests in `tests/test_pipeline/test_summarize.py`, `tests/test_pipeline/test_agenda.py`, and `tests/test_pipeline/test_options.py` covering:

**Summarization:**
- Cluster with members gets a summary generated (mock LLM response)
- Cluster that already has a summary is skipped
- Aggregated text sent to LLM contains member titles/summaries but no user IDs (mock, inspect prompt)
- LLM returning invalid JSON: cluster flagged, no crash
- Summary stored in English (the canonical language)
- Primary summary model failure triggers configured fallback model path

**Agenda:**
- Clusters with member_count >= 5 and endorsements >= threshold included in agenda
- Clusters with member_count < 5 excluded
- Clusters meeting size but missing endorsement threshold are excluded from ballot
- Empty cluster set returns empty agenda
- All qualifying clusters included (no filtering beyond size + endorsements)
- Cluster inherits `policy_topic` from its candidates

**Options (tests/test_pipeline/test_options.py):**
- `_parse_options_json()` handles valid JSON, markdown fences, truncation to 4, rejects < 2 options
- `_build_submissions_block()` formats candidates with stance labels, includes full summaries, includes all candidates
- `_fallback_options()` produces 2 generic support/oppose options
- `generate_policy_options()` calls with `tier="option_generation"` and `grounding=True`
- `generate_policy_options()` creates PolicyOption records via LLM
- `generate_policy_options()` uses fallback on LLM error
- `PolicyOptionCreate` schema validation (rejects empty label, zero position)
