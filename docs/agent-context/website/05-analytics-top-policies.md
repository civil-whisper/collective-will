# Task: Analytics — Community Votes

## Depends on
- `website/04-analytics-cluster-explorer` (analytics page structure, API client, types)

## Goal
Show active voting ballots and archived voting results with per-option vote breakdowns.

## Files

- `web/app/[locale]/collective-concerns/community-votes/page.tsx` — community votes page
- `src/api/routes/analytics.py` — `GET /analytics/active-ballot` and `GET /analytics/top-policies`
- `src/handlers/voting.py` — `close_and_tally` snapshots option labels/vote counts
- `web/messages/en.json` / `web/messages/fa.json` — i18n keys

## Specification

### Community Votes page (`/collective-concerns/community-votes`)

#### Metric cards
- Total Voters | Active Votes (policies on current ballot) | Archived Votes (completed results)

#### Active Ballot section
Fetches `GET /analytics/active-ballot`. Shown when an active voting cycle exists.

For each cluster on the ballot:
- Ballot question (locale-aware: `ballot_question_fa` for Farsi, `ballot_question` otherwise)
- List of options with letter labels (A, B, C...) showing label + description
- TopicBadge for policy topic
- "N voters so far" (total only, no per-option counts to prevent bandwagon effect)
- "Results revealed when voting ends" note
- Time remaining

#### Archived Voting Results section
Fetches `GET /analytics/top-policies`. Shown when tallied results exist.

Ranked list sorted by approval_rate descending:
- Rank number badge
- Cluster summary with link to detail page
- TopicBadge
- Approval rate % with horizontal background bar
- Approval count
- Audit trail link
- **Per-option breakdown** (below main row):
  - Option label (locale-aware)
  - vote_count / total_voters with percentage
  - Horizontal percentage bar

### API endpoints

#### `GET /analytics/active-ballot`
Returns the active voting cycle with cluster details and options (no per-option vote counts):
```json
{
  "id": "uuid",
  "started_at": "iso",
  "ends_at": "iso",
  "total_voters": 7,
  "clusters": [
    {
      "cluster_id": "uuid",
      "summary": "...",
      "policy_topic": "...",
      "ballot_question": "...",
      "ballot_question_fa": "...",
      "options": [
        {"id": "uuid", "position": 1, "label": "...", "label_en": "...", "description": "...", "description_en": "..."}
      ]
    }
  ]
}
```
Returns `null` when no active cycle.

#### `GET /analytics/top-policies`
Returns flattened results from all tallied cycles, sorted by approval_rate descending.
Each item now includes `ballot_question`, `ballot_question_fa`, and `options` list with `vote_count` per option (snapshotted at tally time).

### Tally snapshot (`close_and_tally`)
When a voting cycle closes, `close_and_tally` snapshots into `cycle.results`:
- `summary`, `policy_topic`, `ballot_question`, `ballot_question_fa`
- `options`: list with `id`, `position`, `label`, `label_en`, `vote_count`

This replaces the previous raw `option_counts` dict, ensuring archived results are self-contained.

### Empty states
- No active cycle + no results: "No voting cycles have started yet."
- No active ballot: section hidden
- No archived results: section hidden

## Constraints
- Public page — no auth required
- No per-option vote counts during active voting (prevent bandwagon effect)
- Approval rate displayed as percentage
- Do NOT show individual voter information
- SSR for SEO

## Tests
- Backend: `close_and_tally` snapshots options with vote_count and ballot questions
- Backend: `GET /analytics/active-ballot` returns null / full ballot data
- Frontend: active ballot renders questions, options, voters count, "results after close" note
- Frontend: archived results show per-option breakdown bars with vote counts
