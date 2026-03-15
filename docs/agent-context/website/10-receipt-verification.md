# Task: Receipt Verification UX

## Depends on
- `website/06-dashboard-submissions-votes` (user dashboard)
- `website/08-audit-evidence-explorer` (public audit pages)
- `database/05-public-audit-verification` (bundles, manifests, OpenTimestamps proofs)

## Goal
Give non-programmer users a simple way to verify that their receipted actions were recorded, published, and externally timestamped.

## User problems to solve
- “Did the system record my action?”
- “Is my action part of the public audit trail?”
- “Can the project secretly change that record later?”
- “How do I verify this without knowing cryptography?”

## UX model

### Receipt card in dashboard
Each receipt-eligible action shows:
- action label (endorsement / vote)
- action time
- context (cluster title / voting cycle)
- status chips:
  - `Recorded`
  - `Published`
  - `Timestamped`
- button: `Verify this receipt`
- Implemented at `/{locale}/my-activity`
- Current behavior:
  - cards show a human-readable event label, recorded timestamp, and monotonic progress chips
  - `Verified` appears as an additional success chip once proof validation is confirmed
  - `Needs attention` appears as an error chip when verification artifacts are inconsistent

### Receipt detail page
Route suggestion:
- `/{locale}/my-activity/receipts/{entryHash}`

Implemented route:
- `/{locale}/my-activity/receipts/{entryHash}`

Page sections:
- **What happened** — human-readable summary of the action
- **Verification status** — plain-language explanation of current state
- **What this proves** — anti-tampering after publication
- **What this does not prove** — not a complete fairness guarantee by itself
- **Technical details** — entry hash, receipt token, bundle day
- **Downloads for independent verification** — bundle, manifest, `.ots`
- **How independent verification works** — short explanation for non-programmers

### Plain-language status copy
- `Recorded`: “Your action was written to the audit log.”
- `Published`: “Your action appears in the public daily audit snapshot.”
- `Timestamped`: “That public snapshot was externally timestamped.”
- `Verified`: “The timestamp proof was checked successfully.”
- `Failed`: “We could not verify the proof yet.”

### Frozen state model
Use exactly five verification states:
- `recorded`
- `published`
- `timestamped`
- `verified`
- `failed`

State precedence is monotonic:
- `recorded` -> `published` -> `timestamped` -> `verified`
- `failed` is an error state for missing/invalid verification data and should not be shown at the same time as a higher success state

### Frozen user-facing copy

#### Status labels
- `recorded`: `Recorded`
- `published`: `Published`
- `timestamped`: `Timestamped`
- `verified`: `Verified`
- `failed`: `Needs attention`

#### Status descriptions
- `recorded`: “Your action was written to the internal audit log.”
- `published`: “Your action appears in the public daily audit snapshot.”
- `timestamped`: “That public snapshot was timestamped with OpenTimestamps.”
- `verified`: “The public timestamp proof was checked successfully.”
- `failed`: “We could not confirm the public proof yet.”

#### What this proves
Use this exact meaning in UX and API docs:
- “This shows that your action was recorded by the system and, once published, the public record cannot be changed later without detection.”

#### What this does not prove
Use this exact limitation text in UX and API docs:
- “This does not by itself prove that every possible event was included, or that every system decision was fair. It proves anti-tampering after publication.”

#### Suggested CTA labels
- `Verify this receipt`
- `Download proof files`
- `Show technical details`
- `How independent verification works`

### Farsi parity requirement
The Farsi copy should communicate the same meaning, not a looser or stronger claim.

## Backend contract needed by UI

### Existing
- `GET /user/dashboard/receipts`

### New
- `GET /user/dashboard/receipts/{entry_hash}/verify`
  - implemented backend contract for the receipt detail UI
  - returns the frozen `status` plus the verification booleans needed for explanatory copy
  - now returns working `download_urls` for bundle, manifest, and `.ots` artifact downloads

UI implementation status:
- Dashboard receipt cards are implemented
- Receipt detail page is implemented
- Download rows now link to the public artifact endpoints when files exist; missing `.ots` files still show an unavailable state
- Receipt detail now links to the public independent verification guide at `/{locale}/independent-verification`

Response fields:
- `status`
- `receipt_valid`
- `entry_found`
- `bundle_day`
- `included_in_public_bundle`
- `bundle_hash_matches_manifest`
- `ots_proof_present`
- `ots_verified`
- `verified_before`
- `download_urls`

## Design rules
- Human-readable explanation first; cryptographic fields behind disclosure/advanced section.
- Never present raw hashes as the primary proof UX.
- Do not imply stronger guarantees than the proof actually provides.
- Keep i18n parity in EN and FA.

## Tests
- Dashboard receipt card shows correct status chips
- Receipt detail page shows explanations and download links
- Error state for missing proof
- i18n coverage for all status labels and explanatory copy
