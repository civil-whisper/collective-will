from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    app_public_base_url: str
    anthropic_api_key: str
    openai_api_key: str
    google_api_key: str | None = None
    mistral_api_key: str | None = None
    deepseek_api_key: str
    evolution_api_key: str
    evolution_api_url: str = "http://localhost:8080"
    telegram_bot_token: str | None = None
    telegram_webhook_secret: str | None = None
    cors_allow_origins: str = "http://localhost:3000"
    telegram_http_timeout_seconds: float = 30.0
    whatsapp_http_timeout_seconds: float = 30.0
    email_http_timeout_seconds: float = 10.0
    witness_http_timeout_seconds: float = 20.0

    min_account_age_hours: int = 48
    min_preballot_endorsements: int = 5
    resummarize_growth_threshold: float = 0.5
    max_signups_per_domain_per_day: int = 3
    max_signups_per_ip_per_day: int = 10
    burst_quarantine_threshold_count: int = 3
    burst_quarantine_window_minutes: int = 5
    major_email_providers: str = "gmail.com,outlook.com,yahoo.com,protonmail.com"
    voting_cycle_hours: int = 48
    auto_cycle_cooldown_hours: float = 1.0
    pipeline_interval_hours: float = 6.0
    pipeline_min_interval_hours: float = 0.01
    batch_threshold: int = 10
    batch_poll_seconds: float = 60.0
    max_submissions_per_day: int = 5
    require_contribution_for_vote: bool = True
    max_vote_submissions_per_cycle: int = 2
    signup_domain_diversity_threshold: int = 5
    magic_link_expiry_minutes: int = 15
    linking_code_expiry_minutes: int = 60
    web_session_code_expiry_minutes: int = 10
    web_access_token_expiry_hours: int = 24 * 30
    web_access_token_secret: str
    dispute_metrics_lookback_days: int = 7
    dispute_rate_tuning_threshold: float = 0.05
    dispute_disagreement_tuning_threshold: float = 0.30
    # Voice verification — cloud APIs
    voice_embedding_endpoint_url: str = ""  # Modal web endpoint URL
    voice_embedding_auth_token: str | None = None
    voice_embedding_timeout_seconds: float = 30.0
    voice_transcription_timeout_seconds: float = 20.0
    voice_cloud_max_retries: int = 2
    # Unified embedding thresholds (ECAPA2: same-speaker min ~0.57, cross-speaker max ~0.31)
    voice_embedding_similarity_high: float = 0.45
    voice_embedding_similarity_delta: float = 0.07  # moderate = high - delta = 0.38
    # Unified transcription thresholds (GPT-4o-transcribe: EN and FA both score ~1.0)
    voice_transcription_score_standard: float = 0.65
    voice_transcription_score_strict: float = 0.75
    voice_enrollment_phrases_per_session: int = 3
    voice_enrollment_max_phrase_failures: int = 3
    voice_enrollment_attempts_per_phrase: int = 2
    voice_session_duration_minutes: int = 30
    voice_verification_max_attempts: int = 4
    voice_verification_rate_limit_count: int = 5
    voice_verification_rate_limit_window_seconds: int = 3600
    voice_audio_min_duration_seconds: int = 1  # allow short phrases; technical codes only for pipeline failures
    voice_audio_max_duration_seconds: int = 10
    voice_phrases_file: str = "voice-phrases.json"
    voice_encryption_key: str | None = None

    ops_console_enabled: bool = False
    ops_console_show_in_nav: bool = False
    ops_console_require_admin: bool = True
    ops_admin_emails: str = ""
    ops_event_buffer_size: int = 500
    ops_alert_emails: str = ""
    ops_heartbeat_hour_utc: int = 8
    ops_monitor_lookback_minutes: int = 10
    ops_alert_dedup_minutes: int = 60

    canonicalization_model: str = "gpt-5.4-mini"
    canonicalization_fallback_model: str = "claude-sonnet-4-6"
    farsi_messages_model: str = "gpt-5.4-mini"
    farsi_messages_fallback_model: str = "claude-sonnet-4-6"
    english_reasoning_model: str = "gpt-5.4-mini"
    english_reasoning_fallback_model: str = "claude-sonnet-4-6"
    option_generation_model: str = "gpt-5.4-mini"
    option_generation_fallback_model: str = "claude-sonnet-4-6"
    option_generation_grounding_enabled: bool = False
    option_generation_grounding_topics: str = "digital-rights"
    dispute_resolution_model: str = "gpt-5.4-mini"
    dispute_resolution_fallback_model: str = "claude-sonnet-4-6"
    dispute_resolution_ensemble_models: str = (
        "gpt-5.4-mini,claude-sonnet-4-6"
    )
    dispute_resolution_confidence_threshold: float = 0.75

    resend_api_key: str | None = None
    email_from: str = "onboarding@resend.dev"

    witness_publish_enabled: bool = False
    witness_api_url: str = "https://api.witness.co"
    witness_api_key: str | None = None
    audit_bundle_output_dir: str = "data/audit-bundles"
    audit_timestamp_provider: str = "none"
    opentimestamps_calendar_urls: str = ""
    opentimestamps_timeout_seconds: int = 5
    opentimestamps_required_calendar_count: int = 2
    opentimestamps_bitcoin_node_url: str | None = None

    embedding_model: str = "gemini-embedding-001"
    embedding_fallback_model: str = "text-embedding-3-large"
    llm_max_retries: int = 3
    llm_completion_retry_backoff_base_seconds: float = 0.1
    llm_embedding_retry_backoff_base_seconds: float = 0.5
    llm_embed_batch_size: int = 64
    llm_default_max_tokens: int = 1024
    llm_default_temperature: float = 0.0
    llm_completion_timeout_seconds: float = 60.0
    llm_embedding_timeout_seconds: float = 60.0
    llm_embedding_dimensions: int = 1024
    llm_transient_status_codes: str = "429,500,502,503"
    llm_non_retriable_status_codes: str = "400,401"
    llm_fail_fast_on_transient_errors: bool = False
    llm_retry_debug_logging_enabled: bool = False
    canonicalization_context_max_entries: int = 8
    canonicalization_context_summary_chars: int = 120
    llm_prompt_caching_enabled: bool = True
    dispute_ensemble_temperature: float = 0.1

    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_timeout_seconds: int = 30
    db_echo_sql: bool = False

    model_config = SettingsConfigDict(
        env_file=(".env.secrets", ".env"), case_sensitive=False, extra="ignore",
    )

    @field_validator("app_public_base_url")
    @classmethod
    def validate_public_base_url(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("APP_PUBLIC_BASE_URL must be provided")
        return value

    @field_validator("web_access_token_secret")
    @classmethod
    def validate_web_access_token_secret(cls, value: str) -> str:
        if value == "change-me-in-production":
            raise ValueError("WEB_ACCESS_TOKEN_SECRET must be changed from the default placeholder")
        return value

    @field_validator("audit_timestamp_provider")
    @classmethod
    def validate_audit_timestamp_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"none", "opentimestamps"}:
            raise ValueError("AUDIT_TIMESTAMP_PROVIDER must be 'none' or 'opentimestamps'")
        return normalized

    def major_email_provider_list(self) -> list[str]:
        return [item.strip().lower() for item in self.major_email_providers.split(",") if item.strip()]

    def dispute_ensemble_model_list(self) -> list[str]:
        return [
            item.strip()
            for item in self.dispute_resolution_ensemble_models.split(",")
            if item.strip()
        ]

    def ops_admin_email_list(self) -> list[str]:
        return [item.strip().lower() for item in self.ops_admin_emails.split(",") if item.strip()]

    def ops_alert_email_list(self) -> list[str]:
        return [item.strip().lower() for item in self.ops_alert_emails.split(",") if item.strip()]

    def cors_allow_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_allow_origins.split(",") if item.strip()]

    def llm_transient_status_code_set(self) -> set[int]:
        return {int(item.strip()) for item in self.llm_transient_status_codes.split(",") if item.strip()}

    def llm_non_retriable_status_code_set(self) -> set[int]:
        return {int(item.strip()) for item in self.llm_non_retriable_status_codes.split(",") if item.strip()}

    def opentimestamps_calendar_url_list(self) -> list[str]:
        return [item.strip() for item in self.opentimestamps_calendar_urls.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
