# Task: User Dashboard — Submissions and Votes

## Depends on
- `website/03-auth-magic-links` (authentication, protected routes)
- `website/01-nextjs-setup-i18n` (i18n, layout)

## Goal
Build the authenticated user dashboard where users can see their submissions (with canonical forms and cluster assignments) and their voting history.

## Files to create

- `web/app/[locale]/dashboard/page.tsx` — dashboard overview
- `web/app/[locale]/dashboard/submissions/page.tsx` — my submissions
- `web/app/[locale]/dashboard/votes/page.tsx` — my votes
- `web/components/SubmissionCard.tsx` — single submission view
- `web/components/VoteHistoryCard.tsx` — single vote record
- `web/messages/fa.json` — add dashboard translations
- `web/messages/en.json` — add dashboard translations

## Specification

### Dashboard overview (`/dashboard`)

A summary page showing:
- Total submissions count
- Total votes cast
- Account status (verified / pending)
- Quick links to submissions and votes pages
- WhatsApp connection status

### My submissions (`/dashboard/submissions`)

List of the user's submissions, most recent first.

Each submission card shows:
- **Original text**: The raw Farsi text the user submitted
- **Canonical form**: The structured PolicyCandidate (title + summary) created by the AI
- **Status**: pending / processed / flagged
- **Cluster**: If processed, which cluster this submission belongs to (link to cluster detail)
- **Cluster vote count**: How many people approved that cluster
- **Submitted at**: Timestamp
- **Flag button**: Dispute the canonicalization (links to task 07)

This is the "see what the system did with your input" view — critical for trust.

### My votes (`/dashboard/votes`)

List of voting cycles the user participated in.

Each vote record shows:
- **Cycle dates**: When the cycle ran
- **What I voted for**: List of clusters the user approved
- **Cycle results**: Final ranking of the cycle (with user's choices highlighted)
- **My vote counted**: Confirmation that the vote is in the evidence store

### API calls

- `GET /api/user/submissions` → user's submissions with canonical forms and cluster info
- `GET /api/user/votes` → user's vote history with cycle results
- `GET /api/user/me` → user profile

Add to API client (these require auth header):
```typescript
export async function getMySubmissions(): Promise<UserSubmission[]> { ... }
export async function getMyVotes(): Promise<UserVote[]> { ... }
export async function getMyProfile(): Promise<UserProfile> { ... }
```

### TypeScript types

```typescript
interface UserSubmission {
  id: string;
  raw_text: string;
  status: "pending" | "processed" | "flagged" | "rejected";
  created_at: string;
  candidate?: {
    title: string;
    summary: string;
    domain: PolicyDomain;
    confidence: number;
  };
  cluster?: {
    id: string;
    summary: string;
    approval_count: number;
  };
}

interface UserVote {
  cycle_id: string;
  cycle_started_at: string;
  cycle_ended_at: string;
  approved_clusters: {
    id: string;
    summary: string;
    final_approval_count: number;
    final_rank: number;
  }[];
  total_voters: number;
}
```

### Empty states

- No submissions: "شما هنوز نظری ارسال نکرده‌اید." / "You haven't submitted any concerns yet." + CTA to connect WhatsApp
- No votes: "شما هنوز رای نداده‌اید." / "You haven't voted yet."
- Pending submission: Show "در حال پردازش..." / "Processing..." with explanation that batch runs every 6 hours

## Constraints

- ALL dashboard pages require authentication. Redirect to login if not authenticated.
- Users can only see their OWN submissions and votes. The API must enforce this.
- Show the original raw text only to the submitting user. It is NOT shown on public analytics.
- The "my vote counted" indicator should reference the evidence store entry (show evidence hash, not a fake checkmark).

## Tests

Write tests covering:
- Unauthenticated access to `/dashboard` redirects to sign-in
- Dashboard overview renders with correct summary counts (mock API)
- Submissions page lists user's submissions with canonical forms
- Submission card shows original text, canonical title, status, cluster link
- Pending submission shows "processing" state
- Votes page lists user's voting history
- Vote record highlights which clusters the user approved
- Empty states render correctly for both submissions and votes
- Page renders in Farsi (RTL) and English (LTR)
