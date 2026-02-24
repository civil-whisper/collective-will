from __future__ import annotations

import httpx
import pytest

from src.config import Settings
from src.pipeline.llm import (
    LLMResponse,
    LLMRouter,
)


def _settings(**overrides: str) -> Settings:
    defaults = {
        "database_url": "postgresql+asyncpg://collective:pw@localhost:5432/collective_will",
        "app_public_base_url": "https://collectivewill.org",
        "anthropic_api_key": "test-anthropic",
        "openai_api_key": "test-openai",
        "deepseek_api_key": "test-deepseek",
        "evolution_api_key": "test-evo",
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _make_completion_payload(text: str = "ok") -> dict[str, object]:
    return {"text": text, "usage": {"input_tokens": 10, "output_tokens": 5}}


# --- 1. canonicalization routes to Anthropic Sonnet ---
@pytest.mark.asyncio
async def test_complete_canonicalization_routes_to_anthropic() -> None:
    router = LLMRouter(settings=_settings())
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    result = await router.complete(tier="canonicalization", prompt="x")
    assert "sonnet" in calls[0].lower()
    assert isinstance(result, LLMResponse)


# --- 2. farsi_messages routes to configured primary ---
@pytest.mark.asyncio
async def test_complete_farsi_messages_routes_primary() -> None:
    router = LLMRouter(settings=_settings())
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    await router.complete(tier="farsi_messages", prompt="x")
    assert calls[0] == "claude-sonnet-4-20250514"


# --- 3. farsi_messages falls back on primary failure ---
@pytest.mark.asyncio
async def test_complete_farsi_messages_fallback() -> None:
    router = LLMRouter(settings=_settings())
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("primary fail")
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    result = await router.complete(tier="farsi_messages", prompt="x")
    assert len(calls) == 2
    assert result.model == "claude-sonnet-4-20250514"


# --- 4. english_reasoning routes primary ---
@pytest.mark.asyncio
async def test_complete_english_reasoning_primary() -> None:
    router = LLMRouter(settings=_settings())
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    await router.complete(tier="english_reasoning", prompt="x")
    assert calls[0] == "claude-sonnet-4-20250514"


# --- 5. english_reasoning falls back ---
@pytest.mark.asyncio
async def test_complete_english_reasoning_fallback() -> None:
    router = LLMRouter(settings=_settings())
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("fail")
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    result = await router.complete(tier="english_reasoning", prompt="x")
    assert result.model == "deepseek-chat"


# --- 6. dispute_resolution routes primary ---
@pytest.mark.asyncio
async def test_complete_dispute_resolution_primary() -> None:
    router = LLMRouter(settings=_settings())
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    await router.complete(tier="dispute_resolution", prompt="x")
    assert calls[0] == "claude-opus-4-20250514"


# --- 7. dispute_resolution falls back ---
@pytest.mark.asyncio
async def test_complete_dispute_resolution_fallback() -> None:
    router = LLMRouter(settings=_settings())
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("fail")
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    result = await router.complete(tier="dispute_resolution", prompt="x")
    assert result.model == "claude-sonnet-4-20250514"


# --- 8/9/10. Dispute resolution threshold and ensemble ---
@pytest.mark.asyncio
async def test_dispute_threshold_is_config_driven() -> None:
    settings = _settings(dispute_resolution_confidence_threshold="0.5")
    assert settings.dispute_resolution_confidence_threshold == 0.5

    settings2 = _settings(dispute_resolution_confidence_threshold="0.9")
    assert settings2.dispute_resolution_confidence_threshold == 0.9


# --- 11. Overriding tier models in settings ---
@pytest.mark.asyncio
async def test_overriding_tier_model_ids() -> None:
    router = LLMRouter(settings=_settings(canonicalization_model="custom-model"))
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    await router.complete(tier="canonicalization", prompt="x")
    assert calls[0] == "custom-model"


# --- 12. embed() calls configured provider ---
@pytest.mark.asyncio
async def test_embed_calls_primary() -> None:
    router = LLMRouter(settings=_settings())
    calls: list[str] = []

    async def _fake(*, model: str, texts: list[str], timeout_s: float = 60.0) -> list[list[float]]:
        calls.append(model)
        return [[0.1, 0.2] for _ in texts]

    router._call_embedding_api = _fake  # type: ignore[method-assign]
    result = await router.embed(["a", "b"])
    assert calls[0] == "text-embedding-3-large"
    assert len(result.vectors) == 2


# --- 13. embed() batch splitting ---
@pytest.mark.asyncio
async def test_embed_splits_large_batch() -> None:
    router = LLMRouter(settings=_settings())
    call_count = 0
    batch_size = router.settings.llm_embed_batch_size

    async def _fake(*, model: str, texts: list[str], timeout_s: float = 60.0) -> list[list[float]]:
        nonlocal call_count
        call_count += 1
        assert len(texts) <= batch_size
        return [[0.1] for _ in texts]

    router._call_embedding_api = _fake  # type: ignore[method-assign]
    texts = [f"text-{i}" for i in range(batch_size + 10)]
    result = await router.embed(texts)
    assert call_count == 2
    assert len(result.vectors) == batch_size + 10


# --- 14. Embedding fallback ---
@pytest.mark.asyncio
async def test_embed_fallback_on_primary_failure() -> None:
    router = LLMRouter(settings=_settings())
    calls: list[str] = []

    async def _fake(*, model: str, texts: list[str], timeout_s: float = 60.0) -> list[list[float]]:
        calls.append(model)
        if "text-embedding" in model:
            raise RuntimeError("primary down")
        return [[0.1] for _ in texts]

    router._call_embedding_api = _fake  # type: ignore[method-assign]
    result = await router.embed(["a"])
    assert result.model == "mistral-embed"


# --- 15. LLMResponse fields ---
@pytest.mark.asyncio
async def test_llm_response_fields() -> None:
    router = LLMRouter(settings=_settings())

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        return {"text": "hello", "usage": {"input_tokens": 100, "output_tokens": 50}}

    router._call_with_retries = _fake  # type: ignore[method-assign]
    result = await router.complete(tier="canonicalization", prompt="x")
    assert result.text == "hello"
    assert result.model == "claude-sonnet-4-20250514"
    assert result.input_tokens == 100
    assert result.output_tokens == 50
    assert result.cost_usd >= 0


# --- 16. Retry on transient 429, success on 2nd attempt ---
@pytest.mark.asyncio
async def test_retry_on_429() -> None:
    router = LLMRouter(settings=_settings())
    attempt = 0

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        nonlocal attempt
        attempt += 1
        if attempt == 1:
            resp = httpx.Response(429, request=httpx.Request("POST", "https://example.com"))
            raise httpx.HTTPStatusError("rate limited", request=resp.request, response=resp)
        return _make_completion_payload()

    router._call_completion_api = _fake  # type: ignore[method-assign]
    result = await router.complete(tier="canonicalization", prompt="x")
    assert result.text == "ok"
    assert attempt == 2


# --- 17. Auth error 401 not retried ---
@pytest.mark.asyncio
async def test_auth_error_not_retried() -> None:
    router = LLMRouter(settings=_settings())
    attempt = 0

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        nonlocal attempt
        attempt += 1
        resp = httpx.Response(401, request=httpx.Request("POST", "https://example.com"))
        raise httpx.HTTPStatusError("auth error", request=resp.request, response=resp)

    router._call_completion_api = _fake  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="All completion models failed"):
        await router.complete(tier="canonicalization", prompt="x")
    assert attempt <= 2


