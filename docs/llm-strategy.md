# LLM Strategy & Model Selection

How v0 keeps model quality and safety high while preserving a clean path to later cost optimization.

This doc summarizes the current model landscape (February 2026), the hybrid architecture, and the action plan for the future.

---

## The Short Version

- **Goal:** Prioritize effectiveness and clarity in v0; optimize cost later via config-backed routing.
- **Architecture:** A single LLM abstraction with task-based routing. No vendor lock-in.
- **Language strategy:** Farsi is the primary user language; English is the internal processing language. Models are chosen based on Farsi support needs.
- **Canonicalization and Farsi messages:** Sonnet primary with mandatory fallback paths.
- **English reasoning and summaries:** Sonnet primary with fallback to DeepSeek `deepseek-chat`.
- **Embeddings:** OpenAI `text-embedding-3-large` primary with config-backed fallback (e.g., `mistral-embed`).
- **Dispute adjudication:** dedicated `dispute_resolution` tier with fallback/ensemble escalation.
- **Action plan:** Keep all tier->model mapping in config so policy shifts never require caller rewrites.

---

## Why This Matters for Collective Will

The pipeline has three AI-dependent stages:

| Agent | Task | Language | Model | Why |
|-------|------|----------|-------|-----|
| **Canonicalization** | Freeform Farsi → structured English | Farsi in | Sonnet (fallback configured) | Quality-first extraction in v0 |
| **Embeddings** | Compute vectors for clustering | English | OpenAI `text-embedding-3-large` (fallback configured) | Best semantic quality in v0 |
| **Clustering** | Group similar items, produce summaries | English | HDBSCAN (local) + `english_reasoning` tier | Local clustering with quality-first summaries + fallback |
| **Action planning** | Map voted items to action templates, draft content | English | DeepSeek V3.2 | Complex reasoning, English-only, cheap (v1 only) |
| **User messages** | Bot responses, confirmations, vote prompts | Farsi out | `farsi_messages` tier (Sonnet default, Haiku fallback) | High clarity with continuity risk management |

**Key insight:** v0 chooses quality-first defaults for trust-critical outputs; cost reductions are introduced later through config changes, not architecture rewrites.

---

## Latest Open-Source Models (February 2026)

### Top-Ranked (Cloud / Large Local)

| Model | Params (active) | Notes |
|-------|------------------|-------|
| **Kimi K2.5** | 32B (1T total MoE) | #1 on open-source rankings; 85% LiveCodeBench, 96% AIME. Best via API; full model needs 240GB+ RAM. |
| **GLM-4.7 (Thinking)** | — | #2; 89% LiveCodeBench, 95% AIME. Zhipu AI. |
| **DeepSeek V3.2** | 37B (671B MoE) | #3; 86% LiveCodeBench, 92% AIME. Very cheap API, open weights. |

### Best Small Models for Local (Under 20B / Low VRAM)

| Model | Params (active) | Context | VRAM (Q4) | Best for |
|-------|------------------|---------|-----------|----------|
| **Qwen3-8B** | 8.2B | 131K | ~5GB | #1 under 20B; dual thinking/fast mode; math, code, 100+ languages. |
| **GLM-Z1-9B** | 9B | 128K | ~6GB | Strong reasoning; Zhipu’s latest small model. |
| **Qwen3-14B** | 14B | 128K | ~9GB | Strong all-rounder; 36T training tokens. |
| **MiMo-V2-Flash** | 15B (309B MoE) | 256K | 12GB min | #1 SWE-Bench (73.4%); 150 tok/s; MIT; hybrid attention, multi-token prediction. |
| **Llama 4 Scout** | 17B (16 experts) | 10M | ~12GB | Best multimodal in class; single H100. |
| **Qwen3-Coder-30B-A3B** | 3.3B (30B MoE) | 256K→1M | ~17GB | Coding specialist; only 3.3B active — runs like a small model. |

### Hardware requirements: best local (MiMo-V2-Flash)

The best quality/cost local option in the table above is **MiMo-V2-Flash**. Recommended hardware:

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **GPU VRAM** | 8GB (heavy quantization) | **24GB** (e.g. RTX 3090, RTX 4090, RTX 5090) |
| **System RAM** | 16GB | 32–64GB |
| **Storage** | 100GB | 200GB+ NVMe SSD |
| **GPU** | NVIDIA (CUDA); 12GB for comfortable single-GPU | Single 24GB card (no multi-GPU required) |

- **8GB VRAM:** Possible with aggressive quantization; expect slower inference and lower quality.
- **12GB VRAM:** Usable (e.g. RTX 3060 12GB); may need quantized weights and reduced batch/context.
- **24GB VRAM:** Sweet spot for full context (256K) and good throughput with vLLM or SGLang.

For **Qwen3-8B** (cheapest viable local): ~5GB VRAM (Q4), 8GB RAM; runs on RTX 3060/4060 or similar.

### DeepSeek V4 (Upcoming)

- **Expected:** Mid-February 2026 (around Feb 17, Lunar New Year). Not officially confirmed.
- **Focus:** Coding; internal benchmarks claim gains over Claude/GPT on code.
- **Tech:** Engram memory (1M+ token context), mHC (Manifold-Constrained Hyper-Connections).
- **Expected policy:** Open-source (e.g. MIT), 5–15× cheaper than competitors. Small or distilled variants TBD but likely, given DeepSeek’s history (e.g. R1 distilled 1.5B–32B).

