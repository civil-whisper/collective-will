# Task: LLM Abstraction Layer

## Depends on
- `database/01-project-scaffold` (config with API keys)

## Goal
Create a unified LLM interface with task-based routing to quality-first models in v0 (including user-facing Farsi messaging and autonomous dispute resolution), with mandatory fallbacks for risk management. All AI calls go through this abstraction.

## Files to create

- `src/pipeline/llm.py` — LLM abstraction and router

## Specification

### Model tiers

| Tier | Model | Use case | API |
|------|-------|----------|-----|
| `canonicalization` | Gemini 3.1 Pro (v0 default) | Canonicalization (Farsi→English), structured extraction | Gemini generateContent API |
| `farsi_messages` | Gemini 3.1 Pro (v0 default) | User-facing Farsi messages (notifications/prompts) | Gemini generateContent API |
| `english_reasoning` | Gemini 3.1 Pro (v0 default) | Cluster summaries, complex English reasoning | Gemini generateContent API |
| `option_generation` | Gemini 3.1 Pro (v0 default) | Per-policy stance option generation with Google Search grounding | Gemini generateContent API (with `grounding=True`) |
| `dispute_resolution` | Gemini 3.1 Pro (v0 default) | Autonomous dispute adjudication and resolution rationale | Gemini generateContent API (+ optional ensemble tie-break) |
| `embedding` | Gemini `gemini-embedding-001` (v0 default) | Compute vectors for clustering | Gemini batchEmbedContents API |

### Config-driven model registry

Model IDs are resolved from `Settings`, not hardcoded in callers:

```python
class LLMRouterConfig(BaseModel):
    canonicalization_model: str
    canonicalization_fallback_model: str
    farsi_messages_model: str
    farsi_messages_fallback_model: str
    english_reasoning_model: str
    english_reasoning_fallback_model: str
    option_generation_model: str
    option_generation_fallback_model: str
    dispute_resolution_model: str
    dispute_resolution_fallback_model: str
    dispute_resolution_ensemble_models: str
    dispute_resolution_confidence_threshold: float
    embedding_model: str
    embedding_fallback_model: str
```

Routing behavior:
- `tier="canonicalization"` -> `settings.canonicalization_model`
- On retry exhaustion for canonicalization, optional fallback -> `settings.canonicalization_fallback_model`
- `tier="farsi_messages"` -> `settings.farsi_messages_model`
- On retry exhaustion for farsi_messages, mandatory fallback -> `settings.farsi_messages_fallback_model`
- `tier="english_reasoning"` -> `settings.english_reasoning_model`
- On retry exhaustion for english_reasoning, mandatory fallback -> `settings.english_reasoning_fallback_model`
- `tier="option_generation"` -> `settings.option_generation_model` (Gemini 3.1 Pro with Google Search grounding when `grounding=True`)
- On retry exhaustion for option_generation, mandatory fallback -> `settings.option_generation_fallback_model` (grounding auto-disabled for non-Google providers)
- `tier="dispute_resolution"` -> `settings.dispute_resolution_model`
- On retry exhaustion for dispute_resolution, mandatory fallback -> `settings.dispute_resolution_fallback_model`
- If dispute confidence is below `settings.dispute_resolution_confidence_threshold`, escalate via fallback/ensemble tie-break path
- On low-confidence dispute outcome, optional ensemble tie-break via `settings.dispute_resolution_ensemble_models`
- `embed()` -> `settings.embedding_model`
- On retry exhaustion for embeddings, optional fallback -> `settings.embedding_fallback_model`

### complete() function

```python
async def complete(
    prompt: str,
    tier: Literal["canonicalization", "farsi_messages", "english_reasoning", "option_generation", "dispute_resolution"],
    system_prompt: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.0,
    grounding: bool = False,
) -> LLMResponse:
```

- Routes to the correct API based on tier
- Uses httpx async client
- When `grounding=True` and provider is Google, adds `"tools": [{"google_search": {}}]` to the Gemini request for web search grounding. Non-Google providers silently ignore this parameter.
- Returns structured response

```python
class LLMResponse(BaseModel):
    text: str
    model: str                   # Actual model name used
    input_tokens: int
    output_tokens: int
    cost_usd: float              # Estimated cost
```

### embed() function

```python
async def embed(texts: list[str]) -> list[list[float]]:
```

