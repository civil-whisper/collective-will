# Decision Rationale — pipeline/07-cluster-summarization-agenda.md

> **Corresponds to**: [`docs/agent-context/pipeline/07-cluster-summarization-agenda.md`](../../agent-context/pipeline/07-cluster-summarization-agenda.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Agenda is now multi-stage before final ballot:
  1) cluster size threshold
  2) pre-ballot endorsement-signature threshold
- Cluster summarization is quality-first in v0 (`english_reasoning` primary) with mandatory fallback for risk management.
- After summarization, LLM-generated per-policy stance options are created for each cluster (2–4 options).
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

## Decision: LLM-generated per-policy stance options

**Why this is correct**

- Captures the realistic spectrum of approaches for each policy topic, surfacing perspectives users may not have considered.
- Moves beyond binary approve/reject to nuanced stance selection.
- Options are bilingual (Farsi + English) matching the platform's locale support.

**Risk**

- LLM-generated options could be biased, misleading, or of poor quality.
- Generation adds latency and cost to the pipeline.

**Guardrail**

- Fallback to generic support/oppose when LLM fails — voting is never blocked.
- System prompt enforces nonpartisan, balanced, jargon-free output.
- Options are capped at 2–4 per cluster (too many = decision fatigue, too few = insufficient nuance).
- All generated options are evidence-logged (`policy_options_generated`) for auditability.
- Keep model choice behind `tier="english_reasoning"` — no direct model IDs in business logic.

**Verdict**: **Keep with guardrail**
