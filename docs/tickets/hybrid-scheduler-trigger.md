# Hybrid Scheduler Trigger

## Problem

The batch pipeline scheduler (`src/scheduler/main.py`) currently runs on a fixed time
interval (`PIPELINE_INTERVAL_HOURS`, default 6h). This means:

- After a pipeline run, new submissions wait up to 6 hours to be clustered
- Empty runs waste resources when no new submissions exist
- During high-activity periods, the fixed interval adds unnecessary latency

## Target Behavior

Switch to a hybrid trigger: run the pipeline when **either** condition is met:

1. Unprocessed submission count reaches `BATCH_THRESHOLD` (new config)
2. Time since last run exceeds `PIPELINE_INTERVAL_HOURS` (existing config, used as max interval)

Whichever condition fires first triggers `run_pipeline()`.

## Implementation

### New Config

In `src/config.py`:

```python
batch_threshold: int = 10  # trigger pipeline when this many unprocessed submissions exist
```

### Scheduler Loop Changes

In `src/scheduler/main.py`, replace the fixed `asyncio.sleep()` with a polling loop:

1. After each `run_pipeline()`, start a timer
2. Poll at a short interval (e.g., every 60 seconds) to check the count of
   `canonicalized` + `pending` submissions
3. If count >= `BATCH_THRESHOLD` or elapsed time >= `PIPELINE_INTERVAL_HOURS`, run
4. The `asyncio.Lock` concurrency guard remains unchanged

### Files to Change

- `src/config.py` — add `batch_threshold` setting
- `src/scheduler/main.py` — rewrite `scheduler_loop()` polling logic
- `src/scheduler/__main__.py` — pass new config to `scheduler_loop()`
- `tests/test_pipeline/test_scheduler.py` — update tests for new trigger behavior

### Migration

No database migration needed. The change is backward-compatible — if `BATCH_THRESHOLD`
is set very high, the scheduler degrades to time-only behavior.
