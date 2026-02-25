# Task: Policy-Key Grouping (replaces HDBSCAN as primary)

## Depends on
- `pipeline/03-canonicalization` (candidates have `policy_topic` and `policy_key`)
- `pipeline/04-embeddings` (candidates have embedding vectors for validation)
- `database/03-core-models` (Cluster, PolicyCandidate models)

## Goal

Group policy candidates by their LLM-assigned `policy_key`. Each unique
`policy_key` maps to one persistent `Cluster` record. This replaces HDBSCAN
as the primary grouping mechanism.

## Two-Level Policy Structure

- **`policy_topic`**: Stance-neutral umbrella for browsing (e.g., `internet-censorship`).
  Groups related ballot items together in the UI.
- **`policy_key`**: Stance-neutral ballot-level discussion (e.g., `political-internet-censorship`).
  This is what forms clusters and goes to vote. Specific enough that 2–4 ballot
  options can cover the full discussion.

Both are lowercase-with-hyphens, assigned by the LLM at canonicalization time.

## Pipeline Stages

### Stage 1 — Context-Aware Assignment (Inline)

At canonicalization time (`canonicalize.py`), the LLM sees existing `policy_topic`s
and `policy_key`s loaded from the `clusters` table. This context-aware prompt
maximizes reuse of existing keys.

### Stage 2 — Key Normalization (Batch)

Periodically (`normalize.py`), for each `policy_topic` with multiple keys, an LLM
reviews all keys and merges near-duplicates. Example: `political-internet-censorship`
and `political-internet-filtering` would be merged.

### Stage 3 — Ballot Question Generation (Batch)

For clusters that need (re)summarization (`endorsement.py`), the LLM generates a
stance-neutral ballot question from member submissions. This is the question shown
in the endorsement step ("Should this topic appear on the ballot?").

## Files

- `src/pipeline/cluster.py` — `group_by_policy_key()`, `compute_centroid()`, legacy `run_clustering()`
- `src/pipeline/normalize.py` — `normalize_policy_keys()`, `execute_key_merge()`
- `src/pipeline/endorsement.py` — `generate_ballot_questions()`

## Specification

### group_by_policy_key()

```python
def group_by_policy_key(
    *, candidates: list[PolicyCandidate],
) -> dict[str, list[PolicyCandidate]]:
```

Groups candidates by `policy_key`. Skips candidates with key `"unassigned"`.

### Persistent Clusters

Clusters are persistent — a `policy_key` maps to exactly one `Cluster` record.
The scheduler finds or creates clusters:
- If a cluster with the same `policy_key` exists: merge new candidate IDs
- If new: create a `Cluster` record with `needs_resummarize=True`
- Growth detection: if member_count grows by `resummarize_growth_threshold` (default 50%),
  set `needs_resummarize=True` to trigger ballot question regeneration.

### Key Normalization

`normalize_policy_keys()` runs periodically:
1. For each topic with 2+ keys, asks LLM to identify merge candidates
2. `execute_key_merge()` reassigns candidates and deletes merged clusters
3. Survivor cluster gets `needs_resummarize=True`

### Agenda Qualification

The agenda gate uses a single combined metric:
`total_support = cluster.member_count + endorsement_count >= min_support`

## Constraints

- `policy_key` on the `clusters` table has a UNIQUE constraint
- Merged clusters are deleted; candidates are reassigned
- All merges are evidence-logged (`cluster_merged` event)
- HDBSCAN is retained in `cluster.py` for legacy/backup but not called by the scheduler

## Tests

- `tests/test_pipeline/test_policy_grouping.py` — unit tests for grouping, slug sanitization, centroid
- `tests/test_pipeline/test_normalize.py` — merge response parsing
- `tests/test_pipeline/test_endorsement.py` — ballot response parsing
- `tests/test_pipeline/test_agenda.py` — combined support gate
