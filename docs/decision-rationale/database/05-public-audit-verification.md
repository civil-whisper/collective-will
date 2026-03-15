# Decision Rationale — database/05-public-audit-verification.md

> **Corresponds to**: [`docs/agent-context/database/05-public-audit-verification.md`](../../agent-context/database/05-public-audit-verification.md)
>
> When a decision changes in either file, update the other.

---

## Decision

Adopt an **OpenTimestamps-first** public audit verification model with three usability layers:
- ordinary-user verification
- public watchdog verification
- programmer/auditor verification

---

## Why this is correct

- OpenTimestamps is usable now without vendor onboarding or enterprise sales.
- It gives a strong anti-tampering guarantee: published daily snapshots cannot be silently rewritten later without detection.
- It preserves the privacy model because only hashes are externally timestamped.
- It avoids making verification “real only for programmers” by adding a human-readable receipt/status layer on top of the cryptographic substrate.

---

## Why not Witness-first

- Current provider accessibility is uncertain and not dependable for immediate rollout.
- A trust feature that depends on unclear account onboarding is operationally risky.
- For this project, open and reproducible verification matters more than vendor polish.

---

## Guardrails

- Never claim that timestamping proves the system is fair or complete by itself.
- Always distinguish:
  - recorded internally
  - published publicly
  - timestamped externally
  - independently verified
- Keep raw proofs downloadable for third parties.
- Keep private user receipts separate from public bundles.

---

## Residual risks

- Ordinary users may still rely on the website’s summary instead of independently verifying files.
- Daily snapshots do not prove omission-resistance before publication.
- OpenTimestamps proof lifecycle and upgrade timing may confuse users unless explained clearly.

---

## Mitigations

- Build a plain-language receipt verification UI.
- Publish bundle/manifest/proof files together.
- Add explanation text for “what this proves” and “what this does not prove.”
- Keep verification endpoints and downloadable artifacts aligned.
- Distinguish proof creation from proof verification in code and UX: a generated `.ots` file is `stamped`, while `verified` requires successful Bitcoin-backed verification.

---

## Verdict

**Adopt for v0.1**: OpenTimestamps-backed daily public audit verification with human-readable receipt states and downloadable proof artifacts.
