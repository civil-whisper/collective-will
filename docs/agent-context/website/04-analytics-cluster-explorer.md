# Task: Analytics — Cluster Explorer

## Depends on
- `website/01-nextjs-setup-i18n` (Next.js project with i18n)

## Goal
Build the public analytics page that lists all clusters and allows drill-down into each cluster's details. This is the core transparency feature — no login required.

## Files to create

- `web/app/[locale]/analytics/page.tsx` — cluster list page
- `web/app/[locale]/analytics/clusters/[id]/page.tsx` — cluster detail page
- `web/components/ClusterCard.tsx` — cluster summary card
- `web/components/ClusterDetail.tsx` — full cluster view
- `web/lib/api.ts` — API client helper (if not yet created)
- `web/messages/fa.json` — add analytics translations
- `web/messages/en.json` — add analytics translations

## Specification

### Community Priorities page (`/collective-concerns`)

Page title: "Community Priorities" (اولویت‌های جمعی). Includes a short description explaining that citizen submissions are organized by AI into concern groups around shared policy topics, and groups that gain enough community support enter the voting ballot.

User-facing terminology: "concern groups" / "grouped concerns" instead of "clusters". Internal code still uses `Cluster` model and `clusters` API endpoints.

- **Stats bar at top**: Total Voters, Grouped Concerns (count), Total Submissions, Ungrouped (count)

- **Active cycle banner**: When a voting cycle is active, a green banner appears below the stats showing policy count and end time. Data sourced from `GET /analytics/stats` → `active_cycle` field.

- **Active Concerns section**: Open clusters sorted by total support (endorsements + members). Each card shows:
  - Cluster summary
  - Policy topic badge
  - Member count, endorsement count, total support
  - Click to navigate to cluster detail page

- **Ungrouped Submissions section**: Candidates not yet assigned to a cluster. Each card shows user submission blockquote (RTL-aware), AI interpretation, and confidence score.

- **Archived Concerns section** (at the bottom): Archived clusters that have been included in a voting cycle. Each card shows the same info as active concerns, plus an "Archived" badge. Section includes a description: "These concerns have been included in a voting cycle and are no longer accepting new submissions." Only appears when archived concerns exist.

### Cluster detail page (`/analytics/clusters/[id]`)

- **Cluster summary**: Full text in Farsi + English
- **Member submissions**: Anonymized list of policy candidates in this cluster
  - Show: original user submission text (`raw_text`), title, summary, policy_topic, policy_key, confidence score
  - Each candidate card matches the unclustered card format (user submission blockquote + AI interpretation)
  - Each card has `id="candidate-{uuid}"` anchor for deep linking
  - Do NOT show: user information, submission timestamps
- **Vote count**: If voting has happened, show approval count and rate

### API calls

Fetch data from the Python backend:
- `GET /api/analytics/clusters` → list of clusters with stats
- `GET /api/analytics/clusters/:id` → single cluster with member candidates (includes `raw_text` and `language`)
- `GET /api/analytics/unclustered` → current unclustered/noise candidates + count
- `GET /api/analytics/candidate/:id/location` → returns `{ status: "unclustered" }` or `{ status: "clustered", cluster_id: "..." }`

Create a typed API client:
```typescript
// web/lib/api.ts
export async function getClusters(): Promise<Cluster[]> { ... }
export async function getCluster(id: string): Promise<ClusterDetail> { ... }
```

### TypeScript types

```typescript
interface ClusterSummary {
  id: string;
  policy_topic: string;
  policy_key: string;
  summary: string;
  member_count: number;
  approval_count: number;
}

interface ClusterDetail extends ClusterSummary {
  candidates: PolicyCandidatePublic[];
}

interface UnclusteredResponse {
  total: number;
  items: UnclusteredItem[];
}

interface UnclusteredItem {
  id: string;
  title: string;
  summary: string;
  policy_topic: string;
  policy_key: string;
  confidence: number;
  raw_text: string;        // Original user submission text
  language: string;        // Detected input language (e.g. "fa", "en")
}

interface PolicyCandidatePublic {
  id: string;
  title: string;
  summary: string;
  policy_topic: string;
  policy_key: string;
  confidence: number;
  raw_text: string | null;   // Original user submission text
  language: string | null;   // Detected input language (e.g. "fa", "en")
}
```

### Empty states

- No grouped concerns yet: "No grouped concerns yet." / "هنوز دغدغه گروه‌بندی شده‌ای وجود ندارد."
- No archived concerns: section is hidden entirely
- Cluster with no votes: Show "No votes yet" instead of 0%

## Constraints

- NO login required. This page is fully public.
- Do NOT show any user-identifying information. Candidates are displayed without user references.
- Do NOT show raw submission text. Only the canonicalized form (title + summary).
- Server-side rendered (SSR) for SEO and fast initial load.
- Must work well in RTL (Farsi) layout.
- Unclustered/noise candidates must be visible on analytics (do not hide by default).

## Tests

Write tests covering:
- Analytics page renders cluster cards with correct data (mock API response)
- Cluster card displays summary, member count, approval count, policy_topic
- Clicking a cluster card navigates to detail page
- Cluster detail page shows member candidates
- Cluster detail page does NOT show user IDs or raw text
- Unclustered section renders count and anonymized candidate list
- Empty state renders when no clusters exist
- Sorting by member count works
- Topic filter works
- Page renders correctly in Farsi (RTL) and English (LTR)
