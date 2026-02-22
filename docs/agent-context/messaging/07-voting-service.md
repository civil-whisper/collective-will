# Task: Voting Service

## Depends on
- `messaging/04-submission-intake` (understanding of handler pattern)
- `messaging/02-whatsapp-evolution-client` (channel for sending ballots)
- `messaging/06-abuse-rate-limiting` (vote change check)
- `database/03-core-models` (Vote, VotingCycle, Cluster models)
- `database/04-evidence-store` (append_evidence)

## Goal
Implement the full voting lifecycle: record pre-ballot endorsements (signatures), open a cycle with qualifying agenda items, send ballot prompts, parse and cast votes, send reminders, close and tally.

## Files to create

- `src/handlers/voting.py` — voting service

## Specification

### open_cycle()

```python
async def open_cycle(
    cluster_ids: list[UUID],
    db: AsyncSession,
) -> VotingCycle:
```

1. Create VotingCycle record with `status="active"`, `started_at=now()`, `ends_at=now()+48h`
2. Set `cluster_ids` to the provided pre-qualified list from agenda builder (size + endorsement gates already applied)
3. Log `cycle_opened` event to evidence store with payload `{cycle_id, cluster_ids, starts_at, ends_at}`
4. Return the created cycle

### send_ballot_prompt()

```python
async def send_ballot_prompt(
    user: User,
    cycle: VotingCycle,
    clusters: list[Cluster],
    channel: BaseChannel,
) -> bool:
```

1. Format the ballot in Farsi (numbered list of cluster summaries)
2. Send via `channel.send_ballot()`
3. Return success/failure

### record_endorsement()

```python
async def record_endorsement(
    user: User,
    cluster_id: UUID,
    db: AsyncSession,
) -> bool:
```

1. Check user eligibility baseline: `email_verified`, `messaging_verified`, account age >= `settings.min_account_age_hours`
2. Ensure one signature per user per cluster (idempotent behavior)
3. Create `PolicyEndorsement` record
4. Increment `user.contribution_count` if this is the user's first accepted contribution
5. Log `policy_endorsed` event to evidence store
6. Return True if recorded (or already present), False on ineligible/error

### parse_ballot()

```python
def parse_ballot(text: str, max_options: int) -> list[int] | None:
```

Parse user reply like `"1, 3, 5"` or `"1,3,5"` or `"۱، ۳، ۵"` (Farsi numerals) into a list of 1-based option indices.

- Handle: comma-separated, space-separated, Farsi numerals (۰-۹)
- Validate: all numbers within range `[1, max_options]`
- Return None if unparseable

### cast_vote()

```python
async def cast_vote(
    user: User,
    cycle: VotingCycle,
    approved_indices: list[int],
    db: AsyncSession,
) -> Vote | None:
```

1. Check user eligibility: `email_verified`, `messaging_verified`, `contribution_count >= 1`, account age >= `settings.min_account_age_hours` (default 48 in production). Here, `contribution_count` includes processed submissions and pre-ballot endorsements.
2. Check vote change limit: call `check_vote_change()` from abuse module
3. Map 1-based indices to cluster UUIDs from `cycle.cluster_ids`
4. If user already voted this cycle: allow exactly one full vote-set update for the cycle (this is the one allowed change)
5. If first vote: create new Vote record
6. Log `vote_cast` event to evidence store
7. Send confirmation: `"✅ رای شما ثبت شد!"`
8. Return the Vote, or None if ineligible/rate-limited

### close_and_tally()

```python
async def close_and_tally(
    cycle_id: UUID,
    db: AsyncSession,
) -> VotingCycle:
```

1. Load all votes for this cycle
2. Count approvals per cluster
3. Compute approval_rate = approvals / total_voters for each cluster
4. Update VotingCycle with `status="tallied"`, `results`, `total_voters`
5. Update each Cluster's `approval_count`
6. Log `cycle_closed` event to evidence store
7. Return the updated cycle

### send_reminder()

```python
async def send_reminder(
    cycle: VotingCycle,
    channel: BaseChannel,
    db: AsyncSession,
) -> int:  # Returns number of reminders sent
```

Send a reminder to all verified users who haven't voted yet, 24 hours before cycle ends. Return count of reminders sent.

## Constraints

- Vote eligibility requires `contribution_count >= 1` (accepted contribution = processed submission OR recorded endorsement signature).
- Final ballot must only include pre-qualified clusters returned by agenda builder.
- Vote-change semantics are explicit: one full approval-set re-submission is allowed per cycle (total max: 2 vote submissions). After that, further changes are blocked.
- Tally math must be exact — no floating point errors in counts. Use integer counts; compute rates as `Decimal` or round consistently.
- All voting events logged to evidence store.
- Keep messaging transport abstracted: use `BaseChannel` methods so voting logic remains reusable beyond WhatsApp.
- Do not hardcode `48` for age checks; use config (`MIN_ACCOUNT_AGE_HOURS`) so test environments can run with lower thresholds.
- No manual vote edits/overrides at per-user level. Any corrections must come from deterministic policy logic and be evidence-logged.

## Tests

Write tests in `tests/test_handlers/test_voting.py` covering:
- `open_cycle()` creates cycle with correct dates and logs evidence
- `parse_ballot("1, 3, 5", 10)` returns `[1, 3, 5]`
- `parse_ballot("۱، ۳", 5)` returns `[1, 3]` (Farsi numerals)
- `parse_ballot("0, 11", 10)` returns None (out of range)
- `parse_ballot("hello", 5)` returns None
- `record_endorsement()` creates one signature per user per cluster (duplicate requests are idempotent)
- `cast_vote()` stores vote with correct cluster IDs and logs evidence
- Ineligible user (no accepted contributions) cannot vote
- Eligible user with no submissions but at least one recorded endorsement can vote
- Ineligible user (account age below configured minimum) cannot vote
- With `MIN_ACCOUNT_AGE_HOURS=1` in test config, users older than 1 hour can vote (assuming other checks pass)
- Vote change semantics: first full re-submission succeeds, second re-submission is blocked
- `close_and_tally()` produces correct counts and rates
- `close_and_tally()` updates cluster approval_count values
- `send_reminder()` only sends to users who haven't voted
- Evidence logged for cycle_opened, vote_cast, cycle_closed
