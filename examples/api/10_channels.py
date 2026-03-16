"""
Example 10: Multi-Channel Messaging
=====================================
Demonstrates the channel adapter system for connecting external
messaging platforms to the Numel assistant.

Supported channels:
  - telegram  — Telegram Bot (requires python-telegram-bot)
  - whatsapp  — WhatsApp Business Cloud API (webhook-based)
  - discord   — Discord Bot (requires discord.py)
  - webhook   — Generic HTTP webhook (Slack, custom systems)

This example shows the API for managing channels. To actually connect
a platform, you need valid credentials (bot tokens, API keys, etc.).

Prerequisites:
    pip install httpx
    python app/app.py          # start the server

Run:
    python examples/api/10_channels.py
"""

import asyncio
from client import NumelClient


async def main():
    async with NumelClient() as c:
        print("=== Multi-Channel Messaging ===\n")

        # 1. List available channel types
        types = await c.channel_types()
        print("1. Available channel types:")
        for t in types:
            print(f"   - {t['type']}: {t['doc']}")

        # 2. List current channels
        channels = await c.channel_list()
        print(f"\n2. Active channels: {len(channels)}")
        for ch in channels:
            print(f"   [{ch['status']}] {ch['channel_type']}/{ch['name']} ({ch['id']})")

        # 3. Add a generic webhook channel (no external deps needed)
        print("\n3. Adding a webhook channel...")
        ch = await c.channel_add(
            name="test-webhook",
            channel_type="webhook",
            secret="my-shared-secret",           # for request validation
            callback_url="http://localhost:9999", # where responses go (optional)
        )
        channel_id = ch["id"]
        print(f"   Created: {ch['channel_type']}/{ch['name']} ({channel_id}) [{ch['status']}]")

        # 4. Start the channel
        print("\n4. Starting channel...")
        status = await c.channel_start(channel_id)
        print(f"   Status: {status['status']}")

        # 5. List channels again
        channels = await c.channel_list()
        print(f"\n5. Active channels: {len(channels)}")
        for ch in channels:
            print(f"   [{ch['status']}] {ch['channel_type']}/{ch['name']}")

        # 6. Stop and remove
        print("\n6. Stopping channel...")
        await c.channel_stop(channel_id)

        print("   Removing channel...")
        result = await c.channel_remove(channel_id)
        print(f"   Removed: {result['removed']}")

        # ── Telegram Example (commented — needs real token) ──
        print("\n--- Telegram Example (requires token) ---")
        print("""
        # Get a bot token from @BotFather on Telegram, then:
        ch = await c.channel_add(
            name="my-telegram-bot",
            channel_type="telegram",
            token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            auto_start=True,
        )
        # The bot will start polling Telegram for messages.
        # Any message sent to the bot gets routed to the console agent.
        # The response is sent back to the user on Telegram.
        """)

        # ── WhatsApp Example (commented — needs Meta credentials) ──
        print("--- WhatsApp Example (requires Meta Business API) ---")
        print("""
        ch = await c.channel_add(
            name="whatsapp-business",
            channel_type="whatsapp",
            token="EAAxxxxxxx",  # Meta Graph API access token
            phone_number_id="1234567890",
            verify_token="my-verify-token",
        )
        # Configure Meta webhook URL to:
        #   https://your-server.com/channels/webhook/{channel_id}
        # Meta will send messages to this endpoint.
        """)

        # ── Discord Example (commented — needs bot token) ──
        print("--- Discord Example (requires bot token) ---")
        print("""
        ch = await c.channel_add(
            name="discord-bot",
            channel_type="discord",
            token="MTIzNDU2Nzg5MDEyMzQ1Njc4.XXXXXX.XXXXXXXXXXXXXXXXXX",
            allowed_channels=["123456789"],  # specific channel IDs
            command_prefix="!numel ",        # trigger prefix
        )
        # The bot responds to:
        #   - Direct messages
        #   - @mentions in allowed channels
        #   - Messages starting with the command prefix
        """)

        print("=== Channel example complete ===")


if __name__ == "__main__":
    asyncio.run(main())
