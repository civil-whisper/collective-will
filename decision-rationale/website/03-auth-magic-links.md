# Decision Rationale — website/03-auth-magic-links.md

> **Corresponds to**: [`docs/agent-context/website/03-auth-magic-links.md`](../../agent-context/website/03-auth-magic-links.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements identity and session decisions as:

- Passwordless email magic-link auth in web layer.
- Python backend remains source of truth for user records/verification state.
- Dashboard routes protected; public analytics routes remain open.
- Locale-safe auth flow (`fa`/`en`).

---

## Decision: Passwordless web auth with backend-authoritative identity

**Why this is correct**

- Reduces credential risk and user friction.
- Keeps identity consistency with messaging verification flow.
- Supports access control without introducing OAuth/KYC complexity.

**Risk**

- Session/backend drift can occur if callback synchronization is weak.

**Guardrail**

- Keep JWT payload minimal (no sensitive profile data).
- Enforce server-side route protection for all dashboard paths.
- Test auth redirects and locale-specific verify flows.

**Verdict**: **Keep with guardrail**
