# Task: Analytics — Top Policies

## Depends on
- `website/04-analytics-cluster-explorer` (analytics page structure, API client, types)

## Goal
Build a ranked list of top policy priorities by approval votes, showing the results of completed voting cycles.

## Files to create

- `web/app/[locale]/analytics/top/page.tsx` — top policies page
- `web/components/PolicyRankList.tsx` — ranked list component
- `web/components/VotingCycleSelector.tsx` — cycle dropdown
- `web/messages/fa.json` — add top policies translations
- `web/messages/en.json` — add top policies translations

## Specification

### Top policies page (`/analytics/top`)

Displays voting results ranked by approval count.

- **Cycle selector**: Dropdown to select which voting cycle to view. Default: most recent completed cycle.
- **Ranked list**: Ordered by approval_count descending
  - Each item shows:
    - Rank number (1, 2, 3...)
    - Cluster summary (Farsi primary)
    - Approval count (absolute number)
    - Approval rate (percentage of total voters)
    - Policy topic tag
    - Link to cluster detail (`/analytics/clusters/[id]`)
  - Visual indicator for top 3 (highlight or icon)

- **Cycle stats**: At the top, show:
  - Cycle date range (started_at — ends_at)
  - Total voters
  - Total clusters on ballot

### API calls

- `GET /api/cycles` → list of completed voting cycles
- `GET /api/cycles/:id/results` → cycle results with ranked clusters

Add to API client:
```typescript
export async function getCycles(): Promise<VotingCycle[]> { ... }
export async function getCycleResults(id: string): Promise<CycleResults> { ... }
```

### TypeScript types

```typescript
interface VotingCycleSummary {
  id: string;
  started_at: string;
  ends_at: string;
  status: "active" | "closed" | "tallied";
  total_voters: number;
}

interface CycleResults {
  cycle: VotingCycleSummary;
  results: RankedPolicy[];
}

interface RankedPolicy {
  cluster_id: string;
  summary: string;
  policy_topic: string;
  approval_count: number;
  approval_rate: number;       // 0-1
}
```

### Empty states

- No completed cycles: "هنوز رای‌گیری‌ای انجام نشده است." / "No voting cycles completed yet."
- Cycle with zero votes: Show results but note "No votes were cast in this cycle."

### Navigation

Add a link to this page from the main analytics page and the NavBar.

## Constraints

- Public page — no auth required.
- Approval rate displayed as percentage (e.g., "73%"), not raw decimal.
- Rankings must handle ties correctly (same rank for equal approval counts).
- Do NOT show individual voter information.
- SSR for SEO.

## Tests

Write tests covering:
- Page renders ranked list with correct order (highest approval first)
- Rank numbers are correct (1, 2, 3...)
- Ties handled: two clusters with same count get same rank
- Approval rate displayed as percentage
- Cycle selector switches between cycles
- Empty state renders when no completed cycles
- Link to cluster detail works
- Page renders in both locales (Farsi RTL, English LTR)
