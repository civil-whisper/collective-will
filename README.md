# Coding Docs Pack

Copy everything in this folder into your new repo root.

## Included

- `agent-context/` (implementation contracts)
- `decision-rationale/` (decision rationale + guardrails)
- `mvp-specification.md`
- `llm-strategy.md`
- `v0-precoding-checklist.md`
- `infrastructure-guide.md`
- `roadmap.md`
- `.env.example`
- `AGENTS.md`
- `CONTRIBUTING.md`
- `DECISION_LOCKS.md`

## First Steps in New Repo

1. Place this pack at repo root.
2. Keep `.env.example` as template and create local `.env` (do not commit).
3. Start implementation from `agent-context/database/01-project-scaffold.md`.
4. Keep any behavior change synchronized across `agent-context` and `decision-rationale`.
