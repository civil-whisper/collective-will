# Roadmap

## v0 — Legitimacy

The first version exists to prove one thing: **that the system can be trusted.**

Not scale. Not speed. Not feature completeness. Trust.

If users don't believe the pipeline is fair, transparent, and resistant to manipulation, nothing else matters. v0 is built around earning that trust.

**Pilot focus**: Iran — surfacing what Iranians collectively want.

### What's in v0

- **Issue submission via WhatsApp** — users submit policy concerns in plain text (WhatsApp is the only channel for v0)
- **Agent-based canonicalization and clustering** — AI structures and groups submissions without editorializing
- **Approval voting** — users vote on which clusters represent shared priorities
- **Public analytics dashboard** — a transparent, auditable view of what people care about (no login wall)
- **User dashboard** — see your submissions, their canonical forms, cluster placement, and votes
- **Evidence store** — append-only hash-chain in PostgreSQL; every step is recorded and verifiable
- **Dispute mechanism** — users can flag bad canonicalization or cluster assignment

### What's deliberately excluded from v0

- **Action drafting and execution** — v0 is about consensus visibility, not action. Deferred to v1.
- **Telegram and Signal** — prove the trust loop with one channel first
- **Phone verification, OAuth, vouching** — identity model is email magic-link + WhatsApp linking only
- **Autonomous posting** — no actions fire, period
- **On-chain execution / required external publication** — local Merkle-root anchoring is already required in v0; mandatory external publication is deferred
- **Global-scale guarantees** — v0 targets one community (Iran pilot) to keep things tractable
- **Delegated automation** — no set-and-forget; every interaction is explicit

These are excluded not because they're bad ideas, but because they introduce trust assumptions that v0 hasn't earned yet.

### Pilot gates

See [MVP Specification — v0 Frozen Decisions](mvp-specification.md#v0-frozen-decisions) for exact 30/60/90-day success and kill criteria.

## v1 — Action

Once the trust loop is proven and pilot gates are passed:

- **Action drafting and execution** — map voted items to action templates (email to officials, public submissions), require explicit user consent before sending
- **Official WhatsApp Business API** — migrate from Evolution API to official Meta API for stability and compliance at scale
- **Additional channels** — Telegram, then Signal, based on demand
- **Stronger identity signals** — improve risk scoring and anomaly detection without adding mandatory phone/OAuth identity gates
- **Required external anchoring publication** — make daily root publication mandatory once v0 publication reliability is proven
- **Embedding tier evolution** — migrate from v0 cloud default to local embeddings if privacy/cost requires it
- **Multi-community support** — support multiple concurrent jurisdictions or communities

## v2 — Autonomy

- **Federation** — distributed agent execution across independent nodes
- **Protocol-level decentralization** — the system operates without any single coordinating entity
- **Community governance** — governance of the protocol itself becomes a community function
- **Delegated consent** — users can set limits and delegate within those limits

### Resolved Questions

The following were open questions and are now locked in [v0 Frozen Decisions](mvp-specification.md#v0-frozen-decisions):

- **What does "legitimacy" look like?** — defined by pilot success metrics (trust ratings, dispute rate, audit usage)
- **How large should the pilot be?** — 30-day: >=50 users; 60-day: >=100 users; 90-day kill: <100 users
- **What community?** — Iran (diaspora + inside-Iran)
- **What's the failure condition?** — explicit kill criteria at 90 days

### Remaining Open Questions

- How do you transition from centralized to decentralized without losing the trust built in v0?
- When do additional channels justify the added complexity?
- At what scale does local LLM infrastructure replace cloud APIs?