- Calls configured embedding provider for `settings.embedding_model`
- Batches if list is too long (provider-specific limits)
- Returns list of embedding vectors

### API clients

Use httpx async for all APIs:

**Anthropic (Sonnet + Haiku by tier)**:
- Endpoint: `https://api.anthropic.com/v1/messages`
- Headers: `x-api-key`, `anthropic-version: 2023-06-01`
- `tier="canonicalization"` uses `settings.canonicalization_model`
- `tier="farsi_messages"` uses `settings.farsi_messages_model` (v0 default Sonnet)
- `tier="english_reasoning"` uses `settings.english_reasoning_model` (v0 default Sonnet)
- `tier="dispute_resolution"` uses `settings.dispute_resolution_model` (v0 default Opus)
- `tier="farsi_messages"` fallback uses `settings.farsi_messages_fallback_model` (default Haiku)
- `tier="dispute_resolution"` fallback uses `settings.dispute_resolution_fallback_model` (default Sonnet)

**DeepSeek (english_reasoning fallback)**:
- Endpoint: `https://api.deepseek.com/v1/chat/completions` (OpenAI-compatible)
- Headers: `Authorization: Bearer {api_key}`
- Fallback model: `settings.english_reasoning_fallback_model` (default `deepseek-chat`)

**OpenAI embeddings (v0 default)**:
- Endpoint: `https://api.openai.com/v1/embeddings`
- Headers: `Authorization: Bearer {openai_api_key}`
- Default model: `text-embedding-3-large` (from `settings.embedding_model`)

**Embedding fallback (later/cost-effective option)**:
- Example fallback model: `mistral-embed` (from `settings.embedding_fallback_model`)
- Router should support fallback provider call path without changing callers.
- If fallback provider is enabled, require its API key at runtime; otherwise treat it as disabled.

### Cost tracking

Estimate cost per call based on token counts and known pricing. Log to stdout or a cost tracking table (simple for v0).

### Error handling

- Retry transient errors (429, 500, 502, 503) up to 3 times with exponential backoff
- Timeout: 60 seconds per call
- Raise clear exceptions for auth errors (401) and bad requests (400) — do not retry these

## Constraints

- All LLM calls go through this abstraction. No direct API calls from other modules.
- No module outside `src/pipeline/llm.py` may reference provider model IDs directly.
- The abstraction must be easy to swap backends (e.g., switch DeepSeek to a local model later).
- Log the model name and version with every call (for evidence store reproducibility).
- Do NOT send user IDs, account references, or metadata to any LLM API. Only text content.
- Dispute adjudication must not require human-in-the-loop for individual cases; low-confidence paths use fallback/ensemble model routing.
- Dispute confidence thresholds must be config-driven (no hardcoded adjudication thresholds in callers).
- Every dispute adjudication action must emit an evidence-loggable trace (primary model attempt, fallback/ensemble escalation, final decision).

## Tests

Write tests in `tests/test_pipeline/test_llm.py` covering:
- `complete()` with `tier="canonicalization"` calls Anthropic API with Sonnet model (mock httpx)
- `complete()` with `tier="farsi_messages"` calls Anthropic API with configured primary model (mock httpx)
- `complete()` with `tier="farsi_messages"` falls back to configured fallback model when primary retries are exhausted
- `complete()` with `tier="english_reasoning"` calls Anthropic API with configured primary model (mock httpx)
- `complete()` with `tier="english_reasoning"` falls back to configured fallback model when primary retries are exhausted
- `complete()` with `tier="dispute_resolution"` calls configured primary dispute model (mock httpx)
- `complete()` with `tier="dispute_resolution"` falls back to configured dispute fallback model when primary retries are exhausted
- Low-confidence dispute output triggers configured ensemble tie-breaker flow
- `dispute_resolution_confidence_threshold` override in test settings changes escalation behavior without code edits
- Dispute adjudication trace contains the full resolution path for evidence logging
- Overriding tier model IDs in test settings changes routed model without code edits
- `embed()` calls configured embedding provider API (mock httpx)
- `embed()` with large batch splits into sub-batches
- Embedding fallback model is used when primary embedding provider fails after retries
- LLMResponse contains correct model name and token counts
- Retry logic: transient 429 error retried, succeeds on 2nd attempt
- Auth error (401) not retried, raises immediately
- Timeout fires after configured duration
- Cost estimate is non-negative and reasonable
