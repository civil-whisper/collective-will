# Emit Missing cluster_created / cluster_updated Evidence Events

## Status: Done

## Problem

`cluster_created` and `cluster_updated` were declared in `VALID_EVENT_TYPES`
but never emitted. The `_find_or_create_cluster` function in the scheduler
created and updated clusters silently, leaving a gap in the audit trail.

## Changes

- **`src/scheduler/main.py`** — `_find_or_create_cluster` now:
  - Emits `cluster_created` when a new cluster is created, with payload
    `{cluster_id, policy_key, policy_topic, member_count}`.
  - Emits `cluster_updated` when an existing cluster gains new members, with
    payload `{cluster_id, policy_key, old_member_count, new_member_count}`.
  - Skips the update event if membership did not actually change (idempotent).
- **`tests/test_pipeline/test_scheduler.py`** — three new tests:
  - `test_find_or_create_cluster_emits_cluster_created`
  - `test_find_or_create_cluster_emits_cluster_updated`
  - `test_find_or_create_cluster_skips_event_when_no_change`
