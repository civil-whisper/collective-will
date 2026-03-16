# Task: Policy-Key Grouping

## Depends on
- `pipeline/03-canonicalization` (candidates have `policy_topic` and `policy_key`)
- `pipeline/04-embeddings` (candidates have embedding vectors for validation)
- `database/03-core-models` (Cluster, PolicyCandidate models)

## Goal

Group policy candidates by their LLM-assigned `policy_key` while preserving proposition compatibility. Each unique `policy_key` maps to one persistent `Cluster` record, but grouping and normalization must refuse merges when the actor, mechanism, or target differs in a way that would change what voters are deciding.

## Two-Level Policy Structure

- **`policy_topic`**: Stance-neutral umbrella for browsing/UI only (e.g., `internet-censorship`).
  It may help browsing, but it is not a grouping invariant.
- **`policy_key`**: Stance-neutral ballot-level discussion (e.g., `political-internet-censorship`).
  This is what forms clusters and goes to vote. Specific enough that 2–4 ballot
  options can cover the full discussion.
- **Semantic identity**: `actor_scope`, `action_mechanism`, and `target_scope` must remain proposition-compatible within a cluster.

All are assigned during canonicalization and may be corrected later by dispute resolution or audited normalization.

## Pipeline Stages

### Stage 1 — Context-Aware Assignment (Inline)

At canonicalization time (`canonicalize.py`), the LLM sees existing open `policy_key`s from the `clusters` table. This context-aware prompt should encourage reuse only when the actor, mechanism, and target materially match. Shared political goals are not enough.

### Stage 2 — Hybrid Key Normalization (Batch)

Periodically (`normalize.py`), a hybrid embedding + LLM approach normalizes keys:

1. **Embedding-based candidate discovery**: All non-unassigned candidates with
   embeddings are clustered using agglomerative clustering on cosine distance
   (threshold `COSINE_SIMILARITY_THRESHOLD = 0.55`). This works across all keys,
   but the embedding stage is only a candidate-discovery step, not permission to merge.
2. **LLM key remapping**: For each embedding cluster containing 2+ distinct
   `policy_key` values, the LLM receives **all candidate summaries in full** (no
   truncation, no per-key cap) and produces a `key_mapping`:
   `{old_key: canonical_key}`. The LLM may keep existing keys, merge several
   into one, or create a new key name that better represents the group.
3. **Compatibility guard**: normalization must skip any merge candidate where
   the participating keys do not agree on `actor_scope`, `action_mechanism`, and
   `target_scope`, or where a ballot-ready proposition would be mixed with a broad concern.

### Stage 3 — Ballot Question Generation (Batch)

For clusters that need (re)summarization (`endorsement.py`), the LLM generates
neutral wording. Broad concerns get agenda-setting language; concrete clusters
get proposition-style ballot language.

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
4. `execute_key_merge()` reassigns candidates and deletes merged clusters. Only `open` clusters are matched — archived clusters are excluded from merges.
5. Candidate-level lineage must be recorded when a key changes (`candidate_rekeyed` evidence)
6. Survivor cluster gets `needs_resummarize=True`

Key dependencies: `numpy`, `scipy` (for `pdist`, `linkage`, `fcluster`)

### Agenda Qualification

The agenda gate uses a single combined metric:
`total_support = cluster.member_count + endorsement_count >= min_support`

## Constraints

- `policy_key` on the `clusters` table has a UNIQUE constraint for open clusters
- Merged clusters are deleted; candidates are reassigned
- All merges are evidence-logged (`cluster_merged` event)
- Candidate-level lineage is mandatory whenever a merge changes a candidate's `policy_key`
- HDBSCAN has been removed; policy-key grouping is the sole clustering mechanism

## Tests

- `tests/test_pipeline/test_policy_grouping.py` — unit tests for grouping, slug sanitization, centroid
- `tests/test_pipeline/test_normalize.py` — merge response parsing, submissions block building, embedding clustering
- `tests/test_pipeline/test_endorsement.py` — ballot response parsing
- `tests/test_pipeline/test_agenda.py` — combined support gate
- `tests/test_pipeline/test_grouping_integration.py` — end-to-end LLM grouping test (100 submissions,
  serial canonicalization with cumulative context, interleaved normalization every 25 subs).
  Run with `GENERATE_GROUPING_CACHE=1` to generate cache; excluded from CI.
