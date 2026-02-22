from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    app_public_base_url: str
    anthropic_api_key: str
    openai_api_key: str
    mistral_api_key: str | None = None
    deepseek_api_key: str
    evolution_api_key: str
    evolution_api_url: str = "http://localhost:8080"

    min_account_age_hours: int = 48
    min_preballot_endorsements: int = 5
    max_signups_per_domain_per_day: int = 3
    max_signups_per_ip_per_day: int = 10
    burst_quarantine_threshold_count: int = 3
    burst_quarantine_window_minutes: int = 5
    major_email_providers: str = "gmail.com,outlook.com,yahoo.com,protonmail.com"

    canonicalization_model: str = "claude-sonnet-latest"
    canonicalization_fallback_model: str = "claude-haiku-latest"
    farsi_messages_model: str = "claude-sonnet-latest"
    farsi_messages_fallback_model: str = "claude-haiku-latest"
    english_reasoning_model: str = "claude-sonnet-latest"
    english_reasoning_fallback_model: str = "deepseek-chat"
    dispute_resolution_model: str = "claude-opus-latest"
    dispute_resolution_fallback_model: str = "claude-sonnet-latest"
    dispute_resolution_ensemble_models: str = (
        "claude-opus-latest,claude-sonnet-latest,deepseek-chat"
    )
    dispute_resolution_confidence_threshold: float = 0.75

    witness_publish_enabled: bool = False
    witness_api_url: str = "https://api.witness.co"
    witness_api_key: str | None = None

    embedding_model: str = "text-embedding-3-large"
    embedding_fallback_model: str = "mistral-embed"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    @field_validator("app_public_base_url")
    @classmethod
    def validate_public_base_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("APP_PUBLIC_BASE_URL must be provided")
        return value

    def major_email_provider_list(self) -> list[str]:
        return [item.strip().lower() for item in self.major_email_providers.split(",") if item.strip()]

    def dispute_ensemble_model_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.dispute_resolution_ensemble_models.split(",")
            if item.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
