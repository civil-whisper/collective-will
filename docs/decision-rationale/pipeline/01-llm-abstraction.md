# Decision Rationale — pipeline/01-llm-abstraction.md

> **Corresponds to**: [`docs/agent-context/pipeline/01-llm-abstraction.md`](../../agent-context/pipeline/01-llm-abstraction.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- **OpenAI-first strategy for now**: All primary completion tiers now default to `gpt-5.4-mini`, with Claude Sonnet 4.6 as fallback. This is a temporary operational preference to reduce disruption from current Anthropic rate limiting and OpenAI `gpt-4o` TPM pressure during long pipeline runs.
- All fallbacks default to Claude Sonnet 4.6 for cross-provider resilience.
- Embeddings: `gemini-embedding-001` primary, `text-embedding-3-large` fallback (Gemini embedding quotas are generous — 3K RPM, unlimited RPD).
- Policy option generation (`option_generation`) uses `gpt-5.4-mini` as primary and Claude Sonnet 4.6 as explicit fallback. Grounding is conditional and disabled by default; it is only enabled for configured research-heavy topics. Wrapped prose / fenced JSON responses are salvaged before model fallback.
- Dispute adjudication is autonomous via the `dispute_resolution` tier, with ensemble tie-break using `gpt-5.4-mini` + Claude Sonnet 4.6.

## Decision: OpenAI-first tier routing for now

**Why this is correct**

- Gemini 3.1 Pro has a 25 RPD limit on Paid Tier 1, causing persistent 429 errors under normal pipeline load. Claude Sonnet 4.6 has no comparable daily request cap.
- Claude Sonnet 4.6 matches or exceeds previous Sonnet on coding, reasoning, and instruction following at the same price point ($3/$15 per 1M tokens).
- Avoids accidental model coupling between extraction quality and user-message generation.
- Keeps routing simple and explicit: one tier per job category.
- Enables model swaps via config/env (tier -> model mapping) without touching business logic.
- Cross-provider fallback (OpenAI primary → Claude fallback) provides resilience against single-provider outages.
- Supports no-human per-item dispute handling by routing dispute resolution through explicit model policy instead of operator decisions.

**Guardrail**

- Enforce schema validation and confidence review in canonicalization path.
- Keep mandatory fallback paths configured for each tier where continuity is required (`canonicalization`, `farsi_messages`, `english_reasoning`, `option_generation`, `dispute_resolution`).
- Require low-confidence dispute paths to trigger fallback/ensemble tie-break before finalizing resolution.
- Keep dispute confidence thresholds config-backed so escalation policy can be tuned without code edits.
- Require dispute adjudication traces to be emitted for full evidence logging of every adjudication action.
- Forbid direct model-ID usage outside `llm.py`; all callers use task tiers.
- Keep `option_generation` grounding conditional and opt-in. Always-on grounding inflated prompt size and cost during replay, and increased the chance of non-JSON wrapper output.
- Cost telemetry must normalize provider-specific usage fields and distinguish input/output token pricing so replay spend is explainable.
- Provider-side prompt caching is a router feature (`LLM_PROMPT_CACHING_ENABLED`), not a caller concern. Callers structure their prompts for cache-friendliness (stable prefix first, dynamic suffix last) but never reference caching APIs directly.
- Cache telemetry (read/write tokens) is tracked in `LLMResponse` and replay stats for cost attribution; no schema changes were introduced.
- User-facing wording steps (`canonicalization` rejection reasons, endorsement wording, refinement drafts) must not rely on prompt compliance alone; each step needs lightweight post-LLM validation or normalization where contract violations would be user-visible.

**Verdict**: **Keep with guardrail**
