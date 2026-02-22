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

### Analytics page (`/analytics`)

Displays all clusters from the most recent clustering cycle.

- **Cluster cards grid**: Each card shows:
  - Cluster summary (Farsi primary, with English toggle)
  - Member count (number of submissions in this cluster)
  - Approval count (votes, if voting has happened)
  - Domain tag (e.g., "economy", "rights")
  - Variance flag indicator (if flagged as unstable)
  - Click to navigate to cluster detail page

- **Sorting options**: By member count (default), by approval count, by domain
- **Domain filter**: Filter clusters by PolicyDomain

- **Stats bar at top**: Total submissions, total clusters, unclustered submissions count, active voting cycle (yes/no)

- **Unclustered section** (transparency requirement):
  - Show count of candidates currently labeled as noise/unclustered
  - Show a paginated list of anonymized unclustered canonical candidates (title + summary + domain + confidence)
  - Include explanatory text: these items are retained and may be clustered in future cycles

### Cluster detail page (`/analytics/clusters/[id]`)

- **Cluster summary**: Full text in Farsi + English
- **Grouping rationale**: Why these submissions were grouped (from the LLM summarization)
- **Member submissions**: Anonymized list of canonical policy candidates in this cluster
  - Show: title, summary, domain, confidence score
  - Do NOT show: user information, submission timestamps, raw text
- **Vote count**: If voting has happened, show approval count and rate
- **Variance flag**: If flagged, show notice: "This cluster showed instability across multiple clustering runs."

### API calls

Fetch data from the Python backend:
- `GET /api/analytics/clusters` → list of clusters with stats
- `GET /api/analytics/clusters/:id` → single cluster with member candidates
- `GET /api/analytics/unclustered` → current unclustered/noise candidates + count

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
  summary: string;
  summary_en?: string;
  domain: PolicyDomain;
  member_count: number;
  approval_count: number;
  variance_flag: boolean;
}

interface ClusterDetail extends ClusterSummary {
  candidates: PolicyCandidatePublic[];
  grouping_rationale?: string;
}

interface UnclusteredResponse {
  total: number;
  items: PolicyCandidatePublic[];
}

interface PolicyCandidatePublic {
  id: string;
  title: string;
  title_en?: string;
  summary: string;
  summary_en?: string;
  domain: PolicyDomain;
  confidence: number;
}
```

### Empty states

- No clusters yet: "هنوز خوشه‌ای ایجاد نشده است." / "No clusters have been created yet."
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
- Cluster card displays summary, member count, approval count, domain
- Clicking a cluster card navigates to detail page
- Cluster detail page shows member candidates
- Cluster detail page does NOT show user IDs or raw text
- Unclustered section renders count and anonymized candidate list
- Empty state renders when no clusters exist
- Variance flag indicator shows for flagged clusters
- Sorting by member count works
- Domain filter works
- Page renders correctly in Farsi (RTL) and English (LTR)
