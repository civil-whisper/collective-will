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
        self._transient_status_codes = self.settings.llm_transient_status_code_set()
        self._non_retriable_status_codes = self.settings.llm_non_retriable_status_code_set()

    def _completion_call_params(
        self,
        *,
        max_tokens: int | None,
        temperature: float | None,
        timeout_s: float | None,
    ) -> tuple[int, float, float]:
        return (
            max_tokens if max_tokens is not None else self.settings.llm_default_max_tokens,
            temperature if temperature is not None else self.settings.llm_default_temperature,
            timeout_s if timeout_s is not None else self.settings.llm_completion_timeout_seconds,
        )

    def _embedding_call_params(
        self,
        *,
        dimensions: int | None,
        timeout_s: float | None,
    ) -> tuple[int, float]:
        return (
            dimensions if dimensions is not None else self.settings.llm_embedding_dimensions,
            timeout_s if timeout_s is not None else self.settings.llm_embedding_timeout_seconds,
        )

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
        if "gemini" in lowered:
            return "google"
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
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        max_tokens, temperature, timeout_s = self._completion_call_params(
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
        )
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

            if provider == "google":
                key = self.settings.google_api_key
                if not key:
                    raise RuntimeError("Google API key not configured")
                gemini_body: dict[str, Any] = {
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens,
                    },
                }
                if system_prompt:
                    gemini_body["systemInstruction"] = {"parts": [{"text": system_prompt}]}
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                response = await client.post(
                    url,
                    json=gemini_body,
                    headers={"x-goog-api-key": key},
                )
                response.raise_for_status()
                payload = response.json()
                candidates = payload.get("candidates", [{}])
                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                usage_meta = payload.get("usageMetadata", {})
                usage = {
                    "input_tokens": usage_meta.get("promptTokenCount", 0),
                    "output_tokens": (
                        usage_meta.get("candidatesTokenCount", 0)
                        + usage_meta.get("thoughtsTokenCount", 0)
                    ),
                }
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
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        max_tokens, temperature, timeout_s = self._completion_call_params(
            max_tokens=max_tokens,
            temperature=temperature,
            timeout_s=timeout_s,
        )
        last_exc: Exception | None = None
        retry_count = max(1, self.settings.llm_max_retries)
        backoff_base = self.settings.llm_completion_retry_backoff_base_seconds
        for attempt in range(retry_count):
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
                if exc.response.status_code in self._non_retriable_status_codes:
                    raise
                if exc.response.status_code in self._transient_status_codes:
                    last_exc = exc
                    await asyncio.sleep(backoff_base * (2**attempt))
                    continue
                raise
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                last_exc = exc
                await asyncio.sleep(backoff_base * (2**attempt))
                continue
        raise last_exc or RuntimeError(f"Retries exhausted for model={model}")

    async def complete(
        self,
        *,
        tier: TierName,
        prompt: str,
        system_prompt: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_s: float | None = None,
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
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_s: float | None = None,
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
        self,
        *,
        model: str,
        texts: list[str],
        dimensions: int | None = None,
        timeout_s: float | None = None,
    ) -> list[list[float]]:
        dimensions, timeout_s = self._embedding_call_params(dimensions=dimensions, timeout_s=timeout_s)
        provider = self._provider_for_model(model)
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            if provider == "google":
                key = self.settings.google_api_key
                if not key:
                    raise RuntimeError("Google API key not configured")
                requests_list = [
                    {
                        "model": f"models/{model}",
                        "content": {"parts": [{"text": t}]},
                        "outputDimensionality": dimensions,
                    }
                    for t in texts
                ]
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
                response = await client.post(
                    url,
                    json={"requests": requests_list},
                    headers={"x-goog-api-key": key},
                )
                response.raise_for_status()
                embeddings = response.json().get("embeddings", [])
                return [item["values"] for item in embeddings]

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

    async def embed(self, texts: list[str], timeout_s: float | None = None) -> EmbeddingResult:
        models = [self.settings.embedding_model, self.settings.embedding_fallback_model]
        batch_size = max(1, self.settings.llm_embed_batch_size)
        errors: list[Exception] = []
        for model in models:
            try:
                all_vectors: list[list[float]] = []
                for i in range(0, len(texts), batch_size):
                    batch = texts[i : i + batch_size]
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
        self,
        *,
        model: str,
        texts: list[str],
        timeout_s: float | None = None,
    ) -> list[list[float]]:
        _, timeout_s = self._embedding_call_params(dimensions=None, timeout_s=timeout_s)
        last_exc: Exception | None = None
        retry_count = max(1, self.settings.llm_max_retries)
        backoff_base = self.settings.llm_embedding_retry_backoff_base_seconds
        for attempt in range(retry_count):
            try:
                return await self._call_embedding_api(model=model, texts=texts, timeout_s=timeout_s)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code in self._non_retriable_status_codes:
                    raise
                if exc.response.status_code in self._transient_status_codes:
                    last_exc = exc
                    await asyncio.sleep(backoff_base * (2**attempt))
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
        elif "gemini" in lowered and "flash" in lowered:
            rate = 0.0000003
        elif "gemini" in lowered:
            rate = 0.000002
        else:
            rate = 0.000003
        return (in_tok + out_tok) * rate
