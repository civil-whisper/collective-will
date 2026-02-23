# Decision Rationale — website/09-ops-debug-console.md

> **Corresponds to**: [`docs/agent-context/website/09-ops-debug-console.md`](../../agent-context/website/09-ops-debug-console.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements operations-observability guardrails as:

- Keep public audit transparency (`/analytics/evidence`) separate from operator diagnostics (`/ops`).
- Prefer structured, redacted operational events over raw container log exposure.
- Gate production access by admin auth + feature flags.

---

## Decision: Add `/ops` debug console with strict access and redaction

**Why this is correct**

- Speeds up staging and early production triage by centralizing health/errors/events in the app UI.
- Reduces context switching to shell log tailing for common incidents.
- Preserves trust architecture by keeping public audit verification independent from internal ops diagnostics.

**Risk**

- A debug console can accidentally leak sensitive data (tokens, emails, raw platform ids, secrets) or become an unsafe operational control plane.

**Guardrail**

- Never expose raw container logs directly in browser responses.
- Require structured event payloads with redaction at ingestion and response serialization.
- Keep `/ops` hidden or disabled by default in production unless feature-flagged.
- Require admin authorization for production access.
- Allow only safe operational actions; never add per-item human adjudication controls for votes/disputes/quarantine outcomes.
- Evidence-log operator actions when write capabilities are introduced.

**Verdict**: **Keep with guardrail**
