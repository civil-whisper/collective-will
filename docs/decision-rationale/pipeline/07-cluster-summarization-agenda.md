# Decision Rationale — pipeline/07-cluster-summarization-agenda.md

> **Corresponds to**: [`docs/agent-context/pipeline/07-cluster-summarization-agenda.md`](../../agent-context/pipeline/07-cluster-summarization-agenda.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Agenda is now multi-stage before final ballot:
  1) cluster size threshold
  2) pre-ballot endorsement-signature threshold
- Cluster summarization itself is quality-first in v0 (`english_reasoning` primary) with mandatory fallback for risk management.
- No editorial filtering is allowed beyond these explicit gates.

## Decision: Gate ballot entry with endorsement signatures

**Why this is correct**

- Converts passive clustering into a legitimacy-filtered agenda.
- Lets users contribute by supporting existing proposals, not only by creating new submissions.
- Reduces low-salience/noise clusters from immediately consuming ballot space.

**Risk**

- Overtight thresholds can starve the ballot.
- Loose thresholds can still allow spam influence.

**Guardrail**

- Keep `MIN_PREBALLOT_ENDORSEMENTS` config-backed (default `5`) and monitor qualification rates per cycle.

**Verdict**: **Keep with guardrail**
