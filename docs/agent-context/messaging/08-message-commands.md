# Task: Message Command Router (Button-Only UX)

## Depends on
- `messaging/03-webhook-endpoint` (route_message stub)
- `messaging/04-submission-intake` (handle_submission)
- `messaging/07-voting-service` (cast_vote, record_endorsement)
- `messaging/01-channel-base-types` (BaseChannel, UnifiedMessage, OutboundMessage)
- `database/03-core-models` (User, VotingCycle, Cluster, PolicyOption queries)

## Goal
Implement a button-only Telegram UX that dispatches all user interactions through inline keyboard callbacks. Users never type commands — all actions are selected via buttons. The voting flow presents one policy at a time with LLM-generated stance options, a summary review page, and final submission.

## Files to create/modify

- `src/handlers/commands.py` — callback router and all interaction flows

## Specification

### Interaction Model: Button-Only

All user interaction is driven by Telegram inline keyboards (callback queries). There are no typed commands. The main menu is an inline keyboard sent after linking, after each action completes, and when unrecognized text is received.

### Main Menu Buttons

| Button Label (en) | Button Label (fa) | Callback Data |
|---|---|---|
| Submit a concern | ثبت نگرانی | `submit` |
| Vote on policies | رای‌گیری | `vote` |
| Language: EN/FA | زبان: FA/EN | `lang` |

### State Machine

User interaction state is tracked via two columns on the `User` model:

- `bot_state: str | None` — current high-level state (e.g., `"awaiting_submission"`, `"voting"`)
- `bot_state_data: dict | None` — JSONB session data for multi-step flows

#### States

| State | Trigger | Behavior |
|---|---|---|
| `None` (default) | Any text | Show menu hint + main menu keyboard |
| `None` | Callback `submit` | Set state to `awaiting_submission`, prompt user to type concern |
| `awaiting_submission` | Any text | Route to `handle_submission()`, clear state, show menu |
| `None` | Callback `vote` | Initialize voting session (see below) |
| `voting` | Callbacks `vo:N`, `vsk`, `vbk`, `vchg`, `vsub` | Navigate per-policy voting flow |
| Any | Callback `cancel` | Clear state + state_data, show menu |
| Any | Callback `lang` | Toggle locale, show menu in new language |

### Per-Policy Voting Flow

When the user taps "Vote on policies":

1. **Session initialization**: Query active `VotingCycle`, load `cluster_ids`. Store session in `bot_state_data`:
   ```json
   {
     "cycle_id": "...",
     "cluster_ids": ["...", "..."],
     "current_idx": 0,
     "selections": {}
   }
   ```
   Set `bot_state = "voting"`.

2. **Policy display** (one at a time): Show "Policy X of N", cluster summary (locale-aware), then each `PolicyOption` as an inline keyboard button. Navigation buttons: Skip (→), Back (←).

3. **Option select** (`vo:{position}`): Record selection in `bot_state_data["selections"][cluster_id] = option_id`, advance to next policy.

4. **Skip** (`vsk`): Advance without recording a selection.

5. **Back** (`vbk`): Decrement `current_idx`, re-show previous policy.

6. **Summary** (after last policy): Show all selections with labels. Buttons: Submit Vote (`vsub`), Change Answers (`vchg`).

7. **Change** (`vchg`): Reset `current_idx` to 0, re-show first policy (selections preserved).

8. **Submit** (`vsub`): Convert `selections` dict to `[{cluster_id, option_id}, ...]`, call `cast_vote()` with `selections` parameter. Clear state, show confirmation + analytics link + menu.

### Endorsement Flow

During pre-ballot stage, endorsement buttons are displayed alongside clusters. Callback data: `e:{1-based-index}`. Calls `record_endorsement()` and shows confirmation.

### Callback Data Encoding

Compact strings to fit Telegram's 64-byte limit:

| Action | Format | Example |
|---|---|---|
| Option select | `vo:{position}` | `vo:2` |
| Skip policy | `vsk` | |
| Back to prev | `vbk` | |
| Change answers | `vchg` | |
| Submit vote | `vsub` | |
| Endorse | `e:{index}` | `e:3` |
| Submit concern | `submit` | |
| Vote menu | `vote` | |
| Language toggle | `lang` | |
| Cancel | `cancel` | |

### Locale-Aware Messages

All user-facing text is stored in `_MESSAGES: dict[str, dict[str, str]]` with `"en"` and `"fa"` keys. The `_msg(locale, key, **kwargs)` helper selects the appropriate language based on `user.locale`.

### Analytics Deep Links

After submission or voting, include a link to the public analytics page:
- Submission: `{app_public_base_url}/{locale}/analytics`
- Vote: `{app_public_base_url}/{locale}/analytics?cycle={cycle_id}`

### route_message() Implementation

```python
async def route_message(
    session: AsyncSession, message: UnifiedMessage, channel: BaseChannel
) -> str:
```

1. If `callback_data` present → look up user, dispatch to `_route_callback()`
2. Else look up user by `sender_ref`
3. If user not found and text matches linking code → handle linking
4. If user not found → send bilingual registration prompt
5. If `bot_state == "awaiting_submission"` → route to `handle_submission()`
6. Else → show menu hint with keyboard

Returns a status string for logging/testing (e.g., `"policy_shown"`, `"vote_recorded"`, `"menu_resent"`).

## Constraints

- No typed commands — all interaction through inline keyboard callbacks.
- During voting, `bot_state_data` stores the full session. State is persisted to DB so it survives bot restarts.
- After every completed action (submit, vote, cancel, lang), automatically return to main menu.
- Keep routing based on `UnifiedMessage` + `BaseChannel` — no Telegram-specific payload checks in router logic.
- All responses use the user's preferred locale (`user.locale`).

## Tests

Tests in `tests/test_handlers/test_commands.py` covering:
- Unknown user → registration prompt
- Successful linking → welcome message with menu
- Callback `submit` → sets `awaiting_submission` state
- Text in awaiting state → triggers submission, clears state
- Callback `cancel` → clears state and state_data
- Callback `lang` → toggles locale
- Callback `vote` with no active cycle → no_active_cycle message
- Callback `vote` with active cycle → shows first policy with options
- `vo:N` → advances to next policy, records selection
- `vsk` → skips without selection
- `vbk` → goes back to previous policy
- `vsub` → calls cast_vote with selections, clears state
- `vsub` with empty selections → returns to menu
- `vsub` with expired cycle → no_active_cycle
- `vsub` with rejection → shows error message
- `vo:N` without active session → returns to menu
- `vchg` → resets to first policy
- `e:{index}` → calls record_endorsement
- Last policy option select → shows summary page
- Unrecognized text → re-sends menu
- Bilingual message content verification
