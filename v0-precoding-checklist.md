# v0 Pre-Coding Checklist

Everything that needs to happen before writing code.

Scope reflects current frozen decisions:
- WhatsApp only (Evolution API) for v0
- No action execution in v0
- Cloud embeddings via quality-first default (`text-embedding-3-large`) with fallback configured
- Privacy-first infra (Njalla domain + 1984.is VPS)

---

## 1) Identity and account separation (required)

### Public-facing project identity (pseudonymous)
Use a dedicated pseudonymous identity for:
- GitHub account
- Git commit name/email
- Project communications
- Domain/hosting accounts (Njalla + 1984.is)
- Social media handles

Recommended: dedicated ProtonMail address (example: `pseudo@protonmail.com`).

### Non-public service accounts (can be regular identity)
Use regular accounts for:
- Anthropic API
- OpenAI API
- DeepSeek API
- Dev tooling accounts

Important:
- Do not use your pseudonymous public identity for LLM API billing accounts.
- Keep public pseudonymous identity and personal/billing identity separate.

---

## 2) Claim project name and handles

Register these before anything is public. Names get squatted fast.

### Domains (register via Njalla)
- [ ] `collectivewill.org` — primary domain
- [ ] `collective-will.org` — redirect to primary, prevents confusion

### Social handles
- [ ] Twitter/X — `@collectivewill` (project) and `@civil_whisper` (builder pseudonym)
- [ ] Telegram — `@collectivewill` channel/group (if needed for community)
- [ ] Reddit — `r/collectivewill` (optional, free)

### Code namespaces (claim when publishing, not now)
- [ ] GitHub org or repo under pseudonymous account
- [ ] PyPI / npm package names (when code is ready to publish)

---

## 3) API keys needed before coding

Each collaborator who runs the stack locally should have access to:
- `ANTHROPIC_API_KEY` (canonicalization / messaging / reasoning tiers)
- `OPENAI_API_KEY` (embedding default in v0)
- `DEEPSEEK_API_KEY` (configured fallback path where applicable)
- `MISTRAL_API_KEY` (optional embedding fallback path)
- `EVOLUTION_API_KEY` (WhatsApp gateway auth)

Do not commit keys. Keep them in local `.env` only.

---

## 4) Local development prerequisites

- Python 3.11+
- Node.js 20+ (website work)
- Docker + Docker Compose
- `uv` (Python dependency manager)

---

## 5) Local environment template

Create a local `.env` (never commit):

```bash
# LLM/API
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
MISTRAL_API_KEY=  # Optional fallback provider

# WhatsApp gateway (Evolution API)
EVOLUTION_API_KEY=
EVOLUTION_API_URL=http://evolution:8080

# App
DATABASE_URL=postgres://collective:<password>@postgres:5432/collective_will
```

Also ensure `.env` is in `.gitignore`.

---

## 6) WhatsApp setup for v0

v0 uses:
- Evolution API (self-hosted Docker container)
- No Meta Business verification required for development/early pilot

v1 migration plan:
- Move to official WhatsApp Business API for stability/compliance at scale
- Keep channel adapter boundary clean so migration mostly affects `whatsapp.py`

---

## 7) What to set up now vs later

### Set up now (blocks coding)
- Pseudonymous git identity (for commits and GitHub activity)
- API keys: Anthropic, OpenAI, DeepSeek (Mistral optional fallback)
- Local dev environment (Python/Node/Docker/uv)
- Evolution API local container

### Set up before pilot launch (does not block coding)
- Domain via Njalla
- VPS via 1984.is
- Cloudflare DNS + HTTPS
- Backup/monitoring hardening
- Social media presence

### Claim now (doesn't block coding but gets squatted)
- Domains
- Social handles (Twitter/X, Telegram)

---

## 8) Minimum security rules for collaborators

- Never put real names in commits, code comments, or public docs.
- Never commit secrets (`.env`, private keys, tokens).
- Use VPN for project account access.
- Do not store raw WhatsApp identifiers in logs or analytics exports.
- Treat account mapping data as sensitive; tokenize where possible.

---

## 9) Ready-to-start checklist

- [ ] Pseudonymous ProtonMail created
- [ ] Pseudonymous GitHub account created
- [ ] Git identity configured (repo-level, not global)
- [ ] Domains registered (`collectivewill.org`, `collective-will.org`)
- [ ] Social handles claimed (Twitter/X at minimum)
- [ ] Required API keys available locally
- [ ] `.env` created and ignored by git
- [ ] Docker services run locally (Postgres + Evolution API)
- [ ] Team aligned on v0 boundaries (no action execution, WhatsApp only)
