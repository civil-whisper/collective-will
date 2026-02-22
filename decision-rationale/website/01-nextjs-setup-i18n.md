# Decision Rationale — website/01-nextjs-setup-i18n.md

> **Corresponds to**: [`docs/agent-context/website/01-nextjs-setup-i18n.md`](../../agent-context/website/01-nextjs-setup-i18n.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements frontend language/accessibility decisions as:

- Farsi-first default locale (`fa`) with English secondary (`en`).
- Runtime RTL/LTR switching from locale.
- No hardcoded UI strings; all text through translation keys.

---

## Decision: Farsi-first i18n foundation in v0

**Why this is correct**

- Matches the project’s primary audience and trust requirements.
- Prevents later RTL retrofits across the UI surface.
- Keeps translation discipline from day one.

**Risk**

- RTL regressions can still happen in components that use physical spacing classes.

**Guardrail**

- Require logical CSS properties (`ps/pe`, etc.) and locale-driven `dir`.
- Keep translation-key usage mandatory in UI components.
- Test `lang`/`dir` behavior for both locales.

**Verdict**: **Keep with guardrail**
