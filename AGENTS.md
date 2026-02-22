# Coding Agent Rules (Bootstrap)

When implementing in the new repo, use this precedence order:

1. `agent-context/CONTEXT-shared.md` (global ground truth)
2. `agent-context/**` (module-level implementation contracts)
3. `decision-rationale/**` (why + guardrails for trade-offs)
4. `mvp-specification.md` (product/system context)

## Hard Requirements

- Do not introduce per-item human adjudication for votes, disputes, or quarantine outcomes.
- Keep model routing config-backed through the LLM abstraction; no direct model IDs in business logic.
- Keep WhatsApp linkage as opaque account refs in core tables; raw `wa_id` stays only in sealed mapping.
- Keep evidence logging append-only and hash-chain consistent with canonical full-entry hashing.
- Compute daily local Merkle root in v0; external publication is config-driven.
- Preserve channel-agnostic boundaries (`BaseChannel`) even though v0 is WhatsApp-only.

## Delivery Discipline

- Write tests for each implemented task.
- Keep Python typing strict and schemas explicit (ORM <-> schema conversions).
- Never commit secrets or real identities.
