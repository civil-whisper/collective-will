# Decision Rationale — pipeline/02-privacy-strip-metadata.md

> **Corresponds to**: [`docs/agent-context/pipeline/02-privacy-strip-metadata.md`](../../agent-context/pipeline/02-privacy-strip-metadata.md)
>
> When a decision changes in either file, update the other.

---

## Decision Alignment

This subcontext implements shared-context privacy retention guardrails as:

- Metadata stripping remains mandatory before cloud LLM calls.
- Residual text-level PII redaction is applied as a second safety layer.
- High-risk/unredactable PII is routed to reject-and-resend workflow rather than forwarded downstream.

---

## Decision: Layered PII protection (intake gate + pipeline redaction)

**Why this is correct**

- Prevents immutable storage of obvious personal identifiers when users accidentally include them.
- Maintains usability: users can safely resubmit after redaction instead of being silently dropped.
- Keeps privacy enforcement autonomous and consistent with no per-item human moderation.

**Risk**

- Over-aggressive detection/redaction can suppress legitimate policy details.

**Guardrail**

- Keep detector/redaction patterns configurable and monitored for false positives.
- Preserve minimal evidence trace for reject-and-resend actions without storing raw sensitive content.

**Verdict**: **Keep with guardrail**