When V4 is released, we reassess cloud default and any new small distilled options for local.

### Why Newer Models Help

Newer models bring algorithm and data advantages at the same size: better reasoning (thinking/reasoning modes), MoE (large total params, small active params), longer context, and stronger instruction following. Prefer 2025–2026 models over older families (e.g. DeepSeek-R1 distilled) for the same VRAM budget.

---

## Hybrid Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  LLM abstraction + router               │
│            (task-based: by agent / language)            │
└─────┬─────────────────┬─────────────────┬───────────────┘
      │                 │                 │
┌─────▼─────┐    ┌──────▼──────┐   ┌──────▼──────┐
│  FARSI    │    │  EMBEDDING  │   │  ENGLISH    │
│  TIER     │    │  TIER       │   │  REASONING  │
│           │    │             │   │             │
│ • Canon.  │    │ • Vectors   │   │ • Cluster   │
│ • User    │    │   for       │   │   summaries │
│   messages│    │   clustering│   │ • Complex   │
│           │    │             │   │   drafts    │
│ Model:    │    │ Model:      │   │             │
│ Sonnet    │    │ OpenAI      │   │ Model:      │
│ (+fallback)│   │ text-embed- │   │ Sonnet      │
│           │    │ 3-large     │   │ (+fallback) │
└───────────┘    └─────────────┘   └─────────────┘
                       │
              (v0: cloud API)
              (future: local e5/BGE)
```

- **Router:** Task-tier routing (`canonicalization`, `farsi_messages`, `english_reasoning`, `dispute_resolution`, `embedding`).
- **Embeddings:** v0 default OpenAI `text-embedding-3-large`, with configurable fallback path.
- **Abstraction:** All agents call the same interface (e.g. `complete(prompt, model_tier)` / `embed(text)`); implementation swaps backend.

---

## Action Plan for the Future

### Phase 1 — Now (design / pre-MVP)

- Define the **LLM abstraction**: single interface for completion and embedding, with parameters for model tier, max tokens, temperature.
- Document **which agent uses which tier**, with model/provider IDs sourced only from config.
- Optionally prototype with **RouteLLM** or a simple rule-based router (e.g. by agent name).

### Phase 2 — MVP (first deploy)

- **Canonicalization tier:** Sonnet primary + configured fallback.
- **Farsi messaging tier:** Sonnet primary + configured fallback.
- **English reasoning tier:** Sonnet primary + configured fallback.
- **Embedding tier:** OpenAI `text-embedding-3-large` primary + configured fallback.
- **Dispute-resolution tier:** dedicated primary model + fallback/ensemble escalation.
- **Target hardware:** No GPU required for MVP. All AI workloads are cloud API calls. Add local models later if cost or privacy requires it.

### Phase 3 — After DeepSeek V4 (Feb 2026+)

- Evaluate **DeepSeek V4 API** as default cloud backend (and any small/distilled V4 models for local).
- If local quality matters more: add **MiMo-V2-Flash** (or Qwen3-Coder-30B-A3B for code-heavy tasks) for the local tier.
- Revisit **Kimi K2.5** for agentic or tool-heavy action planning if needed.

### Phase 4 — Scale and cost tuning

- Use router metrics to see what fraction of requests stay local; tune thresholds or router model.
- Consider **multiple local model sizes** (e.g. 8B for latency, 14B for quality) and route by workload.
- Re-evaluate new small/open models (e.g. Llama 4 family, new Qwen/GLM/Zhipu releases) as they appear.

### Cost ballpark (MVP)

**1k submissions/month estimate:**

| Task | Model | Volume | Cost |
|------|-------|--------|------|
| Canonicalization | Sonnet primary | 1k submissions | Higher than cost-first |
| Clustering embeddings | OpenAI `text-embedding-3-large` primary | 1k items | Higher than cost-first |
| Cluster summaries | Sonnet primary + fallback | 50 clusters | Higher than cost-first |
| User messages | Sonnet primary + Haiku fallback | 3k messages | Higher than cost-first |
| **Total** | | | **Quality-first v0 budget; optimize later via config** |

Action planning is deferred to v1 (no cost in v0).

Compare cost phases through config updates after scale is reached; avoid business-logic rewrites when changing model economics.

---

## References

- [RouteLLM](https://github.com/lm-sys/RouteLLM) — drop-in OpenAI-compatible router for cost-efficient routing.
- [LLMRouter](https://ulab-uiuc.github.io/LLMRouter/) — routing strategies and benchmarks.
- [MiMo-V2-Flash](https://github.com/XiaomiMiMo/MiMo-V2-Flash) — 15B active, 309B MoE, MIT, local deployment.
- [Qwen3](https://qwen-ai.com/qwen-3/) — Qwen3-8B/14B, dual-mode reasoning.
- DeepSeek V4 coverage (e.g. The Information, Spectrum AI Lab) — release timing and features (as of Feb 2026).

---

## Open Questions

- Should the router be rule-based (by agent) at v0, or should we train/use a learned router from day one?
- What are the exact latency and throughput requirements for canonicalization and clustering in the first pilot?
- Do we want to support multiple local model backends (e.g. vLLM, SGLang, llama.cpp) behind the same abstraction, and how do we version them in the audit log?
- When DeepSeek V4 ships, do we add a “small/local V4” slot to the strategy as soon as distilled or small variants are available?
