from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import Settings, get_settings


def _required_env() -> dict[str, str]:
    return {
        "DATABASE_URL": "postgresql+asyncpg://collective:pw@localhost:5432/collective_will",
        "APP_PUBLIC_BASE_URL": "https://collectivewill.org",
        "ANTHROPIC_API_KEY": "x",
        "OPENAI_API_KEY": "x",
        "DEEPSEEK_API_KEY": "x",
        "EVOLUTION_API_KEY": "x",
    }


def _make_settings(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> Settings:
    for key, value in _required_env().items():
        monkeypatch.setenv(key, value)
    for key, value in overrides.items():
        monkeypatch.setenv(key, value)
    return Settings()


# --- 1. Settings loads successfully ---
def test_settings_loads_successfully(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.database_url.startswith("postgresql+asyncpg://")


# --- 2. Missing required env var raises validation error ---
def test_missing_required_env_var_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _required_env().items():
        if key != "OPENAI_API_KEY":
            monkeypatch.setenv(key, value)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


# --- 3. get_settings() caching ---
def test_get_settings_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    for key, value in _required_env().items():
        monkeypatch.setenv(key, value)
    first = get_settings()
    second = get_settings()
    assert first is second


# --- 4. .env.example covers all Settings keys ---
def test_env_example_contains_all_expected_keys() -> None:
    content = Path(".env.example").read_text(encoding="utf-8")
    settings_fields = {
        "DATABASE_URL", "APP_PUBLIC_BASE_URL", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "MISTRAL_API_KEY", "DEEPSEEK_API_KEY", "EVOLUTION_API_KEY", "EVOLUTION_API_URL",
        "MIN_ACCOUNT_AGE_HOURS", "MIN_CLUSTER_SIZE", "MIN_PREBALLOT_ENDORSEMENTS",
        "MAX_SIGNUPS_PER_DOMAIN_PER_DAY", "MAX_SIGNUPS_PER_IP_PER_DAY",
        "BURST_QUARANTINE_THRESHOLD_COUNT", "BURST_QUARANTINE_WINDOW_MINUTES",
        "MAJOR_EMAIL_PROVIDERS", "CANONICALIZATION_MODEL", "CANONICALIZATION_FALLBACK_MODEL",
        "FARSI_MESSAGES_MODEL", "FARSI_MESSAGES_FALLBACK_MODEL",
        "ENGLISH_REASONING_MODEL", "ENGLISH_REASONING_FALLBACK_MODEL",
        "DISPUTE_RESOLUTION_MODEL", "DISPUTE_RESOLUTION_FALLBACK_MODEL",
        "DISPUTE_RESOLUTION_ENSEMBLE_MODELS", "DISPUTE_RESOLUTION_CONFIDENCE_THRESHOLD",
        "WITNESS_PUBLISH_ENABLED", "WITNESS_API_URL", "WITNESS_API_KEY",
        "EMBEDDING_MODEL", "EMBEDDING_FALLBACK_MODEL",
    }
    for key in settings_fields:
        assert f"{key}=" in content, f"Missing {key} in .env.example"


# --- 5. app_public_base_url validated as present ---
def test_app_public_base_url_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in _required_env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("APP_PUBLIC_BASE_URL", "   ")
    with pytest.raises(ValidationError, match="APP_PUBLIC_BASE_URL"):
        Settings()


# --- 6/7. min_account_age_hours default and override ---
def test_min_account_age_hours_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.min_account_age_hours == 48

    overridden = _make_settings(monkeypatch, MIN_ACCOUNT_AGE_HOURS="1")
    assert overridden.min_account_age_hours == 1


# --- 8/9. min_preballot_endorsements default and override ---
def test_min_preballot_endorsements_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.min_preballot_endorsements == 5

    overridden = _make_settings(monkeypatch, MIN_PREBALLOT_ENDORSEMENTS="2")
    assert overridden.min_preballot_endorsements == 2


def test_min_cluster_size_default_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.min_cluster_size == 5

    overridden = _make_settings(monkeypatch, MIN_CLUSTER_SIZE="3")
    assert overridden.min_cluster_size == 3


# --- 10. max_signups_per_domain_per_day config ---
def test_max_signups_per_domain_per_day_config(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.max_signups_per_domain_per_day == 3

    overridden = _make_settings(monkeypatch, MAX_SIGNUPS_PER_DOMAIN_PER_DAY="10")
    assert overridden.max_signups_per_domain_per_day == 10


# --- 11. max_signups_per_ip_per_day config ---
def test_max_signups_per_ip_per_day_config(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.max_signups_per_ip_per_day == 10

    overridden = _make_settings(monkeypatch, MAX_SIGNUPS_PER_IP_PER_DAY="5")
    assert overridden.max_signups_per_ip_per_day == 5


# --- 12. burst_quarantine_threshold_count default ---
def test_burst_quarantine_threshold_count_default(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.burst_quarantine_threshold_count == 3


# --- 13. burst_quarantine_window_minutes default ---
def test_burst_quarantine_window_minutes_default(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.burst_quarantine_window_minutes == 5


# --- 14. major_email_providers override ---
def test_major_email_providers_override(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert "gmail.com" in settings.major_email_provider_list()

    overridden = _make_settings(monkeypatch, MAJOR_EMAIL_PROVIDERS="a.com,b.com")
    assert overridden.major_email_provider_list() == ["a.com", "b.com"]


# --- 15. Tier model IDs are config-backed and overridable ---
def test_tier_models_config_backed(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.canonicalization_model == "claude-sonnet-4-20250514"

    overridden = _make_settings(monkeypatch, CANONICALIZATION_MODEL="custom-model")
    assert overridden.canonicalization_model == "custom-model"


# --- 16. farsi_messages_fallback_model is set ---
def test_farsi_messages_fallback_model_set(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.farsi_messages_fallback_model == "claude-sonnet-4-20250514"

    overridden = _make_settings(monkeypatch, FARSI_MESSAGES_FALLBACK_MODEL="other")
    assert overridden.farsi_messages_fallback_model == "other"


# --- 17. english_reasoning_fallback_model is set ---
def test_english_reasoning_fallback_model_set(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.english_reasoning_fallback_model == "deepseek-chat"


# --- 18. dispute_resolution_model and fallback configurable ---
def test_dispute_resolution_model_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.dispute_resolution_model == "claude-opus-4-20250514"
    assert settings.dispute_resolution_fallback_model == "claude-sonnet-4-20250514"

    overridden = _make_settings(
        monkeypatch,
        DISPUTE_RESOLUTION_MODEL="custom-opus",
        DISPUTE_RESOLUTION_FALLBACK_MODEL="custom-sonnet",
    )
    assert overridden.dispute_resolution_model == "custom-opus"
    assert overridden.dispute_resolution_fallback_model == "custom-sonnet"


# --- 19. dispute_resolution_ensemble_models configurable ---
def test_dispute_resolution_ensemble_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert len(settings.dispute_ensemble_model_list()) == 3

    overridden = _make_settings(monkeypatch, DISPUTE_RESOLUTION_ENSEMBLE_MODELS="a,b")
    assert overridden.dispute_ensemble_model_list() == ["a", "b"]


# --- 20. dispute_resolution_confidence_threshold configurable ---
def test_dispute_confidence_threshold_configurable(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.dispute_resolution_confidence_threshold == 0.75

    overridden = _make_settings(monkeypatch, DISPUTE_RESOLUTION_CONFIDENCE_THRESHOLD="0.5")
    assert overridden.dispute_resolution_confidence_threshold == 0.5


# --- 21. witness_publish_enabled default ---
def test_witness_publish_enabled_default_false(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.witness_publish_enabled is False


# --- 22. witness_publish_enabled toggles only publication ---
def test_witness_publish_enabled_toggle(monkeypatch: pytest.MonkeyPatch) -> None:
    enabled = _make_settings(monkeypatch, WITNESS_PUBLISH_ENABLED="true", WITNESS_API_KEY="k")
    assert enabled.witness_publish_enabled is True


# --- 23. witness_api_key optional unless publishing enabled ---
def test_witness_api_key_optional_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _make_settings(monkeypatch)
    assert settings.witness_api_key is None
    assert settings.witness_publish_enabled is False
