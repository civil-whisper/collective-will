# Contributing (Context-Locked)

This coding package is context-locked. Any implementation or spec changes must stay aligned with:

- `docs/agent-context/**`
- `docs/decision-rationale/**`
- `docs/mvp-specification.md`

## Alignment Rules

- If behavior changes, update both implementation docs and rationale docs in the same change.
- Do not weaken frozen v0 decisions without explicit decision updates.
- Keep thresholds and model/provider choices config-driven.
- Keep privacy and audit constraints intact (opaque refs, append-only evidence, required local Merkle roots).

## PR Checklist

- [ ] Implementation matches `docs/agent-context` contracts.
- [ ] Rationale stays synchronized for any decision-level change.
- [ ] Tests added/updated for changed behavior.
- [ ] No secrets or personal identifiers introduced.

## Local CI Parity

Run the same backend checks used in GitHub CI before pushing:

`bash scripts/ci-backend.sh`

Notes:
- The script enforces CI parity mode (`CI_PARITY=1`) and fails if required DB config is missing.
- It can auto-start a local `pgvector` Postgres container when Docker is available.
