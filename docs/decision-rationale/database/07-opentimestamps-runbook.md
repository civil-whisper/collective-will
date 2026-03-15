# Decision Rationale — database/07-opentimestamps-runbook.md

> **Corresponds to**: [`docs/agent-context/database/07-opentimestamps-runbook.md`](../../agent-context/database/07-opentimestamps-runbook.md)
>
> When a decision changes in either file, update the other.

---

## Decision

Use public OpenTimestamps calendars by default in v0, and treat self-hosting as a later operational choice rather than a default requirement.

---

## Why this is correct

- Public calendars are good enough for MVP trust goals.
- They avoid premature ops complexity.
- They preserve the project's core anti-tampering guarantee without vendor onboarding or blockchain transaction fees.

---

## Guardrails

- Local root/bundle generation must never depend on calendar reachability.
- `stamped` and `verified` must remain distinct states.
- Self-hosting should only be introduced for control/availability reasons, not out of vague “more trust” instinct.

---

## Verdict

**Adopt for v0.1**: public calendars first, optional Bitcoin node later, self-hosted calendar only when there is a concrete operational need.
