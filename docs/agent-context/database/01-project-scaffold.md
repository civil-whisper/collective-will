# Task: Project Scaffold

## Depends on
Nothing — this is the first task.

## Goal
Create the Python project skeleton: dependency management, directory structure, configuration module, and environment template.

## Files to create

- `pyproject.toml` — project metadata, dependencies, tool config (ruff, mypy, pytest)
- `src/__init__.py`
- `src/config.py` — Pydantic Settings loading all env vars
- `src/models/__init__.py`
- `src/db/__init__.py`
- `src/channels/__init__.py`
- `src/handlers/__init__.py`
- `src/pipeline/__init__.py`
- `src/api/__init__.py`
- `.env.example` — template with all required env vars (no values)
- `.gitignore` — Python, Node, .env, IDE files

## Specification

### pyproject.toml

Use `uv` as the dependency manager. Key dependencies:

```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
asyncpg
pydantic
pydantic-settings
httpx
hdbscan
scikit-learn
numpy
alembic
python-dotenv
```

Dev dependencies:
```
pytest
pytest-asyncio
mypy
ruff
```

Configure ruff, mypy (strict mode), and pytest in pyproject.toml.

### src/config.py

Use `pydantic_settings.BaseSettings` to load configuration from `.env`:

```python
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
    dispute_resolution_ensemble_models: str = "claude-opus-latest,claude-sonnet-latest,deepseek-chat"
    dispute_resolution_confidence_threshold: float = 0.75
    witness_publish_enabled: bool = False
    witness_api_url: str = "https://api.witness.co"
    witness_api_key: str | None = None
    embedding_model: str = "text-embedding-3-large"
    embedding_fallback_model: str = "mistral-embed"

    model_config = SettingsConfigDict(env_file=".env")
```

Provide a `get_settings()` function with `@lru_cache` for singleton access.

### .env.example

```
DATABASE_URL=postgresql+asyncpg://collective:password@localhost:5432/collective_will
APP_PUBLIC_BASE_URL=https://collectivewill.org
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
MISTRAL_API_KEY=  # Optional in v0 when only primary embedding model is used
DEEPSEEK_API_KEY=
EVOLUTION_API_KEY=
EVOLUTION_API_URL=http://localhost:8080
MIN_ACCOUNT_AGE_HOURS=48
MIN_PREBALLOT_ENDORSEMENTS=5
MAX_SIGNUPS_PER_DOMAIN_PER_DAY=3
MAX_SIGNUPS_PER_IP_PER_DAY=10
BURST_QUARANTINE_THRESHOLD_COUNT=3
BURST_QUARANTINE_WINDOW_MINUTES=5
MAJOR_EMAIL_PROVIDERS=gmail.com,outlook.com,yahoo.com,protonmail.com
CANONICALIZATION_MODEL=claude-sonnet-latest
CANONICALIZATION_FALLBACK_MODEL=claude-haiku-latest
FARSI_MESSAGES_MODEL=claude-sonnet-latest
FARSI_MESSAGES_FALLBACK_MODEL=claude-haiku-latest
ENGLISH_REASONING_MODEL=claude-sonnet-latest
ENGLISH_REASONING_FALLBACK_MODEL=deepseek-chat
DISPUTE_RESOLUTION_MODEL=claude-opus-latest
DISPUTE_RESOLUTION_FALLBACK_MODEL=claude-sonnet-latest
DISPUTE_RESOLUTION_ENSEMBLE_MODELS=claude-opus-latest,claude-sonnet-latest,deepseek-chat
DISPUTE_RESOLUTION_CONFIDENCE_THRESHOLD=0.75
WITNESS_PUBLISH_ENABLED=false
WITNESS_API_URL=https://api.witness.co
WITNESS_API_KEY=  # Optional; required only when WITNESS_PUBLISH_ENABLED=true
EMBEDDING_MODEL=text-embedding-3-large
EMBEDDING_FALLBACK_MODEL=mistral-embed
```

## Constraints

- Do NOT hardcode any secret values.
- Do NOT add dependencies beyond what's listed unless strictly necessary.
- All `__init__.py` files can be empty for now.
- Keep signup-abuse thresholds and major-provider exemptions config-driven (no hardcoded domain list in business logic).

## Tests

Write tests in `tests/test_config.py` covering:
- Settings loads successfully when all env vars are present
- Missing required env var raises a clear validation error
- `get_settings()` returns the same instance on repeated calls (caching works)
- `.env.example` contains all keys that `Settings` expects
- `app_public_base_url` is validated as present and used for external links
- `min_account_age_hours` defaults to `48` when unset
- `MIN_ACCOUNT_AGE_HOURS` can be overridden in tests (e.g., set to `1`)
- `min_preballot_endorsements` defaults to `5` when unset
- `MIN_PREBALLOT_ENDORSEMENTS` can be overridden in tests
- `max_signups_per_domain_per_day` applies to non-major domains only
- `max_signups_per_ip_per_day` blocks abusive signup bursts from a single IP
- `burst_quarantine_threshold_count` defaults to `3`
- `burst_quarantine_window_minutes` defaults to `5`
- `major_email_providers` list can be overridden to tune exemption policy
- Tier model IDs are config-backed and can be overridden without changing code
- `farsi_messages_fallback_model` is set and used when primary messaging model fails
- `english_reasoning_fallback_model` is set and used when primary summary model fails
- `dispute_resolution_model` and fallback are configurable for autonomous dispute adjudication
- `dispute_resolution_ensemble_models` is configurable for low-confidence tie-breaker flow
- `dispute_resolution_confidence_threshold` is configurable and controls escalation policy
- Merkle-root computation runs in v0 regardless of publish setting
- `witness_publish_enabled` toggles only external publication (not root computation)
- `witness_api_key` is optional unless publishing is enabled
