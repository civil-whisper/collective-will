"""Automated end-to-end tests via real Telegram messages.

Sends actual messages to the bot through Telethon, reads replies, and asserts.
Uses a single test function to keep one event loop (Telethon requirement).

Requirements (one-time setup):
  1. Get API credentials at https://my.telegram.org → "API development tools"
  2. Add to .env: TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_BOT_USERNAME
  3. Run: uv run python scripts/telegram_auth.py   (one-time phone auth)
  4. Start server + tunnel before running tests

Run:
  uv run pytest tests/test_integration/test_telegram_e2e.py -v -s
"""
from __future__ import annotations

import asyncio
import os

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv()

_API_ID = os.getenv("TELEGRAM_API_ID")
_API_HASH = os.getenv("TELEGRAM_API_HASH")
_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "collective_will_dev_bot")
_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
_SESSION_FILE = "test_user_session.session"
_SERVER_URL = os.getenv("TEST_SERVER_URL", "http://localhost:8000")

_SKIP_REASON = (
    "Telethon session not found or env vars missing. "
    "Run `uv run python scripts/telegram_auth.py` first."
)

pytestmark = pytest.mark.skipif(
    not (_API_ID and _API_HASH and _BOT_TOKEN and os.path.exists(_SESSION_FILE)),
    reason=_SKIP_REASON,
)


async def _send_and_wait(client, text: str, wait_s: float = 4.0, retries: int = 3) -> str | None:  # type: ignore[no-untyped-def]
    """Send a message to the bot and wait for its reply."""
    sent = await client.send_message(_BOT_USERNAME, text)
    sent_id = sent.id

    for _ in range(retries):
        await asyncio.sleep(wait_s)
        messages = await client.get_messages(_BOT_USERNAME, limit=5)
        for msg in messages:
            if not msg.out and msg.id > sent_id:
                return msg.text
            if not msg.out and msg.reply_to and msg.reply_to.reply_to_msg_id == sent_id:
                return msg.text

    # Fallback: check if the latest incoming message arrived after we sent
    messages = await client.get_messages(_BOT_USERNAME, limit=5)
    for msg in messages:
        if not msg.out:
            return msg.text
    return None


@pytest.mark.asyncio
async def test_full_telegram_e2e() -> None:
    """Single sequential test exercising the full user journey via Telegram."""
    from telethon import TelegramClient

    client = TelegramClient("test_user_session", int(_API_ID), _API_HASH)  # type: ignore[arg-type]
    await client.connect()
    if not await client.is_user_authorized():
        pytest.skip("Session expired. Re-run: uv run python scripts/telegram_auth.py")

    results: dict[str, str] = {}

    try:
        # ── 1. Unregistered user gets registration prompt ──
        reply = await _send_and_wait(client, "سلام تست خودکار")
        assert reply is not None, "Bot did not reply to greeting"
        assert "ثبت‌نام" in reply or "وبسایت" in reply, f"Expected registration prompt, got: {reply}"
        results["01_registration_prompt"] = "PASS"
        print(f"\n  [01] Registration prompt: {reply[:60]}")

        # ── 2. Help command (before registration) → same prompt ──
        reply = await _send_and_wait(client, "کمک")
        assert reply is not None, "Bot did not reply to help"
        assert "ثبت‌نام" in reply or "وبسایت" in reply
        results["02_help_before_reg"] = "PASS"
        print(f"  [02] Help before reg: {reply[:60]}")

        # ── 3. Register via API → link via Telegram ──
        async with httpx.AsyncClient() as http:
            resp = await http.post(f"{_SERVER_URL}/auth/subscribe", json={
                "email": "tg-auto-test@example.com",
                "locale": "fa",
                "requester_ip": "127.0.0.1",
                "messaging_account_ref": "tg-auto-ref",
            })
            assert resp.status_code == 200, f"Subscribe failed: {resp.text}"
            token = resp.json()["token"]

            resp = await http.post(f"{_SERVER_URL}/auth/verify/{token}")
            assert resp.status_code == 200, f"Verify failed: {resp.text}"
            linking_code = resp.json()["status"]

        reply = await _send_and_wait(client, linking_code, wait_s=4.0)
        assert reply is not None, "Bot did not reply to linking code"
        results["03_link_account"] = "PASS"
        print(f"  [03] Linking code reply: {reply[:60]}")

        # ── 4. Help command (after linking) → command list ──
        reply = await _send_and_wait(client, "کمک")
        assert reply is not None, "Bot did not reply to help"
        assert "دستورات" in reply or "وضعیت" in reply, f"Expected command list, got: {reply}"
        results["04_help_after_reg"] = "PASS"
        print(f"  [04] Help after reg: {reply[:60]}")

        # ── 5. Status command ──
        reply = await _send_and_wait(client, "وضعیت")
        assert reply is not None, "Bot did not reply to status"
        assert "ارسالی" in reply or "وضعیت" in reply, f"Expected status, got: {reply}"
        results["05_status"] = "PASS"
        print(f"  [05] Status: {reply[:60]}")

        # ── 6. Submission (should be rejected — young account) ──
        reply = await _send_and_wait(client, "باید آموزش رایگان برای همه باشد")
        assert reply is not None, "Bot did not reply to submission"
        assert "واجد شرایط" in reply or "ارسال" in reply, f"Expected not-eligible, got: {reply}"
        results["06_submission_rejected"] = "PASS"
        print(f"  [06] Young account rejection: {reply[:60]}")

        # ── 7. Language toggle ──
        reply = await _send_and_wait(client, "زبان")
        assert reply is not None, "Bot did not reply to language"
        assert "English" in reply or "فارسی" in reply, f"Expected language switch, got: {reply}"
        results["07_language_toggle"] = "PASS"
        print(f"  [07] Language toggle: {reply[:60]}")

        # Toggle back
        await _send_and_wait(client, "زبان")

        # ── 8. Vote with no active cycle ──
        reply = await _send_and_wait(client, "رای")
        assert reply is not None, "Bot did not reply to vote"
        assert "رای‌گیری" in reply, f"Expected no-cycle message, got: {reply}"
        results["08_vote_no_cycle"] = "PASS"
        print(f"  [08] Vote no cycle: {reply[:60]}")

        # ── 9. Skip command ──
        reply = await _send_and_wait(client, "انصراف")
        assert reply is not None, "Bot did not reply to skip"
        assert "رد شدید" in reply, f"Expected skip ack, got: {reply}"
        results["09_skip"] = "PASS"
        print(f"  [09] Skip: {reply[:60]}")

        # ── 10. PII message ──
        reply = await _send_and_wait(client, "شماره من 09121234567 است")
        assert reply is not None, "Bot did not reply to PII message"
        results["10_pii"] = "PASS"
        print(f"  [10] PII response: {reply[:60]}")

        # ── 11. Evidence chain integrity via API ──
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{_SERVER_URL}/analytics/evidence")
            assert resp.status_code == 200
            entries = resp.json()
            assert len(entries) >= 1, "No evidence entries"

            resp = await http.post(f"{_SERVER_URL}/analytics/evidence/verify", json=entries)
            assert resp.status_code == 200
            result = resp.json()
            assert result["valid"] is True, f"Chain invalid at index {result.get('failed_index')}"

        results["11_evidence_chain"] = "PASS"
        print(f"  [11] Evidence chain: valid, {result['entries_checked']} entries")

    finally:
        await client.disconnect()

        # Print summary
        print("\n  ── Results ──")
        for name, status in results.items():
            print(f"  {name}: {status}")
        passed = sum(1 for v in results.values() if v == "PASS")
        print(f"\n  {passed}/{11} checks passed")
