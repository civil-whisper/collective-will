# Reverse Evidence Ledger Order (Newest First)

## Status: Done

## Problem

The `/analytics/evidence` API endpoint returns entries ordered by `id ASC`
(oldest first). Users expect to see the most recent activity at the top of the
audit ledger page.

## Changes

- **`src/api/routes/analytics.py`** — changed `.order_by(EvidenceLogEntry.id.asc())`
  to `.order_by(EvidenceLogEntry.id.desc())`.
- **`tests/test_api/test_analytics.py`** — added `test_returns_newest_first_order`
  asserting entries come back with the highest id first.

No frontend changes required; pagination ("Previous" / "Next") still works
correctly — page 1 = newest, higher pages = older.
