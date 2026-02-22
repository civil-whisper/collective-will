# Decision Rationale — website/07-dispute-flagging.md

> **Corresponds to**: [`docs/agent-context/website/07-dispute-flagging.md`](../../agent-context/website/07-dispute-flagging.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements shared-context dispute and autonomy rules as:

- User-facing dispute flagging remains available and low-friction.
- Disputes are resolved by autonomous agentic workflows (no per-item human adjudication).
- Resolution paths are pipeline re-runs/model escalation, never manual content edits.
- Resolver calls should route through `tier="dispute_resolution"` with fallback/ensemble policy.
- All dispute state transitions are evidence-logged.

---

## Decision: Autonomous dispute adjudication in UI workflow

**Why this is correct**

- Preserves neutrality by removing manual case-by-case intervention.
- Scales better than operator queues as user volume grows.
- Keeps a transparent user loop (`dispute_open` -> `dispute_resolved`) with auditable actions.

**Risk**

- Automated resolvers can make repeated errors if confidence logic and escalation are weak.

**Guardrail**

- Require confidence-threshold routing and fallback/ensemble escalation for low-confidence disputes.
- Scope individual disputes to submission-level re-canonicalization first; avoid full mid-cycle re-clustering for one case.
- Keep SLA telemetry (`time_to_resolution`, disagreement rate, reopen rate) and tune resolver policies when drift appears.
- If dispute volume exceeds 5% of cycle submissions (or resolver disagreement spikes), trigger model/prompt/policy tuning.
- Require full evidence logging for each dispute adjudication action, including escalation path and final resolution.
- Humans may only modify architecture/policy/risk controls, not resolve individual disputes.

**Verdict**: **Keep with guardrail**
