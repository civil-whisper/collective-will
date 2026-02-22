"""One-time Telethon authentication. Creates a session file for automated tests.

Run: uv run python scripts/telegram_auth.py

You'll be prompted for your phone number and verification code.
After that, `test_user_session.session` is saved and all future test runs
are fully automatic.
"""
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

api_id = os.getenv("TELEGRAM_API_ID")
api_hash = os.getenv("TELEGRAM_API_HASH")
bot_username = os.getenv("TELEGRAM_BOT_USERNAME", "collective_will_dev_bot")

if not api_id or not api_hash:
    print("ERROR: Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env")
    sys.exit(1)


async def main() -> None:
    from telethon import TelegramClient

    client = TelegramClient("test_user_session", int(api_id), api_hash)
    await client.start()
    me = await client.get_me()
    print(f"\nAuthenticated as: {me.first_name} (ID: {me.id})")  # type: ignore[union-attr]

    # Verify we can reach the bot
    await client.send_message(bot_username, "/start")
    await asyncio.sleep(2)
    messages = await client.get_messages(bot_username, limit=1)
    if messages and not messages[0].out:
        print(f"Bot replied: {messages[0].text[:80]}")
    else:
        print("Bot did not reply (is the server running?)")

    await client.disconnect()
    print("\nSession saved to test_user_session.session")
    print("You can now run the automated tests.")


asyncio.run(main())
