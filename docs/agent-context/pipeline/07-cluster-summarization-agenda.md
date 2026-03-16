# Task: Cluster Summarization and Agenda Builder

## Depends on
- `pipeline/01-llm-abstraction` (complete() with english_reasoning tier)
- `pipeline/05-hdbscan-clustering` (clusters exist with member candidates)
- `database/03-core-models` (Cluster, PolicyCandidate, PolicyEndorsement models)
- `database/04-evidence-store` (append_evidence)

## Goal
Generate neutral concern/proposition wording for each cluster using the quality-first `english_reasoning` model, then build the voting agenda using a multi-stage gate: size threshold first, endorsement-signature threshold second, and ballot-readiness before final voting.

## Files

- `src/pipeline/endorsement.py` — neutral concern / proposition wording generation
- `src/pipeline/refinement.py` — autonomous proposition draft generation for non-ballot-ready clusters
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

### Wording prompt

```
You are writing neutral public-process wording for a group of related policy concerns from Iranian citizens.

The following policy positions were clustered together because they address similar concerns:

{aggregated_titles_and_summaries}

Write:
1. Neutral wording for the cluster that sounds like a real democratic process item
2. Agenda-setting language when the issue is still broad
3. Proposition-style language only when the issue is concrete enough for a ballot
4. A short summary suitable for concern lists

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

### Ballot-readiness gate

Agenda qualification is necessary but not sufficient for final voting. A cluster may only receive policy options and enter a `VotingCycle` when all member candidates are classified as `ballot-ready`. `discussion-only` and `needs-refinement` clusters can remain visible and collect endorsements, but they must not be surfaced as final ballot propositions.

### Autonomous refinement drafts

For clusters that are not yet `ballot-ready`, the scheduler may generate a cluster-level refinement artifact:

- `refinement_draft` / `refinement_draft_fa`: a proposed concrete proposition derived from the cluster
- `refinement_confidence`: how trustworthy the autonomous draft is
- `refinement_requires_clarification`: whether the draft is still too uncertain to trust without more input
- `refinement_notes`: short explanation of what is missing or why the draft is plausible

These drafts are website-visible and evidence-logged, but they do not automatically change candidate readiness or allow voting. They are a refinement aid, not a silent promotion to ballot status.

Only clusters with at least one `needs-refinement` member should trigger refinement draft generation. Pure `discussion-only` clusters remain visible as open civic discussion topics, but the scheduler should not manufacture proposition drafts for them.

### Auto-open voting cycles

After the agenda is built, `_maybe_open_cycle()` in `scheduler/main.py` automatically opens a `VotingCycle` when all conditions are met:
1. No active voting cycle exists
2. Cooldown period since last closed cycle has elapsed (`AUTO_CYCLE_COOLDOWN_HOURS`, default 1h)
3. At least one cluster with `status='open'` is vote-ready: qualifies by endorsement threshold, is ballot-ready, has neutral wording, and has policy options generated

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

### Policy Option Generation

After neutral wording generation, `src/pipeline/options.py` generates 2–4 distinct stance options per cluster using the LLM. This only runs for ballot-ready clusters.

### Public wording contract

Cluster wording must sound like public-facing civic text, not internal workflow text.

- `ballot-ready`: write direct proposition language describing what voters would decide
- `needs-refinement`: write a concise draftable civic prompt around the core proposition, with only brief mention of unresolved scope
- `discussion-only`: write a public discussion topic, not meta-process language

Avoid phrases like `move forward`, `structured discussion`, `public consideration`, `further refinement`, or `agenda-setting`.

```python
async def generate_policy_options(
    session: AsyncSession,
    clusters: list[Cluster],
    candidates_by_id: dict[UUID, PolicyCandidate],
    llm_router: LLMRouter,
) -> list[PolicyOption]:
```

Steps:
1. For each cluster, build a submissions block from ALL member candidates — full title, summary, stance, and semantic fields with no truncation
2. Call LLM with `tier="option_generation"` and a **conditional grounding decision**. Default is `grounding=False`; enable search only for configured research-heavy topics.
3. Parse JSON output, including salvage of fenced/wrapped JSON before escalating to another model.
4. If parsing still fails, explicitly retry the fallback model (`gpt-4o`) with the same grounding decision.
5. Create `PolicyOption` records linked to the cluster
6. Log `policy_options_generated` evidence event
7. On final LLM failure: fall back to generic Support/Oppose binary options with `model_version="fallback"`.

The options are used in the per-policy voting flow (see `messaging/08-message-commands`).

## Constraints

- Only aggregated/anonymized content is sent to the LLM. Never individual submissions or user data.
- Full candidate summaries are passed without truncation — the LLM sees the complete citizen input.
- Ballot inclusion uses combined support plus ballot-readiness. Broad concerns must not be silently upgraded into ballot items.
- Autonomous refinement drafts may be generated for broad concerns, but they remain advisory until the cluster itself becomes `ballot-ready`.
- Do not generate policy options for `discussion-only` or `needs-refinement` clusters.
- Small clusters (below threshold) are NOT deleted. They remain visible on the analytics dashboard but don't appear in the voting ballot.
- Summary generation must always have a fallback path configured for risk management (`english_reasoning_fallback_model`).
- Policy option generation must have a fallback path (generic support/oppose) so voting is never blocked by LLM failures.
- Web search grounding is conditional and config-backed; it is off by default to avoid prompt inflation and wrapper-heavy responses.
- Parser salvage should happen before model fallback so wrapper prose or fenced JSON does not trigger generic support/oppose output.
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
- Opens cycle when qualified ballot-ready clusters with wording + options exist and no active cycle
- Skips when active cycle already exists
- Respects cooldown period
- Skips when below endorsement threshold
- Skips when ballot question not generated
- Skips when policy options not generated

**Options (tests/test_pipeline/test_options.py):**
- `_parse_options_json()` handles valid JSON, markdown fences, leading prose + fenced JSON, truncation to 4, rejects < 2 options
- `_build_submissions_block()` formats candidates with stance + semantic labels, includes full summaries, includes all candidates
- `_fallback_options()` produces 2 generic support/oppose options
- `generate_policy_options()` defaults to `grounding=False` in tests
- `generate_policy_options()` retries explicit fallback model on parse failure while preserving the grounding decision
- `generate_policy_options()` creates PolicyOption records via LLM
- `generate_policy_options()` uses fallback on LLM error
- `PolicyOptionCreate` schema validation (rejects empty label, zero position)

**Refinement (tests/test_pipeline/test_refinement.py`, `tests/test_pipeline/test_scheduler.py`):**
- Non-ballot-ready clusters can receive autonomous proposition drafts
- Draft generation records evidence and stores confidence / clarification flags
- Scheduler only runs refinement for clusters that still need refinement
