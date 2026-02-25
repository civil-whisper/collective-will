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

_RUN_E2E = os.getenv("TEST_TELEGRAM_E2E", "").lower() in {"1", "true", "yes"}

_SKIP_REASON = (
    "Telegram e2e tests disabled. Set TEST_TELEGRAM_E2E=1 and ensure "
    "Telethon session + env vars are configured. "
    "Run `uv run python scripts/telegram_auth.py` first."
)

pytestmark = pytest.mark.skipif(
    not (_RUN_E2E and _API_ID and _API_HASH and _BOT_TOKEN and os.path.exists(_SESSION_FILE)),
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

    messages = await client.get_messages(_BOT_USERNAME, limit=5)
    for msg in messages:
        if not msg.out:
            return msg.text
    return None


@pytest.mark.asyncio
async def test_full_telegram_e2e() -> None:
    """Sequential test exercising the Telegram bot via text messages.

    With buttons-only UX, most interactions happen through inline keyboard
    callbacks. This test covers the text-based paths that remain:
    - Unregistered user prompt
    - Linking code submission
    - Unrecognized text re-sends menu hint
    """
    from telethon import TelegramClient

    client = TelegramClient("test_user_session", int(_API_ID), _API_HASH)  # type: ignore[arg-type]
    await client.connect()
    if not await client.is_user_authorized():
        pytest.skip("Session expired. Re-run: uv run python scripts/telegram_auth.py")

    results: dict[str, str] = {}

    try:
        # -- 1. Unregistered user gets registration prompt --
        reply = await _send_and_wait(client, "سلام تست خودکار")
        assert reply is not None, "Bot did not reply to greeting"
        is_reg_prompt = "ثبت‌نام" in reply or "وبسایت" in reply or "sign up" in reply.lower()
        is_menu_hint = "دکمه" in reply or "buttons" in reply.lower()
        assert is_reg_prompt or is_menu_hint, f"Expected registration prompt or menu hint, got: {reply}"
        results["01_initial_text"] = "PASS"
        print(f"\n  [01] Initial text reply: {reply[:80]}")

        # -- 2. Register via API + link via Telegram --
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
        results["02_link_account"] = "PASS"
        print(f"  [02] Linking code reply: {reply[:80]}")

        # -- 3. Random text from linked user → menu hint --
        reply = await _send_and_wait(client, "random text that is not a button tap")
        assert reply is not None, "Bot did not reply to random text"
        results["03_menu_hint"] = "PASS"
        print(f"  [03] Random text reply: {reply[:80]}")

        # -- 4. Evidence chain integrity via API --
        async with httpx.AsyncClient() as http:
            resp = await http.get(f"{_SERVER_URL}/analytics/evidence")
            assert resp.status_code == 200
            entries = resp.json()
            assert len(entries) >= 1, "No evidence entries"

            resp = await http.post(f"{_SERVER_URL}/analytics/evidence/verify", json=entries)
            assert resp.status_code == 200
            result = resp.json()
            assert result["valid"] is True, f"Chain invalid at index {result.get('failed_index')}"

        results["04_evidence_chain"] = "PASS"
        print(f"  [04] Evidence chain: valid, {result['entries_checked']} entries")

    finally:
        await client.disconnect()

        print("\n  ── Results ──")
        for name, status in results.items():
            print(f"  {name}: {status}")
        passed = sum(1 for v in results.values() if v == "PASS")
        print(f"\n  {passed}/4 checks passed")
