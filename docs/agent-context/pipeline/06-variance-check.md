# Task: Multi-Run Variance Check

## Depends on
- `pipeline/05-hdbscan-clustering` (run_clustering function)

## Goal
Run clustering 3 times with different seeds and flag clusters whose membership is unstable. This detects clusters that are artifacts of a particular run rather than genuine groupings.

## Files to create/modify

- Update `src/pipeline/cluster.py` — add variance check function

## Specification

### variance_check()

```python
async def variance_check(
    cycle_id: UUID,
    db: AsyncSession,
    num_runs: int = 3,
    instability_threshold: float = 0.3,
) -> list[Cluster]:
    """
    Run clustering multiple times and flag unstable clusters.
    Returns the final set of clusters (from the primary run) with variance_flag set.
    """
```

Steps:
1. Generate `num_runs` different random seeds
2. Run `run_clustering()` with each seed (these are temporary runs — only the first is persisted)
3. For each cluster in the primary run (run 0):
   - Find the best-matching cluster in each other run (by member overlap — Jaccard similarity)
   - Compute stability score = average Jaccard similarity across other runs
   - If stability score < (1 - instability_threshold): set `variance_flag = True`
4. Update the persisted clusters with `variance_flag` values
5. Return the updated clusters

### Jaccard similarity

```python
def jaccard_similarity(set_a: set[UUID], set_b: set[UUID]) -> float:
    if not set_a and not set_b:
        return 1.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union
```

### Best-matching cluster

For a cluster in run 0, the best match in run N is the cluster with the highest Jaccard similarity of member candidate IDs.

### Instability threshold

Default: 0.3. This means a cluster is flagged if its average Jaccard similarity across runs is below 0.7 (i.e., more than 30% of its membership changes between runs).

## Constraints

- Only the primary run (run 0) is persisted to the database. Other runs are used for comparison only and discarded.
- Variance check is optional in the pipeline — it can be skipped if there are very few candidates (< 20).
- The `variance_flag` is informational. Flagged clusters are still included in the agenda and shown to users. The flag is for transparency.

## Tests

Write tests in `tests/test_pipeline/test_variance.py` covering:
- Stable clusters (tight, well-separated groups): `variance_flag = False`
- Unstable clusters (overlapping groups near decision boundary): `variance_flag = True`
- Jaccard similarity: `{1,2,3}` vs `{1,2,3}` = 1.0
- Jaccard similarity: `{1,2,3}` vs `{4,5,6}` = 0.0
- Jaccard similarity: `{1,2,3}` vs `{1,2,4}` = 0.5
- 3 runs are actually executed (mock or count calls)
- Primary run clusters are persisted; other runs are not
- With fewer than 20 candidates, variance check can be skipped
- `instability_threshold` parameter is respected
