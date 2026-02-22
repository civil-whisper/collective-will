# MVP Specification: Collective Will v0

**Goal**: Surface what Iranians collectively want. Make consensus visible.

**Non-goal for v0**: Action execution against policymakers (deferred to v1).

---

## Table of Contents

0. [v0 Frozen Decisions](#v0-frozen-decisions)
1. [Product Overview](#1-product-overview)
2. [System Architecture](#2-system-architecture)
3. [Module Breakdown](#3-module-breakdown)
4. [Data Models](#4-data-models)
5. [User Flows](#5-user-flows)
6. [Technology Stack](#6-technology-stack)
7. [Design Decisions](#7-design-decisions)
8. [What's In / Out of Scope](#8-whats-in--out-of-scope)
9. [Open Questions](#9-open-questions)

---

## v0 Frozen Decisions

These decisions are locked for v0. They override any conflicting text elsewhere in the docs.

### Scope

- **v0 = consensus visibility + approval voting.** No action drafting, no action execution.
- Action planning and execution are deferred to v1.

### Channel

- **WhatsApp only** (via Evolution API, self-hosted). Telegram and Signal are deferred.
- Each additional channel multiplies verification complexity, abuse vectors, and maintenance overhead. Prove the end-to-end trust loop with one channel first.

### WhatsApp Gateway

- **v0**: Evolution API (self-hosted Docker container). No Meta business verification required. Suitable for development and early pilot (up to a few hundred users).
- **v1**: Migrate to official WhatsApp Business API when user count exceeds a few hundred or when stability/compliance requires it.
- The abstract channel interface (`channels/base.py`) ensures the swap only affects `whatsapp.py`.

### AI Models

- **Canonicalization**: Claude Sonnet (Farsi -> structured English), fallback configured.
- **Embeddings**: OpenAI `text-embedding-3-large` (quality-first in v0), with config-backed fallback (e.g., `mistral-embed`) for resilience/cost phases.
- **Cluster summaries**: `english_reasoning` tier defaults to Claude Sonnet with mandatory fallback (default: DeepSeek `deepseek-chat`).
- **User-facing messages**: `farsi_messages` tier defaults to Claude Sonnet with mandatory fallback (default: Claude Haiku).
- **Clustering algorithm**: HDBSCAN (runs locally on returned vectors).

### Identity and Sybil Resistance

- **Verification path**: email magic-link + WhatsApp account linking. One path, no alternatives in v0.
- **No mandatory phone verification.** WhatsApp linkage uses random opaque account refs; raw identifiers are isolated in a sealed mapping service and stripped from logs/exports.
- **No OAuth, no vouching, no KYC.** These add linkage/governance complexity and can exclude high-risk users.
- **Submission eligibility**: verified account (email + WhatsApp linked) + account age >= 48 hours.
- **Vote eligibility**: verified account + account age >= 48 hours + at least 1 accepted submission.
- **Adjudication autonomy**: Individual votes, disputes, and quarantine outcomes are resolved by autonomous agentic workflows (primary model + fallback/ensemble as needed). Humans do not decide per-item outcomes.

### Abuse Thresholds

| Control | Limit |
|---------|-------|
| Submissions per account per day | 5 |
| Accounts per email domain per day | 3 |
| Burst quarantine trigger | 3 submissions/5 minutes from one account (soft quarantine: accept + flag for automated adjudication) |
| Vote changes per cycle | 1 full vote re-submission per cycle (total max: 2 vote submissions/cycle) |
| Failed verification attempts | 5 per email per 24 hours, then 24-hour lockout |

Quarantined accounts are handled by policy-driven automated adjudication. Submissions from quarantined accounts are held (not processed or published) until the autonomous resolver applies release/hold rules.

### Evidence Store

- **Implementation**: PostgreSQL append-only hash-chain table. No UPDATE/DELETE permissions. Insert trigger validates chain integrity.
- **External anchoring**: Daily local Merkle-root computation is required in v0. External publication (Witness.co) is optional/config-driven.
- **Reproducibility metadata**: every evidence entry includes model version, prompt version, clustering parameters, run ID, and random seed where applicable.

### Dispute Handling

- Users flag bad canonicalization or cluster assignment via their authenticated dashboard.
- Autonomous dispute-resolution workflow targets completion within 72 hours.
- Disputed items are tagged (`dispute_open`, `dispute_resolved`) but never removed or suppressed.
- Resolution is logged to the evidence store with resolver model trace (primary/fallback/ensemble path).
- Disputes are resolved by re-running the pipeline or model escalation/ensemble, not by manual override of content.
- Humans may tune architecture/policy/risk controls, but do not resolve individual disputes/votes/quarantine cases.

### Data Retention and Deletion

| Data | Retention | Deletable on user request? |
|------|-----------|---------------------------|
| Evidence chain entries | Immutable, permanent | No (integrity of chain) |
| Account linkage (email, wa_id mapping) | Until deletion request | Yes (GDPR right to erasure) |
| Opaque user references in evidence chain | Permanent | No (but unlinkable after account deletion) |
| Raw submissions | Permanent (in evidence chain) | User link severed on deletion; text preserved anonymously |
| Votes | Permanent (pseudonymous) | User link severed on deletion |

When a user requests deletion, the account mapping is destroyed. Evidence chain entries remain but become unlinkable to any real identity.

### Infrastructure

- **Domain**: register via Njalla (WHOIS shows registrar, not owner). Credit card payment is acceptable.
- **Hosting**: use 1984.is VPS as primary production host (privacy jurisdiction). Not standard identity-verified providers like Hetzner.
- **All public-facing accounts**: pseudonymous (git, GitHub, project email via ProtonMail).
- **Non-public accounts** (WhatsApp Business API, LLM API, dev tools): regular accounts with credit card are acceptable.

### Pilot Success and Kill Criteria

**30-day checkpoint:**
- >= 50 registered users
- >= 20 submissions
- No critical security incidents
- Evidence chain integrity verified

**60-day checkpoint:**
- >= 100 registered users
- >= 50 total submissions
- >= 1 completed voting cycle
- \> 70% of surveyed users rate clustering as "fair" (4+ out of 5)
- < 10% dispute rate on canonicalization

**90-day kill criteria (stop if ANY is true):**
- < 100 registered users
- < 50 total submissions
- \> 40% negative satisfaction ratings
- Zero voting participation
- AI clustering accuracy < 60% (human evaluation)
- Critical unresolved security vulnerability

---

## 1. Product Overview

### Core Principle: Visibility and Trust

**Trust emerges from visibility, not authority.**

This is the foundational principle of the entire system. Every design decision in this MVP prioritizes:

1. **Visibility** — Users can see exactly what the system did with their input. Every submission, every canonicalization, every cluster assignment, every vote is traceable and publicly verifiable.

2. **Trust through transparency** — The system earns trust not by claiming to be fair, but by proving it. The evidence store, public analytics, and audit trail exist so anyone can verify the pipeline worked correctly.

3. **No hidden decisions** — The AI organizes, but doesn't editorialize. Clustering logic is published. Summaries link to source submissions. Nothing is suppressed.

4. **User sovereignty** — Users can dispute canonicalization, see which cluster their submission joined, verify their vote was counted, and trace the full history.

See [Visibility and Trust](visibility-and-trust.md) for the full technical approach to building verifiable trust.

### How Do I Know You're Not Manipulating the Results?

**Short answer: Don't trust us. Verify.**

| "What if you..." | Our answer |
|------------------|------------|
| ...change my submission? | Your original text is hashed and stored. The canonical form is separate. You can see both and flag if they don't match. |
| ...put me in the wrong cluster? | Every cluster links to its member submissions. Click through and judge for yourself. |
| ...don't count my vote? | Your vote is in the evidence store with a hash. You can verify it's there. The public tally includes it. |
| ...add fake votes? | Every vote links to a verified user. Registration requires email + messaging account verification. |
| ...delete things you don't like? | The evidence store is append-only with a hash chain. Deleting anything breaks the chain — publicly detectable. |
| ...bias the AI clustering? | We run clustering multiple times and flag variance. You can see the "why grouped" explanation for every cluster. |

**What we can't fully prevent in v0** (honest limitations):
- Operators with database access could theoretically insert fake users (solution: federation in v2)
- AI clustering could have subtle bias (solution: multi-run analysis, external audits)
- You have to trust our code is doing what we say (solution: open source, independent review)

**The v0 promise**: We publish everything. If we're cheating, you can catch us.

---

### Core Value Proposition

Iranians don't know what other Iranians want. The regime controls public discourse, diaspora is fragmented, and no neutral platform surfaces collective preferences. Collective Will v0 answers: **"What do we, as a people, actually want?"**

### User Story

> As an Iranian (inside or diaspora), I want to express what I care about and see what others care about, so I can understand where consensus exists and feel connected to a collective voice.

### Success Metrics (v0)

| Metric | Target |
|--------|--------|
| Registered users | >500 in first 3 months |
| Submissions | >200 unique policy concerns |
| Voting participation | >30% of registered users vote |
| Return visits (website) | >20% visit analytics weekly |
| **Trust: Fair representation** | >70% say clustering "fairly represents" their view |
| **Trust: Dispute rate** | <10% of users flag canonicalization as wrong |
| **Trust: Audit usage** | >5% of users check their submission trail |

---

## 2. System Architecture

### High-Level Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                         PUBLIC WEBSITE                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │
│  │  Landing    │  │  Analytics  │  │   User      │               │
│  │  + Subscribe│  │  Dashboard  │  │  Dashboard  │               │
│  └─────────────┘  └─────────────┘  └─────────────┘               │
└──────────────────────────────────────────────────────────────────┘
                              │
                              │ reads from
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                        CORE DATABASE                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │
│  │  Users   │ │Submissions│ │ Clusters │ │  Votes   │            │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │
│                                                                   │
│  ┌──────────────────────────────────────────────────┐            │
│  │              Evidence Store (audit log)           │            │
│  └──────────────────────────────────────────────────┘            │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              │ writes to
                              │
┌──────────────────────────────────────────────────────────────────┐
│                      PROCESSING PIPELINE                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │
│  │Canonicalize  │─▶│   Cluster    │─▶│    Agenda    │           │
│  │   Agent      │  │    Agent     │  │   Builder    │           │
│  └──────────────┘  └──────────────┘  └──────────────┘           │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              │ receives messages
                              │
┌──────────────────────────────────────────────────────────────────┐
│                    MESSAGING GATEWAY (Python)                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    FastAPI + Channels                     │   │
│  │  ┌─────────┐                                              │   │
│  │  │WhatsApp │  (Telegram, Signal deferred to post-v0)      │   │
│  │  │(Evo API)│                                              │   │
│  │  └─────────┘                                              │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
                              ▲
                              │
                           USERS
                    (WhatsApp only for v0)
```

### Module Boundaries

| Module | Responsibility | Talks To |
|--------|---------------|----------|
| **Messaging Gateway** | Receive/send messages, normalize across platforms | Pipeline, Database |
| **Processing Pipeline** | Canonicalize, cluster, build agenda | Database |
| **Core Database** | Store all data, provide queries | All modules |
| **Public Website** | Display analytics, user dashboard | Database (read-only) |
| **Evidence Store** | Append-only audit trail | Embedded in Database |

---

## 3. Module Breakdown

### 3.1 Messaging Gateway

**Purpose**: Interface with WhatsApp (v0 only channel). Normalize messages into common format. Architecture supports adding channels later via the abstract base class.

**Technology Choice**: **Direct channel integrations (Python)**

**Why direct integrations over a framework (like OpenClaw)**:
- Full control over code that runs — critical for a civic platform with security/trust requirements
- No framework lock-in or unexpected upstream changes
- Simpler architecture — only the code we need, nothing more
- Better auditability — every line is ours to inspect and explain
- Python ecosystem for AI/clustering is superior

**Channel libraries (v0)**:
- **WhatsApp**: Evolution API (self-hosted gateway) — handles Baileys complexity, exposes REST/webhooks

**Deferred channels** (post-v0, when trust loop is stable):
- **Telegram**: python-telegram-bot
- **Signal**: signal-cli + Python wrapper

**Key Components**:

```
src/
├── channels/
│   ├── __init__.py
│   ├── base.py              # Abstract channel interface
│   ├── whatsapp.py          # Evolution API client
│   └── types.py             # Unified message format
├── handlers/
│   ├── __init__.py
│   ├── intake.py            # Receives submissions
│   ├── voting.py            # Sends vote prompts, receives votes
│   └── notifications.py     # Sends updates to users
├── middleware/
│   ├── __init__.py
│   ├── audit.py             # Log to evidence store
│   └── validation.py        # Input validation
└── config.py
```

**Design Decisions**:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| v0 channel | WhatsApp only | Prove trust loop with one channel; each additional channel multiplies complexity |
| WhatsApp gateway | Evolution API (self-hosted) | No Meta approval needed; Docker container; migrate to official Business API at v1 |
| Account verification | Email magic-link + WhatsApp account linking | See [v0 Frozen Decisions](#v0-frozen-decisions) |
| Message format | Plain text, Farsi primary | Lowest friction; LLM handles translation |
| Session management | Stateless per-message | Simpler; state lives in database |

**WhatsApp Business API: Medium Risk (Acceptable)**

WhatsApp Business API requires Meta business verification, but this is **not a high-risk exposure**:
- Meta verification is NOT public record (unlike domain WHOIS)
- Iranian government cannot subpoena Meta (no jurisdiction)
- You're one of millions of Business API users
- No public link between your identity and the project

This is the same risk level as using Anthropic's API — acceptable for MVP.

**Setup options:**
1. **Direct registration** with Meta Business (credit card OK)
2. **Via BSP** like Twilio or MessageBird (one step removed)

See [operational-security.md](operational-security.md) for the full risk-tier framework.

---

### 3.2 Processing Pipeline

**Purpose**: Transform raw submissions into clustered policy positions.

**Sub-modules**:

#### 3.2.1 Canonicalization Agent

**Input**: Raw message text (Farsi or English)
**Output**: Structured `PolicyCandidate`

**Technology**: 
- **Model**: Anthropic Claude or Mistral API (cloud)
- **Data separation**: Only anonymous text sent to API; user IDs and metadata never leave local infrastructure

**Processing Steps**:
1. Store raw submission locally with user link (never sent to cloud)
2. Extract text only, strip all metadata
3. Batch submissions, shuffle order (breaks timing correlation)
4. Send anonymous text to cloud LLM for canonicalization
5. Detect language (Farsi, English, Kurdish, etc.)
6. Extract policy concern(s) — may yield multiple candidates from one message
7. Structure into `PolicyCandidate` schema
8. Compute semantic embedding via configured embedding tier (v0 default: OpenAI `text-embedding-3-large`; fallback configurable)
9. Store structured result, link back to original submission

**Prompt Strategy**:
```
You are a policy structuring assistant. Given a user's freeform concern, 
extract structured policy positions WITHOUT editorializing.

Rules:
- Preserve the user's intent exactly
- Do not add opinions or framing
- If the message contains multiple distinct concerns, output multiple candidates
- Flag uncertainty rather than guessing

Output JSON schema: {PolicyCandidate}
```

**Design Decisions**:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM location | Cloud (Anthropic/Mistral) | Simpler infrastructure for MVP; revisit at scale |
| Data separation | Text-only to cloud, user links stay local | Protects user identity while enabling AI processing |
| Multi-issue handling | Split into separate candidates | Research shows joint prediction works; preserves granularity |
| Language | Process in original language, translate for display | Preserves nuance; translation happens at display time |
| Confidence threshold | <0.7 confidence -> automated escalation/fallback path | Better to surface uncertainty than silently fail |
| Schema rigidity | Hybrid (required core + flexible extensions) | Balance between consistency and expressiveness |

#### 3.2.2 Clustering Agent

**Input**: Set of `PolicyCandidate` records with embeddings
**Output**: `Cluster` records with summaries

**Technology**:
- **Embeddings**: configured embedding tier (v0 default: OpenAI `text-embedding-3-large`, cloud) with fallback path for resilience/cost modes
- **Clustering**: HDBSCAN (density-based, no need to specify K) — runs locally on returned vectors
- **Summarization**: `english_reasoning` tier (v0 default Sonnet with mandatory fallback) — receives only aggregated/anonymized cluster content, not individual submissions

**Processing Steps**:
1. Load all candidates from current cycle (or delta since last run)
2. Compute/retrieve embeddings
3. Run HDBSCAN clustering
4. For each cluster:
   - Generate representative summary via LLM
   - Compute cluster statistics (size, diversity)
   - Link member candidates
5. Store clusters with audit trail

**Run Schedule**: 
- **Batch**: Every 6 hours
- **Future**: Consider incremental updates as volume grows

**Design Decisions**:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Clustering algorithm | HDBSCAN | No need to specify K; handles varying densities |
| Granularity control | `min_cluster_size=5` | Prevent micro-clusters; can tune based on feedback |
| Multi-run variance | Run 3x, flag high-variance clusters | Detect instability before publishing |
| Reproducibility | Log random seed, HDBSCAN params, prompt version, and run ID per cycle | If challenged, anyone can re-run the exact pipeline |
| Small clusters | Show all (no suppression) | Transparency principle; minorities visible |

#### 3.2.3 Agenda Builder

**Input**: Clusters from current cycle
**Output**: Voting agenda (subset of clusters)

**Logic for v0**: Simple — all clusters above minimum size go to voting. No editorial selection.

**Future considerations**:
- Diversity weighting (geographic, demographic)
- Recency vs. sustained interest
- Topic balancing

---

### 3.3 Core Database

**Purpose**: Single source of truth for all application data.

**Technology Choice**: **PostgreSQL**

**Why PostgreSQL**:
- Mature, reliable, well-understood
- JSONB for flexible schema fields
- Full-text search for Farsi (with `pg_trgm` or external index)
- Extensions: `pgvector` for embedding similarity search
- Easy to backup, replicate, audit

**Schema Overview**:

```sql
-- See Section 4 for full data models

-- Core tables
users
submissions
policy_candidates
clusters
votes
voting_cycles

-- Audit/evidence
evidence_log (append-only)
```

**Evidence Store Implementation**:

For v0, embed evidence store in PostgreSQL:

```sql
CREATE TABLE evidence_log (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    payload JSONB NOT NULL,
    hash TEXT NOT NULL,           -- SHA-256 of payload
    prev_hash TEXT NOT NULL,      -- Hash of previous entry (chain)
    
    -- Immutability enforced by:
    -- 1. No UPDATE/DELETE permissions on this table
    -- 2. Trigger that validates hash chain on INSERT
);

-- Index for verification queries
CREATE INDEX idx_evidence_hash ON evidence_log(hash);
CREATE INDEX idx_evidence_entity ON evidence_log(entity_type, entity_id);
```

**Witness.co Integration** (config-driven publication):
- Daily job must compute local Merkle root of day's evidence entries (required in v0)
- If publishing is enabled, submit root to Witness.co for anchoring
- Store publish attempt/result and anchor receipt in evidence metadata

**Design Decisions**:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Database | PostgreSQL | Mature, pgvector for embeddings, JSONB flexibility |
| Evidence store | Embedded hash-chain table | Simpler than separate system; sufficient for v0 scale |
| Blockchain anchoring | Required local roots; optional Witness publish | Keeps anchoring logic active while avoiding external dependency lock-in |
| Embedding storage | pgvector extension | Keep embeddings with data; similarity search built-in |

---

### 3.4 Public Website

**Purpose**: Display analytics, allow subscription, show user dashboard.

**Technology Choice**: **Next.js** (TypeScript)

**Why Next.js**:
- SSR for public analytics (SEO, fast initial load)
- React for interactive dashboards
- API routes for subscription flow
- TypeScript for type safety across data models
- Large ecosystem, easy to find developers

**Pages**:

```
# Core trust loop (ship first)
/                           # Landing + subscribe CTA
/analytics                  # Public dashboard (no login required)
/analytics/clusters         # Cluster explorer with drill-down
/dashboard                  # Logged-in user's personal view
/dashboard/submissions      # My submissions and their fate
/dashboard/votes            # My votes
/verify                     # Email/messaging verification flow
/about                      # Mission, methodology, team
/audit                      # Evidence explorer (technical users)

# Post-launch enhancements
/analytics/trends           # Time-series of policy interest
```

**Analytics Dashboard Components**:

*Core trust loop (ship first):*
1. **Cluster Explorer** — list of clusters with size, click to drill into summary + member submissions (anonymized)
2. **Submission Verification** — authenticated users can confirm their submission exists and trace its journey
3. **Audit Evidence Viewer** — hash chain explorer for technical users
4. **Top Policies** — ranked list with vote counts

*Post-launch enhancements:*
5. **Policy Landscape** — treemap or bubble chart of clusters by size
6. **Trends** — time-series of policy interest over cycles
7. **Recent Activity** — stream of anonymized submissions
8. **Demographic Breakdown** — if collected (deferred; privacy concerns)

**Design Decisions**:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Framework | Next.js (App Router) | SSR for public pages, React for dashboards |
| Styling | Tailwind CSS | Rapid development, consistent design |
| Charts | Recharts or D3 | Flexible, well-documented |
| i18n | next-intl | Farsi RTL support built-in |
| Auth | NextAuth.js with email magic links | Simple, no password management |

**Internationalization**:

- Primary: Farsi (RTL)
- Secondary: English
- UI chrome in both languages
- User-generated content displayed in original language with optional translation toggle

---

### 3.5 Voting Service

**Purpose**: Manage voting cycles, collect votes, tally results.

**Implementation**: Part of Messaging Gateway + Database

**Flow**:
1. Agenda Builder produces voting agenda
2. Voting Service creates `VotingCycle` record
3. Messaging Gateway sends vote prompts to all verified users
4. Users reply with votes (via messaging app)
5. Votes recorded in database
6. Cycle closes (time-based or threshold)
7. Results computed and published

**Voting Mechanism for v0**: **Approval Voting**

- User sees list of policies in current cycle
- User can approve any number (including zero)
- Final score = count of approvals
- Simple, understandable, no strategic complexity

**Message Format**:
```
🗳️ صندوق رای باز است!

این هفته، این سیاست‌ها مطرح شدند:

1. [Policy summary in Farsi]
2. [Policy summary in Farsi]
3. [Policy summary in Farsi]

برای رای دادن، شماره‌های موردنظر خود را بفرستید.
مثال: 1, 3

برای انصراف: "انصراف" بفرستید
```

**Design Decisions**:

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Mechanism | Approval voting | Simple, no vote-splitting, universally understood |
| Cycle duration | 48 hours | Long enough for global participation across timezones |
| Reminders | 1 reminder at 24h remaining | Balance engagement vs. annoyance |
| Minimum participation | No threshold for v0 | Learn what natural participation looks like first |

---

## 4. Data Models

### 4.1 User

```typescript
interface User {
  id: UUID;
  email: string;                    // For notifications, magic links
  emailVerified: boolean;
  
  // Messaging account (v0: WhatsApp only)
  messagingPlatform: 'whatsapp';    // Post-v0: 'whatsapp' | 'telegram' | 'signal'
  messagingAccountRef: string;      // Random opaque account ref; raw wa_id stays in sealed mapping
  messagingVerified: boolean;
  messagingAccountAge?: Date;       // For sybil scoring
  
  // Metadata
  createdAt: Date;
  lastActiveAt: Date;
  locale: 'fa' | 'en';              // Preferred language
  
  // Trust scoring (for future sybil resistance)
  trustScore: number;               // Computed from signals
  contributionCount: number;        // Approved submissions
  
  // Privacy
  isAnonymous: boolean;             // True = inside-Iran, extra care
}
```

### 4.2 Submission

```typescript
interface Submission {
  id: UUID;
  userId: UUID;
  
  // Content
  rawText: string;                  // Original message
  language: string;                 // Detected language code
  
  // Processing state
  status: 'pending' | 'processed' | 'flagged' | 'rejected';
  processedAt?: Date;
  
  // Audit
  hash: string;                     // SHA-256 of rawText
  createdAt: Date;
  evidenceLogId: number;            // Link to evidence store entry
}
```

### 4.3 PolicyCandidate

```typescript
interface PolicyCandidate {
  id: UUID;
  submissionId: UUID;               // Source submission
  
  // Structured content
  title: string;                    // 5-15 words
  titleEn?: string;                 // English translation
  domain: PolicyDomain;             // Enum: governance, economy, rights, etc.
  summary: string;                  // 1-3 sentences
  summaryEn?: string;
  stance: 'support' | 'oppose' | 'neutral' | 'unclear';
  
  // Extracted entities
  entities: string[];               // Named entities mentioned
  
  // For clustering
  embedding: number[];              // Vector from configured embedding tier (v0 default OpenAI text-embedding-3-large)
  
  // Quality signals
  confidence: number;               // LLM confidence 0-1
  ambiguityFlags: string[];         // e.g., 'sarcasm_possible', 'multi_issue'
  
  // Audit & reproducibility
  modelVersion: string;             // Which model produced this
  promptVersion: string;            // Version hash of the canonicalization prompt
  createdAt: Date;
  evidenceLogId: number;
}

enum PolicyDomain {
  GOVERNANCE = 'governance',        // System of government, elections
  ECONOMY = 'economy',              // Jobs, inflation, sanctions
  RIGHTS = 'rights',                // Human rights, women's rights
  FOREIGN_POLICY = 'foreign_policy',
  RELIGION = 'religion',            // Role of religion in state
  ETHNIC = 'ethnic',                // Minority rights
  JUSTICE = 'justice',              // Accountability, judiciary
  OTHER = 'other'
}
```

### 4.4 Cluster

```typescript
interface Cluster {
  id: UUID;
  cycleId: UUID;                    // Which clustering cycle
  
  // Content
  summary: string;                  // Representative summary (Farsi)
  summaryEn?: string;
  domain: PolicyDomain;
  
  // Members
  candidateIds: UUID[];             // PolicyCandidates in this cluster
  memberCount: number;
  
  // Clustering metadata & reproducibility
  centroidEmbedding: number[];
  cohesionScore: number;            // How tight is the cluster
  varianceFlag: boolean;            // True if multi-run showed instability
  runId: string;                    // Unique ID for this clustering run
  randomSeed: number;               // Seed used for reproducibility
  clusteringParams: object;         // HDBSCAN parameters used (min_cluster_size, etc.)
  
  // Voting
  approvalCount: number;            // Updated as votes come in
  
  // Audit
  createdAt: Date;
  evidenceLogId: number;
}
```

### 4.5 Vote

```typescript
interface Vote {
  id: UUID;
  userId: UUID;
  cycleId: UUID;
  
  // Vote content
  approvedClusterIds: UUID[];       // Clusters user approved
  
  // Audit
  createdAt: Date;
  evidenceLogId: number;
  
  // Privacy: votes are pseudonymous
  // User can see their own; aggregates are public
}
```

### 4.6 VotingCycle

```typescript
interface VotingCycle {
  id: UUID;
  
  // Timing
  startedAt: Date;
  endsAt: Date;
  status: 'active' | 'closed' | 'tallied';
  
  // Content
  clusterIds: UUID[];               // Clusters in this cycle's agenda
  
  // Results (populated after close)
  results?: {
    clusterId: UUID;
    approvalCount: number;
    approvalRate: number;           // approvals / total votes
  }[];
  totalVoters: number;
  
  // Audit
  evidenceLogId: number;
}
```

### 4.7 EvidenceLogEntry

```typescript
interface EvidenceLogEntry {
  id: number;                       // BIGSERIAL, monotonic
  timestamp: Date;
  
  eventType: 
    | 'submission_received'
    | 'candidate_created'
    | 'cluster_created'
    | 'cluster_updated'
    | 'vote_cast'
    | 'cycle_opened'
    | 'cycle_closed'
    | 'user_created'
    | 'user_verified';
  
  entityType: string;               // 'submission', 'cluster', etc.
  entityId: UUID;
  
  payload: object;                  // Full snapshot of entity at this point
  
  hash: string;                     // SHA-256(canonical JSON of {timestamp,event_type,entity_type,entity_id,payload,prev_hash})
  prevHash: string;                 // Previous entry's hash (chain)
}
```

---

## 5. User Flows

### 5.1 Subscription Flow

```
User visits website
        │
        ▼
   Landing page
   "What do Iranians want? Help us find out."
        │
        ▼
   [Subscribe] button
        │
        ▼
   Enter email
        │
        ▼
   Receive magic link email
        │
        ▼
   Click link → email verified
        │
        ▼
   Prompt: "Connect WhatsApp"
   (Show QR code or deep link)
        │
        ▼
   User messages bot from WhatsApp
        │
        ▼
   Bot verifies account link
   (Checks account ID, age)
        │
        ▼
   ✅ User fully verified
   Bot: "شما آماده‌اید! نگرانی‌های خود را با ما به اشتراک بگذارید."
```

### 5.2 Submission Flow

```
User sends WhatsApp message
"وضعیت اقتصادی خیلی بد است. تورم را کنترل کنید."
        │
        ▼
   Gateway receives message
   → Log to evidence store
        │
        ▼
   Canonicalization Agent
   → Extracts: {
       title: "کنترل تورم",
       domain: "economy",
       summary: "درخواست کنترل تورم و بهبود شرایط اقتصادی",
       confidence: 0.92
     }
   → Log to evidence store
        │
        ▼
   Store PolicyCandidate
   Compute embedding
        │
        ▼
   Reply to user:
   "✅ دریافت شد! نظر شما: «کنترل تورم»
    می‌توانید وضعیت آن را در وبسایت ببینید."
```

### 5.3 Clustering Flow (Batch)

```
Cron trigger (every 6 hours)
        │
        ▼
   Load new PolicyCandidates
   since last run
        │
        ▼
   Compute/retrieve embeddings
        │
        ▼
   Run HDBSCAN clustering
   (on all candidates, not just new)
        │
        ▼
   For each cluster:
   → Generate summary via LLM
   → Compute statistics
   → Log to evidence store
        │
        ▼
   Update cluster table
   (Merge with existing or create new)
        │
        ▼
   Website auto-refreshes
   (Public analytics update)
```

### 5.4 Voting Flow

```
Voting cycle starts (autonomous schedule/policy trigger)
        │
        ▼
   Agenda Builder selects clusters
   → All clusters with size ≥ 5
        │
        ▼
   Create VotingCycle record
   Log to evidence store
        │
        ▼
   For each verified user:
   → Send vote prompt via WhatsApp
        │
        ▼
   User replies: "1, 3, 5"
        │
        ▼
   Gateway parses vote
   → Validate cluster IDs
   → Create Vote record
   → Log to evidence store
        │
        ▼
   Reply: "✅ رای شما ثبت شد!"
        │
        ▼
   (48 hours later)
   Cycle closes
        │
        ▼
   Tally results
   Update cluster approvalCounts
   Log to evidence store
        │
        ▼
   Notify users:
   "نتایج رای‌گیری: [link]"
```

### 5.5 User Dashboard Flow

```
User visits /dashboard
        │
        ▼
   Auth check (magic link session)
        │
        ▼
   Load user's submissions
   For each:
   → Show original text
   → Show canonical form
   → Show which cluster it's in
   → Show cluster's current vote count
        │
        ▼
   Load user's votes
   For each cycle:
   → Show what they voted for
   → Show final results
        │
        ▼
   User can:
   → Flag if canonical form is wrong
   → See full audit trail
```

---

## 6. Technology Stack

### 6.1 Summary

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Messaging Gateway** | Python (FastAPI) | Direct channel control, unified codebase with pipeline |
| **AI Pipeline** | Python | Best ML ecosystem (transformers, HDBSCAN, scikit-learn) |
| **Database** | PostgreSQL + pgvector | Mature, embeddings, JSONB |
| **Website** | Next.js (TypeScript) | SSR, React, good i18n |
| **Hosting** | Single VPS (1984.is primary; Njalla VPS acceptable fallback) | Privacy-first; WHOIS hides owner; see [Frozen Decisions](#v0-frozen-decisions) |
| **Cloud LLM** | Anthropic Claude or Mistral API | EU/US providers with strong privacy posture |
| **Embeddings** | OpenAI `text-embedding-3-large` (cloud, config-backed fallback) | Quality-first in v0; fallback/cost tuning via config |

**LLM Strategy**: Cloud-first for MVP. Local GPU infrastructure deferred until critical mass justifies the complexity. See [Section 7.3](#73-why-cloud-first-for-mvp) for rationale and data separation approach.

### 6.2 Language Choices

**Python** for (primary language):
- Messaging Gateway (FastAPI + channel libraries)
- AI Pipeline (canonicalization, clustering)
- Best ecosystem: transformers, sentence-transformers, hdbscan, scikit-learn
- python-telegram-bot, httpx for Evolution API
- Unified codebase — simpler deployment, shared utilities

**TypeScript** for:
- Website (Next.js) — SSR benefits, React ecosystem
- Frontend components

**Why Python-first**:
- Clustering and embeddings are core to the pipeline — Python owns this space
- AI/LLM libraries are Python-first (Anthropic SDK, sentence-transformers)
- More readable/auditable — important for civic trust
- Single backend language simplifies deployment and maintenance
- Channel integrations work well in Python (python-telegram-bot is excellent)

**Shared**:
- Data models defined in Python (Pydantic), exported as JSON Schema for TypeScript
- Database is source of truth

### 6.3 Python Security & Best Practices

Python is chosen for its excellent ML/AI ecosystem and readability. We treat dependencies as a liability to manage.

#### Dependency Security

| Practice | Implementation |
|----------|----------------|
| **Minimal dependencies** | Every pip package is a risk; justify each one |
| **Lock versions** | Use `uv.lock` or `poetry.lock`; pin exact versions |
| **Audit regularly** | Run `pip-audit` or `safety` in CI; block deploys on critical vulns |
| **Avoid deep trees** | Prefer packages with few transitive dependencies |
| **Virtual environments** | Always use venv/uv; never install globally |

#### Memory Management

| Practice | Implementation |
|----------|----------------|
| **Stream large data** | Use generators/iterators; don't load full evidence store into memory |
| **Connection pooling** | Use SQLAlchemy connection pools; configure pool size appropriately |
| **Profile under load** | Test with realistic message volume before launch |
| **Set timeouts** | All external calls (DB, API) have timeouts via `httpx` or `asyncio.timeout` |
| **Async where appropriate** | Use `asyncio` for I/O-bound operations (API calls, DB queries) |

#### Secure Coding Practices

| Practice | Implementation |
|----------|----------------|
| **Type hints** | Use type hints everywhere; run `mypy` in strict mode |
| **Input validation** | Validate all user input with Pydantic; never trust messaging payloads |
| **No eval/exec** | Never execute dynamic code |
| **Parameterized queries** | Use SQLAlchemy ORM or parameterized queries; no string concatenation for SQL |
| **Secrets management** | Environment variables only; never in code; rotate regularly |
| **Rate limiting** | Use FastAPI middleware or `slowapi`; prevent abuse |

#### Crypto Operations

| Operation | Approach |
|-----------|----------|
| **Hashing (evidence store)** | Use Python built-in `hashlib` (C bindings); SHA-256 for evidence chain |
| **Future: signatures** | Use `cryptography` library (well-audited) or call Rust service |
| **Random generation** | Use `secrets` module, not `random` |

#### Code Quality

| Tool | Purpose |
|------|---------|
| **ruff** | Fast linting and formatting |
| **mypy** | Static type checking |
| **pytest** | Testing |
| **pre-commit** | Enforce checks before commit |

#### Migration Path (If Needed at Scale)

If we reach scale where Python becomes a bottleneck:

1. **Evidence store service** → Rewrite in Rust (crypto operations, append-only log)
2. **Hot paths** → Rewrite specific endpoints in Go/Rust if profiling shows need
3. **Keep Python for** → AI pipeline, clustering, LLM integration (Python wins here)

Design interfaces now (via API boundaries) so these rewrites are possible without full system redesign.

### 6.4 Project Structure

```
collective-will/
├── src/                          # Python backend (main application)
│   ├── __init__.py
│   │
│   ├── channels/                 # Messaging channel integrations
│   │   ├── __init__.py
│   │   ├── base.py              # Abstract channel interface
│   │   ├── whatsapp.py          # Evolution API client (v0 only channel)
│   │   └── types.py             # Unified message format
│   │
│   ├── handlers/                 # Message handlers
│   │   ├── __init__.py
│   │   ├── intake.py            # Receives submissions
│   │   ├── voting.py            # Sends vote prompts, receives votes
│   │   └── notifications.py     # Sends updates to users
│   │
│   ├── pipeline/                 # AI processing pipeline
│   │   ├── __init__.py
│   │   ├── canonicalize.py      # LLM canonicalization
│   │   ├── cluster.py           # HDBSCAN clustering
│   │   ├── embeddings.py        # sentence-transformers
│   │   └── agenda.py            # Agenda building
│   │
│   ├── models/                   # Pydantic data models
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── submission.py
│   │   ├── cluster.py
│   │   └── vote.py
│   │
│   ├── db/                       # Database layer
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── evidence.py          # Evidence store operations
│   │   └── queries.py
│   │
│   ├── api/                      # FastAPI application
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI app
│   │   ├── routes/
│   │   │   ├── webhooks.py      # Channel webhooks
│   │   │   ├── analytics.py     # Public analytics API
│   │   │   └── user.py          # User dashboard API
│   │   └── middleware/
│   │       ├── audit.py
│   │       └── auth.py
│   │
│   ├── scheduler.py              # Background job scheduler
│   └── config.py                 # Configuration management
│
├── migrations/                   # Database migrations (Alembic)
│   ├── versions/
│   └── alembic.ini
│
├── web/                          # Next.js website
│   ├── app/
│   │   ├── page.tsx             # Landing
│   │   ├── analytics/
│   │   ├── dashboard/
│   │   └── api/                 # API routes (proxied to Python backend)
│   ├── components/
│   ├── lib/
│   ├── messages/                # i18n strings
│   │   ├── fa.json
│   │   └── en.json
│   ├── package.json
│   └── tsconfig.json
│
├── tests/                        # Python tests
│   ├── __init__.py
│   ├── test_channels/
│   ├── test_pipeline/
│   └── test_api/
│
├── docs/                         # Documentation (existing)
├── docker-compose.yml            # Local development
├── docker-compose.prod.yml       # Production
├── pyproject.toml                # Python project config (uv/poetry)
├── requirements.txt              # Pinned dependencies
└── README.md
```

### 6.5 Development Setup

```bash
# Prerequisites
- Python 3.11+
- Node.js 20+ (for website only)
- PostgreSQL 15+
- Docker (optional, for easy setup)
- uv (recommended) or pip for Python dependency management

# Quick start
docker-compose up -d postgres      # Start database
uv sync                            # Install Python dependencies
alembic upgrade head               # Run migrations
uv run python -m src.api.main      # Start FastAPI backend

# In another terminal (for website):
cd web && pnpm install && pnpm dev

# Or run everything with Docker:
docker-compose up -d

# Individual services:
uv run python -m src.api.main      # API server
uv run python -m src.scheduler     # Background jobs
cd web && pnpm dev                 # Website
```

### 6.6 Production Deployment

**Single-server deployment for v0** (simplicity over scale).

> **📖 See [Infrastructure Guide](infrastructure-guide.md)** for complete step-by-step setup instructions.

**Architecture Summary:**

```
Internet → Cloudflare (DNS/CDN) → 1984.is VPS (primary)
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                 │
                    ▼                 ▼                 ▼
                  nginx ──────► web (Next.js)      backend
                    │               │             (FastAPI)
                    │               │                 │
                    │               └────────┬────────┘
                    │                        ▼
                    │                    postgres
                    │                   (pgvector)
                    │                        │
                    └──► scheduler ──────────┘
                        (background jobs)
```

**Recommended Setup:**

| Component | Specification |
|-----------|---------------|
| Provider | **1984.is VPS** (primary), with Njalla VPS as fallback |
| Plan | 4GB+ RAM VPS |
| Jurisdiction | Iceland (1984.is primary), Sweden (Njalla fallback) |
| OS | Ubuntu 22.04 LTS |
| Deployment | Docker Compose |

**Why privacy-first hosting (not Hetzner/AWS):**
- **WHOIS shows registrar, not you** — the key protection for contributor safety
- **Privacy jurisdiction** (Sweden/Iceland) — requires local legal process to reveal customer
- **Credit card payment is acceptable** — privacy comes from the provider model, not payment method
- **Sufficient for MVP** — handles <1000 concurrent users easily

See [Operational Security Guide](operational-security.md) for the full risk-tier framework.

**Monthly Cost Breakdown:**

| Item | Cost |
|------|------|
| VPS (Njalla 4GB) | ~€30 (~$32) |
| LLM API (Anthropic/Mistral) | $5-15 |
| Domain (Njalla, amortized) | ~$1 |
| DNS/CDN (Cloudflare) | Free |
| SSL (Let's Encrypt) | Free |
| **Total** | **~$40-50/month** |

**Infrastructure Guide covers:**
- [ ] Server provisioning and SSH setup
- [ ] Docker installation and configuration  
- [ ] Domain, DNS (Cloudflare), and HTTPS (Let's Encrypt)
- [ ] Database access methods (SSH tunnel, GUI tools)
- [ ] Automated backup strategy
- [ ] Security hardening (firewall, fail2ban, etc.)
- [ ] Monitoring and alerting

**Future scaling**: When volume exceeds ~10K submissions/month, consider dedicated server with GPU for local LLM inference.

---

## 7. Design Decisions

### 7.0 Visibility and Trust as Non-Negotiable

Every feature in v0 is filtered through one question: **"Can a user verify this?"**

| Principle | Implementation |
|-----------|----------------|
| **Every input is preserved** | Raw submissions stored with hash; never modified |
| **Every AI decision is logged** | Canonicalization, clustering logged to evidence store with model version |
| **Every cluster is traceable** | Click any cluster → see member submissions |
| **Every vote is verifiable** | User can see their vote in dashboard; aggregate tallies are public |
| **No suppression** | All clusters shown, even small ones; no editorial filtering |
| **Public by default** | Analytics visible to anyone; no login wall for transparency |

This is why we have an evidence store, why clustering shows "why these were grouped," why users can flag bad canonicalization, and why the audit explorer exists.

**If we can't make it visible, we don't build it.**

---

### 7.0.1 Contributor Safety and Anonymity

**The problem**: Contributors may have family in Iran. If identity is linked to this project, families could face pressure.

**The principle**: The key is **publicly discoverable** vs **requires subpoena**. Use privacy-focused providers; credit card is fine.

| Vector | Risk | Approach |
|--------|------|----------|
| Regular domain registrar | **High** | Your name in WHOIS — DON'T USE |
| Regular hosting (Hetzner) | **High** | Identity verified — DON'T USE |
| Git commits with real name | **High** | Permanent in history — USE PSEUDONYM |
| GitHub with real identity | **High** | Public profile — USE PSEUDONYM |
| Njalla domain | Medium | WHOIS shows Njalla — credit card OK |
| 1984.is hosting (Njalla fallback) | Medium | Privacy jurisdiction — credit card OK |
| WhatsApp Business API | Medium | Not public — credit card OK |
| LLM API accounts | Medium | Not public — credit card OK |

**Key insight**: The protection comes from **using privacy-focused registrar/host** (Njalla, 1984.is), not from paying with crypto. Credit card is acceptable.

**MVP requirements**:
- Domain via Njalla + hosting via 1984.is (credit card OK)
- Pseudonymous identity for code (git, GitHub, public comms)
- Regular accounts OK for WhatsApp, LLM APIs, dev tools

See **[Operational Security Guide](operational-security.md)** for implementation details.

**Long-term goal**: Decentralize so project can run without any single identity exposure point.

---

### 7.1 Why Direct Channel Integrations (Not a Framework)

| Alternative | Pros | Cons | Decision |
|-------------|------|------|----------|
| **OpenClaw** | Ready integrations, agent model | Framework lock-in, TypeScript, security model for personal use not civic platforms | ❌ |
| **Automagik Omni** | Multi-channel hub, Python | Newer project, another dependency | ❌ |
| **Twilio + custom** | Well-documented API | Higher cost, vendor dependency | ❌ |
| **Direct libraries** | Full control, Python-native, auditable | Some integration work | ✅ |

**Why we chose direct integrations:**
- **Security**: Full control over what code runs — critical for civic trust
- **Auditability**: Every line is ours to inspect and explain
- **Simplicity**: Only the code we need, no framework ecosystem
- **Python ecosystem**: Unified codebase with AI/clustering pipeline
- **No upstream risk**: Framework changes don't affect us

**Channel-specific choices (v0: WhatsApp only):**
- **WhatsApp**: Evolution API (self-hosted gateway) wraps Baileys complexity, exposes clean REST/webhooks

**Post-v0 candidates:**
- **Telegram**: python-telegram-bot — excellent library, 25k+ stars, well-maintained
- **Signal**: signal-cli + Python wrapper — the actively maintained option for Signal bots

### 7.2 Why PostgreSQL (not specialized stores)

| Alternative | Use Case | Why Not for v0 |
|-------------|----------|----------------|
| **Kafka** | Append-only log | Overkill; hash-chain in Postgres sufficient |
| **MongoDB** | Flexible schema | Postgres JSONB is enough; lose ACID |
| **Pinecone** | Vector search | pgvector sufficient; one less service |
| **Redis** | Caching | Premature optimization |

### 7.3 Why Cloud-First for MVP

| Approach | Infra Cost | LLM Cost (1K submissions) | Complexity |
|----------|------------|---------------------------|------------|
| **GPU server + local LLM** | ~$150-200/mo | ~$0.50 | High (GPU procurement, vLLM setup, model management) |
| **VPS + cloud LLM** | ~$50/mo | ~$5-15 | Low (standard VPS, API calls) |

**Decision**: Cloud-first for MVP. At 500 users / ~200 submissions, API costs are negligible (~$5-15/month). GPU infrastructure complexity is not justified until we reach critical mass.

**When to revisit**: Consider local LLM infrastructure when:
- Submission volume exceeds ~10K/month (cost crossover)
- Privacy requirements escalate (e.g., government partnership)
- Latency becomes critical (real-time processing needed)

#### Data Separation Strategy

The key concern with cloud LLMs is privacy for users inside Iran whose political views could be dangerous if exposed.

**What stays local (never sent to cloud):**
- User identifiers and account information
- Submission-to-user mapping
- Timing metadata that could correlate submissions

**What goes to cloud LLM/embedding API (anonymized):**
- Submission text only (stripped of all context) — for canonicalization and embedding
- Batched and shuffled to break timing correlation
- Cluster summaries (aggregated content, not individual voices)

**Note on embeddings**: v0 uses a quality-first cloud embedding tier (default OpenAI `text-embedding-3-large`) with config-backed fallback. The text sent for embedding is the same anonymized canonicalized text already sent for canonicalization — no additional privacy exposure.

**Provider selection criteria:**
| Provider | Jurisdiction | Data Handling | Recommendation |
|----------|-------------|---------------|----------------|
| **Anthropic Claude** | US | No training on API data, SOC2 | ✅ Good for MVP |
| **Mistral** | France/EU | EU data residency, GDPR compliant | ✅ Good for MVP |
| **DeepSeek** | China | Unclear data handling | ❌ Avoid for sensitive content |
| **OpenAI** | US | Enterprise tier has strong privacy | ⚠️ Acceptable |

**Implementation pattern:**

```
User submission → Store locally with user_id
                         ↓
              Strip metadata, extract text only
                         ↓
              Batch submissions (every 6 hours)
                         ↓
              Shuffle batch order
                         ↓
              Send anonymous text[] to cloud LLM
                         ↓
              Receive structured PolicyCandidate[]
                         ↓
              Match results back to local submissions
                         ↓
              Store with audit trail
```

**Threat model acknowledgment**: Even anonymized political text in bulk could theoretically be valuable to adversaries, but it represents aggregate opinions without individual identification. The user-to-submission link is the critical secret, and that never leaves local infrastructure.

### 7.4 Why Approval Voting

| Mechanism | Comprehension | Strategic Resistance | Implementation |
|-----------|--------------|---------------------|----------------|
| **Plurality** | Universal | Low | Trivial |
| **Approval** | High | Medium | Simple |
| **Ranked choice** | Medium | High | Complex |
| **Quadratic** | Low-Medium | Medium-High | Complex + needs credits |

**Decision**: Approval voting. Users understand it, implementation is simple, no vote-splitting problem.

### 7.5 Why Batch Clustering (not real-time)

- **Stability**: Clusters don't jump around as users watch
- **Efficiency**: Embedding computation is batched
- **Simplicity**: No complex incremental clustering logic
- **Audit**: Clear cycle boundaries in evidence store

**Tradeoff**: 6-hour delay between submission and cluster assignment. Acceptable for v0.

### 7.6 Why Public Analytics (no login wall)

- **Purpose**: Make collective will visible to everyone
- **Trust**: Transparency builds credibility
- **Reach**: Journalists, policymakers can cite without account
- **Safety**: Aggregated data doesn't expose individuals

### 7.7 Identity: Why No Phone Numbers

Per research: Iranian SIAM system uses phone numbers for surveillance. Platform must not require phone verification.

**v0 identity model** (see [Frozen Decisions](#v0-frozen-decisions)):
- Email magic-link verification
- WhatsApp account linking (random opaque account refs; raw wa_id isolated in sealed mapping service)
- Account age threshold (48 hours) before submissions
- Contribution threshold (1+ accepted contribution) before voting (processed submission or pre-ballot endorsement)
- No OAuth, no vouching, no KYC — these add linkage/governance complexity and exclude high-risk users

---

### 7.8 Coercion-Resistant Verification

**The problem**: In authoritarian contexts, users may be forced to prove how they voted or what they submitted. A verification system that lets users prove inclusion to themselves must not create transferable proof that a third party could demand.

**Design principles**:

| Principle | Implementation |
|-----------|----------------|
| **Self-only verification** | Users can verify their submission/vote exists via their authenticated dashboard, but cannot export a standalone proof |
| **No transferable receipts** | Verification tokens are session-bound; they prove inclusion to the logged-in user, not to an arbitrary third party |
| **Timestamp obfuscation** | Submissions are batched and shuffled before processing; individual timing is not exposed in public views |
| **Plausible deniability** | Users can see aggregate results but cannot prove their individual contribution to an outside observer |

**What this means concretely**:
- The `/verify` endpoint requires authentication — no anonymous proof lookup
- The evidence store is public for aggregate chain integrity, but individual entries are keyed by internal IDs, not user-facing tokens
- Vote records are pseudonymous: users see their own votes in their dashboard, but cannot generate a shareable "I voted for X" certificate

**Tradeoff acknowledged**: This reduces transparency slightly (a user cannot independently prove to a journalist "my vote was counted"). We accept this tradeoff because coercion resistance is more important in the Iran context than third-party verifiability. External auditors can verify the aggregate chain without individual attribution.

---

## 8. What's In / Out of Scope

### In Scope (v0)

| Feature | Notes |
|---------|-------|
| WhatsApp submission intake | Only channel for v0 (via Evolution API) |
| Email verification | Magic links, no passwords |
| WhatsApp account linking | Tokenized via HMAC; raw ID isolated |
| Canonicalization (LLM) | Cloud API (Anthropic/Mistral) with data separation |
| Clustering (HDBSCAN) | Batch every 6 hours |
| Approval voting | Via WhatsApp; no action execution |
| Public analytics dashboard | Anyone can view, no login wall |
| User dashboard | See own submissions/votes, flag disputes |
| Evidence store | Hash-chain in Postgres; external anchoring optional |
| Farsi + English UI | RTL support |
| Basic audit explorer | For technical users |
| Abuse controls | Rate limits, burst detection, quarantine (see Frozen Decisions) |

### Out of Scope (v0)

| Feature | Why Deferred |
|---------|-------------|
| Action execution / drafting | v0 is about visibility and consensus, not action |
| Telegram intake | Prove trust loop with WhatsApp first |
| Signal integration | Lower priority; add if demand |
| Phone verification | Surveillance risk in Iran context; see Frozen Decisions |
| OAuth / Google verification | Adds linkage risk; deferred |
| Vouching / progressive trust | Governance complexity; deferred |
| Quadratic/conviction voting | Start simple, iterate |
| Federation/decentralization | Single server sufficient for pilot |
| Blockchain anchoring (external publication required) | Daily local Merkle computation required in v0; external publication can be required later |
| Mobile app | Website + messaging app sufficient |
| AI-generated translations | Use automated quality checks + fallback/ensemble; no per-item human review |
| Demographic collection | Privacy concerns; add carefully later |
| Bridging algorithm | Can add after basic voting works |

---

## 9. Open Questions

### Resolved by Frozen Decisions

The following are now locked. See [v0 Frozen Decisions](#v0-frozen-decisions):
- Identity/verification model
- Evidence store implementation and anchoring policy
- Channel scope (WhatsApp only)
- Vote eligibility and abuse thresholds
- Dispute handling process
- Data retention/deletion policy
- Pilot success/kill criteria
- Infrastructure provider choice

### Must Resolve Before Build

1. ~~**WhatsApp Business API access**~~ — **Resolved.** Use Evolution API (self-hosted) for v0. Migrate to official Business API at v1. See [Frozen Decisions](#v0-frozen-decisions).

2. **Evolution API deployment** — Self-hosted WhatsApp gateway. Docker setup, connection stability, reconnection handling. (Can resolve during Milestone 1.)

3. **Cluster summary quality** — Need sample data to test. Where do we get realistic Farsi policy submissions for development? (Can synthesize with LLM for dev/testing.)

### Can Resolve During Build

4. **Voting cycle timing** — Start with 48 hours, adjust based on participation patterns.

5. **Cluster granularity** — Start with `min_cluster_size=5`, tune based on feedback.

### Can Resolve After Launch

6. **Optimal clustering frequency** — 6 hours to start; could go to real-time if needed.

7. **Translation strategy** — LLM auto-translate vs. automated QA/fallback vs. community edit.

8. **Demographic insights** — If/when/how to collect and display.

---

## Appendix A: Evidence Store Events

| Event | Payload |
|-------|---------|
| `submission_received` | `{ submissionId, userId, rawText, hash, timestamp }` |
| `candidate_created` | `{ candidateId, submissionId, title, domain, summary, confidence, modelVersion, promptVersion }` |
| `cluster_created` | `{ clusterId, cycleId, summary, candidateIds, memberCount, runId, randomSeed, clusteringParams }` |
| `cluster_updated` | `{ clusterId, candidateIds, memberCount, reason }` |
| `vote_cast` | `{ voteId, userId, cycleId, approvedClusterIds }` |
| `cycle_opened` | `{ cycleId, clusterIds, startsAt, endsAt }` |
| `cycle_closed` | `{ cycleId, results, totalVoters }` |
| `user_created` | `{ userId, email, messagingPlatform }` |
| `user_verified` | `{ userId, verificationType, timestamp }` |

---

## Appendix B: API Endpoints (Website)

```
GET  /api/analytics/clusters          # Public: all clusters with stats
GET  /api/analytics/clusters/:id      # Public: cluster detail + members
GET  /api/analytics/trends            # Public: time-series data
GET  /api/cycles                      # Public: voting cycles
GET  /api/cycles/:id/results          # Public: cycle results

POST /api/auth/subscribe              # Start subscription flow
GET  /api/auth/verify                 # Verify magic link
POST /api/auth/link-messaging         # Initiate messaging link

GET  /api/user/me                     # Authenticated: user profile
GET  /api/user/submissions            # Authenticated: my submissions
GET  /api/user/votes                  # Authenticated: my votes
POST /api/user/flag                   # Authenticated: flag bad canonicalization

GET  /api/evidence/:hash              # Public: verify evidence entry
GET  /api/evidence/chain              # Public: verify hash chain integrity
```

---

## Appendix C: Messaging Commands

| User Input | Bot Response |
|------------|--------------|
| (any freeform text) | Process as submission → confirmation |
| `وضعیت` / `status` | Show pending submissions, active votes |
| `کمک` / `help` | Show available commands |
| `رای` / `vote` | Show current voting agenda (if active) |
| `1, 3, 5` (during voting) | Record vote → confirmation |
| `انصراف` / `skip` | Skip current voting cycle |
| `زبان` / `language` | Toggle Farsi/English |

---

## Appendix D: Milestones

### Milestone 1: Foundation (Week 1-2)
- [ ] Set up Python project structure
- [ ] PostgreSQL schema + migrations (Alembic)
- [ ] FastAPI skeleton with health check
- [ ] Evolution API setup for WhatsApp
- [ ] "Hello world" message round-trip

### Milestone 2: Pipeline (Week 3-4)
- [ ] Canonicalization agent (cloud API with data separation)
- [ ] Embedding computation (local, CPU)
- [ ] HDBSCAN clustering
- [ ] Batch scheduler

### Milestone 3: Website (Week 5-6)
- [ ] Next.js setup with Farsi/English
- [ ] Public analytics dashboard
- [ ] User authentication (magic links)
- [ ] User dashboard

### Milestone 4: Voting (Week 7-8)
- [ ] Voting cycle management
- [ ] Vote collection via WhatsApp
- [ ] Results display
- [ ] Evidence store integration

### Milestone 5: Polish (Week 9-10)
- [ ] End-to-end testing
- [ ] Security review
- [ ] Documentation
- [ ] Soft launch with test users

---

*This specification will evolve. All decisions are documented so they can be revisited as we learn from real usage.*
