# Task: Audit Evidence Explorer

## Depends on
- `website/01-nextjs-setup-i18n` (Next.js project with i18n)

## Goal
Build a public evidence chain explorer that lets technical users verify the integrity of the system's audit trail. This is the ultimate trust mechanism — anyone can check that nothing was tampered with.

## Files to create

- `web/app/[locale]/audit/page.tsx` — evidence explorer page
- `web/components/EvidenceChainViewer.tsx` — chain visualization
- `web/components/EvidenceEntryCard.tsx` — single evidence entry
- `web/components/ChainVerifier.tsx` — client-side chain verification
- `web/messages/fa.json` — add audit translations
- `web/messages/en.json` — add audit translations

## Specification

### Audit page (`/audit`)

A public page (no auth required) for exploring and verifying the evidence chain.

Sections:
1. **Chain status**: Green/red indicator showing chain integrity status
2. **Chain statistics**: Total entries, first entry date, last entry date
3. **Entry browser**: Paginated list of evidence entries
4. **Search**: Search by entity ID, hash, or event type
5. **Verify button**: Run client-side chain verification

### EvidenceChainViewer

Paginated list of evidence log entries, most recent first.

Each entry shows:
- Entry ID (sequence number)
- Timestamp
- Event type (e.g., `submission_received`, `vote_cast`)
- Entity type and ID
- Hash (truncated, expandable)
- Previous hash (truncated, expandable)
- Chain link indicator (visual arrow connecting prev_hash to previous entry's hash)

### EvidenceEntryCard

Expandable card showing full entry details:
- All fields listed above
- Full payload (JSON, formatted)
- Full hash and prev_hash (copyable)

The payload should NOT contain user-identifying information (the backend strips this before serving).

### ChainVerifier

Client-side JavaScript that verifies the hash chain:

```typescript
async function verifyChain(entries: EvidenceEntry[]): Promise<VerificationResult> {
  // For each entry:
  // 1. Build canonical entry material: {timestamp,event_type,entity_type,entity_id,payload,prev_hash}
  // 2. Compute SHA-256 of canonical serialized entry material
  // 3. Verify it matches the stored hash
  // 4. Verify prev_hash matches previous entry's hash
  // Return: { valid: boolean, entriesChecked: number, brokenAt?: number }
}
```

Uses the Web Crypto API for SHA-256:
```typescript
async function sha256(text: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(text);
  const hash = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hash))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
}
```

The verification runs in the browser — the user doesn't need to trust the server's verification endpoint.

### API calls

- `GET /api/evidence/chain?page=1&per_page=50` → paginated evidence entries
- `GET /api/evidence/:hash` → single entry by hash
- `GET /api/evidence/chain/stats` → chain statistics

### Search

- By entity ID: find all evidence entries for a specific submission, cluster, or user action
- By hash: find a specific entry by its hash
- By event type: filter to specific events (e.g., only `vote_cast`)

### TypeScript types

```typescript
interface EvidenceEntry {
  id: number;
  timestamp: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  payload: Record<string, unknown>;
  hash: string;
  prev_hash: string;
}

interface ChainStats {
  total_entries: number;
  first_entry: string;       // timestamp
  last_entry: string;
  chain_valid: boolean;       // Server-side verification result
}

interface VerificationResult {
  valid: boolean;
  entries_checked: number;
  broken_at?: number;         // Entry ID where chain broke
  error?: string;
}
```

## Constraints

- NO login required. The audit trail is public.
- The payload displayed must NOT contain raw user IDs, emails, or WhatsApp IDs. The backend must strip these before serving. Only tokenized references and non-identifying data.
- Client-side verification is the key feature. Users must be able to verify the chain WITHOUT trusting the server.
- Hash computation on client must match server computation exactly: canonical JSON over full entry material with sorted keys and compact separators.
- Pagination is required — do not attempt to load the entire chain at once.

## Tests

Write tests covering:
- Audit page renders chain status and statistics (mock API)
- Evidence entries display with correct fields
- Entry card expands to show full payload
- Search by entity ID returns matching entries
- Search by event type filters correctly
- `verifyChain()` returns valid=true for a correct chain (construct test data in JS)
- `verifyChain()` returns valid=false with broken_at when a hash doesn't match
- `verifyChain()` returns valid=false when metadata is tampered (`event_type`, `entity_type`, `entity_id`, or `timestamp`)
- `verifyChain()` returns valid=false when prev_hash chain is broken
- Canonical entry serialization + SHA-256 computation matches Python's output (known parity fixture)
- Pagination controls work (next/prev page)
- Page is public (no auth redirect)
- Renders in Farsi (RTL) and English (LTR)
