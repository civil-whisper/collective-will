# Decision Rationale — CONTEXT-shared.md

> **Corresponds to**: [`docs/agent-context/CONTEXT-shared.md`](../agent-context/CONTEXT-shared.md)
>
> When a decision changes in either file, update the other. Every decision here must map to a rule in the context file and vice versa.

---

## Verdicts Key

| Verdict | Meaning |
|---------|---------|
| **Keep** | Decision is sound. No changes needed. |
| **Keep with guardrail** | Decision is correct but needs a documented safeguard to avoid a foreseeable risk. |
| **Reconsider** | A better alternative exists and should be adopted before implementation. |

---

## Theme 1: Product Scope, Channel, and Identity

### D1 — Scope: Consensus visibility + approval voting only

**Context rule**: No action drafting or execution in v0.

**Rationale**: Build the sensing layer before the acting layer. Action execution (petitions, legislative drafts, fund allocation) is politically and legally explosive. Scoping v0 to surfacing and ranking proves the data pipeline works without solving downstream trust/governance problems.

**Risk**: Users may feel "nothing happens" and disengage before v1.

**Guardrail**: Plan a lightweight "what happens next" communication in the WhatsApp flow so users understand they're contributing to a growing picture, not shouting into a void. This is a UX copy concern, not a scope change.

**Verdict**: **Keep**

---

### D2 — Channel: WhatsApp only (Evolution API, self-hosted)

**Context rule**: No Telegram, no Signal in v0. Messaging architecture must remain channel-agnostic via `BaseChannel`.

**Rationale**: WhatsApp is overwhelmingly dominant in Iran (inside and diaspora). Evolution API is a self-hosted, unofficial WhatsApp gateway that avoids Meta's Business API approval process — important for a politically sensitive project. One channel first simplifies the messaging abstraction, webhook handling, and testing surface.

**Risk**: Evolution API is unofficial. Meta can break it with protocol changes at any time, taking the project offline. Some security-conscious users inside Iran prefer Signal; excluding them excludes the most at-risk demographic.

**Guardrail**: Treat `BaseChannel` boundary as mandatory: keep provider-specific parsing in channel adapters, keep handlers/router on normalized models only, and enforce this with fake/mock-channel tests so adding Signal/Telegram in v1 is a one-module addition.

**Verdict**: **Keep with guardrail**

---

### D3 — Identity: Email magic-link + WhatsApp account linking

**Context rule**: No phone verification, no OAuth, no vouching.

