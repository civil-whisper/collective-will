# Task: Public Audit Verification

## Depends on
- `database/04-evidence-store` (append-only chain, daily Merkle roots, receipts)
- `website/08-audit-evidence-explorer` (public audit UX)

## Goal
Make the public audit trail independently verifiable while keeping everyday verification understandable for non-programmers.

## Verification layers

### Layer 1 — Ordinary user verification
Users should be able to answer:
- Was my action recorded?
- Was it included in a public redacted daily snapshot?
- Was that snapshot externally timestamped?

This layer is human-readable first. Do not require users to understand hashes, Merkle proofs, or Bitcoin internals.

### Layer 2 — Public watchdog / journalist verification
Public users should be able to download:
- daily bundle
- manifest
- OpenTimestamps proof file (`.ots`)

They should also get a guided explanation of what each file proves.

### Layer 3 — Programmer / auditor verification
Auditors should be able to:
- reproduce bundle hash from downloaded file
- verify entry inclusion in the bundle
- verify the OpenTimestamps proof independently

## External anchoring choice

### OpenTimestamps-first
- Use OpenTimestamps as the default external timestamping layer.
- No account, API key, or vendor dashboard is required.
- Timestamp the **daily Merkle root** (and optionally the bundle hash as metadata in the manifest).
- Store the resulting `.ots` proof file beside the manifest.
- Current implementation timestamps the UTF-8 bytes of `daily_merkle_root` as a detached OpenTimestamps file and stores the proof at `audit/{YYYY-MM-DD}/audit-{YYYY-MM-DD}.ots`.

### Provider strategy
- Keep external publishing provider-pluggable in code/config:
  - `none`
  - `opentimestamps`
  - future optional providers later if needed

## Artifacts

### Daily bundle
- Path: `audit/{YYYY-MM-DD}/audit-{YYYY-MM-DD}.jsonl.gz`
- Content: public-redacted evidence entries ordered by `id ASC`

### Manifest
- Path: `audit/{YYYY-MM-DD}/manifest-{YYYY-MM-DD}.json`
- Required fields:
  - `schema_version`
  - `day_utc`
  - `entry_count`
  - `first_entry_id`
  - `last_entry_id`
  - `first_hash`
  - `last_hash`
  - `daily_merkle_root`
  - `bundle_sha256`
  - `generated_at`
  - `visibility_policy_version`
  - `event_catalog_version`
  - `timestamping` object:
    - `provider` (`opentimestamps`)
    - `status` (`disabled` | `pending` | `stamped` | `verified` | `failed`)
    - `ots_proof_path`
    - `verified_before` (nullable)
    - `bitcoin_block_height` (nullable)

### Public index
- Path: `audit/index.json`
- Fields:
  - `schema_version`
  - `updated_at`
  - `days[]` newest-first
    - `day_utc`
    - `entry_count`
    - `daily_merkle_root`
    - `bundle_path`
    - `manifest_path`
    - `ots_proof_path`
    - `timestamping_status`

Implementation notes:
- `AUDIT_TIMESTAMP_PROVIDER=none` preserves local root/bundle generation and writes `disabled` timestamping status when no compatible proof exists.
- `AUDIT_TIMESTAMP_PROVIDER=opentimestamps` creates or upgrades the `.ots` proof file for the current day.
- `verified` is only set after successful Bitcoin-backed verification; without a configured Bitcoin node, completed proofs remain `stamped`.

## User receipt model

### Existing receipt token
- Keep HMAC receipt tokens for private inclusion proof.

### Receipt verification states
- `recorded` — action exists in evidence chain
- `published` — action appears in public redacted daily bundle
- `timestamped` — the bundle/day root has an OpenTimestamps proof
- `verified` — proof validated successfully against OpenTimestamps/Bitcoin path
- `failed` — verification data missing or invalid

State progression is one-way:
- `recorded` -> `published` -> `timestamped` -> `verified`
- `failed` is reserved for missing/invalid verification artifacts or proof mismatch

Verification APIs should return both:
- `status` (one of the five frozen states)
- detailed booleans (`receipt_valid`, `included_in_public_bundle`, `ots_proof_present`, `ots_verified`) so UI can explain the result without inventing new states

### Trust-language rule
UI copy must clearly say:
- what this proves: no silent rewriting after publication
- what this does not prove: perfect fairness or completeness on its own

Frozen language:
- proves: “your action was recorded and, once published, the public record cannot be changed later without detection”
- does not prove: “that every possible event was included or that every system decision was fair”

## Proposed backend endpoints

### Public endpoints
- `GET /analytics/audit-bundles`
  - implemented; lists available bundle days from `audit/index.json`
  - returns per-day summary rows with download URLs and detail URLs
- `GET /analytics/audit-bundles/{day}`
  - implemented; returns manifest summary, timestamping metadata, bundle hash verification status, and artifact links
- `GET /analytics/audit-bundles/{day}/proof?entry_hash=...`
  - implemented; returns bundle inclusion result plus proof metadata for a specific entry hash
- `GET /analytics/audit-bundles/{day}/bundle`
  - implemented; downloads the published `jsonl.gz` bundle file
- `GET /analytics/audit-bundles/{day}/manifest`
  - implemented; downloads the manifest JSON
- `GET /analytics/audit-bundles/{day}/ots`
  - implemented; downloads the OpenTimestamps proof file when present

### Authenticated user verification
- `GET /user/dashboard/receipts`
  - existing receipt list
- `GET /user/dashboard/receipts/{entry_hash}/verify`
  - implemented; checks the authenticated user's receipt-eligible evidence entry and derives a frozen verification state from local audit artifacts
  - returns:
    - `receipt_valid`
    - `entry_found`
    - `bundle_day`
    - `included_in_public_bundle`
    - `bundle_hash_matches_manifest`
    - `ots_proof_present`
    - `ots_verified`
    - `verified_before`
    - `status`
    - `download_urls`
  - current behavior:
    - `recorded` when the internal evidence entry exists but no public bundle/manifest has been generated yet
    - `published` when the entry is present in the daily bundle and the bundle hash matches the manifest
    - `timestamped` when a manifest-backed `.ots` proof file exists
    - `verified` when manifest metadata marks the OpenTimestamps proof as verified
    - `failed` when verification artifacts exist but are inconsistent (for example bundle mismatch or missing inclusion)

## Proposed website UX

### Dashboard receipt cards
For each receipt-eligible action:
- show human-readable action label
- show action timestamp and cluster/cycle context
- show status chips:
  - `Recorded`
  - `Published`
  - `Timestamped`
- provide `Verify this receipt` action

### Receipt detail page
- Explain what happened
- Explain what the current status means
- Show plain-language verification summary
- Offer advanced downloads:
  - bundle
  - manifest
  - `.ots`
  - entry hash / receipt details

### Public audit snapshot page
- One row/card per day
- Show:
  - entry count
  - bundle hash
  - Merkle root
  - timestamping status
  - download links
- Implemented routes:
  - `/{locale}/collective-concerns/audit-bundles`
  - `/{locale}/collective-concerns/audit-bundles/{day}`

## Constraints
- Public bundles must use the same visibility/redaction logic as `/analytics/evidence`.
- No private receipt-only fields or platform identifiers in published artifacts.
- External timestamping failure must not block local bundle generation.
- Ordinary-user verification must be possible without requiring shell commands.

## Tests
- Deterministic bundle and manifest generation
- Receipt status derivation (`recorded`/`published`/`timestamped`/`verified`)
- Manifest/index OpenTimestamps metadata persistence
- Verification endpoint tests (happy path + missing proof + invalid proof)
- UI tests for receipt status chips and plain-language explanations
