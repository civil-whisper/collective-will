from __future__ import annotations

import asyncio
import logging
from typing import Any, Literal

import httpx
from pydantic import BaseModel

from src.config import Settings, get_settings

logger = logging.getLogger(__name__)

TASK_TIERS: dict[str, tuple[str, str]] = {
    "canonicalization": ("canonicalization_model", "canonicalization_fallback_model"),
    "farsi_messages": ("farsi_messages_model", "farsi_messages_fallback_model"),
    "english_reasoning": ("english_reasoning_model", "english_reasoning_fallback_model"),
    "dispute_resolution": ("dispute_resolution_model", "dispute_resolution_fallback_model"),
}

TRANSIENT_STATUS_CODES = {429, 500, 502, 503}
NON_RETRIABLE_STATUS_CODES = {400, 401}
MAX_RETRIES = 3
EMBED_BATCH_SIZE = 64

TierName = Literal["canonicalization", "farsi_messages", "english_reasoning", "dispute_resolution"]


class LLMResponse(BaseModel):
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float


class EmbeddingResult(BaseModel):
    vectors: list[list[float]]
    model: str
    provider: str


class LLMRouter:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.total_cost_usd = 0.0

    def _resolve_tier_models(self, tier: str) -> tuple[str, str | None]:
        if tier not in TASK_TIERS:
            raise ValueError(f"Unknown tier: {tier}")
        primary_key, fallback_key = TASK_TIERS[tier]
        primary: str = getattr(self.settings, primary_key)
        fallback: str | None = getattr(self.settings, fallback_key, None)
        return primary, fallback

    def _provider_for_model(self, model: str) -> str:
        lowered = model.lower()
        if "claude" in lowered:
            return "anthropic"
        if "deepseek" in lowered:
            return "deepseek"
        if "text-embedding" in lowered:
            return "openai"
        if "mistral" in lowered:
            return "mistral"
        return "openai"

    async def _call_completion_api(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout_s: float = 60.0,
    ) -> dict[str, Any]:
        provider = self._provider_for_model(model)
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            if provider == "anthropic":
                body: dict[str, Any] = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                if system_prompt:
                    body["system"] = system_prompt
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    json=body,
                    headers={"x-api-key": self.settings.anthropic_api_key, "anthropic-version": "2023-06-01"},
                )
                response.raise_for_status()
                payload = response.json()
                text = payload.get("content", [{}])[0].get("text", "")
                usage = payload.get("usage", {})
                return {"text": text, "usage": usage}

            messages: list[dict[str, str]] = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            if provider == "deepseek":
                response = await client.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
                    headers={"Authorization": f"Bearer {self.settings.deepseek_api_key}"},
                )
            else:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature},
                    headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
                )
            response.raise_for_status()
            payload = response.json()
            text = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage", {})
            return {"text": text, "usage": usage}

    async def _call_with_retries(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout_s: float = 60.0,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return await self._call_completion_api(
                    model=model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout_s=timeout_s,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in NON_RETRIABLE_STATUS_CODES:
                    raise
                if exc.response.status_code in TRANSIENT_STATUS_CODES:
                    last_exc = exc
                    await asyncio.sleep(0.1 * (2**attempt))
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                await asyncio.sleep(0.1 * (2**attempt))
                continue
        raise last_exc or RuntimeError(f"Retries exhausted for model={model}")

    async def complete(
        self,
        *,
        tier: TierName,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout_s: float = 60.0,
    ) -> LLMResponse:
        primary, fallback = self._resolve_tier_models(tier)
        models = [primary] + ([fallback] if fallback else [])
        errors: list[Exception] = []
        for model in models:
            try:
                payload = await self._call_with_retries(
                    model=model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout_s=timeout_s,
                )
                usage = payload.get("usage", {})
                cost = self._estimate_completion_cost(model=model, usage=usage)
                self.total_cost_usd += cost
                return LLMResponse(
                    text=payload["text"],
                    model=model,
                    input_tokens=int(usage.get("input_tokens", 0)),
                    output_tokens=int(usage.get("output_tokens", 0)),
                    cost_usd=cost,
                )
            except Exception as exc:
                errors.append(exc)
                logger.warning("Model %s failed for tier=%s: %s", model, tier, exc)
        raise RuntimeError(f"All completion models failed for tier={tier}: {errors}")

    async def complete_with_model(
        self,
        *,
        model: str,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        timeout_s: float = 60.0,
    ) -> LLMResponse:
        payload = await self._call_with_retries(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
        )
        usage = payload.get("usage", {})
        cost = self._estimate_completion_cost(model=model, usage=usage)
        self.total_cost_usd += cost
        return LLMResponse(
            text=payload["text"],
            model=model,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cost_usd=cost,
        )

    async def _call_embedding_api(
        self, *, model: str, texts: list[str], dimensions: int = 1024, timeout_s: float = 60.0
    ) -> list[list[float]]:
        provider = self._provider_for_model(model)
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            if provider == "mistral":
                key = self.settings.mistral_api_key
                if not key:
                    raise RuntimeError("Mistral API key not configured")
                response = await client.post(
                    "https://api.mistral.ai/v1/embeddings",
                    json={"model": model, "input": texts},
                    headers={"Authorization": f"Bearer {key}"},
                )
                response.raise_for_status()
                data = response.json().get("data", [])
                return [item["embedding"] for item in data]

            body: dict[str, Any] = {"model": model, "input": texts}
            if "text-embedding-3" in model:
                body["dimensions"] = dimensions
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                json=body,
                headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            return [item["embedding"] for item in data]

    async def embed(self, texts: list[str], timeout_s: float = 60.0) -> EmbeddingResult:
        models = [self.settings.embedding_model, self.settings.embedding_fallback_model]
        errors: list[Exception] = []
        for model in models:
            try:
                all_vectors: list[list[float]] = []
                for i in range(0, len(texts), EMBED_BATCH_SIZE):
                    batch = texts[i : i + EMBED_BATCH_SIZE]
                    vectors = await self._call_embedding_with_retries(
                        model=model, texts=batch, timeout_s=timeout_s
                    )
                    all_vectors.extend(vectors)
                return EmbeddingResult(
                    vectors=all_vectors,
                    model=model,
                    provider=self._provider_for_model(model),
                )
            except Exception as exc:
                errors.append(exc)
                logger.warning("Embedding model %s failed: %s", model, exc)
        raise RuntimeError(f"All embedding models failed: {errors}")

    async def _call_embedding_with_retries(
        self, *, model: str, texts: list[str], timeout_s: float = 60.0
    ) -> list[list[float]]:
        last_exc: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                return await self._call_embedding_api(model=model, texts=texts, timeout_s=timeout_s)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in NON_RETRIABLE_STATUS_CODES:
                    raise
                if exc.response.status_code in TRANSIENT_STATUS_CODES:
                    last_exc = exc
                    await asyncio.sleep(0.5 * (2**attempt))
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError, RuntimeError) as exc:
                last_exc = exc
                break
        raise last_exc or RuntimeError(f"Embedding retries exhausted for model={model}")

    def _estimate_completion_cost(self, *, model: str, usage: dict[str, Any]) -> float:
        in_tok = float(usage.get("input_tokens", 0))
        out_tok = float(usage.get("output_tokens", 0))
        lowered = model.lower()
        if "opus" in lowered:
            rate = 0.000015
        elif "haiku" in lowered:
            rate = 0.000001
        elif "sonnet" in lowered:
            rate = 0.000003
        elif "deepseek" in lowered:
            rate = 0.0000014
        else:
            rate = 0.000003
        return (in_tok + out_tok) * rate
