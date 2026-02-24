# Task: Batch Scheduler

## Depends on
- `pipeline/03-canonicalization` (canonicalize_single, canonicalize_batch)
- `pipeline/04-embeddings` (compute_and_store_embeddings)
- `pipeline/05-hdbscan-clustering` (run_clustering)
- `pipeline/06-variance-check` (variance_check)
- `pipeline/07-cluster-summarization-agenda` (summarize_clusters, build_agenda)
- `database/02-db-connection` (session factory)
- `database/04-evidence-store` (append_evidence)

## Goal
Run the batch clustering pipeline on a config-backed interval (`PIPELINE_INTERVAL_HOURS`).
Canonicalization and embedding now happen **inline at submission time** in `src/handlers/intake.py`.
The scheduler handles clustering, summarization, and agenda building for submissions that are already canonicalized.

## Architecture: Inline vs Batch Split

### Inline (at submission time, in `src/handlers/intake.py`)
1. **Canonicalize**: `canonicalize_single()` evaluates validity and structures the submission
2. **Garbage rejection**: If `is_valid_policy=false`, mark `status="rejected"` and send contextual feedback
3. **Embed**: `compute_and_store_embeddings()` for the single candidate
4. **Status**: Set `status="canonicalized"` on success, `status="pending"` on LLM failure (batch fallback)

### Batch (scheduler, in `src/scheduler/main.py`)
1. **Load ready submissions**: Query submissions with `status="canonicalized"` or `status="pending"` (fallback)
2. **Fallback canon+embed**: If any `status="pending"` submissions exist (LLM was down at intake time), canonicalize and embed them now
3. **Cluster**: `run_clustering()` → produces Clusters
4. **Variance check**: `variance_check()` → flags unstable clusters
5. **Summarize**: `summarize_clusters()` → generates summaries
6. **Build agenda**: `build_agenda()` → selects clusters for voting
7. **Update statuses**: Mark all as `status="processed"`

## Files

- `src/scheduler/main.py` — batch pipeline orchestration
- `src/scheduler/__main__.py` — entry point
- `src/handlers/intake.py` — inline canonicalization + embedding

### PipelineResult

```python
class PipelineResult(BaseModel):
    started_at: datetime
    completed_at: datetime
    submissions_processed: int
    candidates_created: int
    embeddings_computed: int
    clusters_created: int
    clusters_flagged: int      # variance_flag = True
    agenda_size: int
    errors: list[str]
```

### Scheduler

Use a simple async loop with sleep, or `apscheduler`:

```python
async def scheduler_main():
    """Entry point for the scheduler process."""
    while True:
        try:
            result = await run_pipeline()
            log_pipeline_result(result)
        except Exception as e:
            log_pipeline_error(e)
        await asyncio.sleep(settings.pipeline_interval_hours * 3600)
```

Run as a separate process: `python -m src.scheduler`

### Idempotency

The pipeline must be safe to re-run:
- Submissions already processed (status != "pending") are skipped
- Candidates that already have embeddings are skipped
- If clustering was already run for this cycle, re-running creates a new run (don't delete previous)

### Error handling

- Each step should catch exceptions and continue to the next step where possible
- If canonicalization fails for some submissions: log errors, continue with successful ones
- If embedding fails for some candidates: log, continue with those that have embeddings
- If clustering fails entirely: log error, skip summarization and agenda
- Never leave the database in an inconsistent state — use transactions per step

### Logging

Log pipeline start, each step's result, and completion to:
1. stdout (for Docker logs)
2. Evidence store: a `pipeline_run` event (optional, but recommended for auditability)

### Entry point

The scheduler runs as a separate Docker service (defined in docker-compose.yml):
```
command: python -m src.scheduler
```

Add `__main__.py` handling:
```python
# src/scheduler.py
if __name__ == "__main__":
    asyncio.run(scheduler_main())
```

## Constraints

- The pipeline processes ALL pending submissions, not just a fixed batch size. At v0 scale (< 1000 submissions), this is fine.
- Each pipeline step uses its own database session/transaction. A failure in step 5 should not roll back steps 1-4.
- The scheduler must not run multiple pipeline instances concurrently. Use a simple lock (database advisory lock or file lock).
- Do NOT use Celery or heavy task queue infrastructure. A simple async loop or apscheduler is sufficient for v0.

## Tests

Write tests in `tests/test_pipeline/test_scheduler.py` covering:
- `run_pipeline()` executes all steps in correct order (mock each step, verify call order)
- No pending submissions: pipeline completes quickly, PipelineResult shows 0 for all counts
- Partial failure: canonicalization fails for 2 of 10 submissions, remaining 8 proceed through pipeline
- Idempotency: running pipeline twice doesn't double-process submissions
- PipelineResult contains accurate counts
- Pipeline errors are captured in `PipelineResult.errors`, not raised
- Concurrent execution prevented (if using advisory lock, test that second run is blocked)
