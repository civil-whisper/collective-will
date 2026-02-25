#!/usr/bin/env python3
"""Smoke-test LLM providers with real API calls.

Reads config from .env and makes one completion + one embedding call per
configured provider to verify keys and routing work.

Usage:
    uv run python scripts/smoke_test_llm.py              # test all providers
    uv run python scripts/smoke_test_llm.py --provider google   # test Google only
    uv run python scripts/smoke_test_llm.py --provider anthropic
    uv run python scripts/smoke_test_llm.py --tier canonicalization  # test one tier
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import Settings
from src.pipeline.llm import LLMRouter

FARSI_TEST_PROMPT = "یک جمله کوتاه به فارسی بنویس."
ENGLISH_TEST_PROMPT = "Respond with exactly one sentence: what is 2+2?"
EMBEDDING_TEST_TEXTS = ["collective decision making", "تصمیم‌گیری جمعی"]

TIER_TEST_PROMPTS: dict[str, str] = {
    "canonicalization": FARSI_TEST_PROMPT,
    "farsi_messages": FARSI_TEST_PROMPT,
    "english_reasoning": ENGLISH_TEST_PROMPT,
    "dispute_resolution": ENGLISH_TEST_PROMPT,
}

PROVIDER_MODELS: dict[str, tuple[str, str]] = {
    "google": ("gemini-2.5-flash", "gemini-embedding-001"),
    "anthropic": ("claude-sonnet-4-6", ""),
    "openai": ("", "text-embedding-3-large"),
    "deepseek": ("deepseek-chat", ""),
}


def _settings() -> Settings:
    return Settings()  # type: ignore[call-arg]


async def test_completion(router: LLMRouter, model: str, prompt: str) -> bool:
    print(f"  completion  {model:<40s} ", end="", flush=True)
    t0 = time.monotonic()
    try:
        resp = await router.complete_with_model(model=model, prompt=prompt, max_tokens=64)
        elapsed = time.monotonic() - t0
        preview = resp.text[:80].replace("\n", " ")
        print(
            f"OK  {elapsed:.1f}s  "
            f"in={resp.input_tokens} out={resp.output_tokens} "
            f"${resp.cost_usd:.6f}  \"{preview}...\""
        )
        return True
    except Exception as exc:
        elapsed = time.monotonic() - t0
        print(f"FAIL  {elapsed:.1f}s  {exc}")
        return False


async def test_embedding(router: LLMRouter, model: str) -> bool:
    print(f"  embedding   {model:<40s} ", end="", flush=True)
    t0 = time.monotonic()
    try:
        result = await router.embed(EMBEDDING_TEST_TEXTS)
        elapsed = time.monotonic() - t0
        dims = len(result.vectors[0]) if result.vectors else 0
        print(
            f"OK  {elapsed:.1f}s  "
            f"vectors={len(result.vectors)} dims={dims} "
            f"provider={result.provider} model={result.model}"
        )
        return True
    except Exception as exc:
        elapsed = time.monotonic() - t0
        print(f"FAIL  {elapsed:.1f}s  {exc}")
        return False


async def test_tier(router: LLMRouter, tier: str) -> bool:
    prompt = TIER_TEST_PROMPTS[tier]
    print(f"  tier        {tier:<40s} ", end="", flush=True)
    t0 = time.monotonic()
    try:
        resp = await router.complete(tier=tier, prompt=prompt, max_tokens=64)  # type: ignore[arg-type]
        elapsed = time.monotonic() - t0
        preview = resp.text[:80].replace("\n", " ")
        print(
            f"OK  {elapsed:.1f}s  "
            f"model={resp.model}  "
            f"in={resp.input_tokens} out={resp.output_tokens}  "
            f"\"{preview}...\""
        )
        return True
    except Exception as exc:
        elapsed = time.monotonic() - t0
        print(f"FAIL  {elapsed:.1f}s  {exc}")
        return False


async def run_provider(router: LLMRouter, provider: str) -> list[bool]:
    comp_model, embed_model = PROVIDER_MODELS.get(provider, ("", ""))
    results: list[bool] = []
    if comp_model:
        results.append(await test_completion(router, comp_model, ENGLISH_TEST_PROMPT))
    if embed_model:
        orig_model = router.settings.embedding_model
        orig_fallback = router.settings.embedding_fallback_model
        object.__setattr__(router.settings, "embedding_model", embed_model)
        object.__setattr__(router.settings, "embedding_fallback_model", embed_model)
        results.append(await test_embedding(router, embed_model))
        object.__setattr__(router.settings, "embedding_model", orig_model)
        object.__setattr__(router.settings, "embedding_fallback_model", orig_fallback)
    return results


async def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test LLM providers")
    parser.add_argument("--provider", choices=list(PROVIDER_MODELS.keys()), help="Test one provider only")
    parser.add_argument("--tier", choices=list(TIER_TEST_PROMPTS.keys()), help="Test one tier only")
    args = parser.parse_args()

    settings = _settings()
    router = LLMRouter(settings=settings)
    results: list[bool] = []

    if args.tier:
        print(f"\n--- Tier: {args.tier} ---")
        results.append(await test_tier(router, args.tier))
    elif args.provider:
        print(f"\n--- Provider: {args.provider} ---")
        results.extend(await run_provider(router, args.provider))
    else:
        print("\n--- Tier routing (uses your .env model config) ---")
        for tier in TIER_TEST_PROMPTS:
            results.append(await test_tier(router, tier))

        print("\n--- Embedding (uses your .env embedding config) ---")
        results.append(await test_embedding(router, settings.embedding_model))

        print(f"\n--- Direct provider checks ---")
        for provider in PROVIDER_MODELS:
            comp_model, _ = PROVIDER_MODELS[provider]
            if not comp_model:
                continue
            key_attr = f"{provider}_api_key"
            key = getattr(settings, key_attr, None)
            if not key:
                print(f"  skip        {provider:<40s} (no API key)")
                continue
            results.append(await test_completion(router, comp_model, ENGLISH_TEST_PROMPT))

    passed = sum(results)
    failed = len(results) - passed
    print(f"\n{'='*60}")
    print(f"  {passed} passed, {failed} failed, total cost ${router.total_cost_usd:.6f}")
    print(f"{'='*60}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
