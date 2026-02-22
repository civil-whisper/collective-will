# Contributing (Context-Locked)

This coding package is context-locked. Any implementation or spec changes must stay aligned with:

- `agent-context/**`
- `decision-rationale/**`
- `mvp-specification.md`

## Alignment Rules

- If behavior changes, update both implementation docs and rationale docs in the same change.
- Do not weaken frozen v0 decisions without explicit decision updates.
- Keep thresholds and model/provider choices config-driven.
- Keep privacy and audit constraints intact (opaque refs, append-only evidence, required local Merkle roots).

## PR Checklist

- [ ] Implementation matches `agent-context` contracts.
- [ ] Rationale stays synchronized for any decision-level change.
- [ ] Tests added/updated for changed behavior.
- [ ] No secrets or personal identifiers introduced.
