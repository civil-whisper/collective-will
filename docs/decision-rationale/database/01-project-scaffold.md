# Decision Rationale — database/01-project-scaffold.md

> **Corresponds to**: [`docs/agent-context/database/01-project-scaffold.md`](../../agent-context/database/01-project-scaffold.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

- Shared-context D4 now uses random opaque account refs plus sealed mapping.
- Scaffold/config should not require `SECRET_PEPPER` for WhatsApp identity tokenization.
- Shared-context D5/D6 age gating should be config-backed for testability (`MIN_ACCOUNT_AGE_HOURS`, default `48`).
- Shared-context clustering policy should expose `MIN_CLUSTER_SIZE` as config (default `5`) for sparse-cycle calibration.
- Multi-stage agenda gating should expose `MIN_PREBALLOT_ENDORSEMENTS` as config (default `5`) for calibration.
- Shared-context D14 signup-abuse policy should be config-backed: non-major domain cap (`MAX_SIGNUPS_PER_DOMAIN_PER_DAY`), per-IP cap (`MAX_SIGNUPS_PER_IP_PER_DAY`), and major-provider exemption list (`MAJOR_EMAIL_PROVIDERS`).
- Shared-context D15 burst soft-quarantine policy should be config-backed: trigger count (`BURST_QUARANTINE_THRESHOLD_COUNT`, default `3`) and window (`BURST_QUARANTINE_WINDOW_MINUTES`, default `5`).
- Shared-context adjudication-autonomy policy should expose dispute-resolver model config (`DISPUTE_RESOLUTION_MODEL`, fallback, and optional ensemble list) so resolver quality can be tuned without code edits.
- Shared-context adjudication guardrail should expose `DISPUTE_RESOLUTION_CONFIDENCE_THRESHOLD` as config so low-confidence escalation policy is explicit and tunable.
- Shared-context anchoring guardrail should expose `WITNESS_PUBLISH_ENABLED` (+ Witness endpoint/key) so publication is optional while daily Merkle-root computation remains mandatory.
- Infrastructure/domain setup should expose `APP_PUBLIC_BASE_URL` so auth links and public callbacks are not hardcoded (production: `https://collectivewill.org`).
- LLM tier->model mapping should be env-configured so model swaps do not require code edits in pipelines/handlers.
- Embedding config should include both primary quality-first model and cost-effective fallback for later phases.
- English reasoning/summarization should include both primary quality-first model and mandatory fallback for risk management.
- User-facing Farsi messaging should include both primary quality-first model and mandatory fallback for risk management.

**Guardrail**: Keep bootstrap config free of deterministic-wa_id tokenization settings, and expose abuse/eligibility/adjudication knobs via settings/env so test environments can override without code edits.