# --- 18. Cost estimate is non-negative ---
def test_cost_estimate_non_negative() -> None:
    router = LLMRouter(settings=_settings())
    usage = {"input_tokens": 100, "output_tokens": 50}
    cost = router._estimate_completion_cost(model="claude-sonnet-4-20250514", usage=usage)
    assert cost >= 0
    assert cost > 0

    opus_cost = router._estimate_completion_cost(model="claude-opus-4-20250514", usage=usage)
    assert opus_cost >= 0
    assert opus_cost > cost  # opus more expensive than sonnet


# --- 19. Provider detection for Gemini models ---
def test_provider_for_gemini_models() -> None:
    router = LLMRouter(settings=_settings())
    assert router._provider_for_model("gemini-3.1-pro-preview") == "google"
    assert router._provider_for_model("gemini-2.5-pro") == "google"
    assert router._provider_for_model("gemini-2.5-flash") == "google"
    assert router._provider_for_model("gemini-embedding-001") == "google"


# --- 20. Gemini completion routes correctly when configured ---
@pytest.mark.asyncio
async def test_complete_routes_to_gemini_when_configured() -> None:
    router = LLMRouter(settings=_settings(
        canonicalization_model="gemini-3.1-pro-preview",
        canonicalization_fallback_model="claude-sonnet-4-20250514",
    ))
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    result = await router.complete(tier="canonicalization", prompt="x")
    assert calls[0] == "gemini-3.1-pro-preview"
    assert result.model == "gemini-3.1-pro-preview"


# --- 21. Gemini fallback to Claude on failure ---
@pytest.mark.asyncio
async def test_gemini_falls_back_to_claude() -> None:
    router = LLMRouter(settings=_settings(
        english_reasoning_model="gemini-2.5-pro",
        english_reasoning_fallback_model="claude-sonnet-4-20250514",
    ))
    calls: list[str] = []

    async def _fake(*, model: str, **kw: object) -> dict[str, object]:
        calls.append(model)
        if "gemini" in model:
            raise RuntimeError("gemini down")
        return _make_completion_payload()

    router._call_with_retries = _fake  # type: ignore[method-assign]
    result = await router.complete(tier="english_reasoning", prompt="x")
    assert len(calls) == 2
    assert calls[0] == "gemini-2.5-pro"
    assert result.model == "claude-sonnet-4-20250514"


# --- 22. Gemini cost estimates ---
def test_gemini_cost_estimates() -> None:
    router = LLMRouter(settings=_settings())
    usage = {"input_tokens": 100, "output_tokens": 50}

    pro_cost = router._estimate_completion_cost(model="gemini-3.1-pro-preview", usage=usage)
    assert pro_cost > 0

    flash_cost = router._estimate_completion_cost(model="gemini-2.5-flash", usage=usage)
    assert flash_cost > 0
    assert flash_cost < pro_cost  # flash cheaper than pro

    sonnet_cost = router._estimate_completion_cost(model="claude-sonnet-4-20250514", usage=usage)
    assert pro_cost < sonnet_cost  # gemini pro cheaper than sonnet


# --- 23. Gemini embedding routes correctly ---
@pytest.mark.asyncio
async def test_embed_routes_to_gemini_when_configured() -> None:
    router = LLMRouter(settings=_settings(
        embedding_model="gemini-embedding-001",
        embedding_fallback_model="text-embedding-3-large",
    ))
    calls: list[str] = []

    async def _fake(*, model: str, texts: list[str], timeout_s: float = 60.0) -> list[list[float]]:
        calls.append(model)
        return [[0.1, 0.2] for _ in texts]

    router._call_embedding_api = _fake  # type: ignore[method-assign]
    result = await router.embed(["a", "b"])
    assert calls[0] == "gemini-embedding-001"
    assert result.provider == "google"
    assert len(result.vectors) == 2
