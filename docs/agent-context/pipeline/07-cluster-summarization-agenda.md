# Task: Cluster Summarization and Agenda Builder

## Depends on
- `pipeline/01-llm-abstraction` (complete() with english_reasoning tier)
- `pipeline/05-hdbscan-clustering` (clusters exist with member candidates)
- `database/03-core-models` (Cluster, PolicyCandidate, PolicyEndorsement models)
- `database/04-evidence-store` (append_evidence)

## Goal
Generate human-readable summaries for each cluster using the quality-first `english_reasoning` model (v0 default: Claude Sonnet), then build the voting agenda using a multi-stage gate: size threshold first, endorsement-signature threshold second.

## Files

- `src/pipeline/endorsement.py` — ballot question generation (replaced legacy `summarize.py`)
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
def build_agenda(
    *,
    clusters: list[Cluster],
    endorsement_counts: dict[str, int],
    min_support: int,
) -> list[AgendaItem]:
    """Build the voting agenda using a single combined gate."""
```

Qualification formula: `total_support = member_count + endorsement_count >= min_support`.
Submissions count as implicit endorsements. `min_support` defaults to 5 (`MIN_PREBALLOT_ENDORSEMENTS`).

### Auto-open voting cycles

After the agenda is built, `_maybe_open_cycle()` in `scheduler/main.py` automatically opens a `VotingCycle` when all conditions are met:
1. No active voting cycle exists
2. Cooldown period since last closed cycle has elapsed (`AUTO_CYCLE_COOLDOWN_HOURS`, default 1h)
3. At least one cluster with `status='open'` is vote-ready: qualifies by endorsement threshold AND has a ballot question AND has policy options generated

When a cycle opens, `open_cycle()` sets all included clusters to `status='archived'`. This prevents re-voting on the same policies and frees up the `policy_key` for new submissions to create a fresh cluster on the same topic.

The function runs in both the early-return (no submissions) and full pipeline paths, so cycles open even when no new submissions are pending.

**Important**: Both `_close_expired_cycles` and `_maybe_open_cycle` also run in the **60-second polling loop** inside `scheduler_loop`, not just inside `run_pipeline`. This ensures cycles close promptly (within ~60s of `ends_at`) regardless of submission activity — the full pipeline may only run every 6 hours on production.

### Cluster lifecycle

Clusters have a `status` field with two states:
- **`open`** — actively collecting submissions and endorsements. The pipeline processes only open clusters (summarization, ballot questions, options, agenda, normalization, key merges). The Telegram endorsement flow also only shows open clusters.
- **`archived`** — included in a voting cycle and frozen. New submissions with the same `policy_key` create a fresh `open` cluster. Archived clusters remain visible on the website in a separate "Archived Concerns" section.

A partial unique index on `policy_key` (`WHERE status = 'open'`) ensures only one open cluster per policy key, while allowing multiple archived clusters with the same key.

### Cycle timing visibility

When a voting cycle is active:
- **Telegram**: The bot sends a timing header (`cycle_timing` message) showing policy count and time remaining before presenting the ballot.
- **Website**: The Collective Concerns page shows a green banner with policy count and end time via `GET /analytics/stats` → `active_cycle` field (includes `started_at`, `ends_at`, `cluster_count`).

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
- Ballot inclusion uses a single combined gate: `total_support = member_count + endorsements >= min_support`. No editorial filtering beyond this gate.
- Small clusters (below threshold) are NOT deleted. They remain visible on the analytics dashboard but don't appear in the voting ballot.
- Summary generation must always have a fallback path configured for risk management (`english_reasoning_fallback_model`).
- Policy option generation must have a fallback path (generic support/oppose) so voting is never blocked by LLM failures.
- Web search grounding (`grounding=True`) is only applied when the provider supports it (currently Gemini). Non-Google fallback models run without grounding automatically.
- Keep provider/model choice behind config-backed tiers only; these modules must not hardcode provider model IDs.

## Tests

Tests in `tests/test_pipeline/test_endorsement.py`, `tests/test_pipeline/test_agenda.py`, and `tests/test_pipeline/test_options.py` covering:

**Ballot question generation (tests/test_pipeline/test_endorsement.py):**
- Ballot response JSON parsing (plain, markdown-wrapped, leading text)
- Bilingual ballot question fields extracted correctly

**Agenda:**
- Clusters with `total_support >= min_support` included in agenda
- Clusters below threshold excluded
- Empty cluster set returns empty agenda
- All qualifying clusters included (no editorial filtering)

**Auto-cycle opening (tests/test_pipeline/test_scheduler.py):**
- Opens cycle when qualified clusters with ballot questions + options exist and no active cycle
- Skips when active cycle already exists
- Respects cooldown period
- Skips when below endorsement threshold
- Skips when ballot question not generated
- Skips when policy options not generated

**Options (tests/test_pipeline/test_options.py):**
- `_parse_options_json()` handles valid JSON, markdown fences, truncation to 4, rejects < 2 options
- `_build_submissions_block()` formats candidates with stance labels, includes full summaries, includes all candidates
- `_fallback_options()` produces 2 generic support/oppose options
- `generate_policy_options()` calls with `tier="option_generation"` and `grounding=True`
- `generate_policy_options()` creates PolicyOption records via LLM
- `generate_policy_options()` uses fallback on LLM error
- `PolicyOptionCreate` schema validation (rejects empty label, zero position)
