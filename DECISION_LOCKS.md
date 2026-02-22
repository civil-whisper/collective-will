# v0 Decision Locks (Do Not Drift)

These are non-negotiable unless you intentionally revise `agent-context` and `decision-rationale` together.

## Governance and Autonomy

- No action drafting/execution in v0.
- No per-item human adjudication for disputes, quarantine outcomes, or individual votes.
- Dispute resolution is autonomous with confidence thresholds and fallback/ensemble escalation.

## Identity and Privacy

- Identity path: email magic-link + WhatsApp linking only.
- No phone verification, no OAuth, no vouching in v0.
- Store only opaque messaging account refs in core tables; raw IDs only in sealed mapping.
- Reject-and-resend on high-risk PII before persistence.

## Modeling and Pipeline

- LLM usage goes through centralized abstraction with config-backed task tiers.
- v0 defaults are quality-first; fallback models are mandatory.
- Clustering uses HDBSCAN with config-backed `min_cluster_size`; show noise publicly.

## Evidence and Auditability

- Evidence store is append-only hash-chain.
- Hash covers canonical full entry material, not payload-only.
- Daily local Merkle root computation is required in v0.
- External root publication is optional/config-driven in v0.
