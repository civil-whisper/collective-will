# Complete Frontend Evidence Event Coverage

## Status: Done

## Problem

Several emitted evidence event types were invisible in the audit explorer UI or
showed raw type strings instead of human-readable descriptions. Missing from
filter categories, missing from the default deliberation view, and missing i18n
translations.

## Changes

### `web/lib/evidence.ts`

- **`DELIBERATION_EVENT_TYPES`** — added `submission_rejected_not_policy`,
  `cluster_merged`, `ballot_question_generated`, `policy_options_generated`.
- **`EVENT_CATEGORIES`** — added:
  - `submissions`: `submission_rejected_not_policy`
  - `policies`: `cluster_merged`, `ballot_question_generated`,
    `policy_options_generated`
- **`eventDescription()`** — added switch cases for:
  - `submission_rejected_not_policy`
  - `cluster_created` (split from the shared `cluster_updated` case)
  - `cluster_merged`
  - `ballot_question_generated`
  - `policy_options_generated`

### `web/messages/en.json` and `web/messages/fa.json`

Added translation keys under `analytics.events.*`:
- `submissionRejectedNotPolicy`
- `clusterCreated`
- `clusterMerged`
- `ballotQuestionGenerated`
- `policyOptionsGenerated`

### `web/app/[locale]/collective-concerns/evidence/page.tsx`

Extended `payloadDisplayKeys` to surface fields from newly-visible events:
`policy_key`, `old_member_count → new_member_count` growth, `survivor_key`,
`merged_key`, `option_count`.
