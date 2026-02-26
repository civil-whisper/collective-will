# Task: Policy-Key Grouping

## Depends on
- `pipeline/03-canonicalization` (candidates have `policy_topic` and `policy_key`)
- `pipeline/04-embeddings` (candidates have embedding vectors for validation)
- `database/03-core-models` (Cluster, PolicyCandidate models)

## Goal

Group policy candidates by their LLM-assigned `policy_key`. Each unique
`policy_key` maps to one persistent `Cluster` record.

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

### Stage 2 — Hybrid Key Normalization (Batch)

Periodically (`normalize.py`), a hybrid embedding + LLM approach normalizes keys:

1. **Embedding-based candidate discovery**: All non-unassigned candidates with
   embeddings are clustered using agglomerative clustering on cosine distance
   (threshold `COSINE_SIMILARITY_THRESHOLD = 0.55`). This works **across all
   topics**, not just within a single topic. The low threshold creates bigger
   clusters so the LLM sees more context.
2. **LLM key remapping**: For each embedding cluster containing 2+ distinct
   `policy_key` values, the LLM receives **all candidate summaries in full** (no
   truncation, no per-key cap) and produces a `key_mapping`:
   `{old_key: canonical_key}`. The LLM may keep existing keys, merge several
   into one, or create a new key name that better represents the group.

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

### Key Normalization (Hybrid Embedding + LLM)

`normalize_policy_keys()` runs periodically:
1. Loads all non-unassigned candidates with embeddings from the DB
2. Clusters by cosine similarity (agglomerative, threshold 0.55) across ALL topics
3. For each cluster with 2+ distinct `policy_key` values, sends all candidate
   summaries in full (no truncation) to LLM which produces a `key_mapping`
   (old→canonical, may create new keys)
4. `execute_key_merge()` reassigns candidates and deletes merged clusters
5. Survivor cluster gets `needs_resummarize=True`

Key dependencies: `numpy`, `scipy` (for `pdist`, `linkage`, `fcluster`)

### Agenda Qualification

The agenda gate uses a single combined metric:
`total_support = cluster.member_count + endorsement_count >= min_support`

## Constraints

- `policy_key` on the `clusters` table has a UNIQUE constraint
- Merged clusters are deleted; candidates are reassigned
- All merges are evidence-logged (`cluster_merged` event)
- HDBSCAN has been removed; policy-key grouping is the sole clustering mechanism

## Tests

- `tests/test_pipeline/test_policy_grouping.py` — unit tests for grouping, slug sanitization, centroid
- `tests/test_pipeline/test_normalize.py` — merge response parsing, submissions block building, embedding clustering
- `tests/test_pipeline/test_endorsement.py` — ballot response parsing
- `tests/test_pipeline/test_agenda.py` — combined support gate
- `tests/test_pipeline/test_grouping_integration.py` — end-to-end LLM grouping test (100 submissions,
  serial canonicalization with cumulative context, interleaved normalization every 25 subs).
  Run with `GENERATE_GROUPING_CACHE=1` to generate cache; excluded from CI.
