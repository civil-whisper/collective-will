# Task: HDBSCAN Clustering

## Depends on
- `pipeline/04-embeddings` (candidates have embedding vectors)
- `database/03-core-models` (Cluster, PolicyCandidate models)
- `database/04-evidence-store` (append_evidence)

## Goal
Implement HDBSCAN clustering on policy candidate embeddings. This groups similar policy concerns together.

## Files to create

- `src/pipeline/cluster.py` — clustering logic

## Specification

### run_clustering()

```python
async def run_clustering(
    cycle_id: UUID,
    db: AsyncSession,
    min_cluster_size: int = 5,
    random_seed: int | None = None,
) -> list[Cluster]:
```

`min_cluster_size` is supplied from cycle/runtime config (not hardcoded in this module).

Steps:
1. Load all PolicyCandidates that have embeddings
2. Extract embedding vectors into a numpy array
3. If `random_seed` is None, generate one using `secrets.randbelow(2**32)`
4. Run HDBSCAN:
   ```python
   import hdbscan
   clusterer = hdbscan.HDBSCAN(
       min_cluster_size=min_cluster_size,
       metric="euclidean",
       core_dist_n_jobs=1,  # Deterministic
   )
   labels = clusterer.fit_predict(embeddings)
   ```
5. Group candidates by cluster label. Label `-1` means noise (unclustered).
6. For each cluster (label >= 0):
   - Collect member candidate IDs
   - Compute centroid embedding (mean of member vectors)
   - Compute cohesion score (mean pairwise distance within cluster)
   - Create Cluster record with `cycle_id`, member info, `run_id=uuid4()`, `random_seed`, `clustering_params`
7. Save clusters to database
8. Log `cluster_created` event for each cluster to evidence store
9. Return list of created clusters

### Noise handling

Candidates with label `-1` (noise/unclustered) are NOT discarded:
- They remain as unclustered candidates
- They may be clustered in a future run as more submissions arrive
- Log how many candidates were unclustered
- Expose unclustered candidate counts (and IDs via internal API) so analytics can surface them transparently

### Cold-start guardrail

Use config-backed size thresholds with an explicit v0 default:
- Default in v0: `min_cluster_size=5`
- If sparse cycles need calibration, tune via config/policy (no hardcoded logic forks)

Persist the chosen value in `clustering_params` for reproducibility.

### Clustering parameters logging

Store with each cluster:
```python
clustering_params = {
    "algorithm": "hdbscan",
    "min_cluster_size": min_cluster_size,
    "metric": "euclidean",
    "total_candidates": len(embeddings),
    "noise_count": noise_count,
}
```

### Determinism

HDBSCAN is mostly deterministic for the same input, but set `core_dist_n_jobs=1` to avoid non-determinism from parallel execution. Log the seed even though HDBSCAN doesn't use a random seed directly — it's for the multi-run variance check.

## Constraints

- Do NOT suppress small clusters. All clusters are visible, even those with exactly `min_cluster_size` members.
- Do NOT run clustering if there are fewer than `min_cluster_size` candidates total. Return empty list.
- Store `run_id`, `random_seed`, and `clustering_params` on every cluster for reproducibility.
- Clustering runs on ALL candidates (not just new ones since last run). The full dataset is re-clustered each cycle.
- `min_cluster_size` must come from config/cycle policy; do not hardcode a constant in implementation logic.
- Unclustered/noise candidates must remain queryable for analytics visibility.

## Tests

Write tests in `tests/test_pipeline/test_cluster.py` covering:
- Known synthetic embeddings (e.g., 3 tight groups of 5+ vectors each) produce expected number of clusters
- `min_cluster_size` is respected (no cluster smaller than the threshold)
- Configured `min_cluster_size` values are respected across different fixture densities (for example `4` and `5`)
- Noise points (widely scattered vectors) get label -1
- Determinism: same input + same seed = same cluster assignments (run twice, compare)
- Too few candidates (< min_cluster_size total): returns empty list, no error
- Unclustered candidate count is logged/stored for analytics exposure
- Each cluster has `run_id`, `random_seed`, `clustering_params` populated
- Centroid embedding is the mean of member embeddings
- Evidence logged for each cluster_created
- Cluster member_count matches len(candidate_ids)