**Rationale**: Magic links are the simplest identity scheme that produces a verifiable, unique account. Avoids phone-number collection (privacy risk for Iranians), OAuth dependency on Google/Apple (censorship/sanctions risk), and vouching (requires an existing trust graph that doesn't exist at launch). Linking email to WhatsApp gives one-person-one-voice without storing the phone number.

**Risk**: Email addresses are cheap to create. A motivated adversary can generate many addresses across many providers and bypass the per-domain limit. No Sybil-resistant identity check.

**Guardrails**:
1. Enforce per-IP signup cap (`MAX_SIGNUPS_PER_IP_PER_DAY`) as a hard abuse block.
2. Exempt major email providers from domain cap; apply domain cap only to non-major domains.
3. Track distinct `email_domain` counts per IP and flag anomalies.
4. Add disposable-email-domain detection (open-source lists) as a soft signal for `trust_score`.
5. Log account-creation velocity metrics to detect Sybil attacks early.

**Verdict**: **Keep with guardrail**

---

### D4 — WhatsApp ID storage: random opaque account ref + sealed mapping

**Context rule**: Raw IDs isolated in sealed mapping, stripped from logs/exports.

**Rationale**: Core tables and logs store only a random opaque account ref (UUIDv4), never raw `wa_id`. The sealed mapping (`wa_id ↔ account_ref`) exists only for transport operations and is isolated from the main store. This removes deterministic token derivation and makes leaked refs non-derivable from phone-number space.

**Risk**: The sealed mapping becomes higher value and must be operationally protected (strict ACLs, minimized access paths, careful backups). If mapping and app DB are both compromised, identity linkage risk remains.

**Guardrail**: Restrict raw `wa_id` access to the adapter/mapping layer only, emit only opaque refs in application logs, and test that all non-adapter modules can run without seeing raw IDs.

**Verdict**: **Keep with guardrail**

---

### D5 — Submission eligibility: Verified account + age >= 48 hours

**Context rule**: Must have verified account and account must be at least 48 hours old in production; threshold should be config-backed for lower test/dev values.

**Rationale**: 48-hour delay is lightweight Sybil friction. Creating an account today doesn't allow submissions until the day after tomorrow, requiring days of pre-seeding for burst-spam attacks.

**Risk**: 48h is short enough that a determined adversary pre-creates accounts weeks in advance. It also frustrates legitimate first-time users.

**Assessment**: Combined with rate limits and quarantine, 48h raises the cost enough for v0. Lowering to 24h increases spam risk; raising to 72h+ hurts onboarding. 48h is the sweet spot.

**Guardrail**: Implement eligibility with `MIN_ACCOUNT_AGE_HOURS` (default `48`) and use config in handlers/tests instead of hardcoded `48`, so test environments can safely run with smaller values.

**Verdict**: **Keep**

---

### D6 — Vote eligibility: Verified + 48h + at least 1 accepted contribution

**Context rule**: Voters must have at least one accepted contribution. Accepted contribution = processed submission OR recorded pre-ballot endorsement signature.

**Rationale**: Keeps "skin in the game" while avoiding submitter-only bias. Users who agree with existing policy clusters can contribute by signing/endorsing before ballot, similar to collecting signatures before an item reaches final vote.

**Risk**: If endorsement signatures are too easy to spam, attackers can farm minimal contributions to unlock voting. Also, if endorsement thresholds are too high, agenda throughput can stall.

**Guardrails**:
1. Use distinct-user endorsements only (one signature per user per cluster).
2. Keep age eligibility config-backed (`MIN_ACCOUNT_AGE_HOURS`, default `48`) and avoid hardcoded values.
3. Keep pre-ballot threshold config-backed (`MIN_PREBALLOT_ENDORSEMENTS`, default `5`) for calibration by environment.
4. Log endorsement events to evidence store for auditability.

**Verdict**: **Keep with guardrail**

---

### D7 — Infrastructure: Njalla/1984.is VPS

**Context rule**: Njalla domain (`collectivewill.org`) is registered with WHOIS privacy; primary hosting is 1984.is VPS. Production must run behind reverse-proxy edge protection and include a documented failover path.

**Rationale**: Operator safety is paramount for an Iranian civic project. Njalla domain privacy reduces attribution risk, and 1984.is offers privacy-forward hosting under a stronger free-speech jurisdiction. Adding reverse-proxy edge protection reduces DDoS and origin exposure risk without sacrificing operator privacy.

**Risk**: Small providers. If pressured, outaged, or shuttered, migration is manual. No CDN/DDoS protection by default. Single VPS = single point of failure.

**Guardrails**:
1. Keep origin backend non-public; only edge proxy should be publicly reachable.
2. Use reverse-proxy DDoS protection (Cloudflare or OVH) in front of origin.
3. Document and maintain a failover playbook (standby VPS, encrypted backups, DNS switchover procedure).

**Verdict**: **Keep with guardrail**

---

## Theme 2: Model and Pipeline Choices

### D8 — Canonicalization model: Claude Sonnet

**Context rule**: Farsi -> structured English, per-submission.

**Rationale**: For v0, priority is effectiveness and simplicity rather than cost. A single always-on Sonnet canonicalizer improves Farsi nuance handling and reduces ambiguous/misclassified policy extraction compared to smaller models, without adding routing complexity.

**Risk**: Higher-capability models can still fail schema/format constraints and may produce overconfident structured output. Also, single-model dependence increases outage impact if not mitigated.

**Guardrails**:
1. Build a human-evaluated golden set of 100+ diverse Farsi submissions and track extraction accuracy over time.
2. Enforce strict JSON schema validation before candidate creation; schema failures are flagged, not auto-accepted.
3. Route low-confidence outputs (`confidence < 0.7`) to review automatically.
4. Keep Haiku fallback for continuity only when Sonnet is unavailable, and mark fallback outputs for review.
5. Keep model/provider IDs behind the LLM abstraction layer; downstream modules call tiers, not model strings.

**Verdict**: **Keep with guardrail**

---

### D9 — Embeddings: quality-first cloud model in v0

**Context rule**: Cloud API, used for clustering input.

**Rationale**: v0 priority is effectiveness over cost, so embeddings should use a top-quality model by default (OpenAI `text-embedding-3-large`) to maximize semantic clustering quality. Cloud API avoids local GPU complexity. Since canonicalized text is English, the biggest quality gain comes from stronger semantic representation rather than multilingual raw-text handling.

**Risk**: Higher model cost and possible provider lock concentration in v0 if fallback is not configured.

**Guardrails**:
1. Keep embedding model selection behind config (`EMBEDDING_MODEL`) and route through the LLM abstraction.
2. Define a cheaper fallback model (`EMBEDDING_FALLBACK_MODEL`, e.g., `mistral-embed`) for later versions or outage/cost controls.
3. Track clustering quality metrics so you can switch to cost-effective models with evidence, not guesswork.

**Verdict**: **Keep with guardrail**

---

### D10 — Cluster summaries: quality-first model in v0 with mandatory fallback

**Context rule**: Low-volume (once per cluster per cycle), longer context.

**Rationale**: Since cluster summarization is low-volume in v0, prioritize effectiveness over cost. Use the strongest available reasoning model (default Sonnet via `english_reasoning` tier) for better summary fidelity and grouping rationale quality.

**Risk**: Single-provider outages can stall batch summarization. Cross-provider fallback may introduce slight style variance between summaries.

**Guardrails**:
1. Document which AI providers see which data on the transparency/methodology page.
2. Always configure and test a fallback path for `english_reasoning` (default fallback: DeepSeek `deepseek-chat`).
3. Keep model selection config-driven so later versions can move to cost-effective models without pipeline code changes.

**Verdict**: **Keep with guardrail**

---

### D11 — User-facing messages: quality-first model in v0 with mandatory fallback

**Context rule**: WhatsApp confirmations, vote prompts, notifications in natural Farsi.

**Rationale**: Same policy as D8/D10: prioritize effectiveness in v0. Use the strongest messaging-capable Farsi model by default (Sonnet via `farsi_messages` tier) to maximize clarity and reduce misunderstood prompts in a sensitive user context.

**Risk**: Strong-model dependence can impact availability if the provider has incident windows. Style may differ when fallback activates.

**Guardrails**:
1. Always configure/test a fallback model for `farsi_messages` (default fallback: Haiku).
2. Keep tier-model mapping config-backed so later versions can move to cost-effective defaults without caller changes.
3. Log `model_version` for outbound message generation where auditability is needed.

**Verdict**: **Keep with guardrail**

---

### D12 — Clustering: HDBSCAN, min_cluster_size=5

**Context rule**: Runs locally, density-based, no pre-specified cluster count.

**Rationale**: HDBSCAN doesn't require specifying the number of clusters (unlike K-means) — essential because the number of themes is unknown. Running locally avoids sending data to another service. Deterministic with a fixed seed. `min_cluster_size=5` filters noise.

**Risk**: Cold-start problem. With low submission volume early on, almost nothing clusters. 30 submissions across 10 topics = zero clusters = nothing to vote on.

**Guardrails**:
1. Make `min_cluster_size` configurable per cycle (stored in `clustering_params`) with a v0 default of `5`; adjust only through config/policy if sparse cycles require it.
2. Surface "unclustered submissions" in the analytics dashboard so users see their input isn't lost.

**Verdict**: **Keep with guardrail**

---

## Theme 3: Governance and Anti-abuse

### D13 — Submissions per account per day: 5

**Rationale**: Prevents single-user flooding. Generous enough for real users, low enough that spam requires many accounts.

**Verdict**: **Keep**

---

### D14 — Accounts per email domain per day: 3

**Rationale**: Domain-level controls still help for disposable/niche domains commonly used in abuse campaigns, but major shared providers should not be penalized.

**Risk**: If domain caps are applied indiscriminately, legitimate users on popular providers get blocked. If only per-domain controls are used, attackers can spread signups across many domains.

**Applied alternative (v0 policy)**:
- Exempt major providers (`gmail.com`, `outlook.com`, `yahoo.com`, `protonmail.com`) from per-domain caps.
- Apply `MAX_SIGNUPS_PER_DOMAIN_PER_DAY=3` only to non-major domains.
- Add blocking per-IP signup cap (`MAX_SIGNUPS_PER_IP_PER_DAY`, default 10/day).
- Keep domain-diversity and disposable-domain signals as telemetry/trust inputs.

**Verdict**: **Keep with guardrail**

---

### D15 — Burst quarantine: 3 submissions/5 minutes (soft quarantine)

**Rationale**: Defense against rapid submission dumps with a reachable trigger that actually activates under abuse conditions.

**Risk**: If too aggressive, fast but legitimate multi-message users can be flagged and delayed.

**Applied alternative (v0 policy)**:
- Use `3 submissions in 5 minutes` as the burst trigger.
- Make it a soft quarantine action: accept submissions but flag/hold for review.
- Keep the hard 5/day submission cap unchanged.

**Guardrail**:
- Keep burst thresholds config-backed and monitor false-positive rate; tune by environment if legitimate users are over-flagged.

**Verdict**: **Keep with guardrail**

---

### D16 — Vote changes per cycle: 1

**Rationale**: Allows one revision if the user changes their mind or sees new clusters, but prevents continuous flip-flopping.

**Applied clarification**: "1 change" means exactly one full re-submission of the approval set per cycle (total max: 2 vote submissions). It does **not** mean one toggle per cluster.

**Guardrail**: Enforce this at the policy engine level (not via human moderation): "you may re-submit your full approval set once per cycle (total 2 submissions)." No manual vote overrides.

**Verdict**: **Keep with guardrail**

---

### D17 — Failed verification: 5 per email per 24h, then lockout

**Rationale**: Prevents brute-forcing magic-link codes and email-bombing.

**Verdict**: **Keep**

---

### D18 — Disputes: flag, autonomous <=72h resolution, re-run pipeline, never suppress

**Rationale**: Resolution is always produced by autonomous dispute workflows (new `run_id` evidence), never manual content edits. This keeps per-item governance unbiased, scalable, and auditable.

**Risk**: A single-model resolver can become overconfident or drift, causing repeated mis-resolutions at scale if confidence checks and escalation are weak.

**Guardrails**:
1. Scope dispute resolution: re-canonicalize the disputed submission only; the next batch cycle naturally re-clusters it. Do not re-run clustering mid-cycle for a single dispute.
2. Use multi-stage resolver policy: primary model -> stronger fallback -> ensemble/tie-breaker for low-confidence cases.
3. Add dispute volume and resolver-disagreement metrics. If disputes exceed 5% of submissions in a cycle (or resolver disagreement spikes), tune model/prompt/policy.

**Verdict**: **Keep with guardrail**

---

### D18A — Adjudication autonomy: no per-item human intervention

**Context rule**: Individual votes, disputes, and quarantine outcomes are handled by autonomous policy/model workflows. Humans only modify architecture, policy thresholds, and risk controls.

**Rationale**: Prevents selective/manual influence over individual outcomes, preserves consistency, and scales better than case-by-case moderation.

**Risk**: Poorly tuned automation can make consistent mistakes quickly.

**Guardrail**: Require confidence thresholds, fallback/ensemble paths, and full evidence logging for every adjudication action.

**Verdict**: **Keep with guardrail**

---

## Theme 4: Evidence, Audit, Privacy, and Retention

### D19 — Evidence store: PostgreSQL append-only hash-chain

**Context rule**: No UPDATE/DELETE.

**Rationale**: Every significant event is logged as a hash-chained entry. Tampering with a historical entry breaks the chain. Provides auditability without a blockchain.

**Risk**: Only as trustworthy as the database operator. The operator can rewrite the entire chain consistently. External anchoring (D20) covers this.

**Verdict**: **Keep**

---

### D20 — External anchoring: required local Merkle roots + optional Witness publish

**Context rule**: Merkle root computation is required in v0; publishing to Witness.co is optional and config-driven.

**Rationale**: Daily local Merkle-root computation keeps tamper-evidence logic exercised from day one. Keeping only external publish optional avoids blocking v0 on third-party availability while preserving upgrade readiness.

**Risk**: "Optional" tends to mean "never." Without anchoring, the operator-tamper-resistance benefit is lost.

**Guardrail**: Implement Merkle root computation in v0 (trivial code). Make only the "publish to Witness.co" step optional. That way the code is tested; flipping the switch is a config change.

**Verdict**: **Keep with guardrail**

---

### D21 — Data retention: evidence immutable, account linkage deletable

**Context rule**: GDPR right-to-erasure achieved by severing identity links, not by deleting evidence entries.

**Rationale**: Submissions remain in the chain anonymously after account deletion. The `user_id` (UUID) becomes an orphan, and the email/wa_id mapping is deleted. Chain integrity is preserved while complying with erasure requests.

**Risk**: If `raw_text` contains PII ("my name is X, I live in Y"), deleting the account doesn't anonymize the submission.

**Guardrails**:
1. Add pre-persist PII checks in intake. If high-risk PII is detected, do not store the text; ask the user to remove personal identifiers and resend.
2. Keep automated PII stripping in `pipeline/privacy.py` as a second safety layer for residual PII before downstream processing.
3. In deletion flow, run automated PII scans and emit risk flags/metrics for policy tuning; no per-item human review path.

**Verdict**: **Keep with guardrail**

---

## Theme 5: Tech Stack, Data Models, and Process Rules

### D22 — Backend: Python 3.11+, FastAPI, SQLAlchemy async, Pydantic

**Rationale**: FastAPI is the modern standard for Python APIs. SQLAlchemy 2.0 async is mature. Python is natural given the ML pipeline (HDBSCAN, embeddings) is Python-native.

**Verdict**: **Keep**

---

### D23 — Database: PostgreSQL 15+ with pgvector

**Rationale**: pgvector stores embeddings in Postgres, avoiding a separate vector DB. Since HDBSCAN runs in Python, pgvector is for storage and optional nearest-neighbor lookups.

**Verdict**: **Keep**

---

### D24 — Website: Next.js App Router, TypeScript, Tailwind, next-intl

**Rationale**: SSR for public analytics (SEO), server components (lower client JS), built-in routing. `next-intl` handles Farsi/English i18n with RTL.

**Verdict**: **Keep**

---

### D25 — Dependency management: uv (Python), pnpm (Node)

**Rationale**: `uv` is 10-100x faster than pip. `pnpm` is disk-efficient via content-addressable storage.

**Verdict**: **Keep**

---

### D26 — Dual model layer: Pydantic BaseModel + SQLAlchemy ORM, separate

**Context rule**: "Separate but aligned."

**Rationale**: Pydantic models define data shape for validation/serialization (API layer). SQLAlchemy models define the database schema. Separation avoids coupling API contracts to DB schema.

**Risk**: Maintenance burden keeping the two in sync. No explicit conversion pattern documented.

**Guardrail**: Define explicit conversion methods (`User.from_orm()`, `db_user.to_schema()`), tested for field round-trips. Evaluate whether `SQLModel` could reduce boilerplate (acceptable for v0's ~6 models).

**Verdict**: **Keep with guardrail**

---

### D27 — Data model specifics

**D27a — `trust_score: float` on User**: Field exists but computation/usage is undefined. If unused in v0, document as "reserved for v1" to prevent agents building logic around it.

**D27b — `stance` enum includes `"unclear"`**: Keep enum as-is in v0, but enforce semantics explicitly: `"neutral"` means descriptive/no explicit side; `"unclear"` means model uncertainty.

**D27c — `approved_cluster_ids: list[UUID]` on Vote (JSON array)**: Keep array storage in v0, but enforce query abstraction (`count_votes_for_cluster` helper) so callers are decoupled from storage shape and a future `vote_approval` junction-table migration stays low-risk.

**Verdict**: **Keep with guardrails** on all three points.

---

### D28 — EvidenceLogEntry hash chain

**Context rule**: `hash = SHA-256(canonical_json({timestamp,event_type,entity_type,entity_id,payload,prev_hash}))`, `prev_hash = previous entry's hash`.

**Risk**: If canonical serialization rules are underspecified, independent verifiers may compute different hashes for equivalent records. Linear chain also serializes writes.

**Guardrails**:
1. Hash the entire entry: `SHA-256(timestamp + event_type + entity_type + entity_id + payload + prev_hash)`.
2. Document the serialization format (canonical JSON with sorted keys) so independent verifiers can reproduce hashes.

**Verdict**: **Keep with guardrail**

---

### Process Rules (D29–D37)

| ID | Rule | Verdict |
|----|------|---------|
| D29 | Test after every task | **Keep** |
| D30 | Type hints everywhere, mypy strict | **Keep** |
| D31 | Pydantic for all data models | **Keep** |
| D32 | Parameterized queries only (SQLAlchemy ORM) | **Keep** |
| D33 | `secrets` not `random` for crypto | **Keep** |
| D34 | No `eval`/`exec` | **Keep** |
| D35 | Ruff for formatting | **Keep** |
| D36 | Never commit secrets | **Keep** |
| D37 | OpSec: no real names, store opaque account refs only | **Keep** |

All process rules are sound. No changes needed.

---

## Summary

| Verdict | Count |
|---------|-------|
| **Keep** | ~20 |
| **Keep with guardrail** | ~13 |
| **Reconsider** | 0 |

### Remaining decisions to change before coding

None currently.
