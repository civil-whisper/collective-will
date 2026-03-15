# Task: Evidence Store

## Depends on
- `database/02-db-connection` (engine, session, Base)

## Goal
Implement the append-only evidence log with hash-chain integrity, an append function, chain verification, daily Merkle-root computation, and optional external root timestamping/publication.

## Files to create/modify

- `src/db/evidence.py` — EvidenceLogEntry ORM model, append and verify functions
- `src/db/anchoring.py` — daily Merkle-root computation and optional OpenTimestamps publisher
- SQL for the `evidence_log` table, trigger, and indexes (can be inline or in a separate `.sql` file referenced by migrations later)

## Specification

### Table DDL

```sql
CREATE TABLE evidence_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    payload JSONB NOT NULL,
    hash TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    
    -- Immutability enforced by:
    -- 1. No UPDATE/DELETE permissions on this table
    -- 2. Trigger that validates hash chain on INSERT
);

CREATE INDEX idx_evidence_hash ON evidence_log(hash);
CREATE INDEX idx_evidence_entity ON evidence_log(entity_type, entity_id);
```

### Hash computation

```python
import hashlib, json

def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def compute_entry_hash(
    *,
    timestamp_iso: str,
    event_type: str,
    entity_type: str,
    entity_id: str,
    payload: dict,
    prev_hash: str,
) -> str:
    material = {
        "timestamp": timestamp_iso,   # UTC ISO-8601, e.g. 2026-02-20T12:34:56.789Z
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,       # canonical UUID string (lowercase)
        "payload": payload,
        "prev_hash": prev_hash,
    }
    serialized = canonical_json(material)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
```

Canonical serialization format (must be documented and stable):
- Material object keys: `timestamp`, `event_type`, `entity_type`, `entity_id`, `payload`, `prev_hash`
- JSON: sorted keys, compact separators `(",", ":")`, UTF-8 encoding
- Timestamp: UTC ISO-8601 with `Z`
- UUIDs: lowercase canonical string form

### Chain trigger (SQL)

On INSERT, validate that `prev_hash` matches the `hash` of the most recent existing entry. For the very first entry, `prev_hash` should be a known genesis value (e.g., `"0"` or `"genesis"`).

### append_evidence() function

```python
async def append_evidence(
    session: AsyncSession,
    event_type: str,
    entity_type: str,
    entity_id: UUID,
    payload: dict,
) -> EvidenceLogEntry:
```

Steps:
1. Get the hash of the last entry (or genesis value if empty)
2. Build canonical hash material from full entry fields (`timestamp`, `event_type`, `entity_type`, `entity_id`, `payload`, `prev_hash`)
3. Compute entry hash from canonical serialized material
4. Insert new row with `prev_hash` = last entry's hash, `hash` = computed full-entry hash
5. Return the created entry

This must be atomic — use a transaction with row-level locking to prevent race conditions on concurrent inserts.

### verify_chain() function

```python
async def verify_chain(session: AsyncSession) -> tuple[bool, int]:
    """Returns (is_valid, entries_checked)."""
```

Iterate through all entries in order. For each entry, verify:
1. `hash` matches `compute_entry_hash(...)` over full entry fields (including `prev_hash`)
2. `prev_hash` matches the preceding entry's `hash`

Return False immediately if any link is broken.

### compute_daily_merkle_root() function

```python
async def compute_daily_merkle_root(
    session: AsyncSession,
    day: date,
) -> str | None:
    """Compute and persist Merkle root for all evidence entries on `day`."""
```

Steps:
1. Load that day's `evidence_log` rows ordered by `id`
2. Build leaf list from entry `hash` values
3. Compute Merkle root deterministically (pairwise hash; duplicate last node for odd counts)
4. Persist root in a daily anchors table (or equivalent evidence payload entry)
5. Return root (or `None` if no entries that day)

Merkle-root computation is required in v0 and should run daily even when external publishing is disabled.

### publish_daily_merkle_root() function (optional external step)

```python
async def publish_daily_merkle_root(
    root: str,
    day: date,
    settings: Settings,
) -> TimestampingResult | None:
    """Publish/timestamp root when enabled; return proof metadata."""
```

Behavior:
- If external timestamping is disabled, preserve any existing compatible `.ots` metadata and otherwise return a disabled placeholder
- If enabled with `AUDIT_TIMESTAMP_PROVIDER=opentimestamps`, create or upgrade a detached timestamp for the UTF-8 bytes of `daily_merkle_root`
- Store proof metadata (`status`, `ots_proof_path`, `verified_before`, `bitcoin_block_height`) in the anchors table metadata and the public manifest/index
- Failures in publish path must not skip daily root computation or bundle generation; return `failed` metadata instead of aborting the local export flow

### Event types

