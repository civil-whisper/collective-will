# Fix contribution_count Increment

## Problem

Vote eligibility requires `contribution_count >= 1` (configurable via
`REQUIRE_CONTRIBUTION_FOR_VOTE`). The intended rule is:

- **+1** on each successfully canonicalized submission (not rejected, not PII-blocked)
- **+1** on each policy endorsement

### Current Bugs

1. **`handle_submission()`** (`src/handlers/intake.py`) — inline path: after setting
   `submission.status = "canonicalized"`, `user.contribution_count` is never incremented.
   A user who submits accepted concerns cannot vote.

2. **`run_pipeline()`** (`src/scheduler/main.py`) — batch path: after processing pending
   submissions and marking them `"processed"`, the submitters' `contribution_count` is
   never incremented.

3. **`record_endorsement()`** (`src/handlers/voting.py`) — uses
   `if user.contribution_count == 0: user.contribution_count = 1` instead of
   `user.contribution_count += 1`. A user who endorses 3 clusters still has
   `contribution_count == 1`.

## Impact

A user who submits 10 accepted concerns but never endorses anything has
`contribution_count == 0` and cannot vote. Their submissions are processed, clustered,
and appear on the ballot — but the submitter themselves is locked out of voting.

## Fix

### `src/handlers/intake.py` — `handle_submission()`

After `submission.status = "canonicalized"` (around line 193):

```python
user.contribution_count += 1
```

### `src/scheduler/main.py` — `run_pipeline()`

After marking submissions as `"processed"` (around line 162), load and increment each
submitter's contribution_count for successfully processed submissions (those that
produced candidates).

### `src/handlers/voting.py` — `record_endorsement()`

Change:

```python
if user.contribution_count == 0:
    user.contribution_count = 1
```

To:

```python
user.contribution_count += 1
```

### Files to Change

- `src/handlers/intake.py` — increment on successful inline canonicalization
- `src/scheduler/main.py` — increment on successful batch processing
- `src/handlers/voting.py` — change set-to-1 to increment
- `tests/test_handlers/test_intake.py` — verify contribution_count after submission
- `tests/test_handlers/test_voting.py` — verify contribution_count increments on each
  endorsement
- `tests/test_pipeline/test_scheduler.py` — verify contribution_count after batch
  processing
