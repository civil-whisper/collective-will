# Decision Rationale — database/02-db-connection.md

> **Corresponds to**: [`docs/agent-context/database/02-db-connection.md`](../../agent-context/database/02-db-connection.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements infrastructure and reliability decisions as:

- Async SQLAlchemy engine/session (`asyncpg`) for all DB access.
- Conservative pool defaults for MVP scale.
- A single `get_db()` dependency path for API handlers.
- Explicit DB health check behavior.

---

## Decision: Centralized async DB connection layer

**Why this is correct**

- Prevents ad-hoc connection handling across modules.
- Matches the backend stack decision (FastAPI + SQLAlchemy async).
- Keeps failure modes predictable through one dependency boundary.

**Risk**

- Bad pool configuration can cause starvation or burst-time failures.
- Mixed sync/async usage can create hidden blocking behavior.

**Guardrail**

- Keep all DB I/O async-only.
- Keep pool sizes calibrated for v0 load (no oversized defaults).
- Require health-check tests for success and connection failure paths.

**Verdict**: **Keep with guardrail**
