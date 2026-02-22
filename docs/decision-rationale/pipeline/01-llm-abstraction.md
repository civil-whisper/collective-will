# Decision Rationale — pipeline/01-llm-abstraction.md

> **Corresponds to**: [`docs/agent-context/pipeline/01-llm-abstraction.md`](../../agent-context/pipeline/01-llm-abstraction.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Canonicalization now prioritizes effectiveness/simplicity over cost, so it uses a single Sonnet tier.
- User-facing Farsi messaging is also quality-first in v0 (Sonnet primary) with mandatory fallback (Haiku).
- Embeddings are quality-first in v0, with model selection/fallback controlled by config for later cost optimization.
- Cluster summarization (`english_reasoning`) is quality-first in v0, with mandatory fallback for resilience.
- Dispute adjudication is autonomous and quality-first in v0 (`dispute_resolution` tier), with fallback and optional ensemble tie-break for low-confidence cases.

## Decision: Split Anthropic tiers by task

**Why this is correct**

- Keeps canonicalization quality high with an always-on strong model (`canonicalization` -> Sonnet).
- Avoids accidental model coupling between extraction quality and user-message generation.
- Keeps routing simple and explicit: one tier per job category.
- Enables model swaps via config/env (tier -> model mapping) without touching business logic.
- Supports no-human per-item dispute handling by routing dispute resolution through explicit model policy instead of operator decisions.

**Guardrail**

- Enforce schema validation and confidence review in canonicalization path.
- Keep mandatory fallback paths configured for each tier where continuity is required (`canonicalization`, `farsi_messages`, `english_reasoning`, `dispute_resolution`).
- Require low-confidence dispute paths to trigger fallback/ensemble tie-break before finalizing resolution.
- Keep dispute confidence thresholds config-backed so escalation policy can be tuned without code edits.
- Require dispute adjudication traces to be emitted for full evidence logging of every adjudication action.
- Forbid direct model-ID usage outside `llm.py`; all callers use task tiers.

**Verdict**: **Keep with guardrail**
