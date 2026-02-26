# Task: Core Data Models

## Depends on
- `database/01-project-scaffold` (project structure, config)
- `database/02-db-connection` (Base declarative class, session factory)

## Goal
Create SQLAlchemy ORM models and Pydantic schemas for all core tables, plus basic CRUD query functions.

## Files to create/modify

- `src/models/user.py` — User ORM + Pydantic schemas (includes `bot_state` and `bot_state_data`)
- `src/models/submission.py` — Submission + PolicyCandidate ORM + Pydantic schemas
- `src/models/cluster.py` — Cluster ORM + Pydantic schemas (includes `options` relationship)
- `src/models/vote.py` — Vote + VotingCycle ORM + Pydantic schemas (includes `selections` JSONB)
- `src/models/endorsement.py` — PolicyEndorsement ORM + Pydantic schemas
- `src/models/policy_option.py` — PolicyOption ORM + Pydantic schemas (LLM-generated stance options)
- `src/models/__init__.py` — re-export all models
- `src/db/queries.py` — basic CRUD functions

## Specification

### ORM models

Map exactly to the data models in CONTEXT-shared.md. Key details:

**User table**
- `id`: UUID primary key (use `uuid4` default)
- `email`: unique, indexed
- `messaging_account_ref`: unique, indexed (random opaque account ref, NOT raw wa_id)
- `locale`: default `"fa"`
- `trust_score`: default `0.0` (reserved in v0 unless an explicit policy consumes it)
- `contribution_count`: default `0` (processed submissions + recorded policy endorsements)
- `is_anonymous`: default `False`
- `bot_state`: nullable string — tracks current interaction state
- `bot_state_data`: nullable JSONB — session data for multi-step flows

**Submission table**
- `id`: UUID primary key
- `user_id`: foreign key to users
- `hash`: SHA-256 of raw_text, indexed
- `status`: default `"pending"`

**PolicyCandidate table**
- `id`: UUID primary key
- `submission_id`: foreign key to submissions
- `title`: string (English)
- `summary`: string (English)
- `stance`: one of support/oppose/neutral/unclear
- `policy_topic`: string, indexed — umbrella topic (e.g., "internet-censorship")
- `policy_key`: string, indexed — specific ballot-level key (e.g., "political-internet-censorship")
- `entities`: JSONB array of strings
- `embedding`: pgvector `Vector(1024)` column, nullable
- `confidence`: float, 0-1
- `ambiguity_flags`: JSONB array of strings
- `model_version`, `prompt_version`: string, not null

**Cluster table**
- `id`: UUID primary key
- `policy_topic`: string, indexed
- `policy_key`: string, unique, indexed — one cluster per policy_key
- `summary`: string (English)
- `ballot_question`: nullable string
- `ballot_question_fa`: nullable string (Farsi translation)
- `candidate_ids`: ARRAY of UUIDs
- `member_count`: int
- `approval_count`: int, default 0
- `needs_resummarize`: bool, default True
- `last_summarized_count`: int, default 0
- `options`: relationship to `PolicyOption` (ordered by position)

**Vote table**
- `id`: UUID primary key
- `user_id`: foreign key to users
- `cycle_id`: foreign key to voting_cycles
- `approved_cluster_ids`: ARRAY of UUIDs
- `selections`: nullable JSONB — per-policy stance selections

**PolicyOption table**
- `id`: UUID primary key
- `cluster_id`: foreign key to clusters (indexed)
- `position`: int, 1-based display order
- `label`: string (Farsi), not null
- `label_en`: string (English), nullable
- `description`: text (Farsi), not null
- `description_en`: text (English), nullable
- `model_version`: string, not null
- `created_at`: datetime with timezone
- `evidence_log_id`: nullable int

**PolicyEndorsement table**
- `id`: UUID primary key
- `user_id`: foreign key to users
- `cluster_id`: foreign key to clusters
- Unique constraint on `(user_id, cluster_id)`

**VotingCycle table**
- `id`: UUID primary key
- `status`: default `"active"`
- `results`: JSONB (nullable, populated after close)

### Pydantic schemas

For each model, create:
- `Create` schema (input for creating a new record)
- `Read` schema (output for API responses, includes id and timestamps)

### ORM <-> schema conversion pattern

Define explicit conversion methods instead of implicit dict unpacking.

### CRUD queries (src/db/queries.py)

Basic async functions:
- `create_user(session, data) -> User`
- `get_user_by_email(session, email) -> User | None`
- `get_user_by_messaging_ref(session, ref) -> User | None`
- `create_submission(session, data) -> Submission`
- `get_submissions_by_user(session, user_id) -> list[Submission]`
- `create_policy_candidate(session, data) -> PolicyCandidate`
- `create_cluster(session, data) -> Cluster`
- `create_policy_endorsement(session, data) -> PolicyEndorsement`
- `count_cluster_endorsements(session, cluster_id) -> int`
- `create_vote(session, data) -> Vote`
- `count_votes_for_cluster(session, cycle_id, cluster_id) -> int`
- `create_voting_cycle(session, data) -> VotingCycle`
- `create_policy_option(session, data) -> PolicyOption`
- `get_options_for_cluster(session, cluster_id) -> list[PolicyOption]`

## Constraints

- Use `pgvector` for embedding columns.
- UUID columns must use `uuid.uuid4` as default.
- All timestamps use timezone-aware datetimes.
- Do NOT store raw WhatsApp IDs in any model. `messaging_account_ref` is always an opaque random ref.
- Keep SQLAlchemy and Pydantic as separate layers with explicit conversion methods.
- Naming convention: base fields (`title`, `summary`) are English. Farsi translations use `_fa` suffix (e.g., `ballot_question_fa`). No `_en` suffix for English fields.

## Tests

Write tests in `tests/test_db/test_models.py` covering:
- Each ORM model can be created and saved to the test database
- Pydantic schemas validate correct input and reject invalid input
- `get_user_by_email` returns None for nonexistent user
- `get_user_by_messaging_ref` finds user by opaque account ref
- Embedding column stores and retrieves a vector correctly
- Foreign key constraints work
- Duplicate endorsement by same user for the same cluster is rejected by unique constraint
- Conversion methods exist for each core model
