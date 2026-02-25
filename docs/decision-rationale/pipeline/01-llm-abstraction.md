# Decision Rationale — pipeline/01-llm-abstraction.md

> **Corresponds to**: [`docs/agent-context/pipeline/01-llm-abstraction.md`](../../agent-context/pipeline/01-llm-abstraction.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- **Claude-first strategy**: All primary tiers default to `claude-sonnet-4-6` for reliable throughput (no restrictive RPD limits). Gemini 3.1 Pro rate limits (25 RPD on Paid Tier 1) caused persistent 429 errors under normal workload.
- All fallbacks default to `gemini-3.1-pro-preview` for cross-provider resilience.
- Embeddings: `gemini-embedding-001` primary, `text-embedding-3-large` fallback (Gemini embedding quotas are generous — 3K RPM, unlimited RPD).
- Policy option generation (`option_generation`) uses Claude Sonnet 4.6 as primary (no grounding). Fallback: Gemini 3.1 Pro (Google Search grounding activates automatically for Google models when `grounding=True`).
- Dispute adjudication is autonomous via the `dispute_resolution` tier, with ensemble tie-break using Claude Sonnet 4.6 + Gemini 3.1 Pro.

## Decision: Claude-first tier routing by task

**Why this is correct**

- Gemini 3.1 Pro has a 25 RPD limit on Paid Tier 1, causing persistent 429 errors under normal pipeline load. Claude Sonnet 4.6 has no comparable daily request cap.
- Claude Sonnet 4.6 matches or exceeds previous Sonnet on coding, reasoning, and instruction following at the same price point ($3/$15 per 1M tokens).
- Avoids accidental model coupling between extraction quality and user-message generation.
- Keeps routing simple and explicit: one tier per job category.
- Enables model swaps via config/env (tier -> model mapping) without touching business logic.
- Cross-provider fallback (Claude primary → Gemini fallback) provides resilience against single-provider outages.
- Supports no-human per-item dispute handling by routing dispute resolution through explicit model policy instead of operator decisions.

**Guardrail**

- Enforce schema validation and confidence review in canonicalization path.
- Keep mandatory fallback paths configured for each tier where continuity is required (`canonicalization`, `farsi_messages`, `english_reasoning`, `option_generation`, `dispute_resolution`).
- Require low-confidence dispute paths to trigger fallback/ensemble tie-break before finalizing resolution.
- Keep dispute confidence thresholds config-backed so escalation policy can be tuned without code edits.
- Require dispute adjudication traces to be emitted for full evidence logging of every adjudication action.
- Forbid direct model-ID usage outside `llm.py`; all callers use task tiers.
- Google Search grounding for `option_generation` is only active when the Gemini fallback is reached; if grounding is critical, consider overriding `option_generation_model` to a Gemini model via env.

**Verdict**: **Keep with guardrail**
