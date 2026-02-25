# Decision Rationale — pipeline/01-llm-abstraction.md

> **Corresponds to**: [`docs/agent-context/pipeline/01-llm-abstraction.md`](../../agent-context/pipeline/01-llm-abstraction.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- **Gemini-first strategy**: All primary tiers default to `gemini-3.1-pro-preview` for best performance-to-cost ratio ($2/$12 per 1M tokens vs Claude Sonnet $3/$15). Higher reasoning benchmark scores and 2x throughput.
- All fallbacks default to `claude-sonnet-4-20250514` for cross-provider resilience.
- Embeddings: `gemini-embedding-001` primary, `text-embedding-3-large` fallback.
- Policy option generation (`option_generation`) uses Gemini 3.1 Pro with Google Search grounding. The `grounding` parameter on `complete()` is provider-aware — only applied for Google models. Fallback: Claude Sonnet (no grounding).
- Dispute adjudication is autonomous via the `dispute_resolution` tier, with ensemble tie-break using Gemini + Claude Sonnet.

## Decision: Gemini-first tier routing by task

**Why this is correct**

- Gemini 3.1 Pro outperforms Claude Sonnet on reasoning benchmarks (94.1% vs 87.5% GPQA) at lower cost.
- Avoids accidental model coupling between extraction quality and user-message generation.
- Keeps routing simple and explicit: one tier per job category.
- Enables model swaps via config/env (tier -> model mapping) without touching business logic.
- Cross-provider fallback (Gemini primary → Claude fallback) provides resilience against single-provider outages.
- Supports no-human per-item dispute handling by routing dispute resolution through explicit model policy instead of operator decisions.

**Guardrail**

- Enforce schema validation and confidence review in canonicalization path.
- Keep mandatory fallback paths configured for each tier where continuity is required (`canonicalization`, `farsi_messages`, `english_reasoning`, `option_generation`, `dispute_resolution`).
- Require low-confidence dispute paths to trigger fallback/ensemble tie-break before finalizing resolution.
- Keep dispute confidence thresholds config-backed so escalation policy can be tuned without code edits.
- Require dispute adjudication traces to be emitted for full evidence logging of every adjudication action.
- Forbid direct model-ID usage outside `llm.py`; all callers use task tiers.

**Verdict**: **Keep with guardrail**
