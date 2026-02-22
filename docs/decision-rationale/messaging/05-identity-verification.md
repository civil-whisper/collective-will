# Decision Rationale — messaging/05-identity-verification.md

> **Corresponds to**: [`docs/agent-context/messaging/05-identity-verification.md`](../../agent-context/messaging/05-identity-verification.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements shared-context D3 (identity) as:

- Email magic-link + WhatsApp linking (no phone verification, no OAuth, no vouching)
- WhatsApp linkage stored as opaque `account_ref` (raw `wa_id` only in sealed mapping)
- Sybil-risk telemetry on signup path
- Soft trust signals without over-blocking legitimate users in v0
- Magic-link URLs are built from `APP_PUBLIC_BASE_URL` so production links point to the Njalla domain (`https://collectivewill.org`).
- Major providers are exempt from per-domain caps; domain cap applies only to non-major domains.
- Per-IP signup cap is enforced as a blocking control.

---

## Decision: Keep low-friction identity, add monitoring guardrails

**Why this is correct**

- Preserves privacy and accessibility for an at-risk user base.
- Keeps onboarding friction low while still creating a verifiable account path.
- Adds detection of coordinated signup patterns without punishing normal users.

**Guardrails enforced here**

1. Enforce per-IP signup cap as a hard abuse control.
2. Apply per-domain cap only to non-major domains; exempt major providers.
3. Track distinct email domains per requester IP (24h) and flag anomalies.
4. Detect disposable-email domains as a negative `trust_score` signal (not auto-deny by itself).
5. Emit account-creation velocity metrics for risk-monitoring dashboards.

**Risk**

- Overly strict per-IP thresholds can affect shared-network users (cafes, campus, VPN exits).
- Attackers can still distribute across IP pools and providers; controls reduce abuse but do not eliminate it.

**Verdict**: **Keep with guardrail**