Valid event types are defined by `EVENT_CATALOG` in `src/db/evidence.py`. Each event type has an `EventSpec` with description, entity_type, receipt eligibility, and visibility tier fields (`public_fields`, `delayed_fields`).

**Submission lifecycle:**
`submission_received`, `submission_not_eligible`, `submission_rate_limited`, `submission_rejected_not_policy`

**Candidate lifecycle:**
`candidate_created`

**Cluster lifecycle:**
`cluster_created`, `cluster_updated`, `cluster_merged`, `ballot_question_generated`, `policy_options_generated`

**Endorsement lifecycle:**
`policy_endorsed`, `endorsement_not_eligible`

**Voting lifecycle:**
`vote_cast`, `vote_not_eligible`, `vote_change_limit_reached`, `cycle_opened`, `cycle_closed`

**Identity:**
`user_verified`

**Disputes:**
`dispute_escalated`, `dispute_resolved`, `dispute_metrics_recorded`, `dispute_tuning_recommended`

**Anchoring:**
`anchor_computed`, `anchor_publish_attempted`, `anchor_publish_succeeded`, `anchor_publish_failed`,
`audit_bundle_generated`, `audit_bundle_publish_succeeded`, `audit_bundle_publish_failed`

**Voice:**
`voice_enrolled`, `voice_enroll_phrase_rejected`, `voice_verified`

### Visibility tiers

Each event type defines:
- `public_fields` — visible immediately in public API after PII stripping
- `delayed_fields` — visible only after associated voting cycle closes (e.g., `vote_cast` selections)
- Receipt-eligible events (`generates_receipt=True`) generate HMAC-based receipts for user-verifiable proof of inclusion

`apply_visibility_tier()` in `src/db/evidence.py` applies PII stripping + delayed field filtering. The evidence API calls this per-entry with cycle-status awareness.

### Payload enrichment

All `append_evidence` call sites include human-readable context fields so entries are self-describing.
See `CONTEXT-shared.md` → "Evidence Payload Enrichment" for the per-event-type field contract.

### PII stripping

The public API endpoint (`GET /analytics/evidence`) recursively strips `user_id`, `email`, `account_ref`, and `wa_id` from payloads via `strip_evidence_pii()` in `src/db/evidence.py`. The stripping is recursive (handles nested dicts and lists). Internal DB entries retain all fields.

### User receipts

Receipt-eligible events (endorsements, votes) generate HMAC-SHA256 receipt tokens via `generate_receipt_token()`. Users retrieve their receipted evidence entries at `GET /user/dashboard/receipts` (authenticated). Receipts prove a user's action was included in the chain without revealing their identity publicly.

### Evidence API

- `GET /analytics/evidence?entity_id=&event_type=&page=&per_page=` — paginated with filtering, visibility-tier-aware payload redaction
- `GET /analytics/evidence/verify` — server-side `verify_chain()` call; returns `{valid, entries_checked}`
- `GET /user/dashboard/receipts?page=&per_page=` — authenticated; returns user's receipt-eligible evidence entries with HMAC receipt tokens

## Constraints

- The evidence_log table must NEVER allow UPDATE or DELETE. Enforce this at the database permission level and in application code (no ORM update/delete methods exposed).
- Use `hashlib.sha256` from Python stdlib. Do NOT use `random` module.
- Hash computation must be deterministic and reproducible by third parties using the canonical serialization format defined above.
- Concurrent appends must not corrupt the chain. Use database-level locking.
- Daily Merkle-root computation is mandatory in v0.
- External timestamping/publication is optional and config-driven; this toggle must not disable local root computation.
- Anchor computation and publication metadata must be evidence-loggable for audit reproducibility.

## Tests

Write tests in `tests/test_db/test_evidence.py` covering:
- Append a single evidence entry — hash and prev_hash are correct
- Append a chain of 5 entries — each prev_hash links to the previous hash
- `verify_chain()` returns True on a valid chain
- `verify_chain()` returns False when a payload is tampered with (modify payload in DB directly for test)
- `verify_chain()` returns False when metadata is tampered (`event_type`, `entity_type`, `entity_id`, or `timestamp`)
- Genesis entry has prev_hash = "genesis" (or chosen sentinel)
- All valid event types are accepted
- Invalid event type is rejected
- Concurrent appends (two near-simultaneous inserts) maintain chain integrity
- `compute_entry_hash()` is deterministic — same canonical entry material always produces same hash
- Canonical serialization output is stable for equivalent dict ordering (sorted-key invariance)
- `compute_daily_merkle_root()` returns deterministic root for a fixed day's entries
- Merkle root is computed even when external publication is disabled
- `publish_daily_merkle_root()` returns disabled metadata when `AUDIT_TIMESTAMP_PROVIDER=none`
- `publish_daily_merkle_root()` writes `.ots` proof metadata when OpenTimestamps is enabled
- Publish failure does not erase or skip the already computed local root
