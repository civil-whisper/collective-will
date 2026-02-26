# Auto-Close Expired Voting Cycles

## Problem

`VotingCycle` records have an `ends_at` timestamp, but nothing in the system detects when
that time has passed. Once a cycle is opened with `open_cycle()`, it stays in `active`
status indefinitely unless `close_and_tally()` is called manually.

This means:

- Users can continue voting after the intended deadline
- Results are never computed automatically
- The command router keeps showing the expired cycle as votable

## Target Behavior

The scheduler should check for expired active cycles on each run and close them
automatically.

## Implementation

### In `src/scheduler/main.py` — `run_pipeline()`

Add a step at the beginning (before processing submissions):

```python
from datetime import UTC, datetime
from src.handlers.voting import close_and_tally

expired_result = await session.execute(
    select(VotingCycle)
    .where(VotingCycle.status == "active")
    .where(VotingCycle.ends_at <= datetime.now(UTC))
)
for cycle in expired_result.scalars().all():
    await close_and_tally(session=session, cycle=cycle)
```

### Consider: Two-Phase Close

The schema defines a `closed` status that is currently unused. If tallying becomes
expensive or needs to run asynchronously in the future, consider a two-phase approach:

1. Scheduler detects `ends_at` passed → sets `status = "closed"` (blocks new votes)
2. Tallying runs separately → sets `status = "tallied"`

For now, the single-step `close_and_tally()` is sufficient.

### Command Router Guard

The command router already checks `VotingCycle.status == "active"` before showing voting
UI. Once the scheduler sets `tallied`, users will see "no active vote" — no additional
change needed.

### Files to Change

- `src/scheduler/main.py` — add expired-cycle check at the start of `run_pipeline()`
- `tests/test_pipeline/test_scheduler.py` — add test for auto-close behavior
