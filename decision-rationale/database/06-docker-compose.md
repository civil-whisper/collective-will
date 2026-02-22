# Decision Rationale — database/06-docker-compose.md

> **Corresponds to**: [`docs/agent-context/database/06-docker-compose.md`](../../agent-context/database/06-docker-compose.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Infrastructure decision is now concrete: Njalla domain in front of 1984.is origin.
- Local compose remains development-only and must not be treated as production exposure model.

## Decision: Keep dev compose simple, enforce production edge hardening

**Why this is correct**

- Preserves fast local developer workflow (single `docker compose up`).
- Separates developer convenience from production threat model.
- Ensures domain/privacy posture (Njalla + hidden origin) is compatible with operational resilience.

**Guardrails**

1. Production traffic goes through reverse-proxy edge (Cloudflare or OVH), not direct origin.
2. Keep origin IP private and rotate if exposed.
3. Maintain failover runbook (standby VPS, backups, DNS cutover).

**Verdict**: **Keep with guardrail**
