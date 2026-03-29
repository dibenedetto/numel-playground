"""
Example 10: Multi-Channel Messaging
=====================================
Demonstrates the channel adapter system for connecting external
messaging platforms to the Numel assistant.

Supported channels (9 platforms):
  - telegram  — Telegram Bot (requires python-telegram-bot)
  - whatsapp  — WhatsApp Business Cloud API (webhook-based)
  - discord   — Discord Bot (requires discord.py)
  - slack     — Slack Bot (Socket Mode or webhook)
  - signal    — Signal Messenger (requires signal-cli-rest-api)
  - teams     — Microsoft Teams (Bot Framework)
  - email     — Email (IMAP polling + SMTP replies)
  - webhook   — Generic HTTP webhook (any system)

All channels support sending and receiving media/attachments.

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

        # 5. Send a message with attachments
        print("\n5. Sending message with attachments...")
        result = await c.channel_send(
            channel_id=channel_id,
            recipient_id="user-123",
            text="Here is the report you requested.",
            attachments=[
                {"url": "https://example.com/report.pdf", "mime_type": "application/pdf", "filename": "report.pdf"},
                {"url": "https://example.com/chart.png", "mime_type": "image/png", "filename": "chart.png"},
            ],
        )
        print(f"   Sent: {result.get('sent', result)}")

        # 6. List channels again
        channels = await c.channel_list()
        print(f"\n6. Active channels: {len(channels)}")
        for ch in channels:
            print(f"   [{ch['status']}] {ch['channel_type']}/{ch['name']}")

        # 7. Stop and remove
        print("\n7. Stopping channel...")
        await c.channel_stop(channel_id)

        print("   Removing channel...")
        result = await c.channel_remove(channel_id)
        print(f"   Removed: {result['removed']}")

        # ─────────────────────────────────────────────────────────────
        # Channel configuration examples (commented — need real creds)
        # ─────────────────────────────────────────────────────────────

        # ── Telegram ─────────────────────────────────────────────────
        print("\n--- Telegram (requires bot token from @BotFather) ---")
        print("""
        ch = await c.channel_add(
            name="my-telegram-bot",
            channel_type="telegram",
            token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            auto_start=True,
        )
        # Receives: text, photos, documents, audio, video, voice, stickers
        # Sends:    text, photos (send_photo), documents, audio, video
        """)

        # ── WhatsApp ─────────────────────────────────────────────────
        print("--- WhatsApp (requires Meta Business API) ---")
        print("""
        ch = await c.channel_add(
            name="whatsapp-business",
            channel_type="whatsapp",
            token="EAAxxxxxxx",          # Meta Graph API access token
            phone_number_id="1234567890",
            verify_token="my-verify-token",
            app_secret="your-app-secret", # webhook signature verification
        )
        # Configure Meta webhook URL to:
        #   https://your-server.com/channels/webhook/{channel_id}
        # Receives: text, images, video, audio, documents, stickers
        # Sends:    text, images, video, audio, documents (via media links)
        """)

        # ── Discord ──────────────────────────────────────────────────
        print("--- Discord (requires bot token) ---")
        print("""
        ch = await c.channel_add(
            name="discord-bot",
            channel_type="discord",
            token="MTIzNDU2Nzg5MDEyMzQ1Njc4.XXXXXX.XXXXXXXXXXXXXXXXXX",
            allowed_channels=["123456789"],  # specific channel IDs
            command_prefix="!numel ",        # trigger prefix
        )
        # Responds to: DMs, @mentions, command prefix
        # Receives: text + file attachments (any type)
        # Sends:    text + file uploads (discord.File)
        """)

        # ── Slack ────────────────────────────────────────────────────
        print("--- Slack (Socket Mode or webhook) ---")
        print("""
        # Socket Mode (no public webhook needed):
        ch = await c.channel_add(
            name="slack-bot",
            channel_type="slack",
            token="xoxb-...",            # Bot token
            app_token="xapp-...",        # App-level token for Socket Mode
            signing_secret="abc123...",
            allowed_channels=["C0123456789"],
        )

        # Webhook Mode (Events API):
        ch = await c.channel_add(
            name="slack-webhook",
            channel_type="slack",
            token="xoxb-...",
            signing_secret="abc123...",
        )
        # Configure Slack Events API URL to:
        #   https://your-server.com/channels/webhook/{channel_id}
        # Receives: text + file uploads (url_private_download)
        # Sends:    text + file uploads (files.uploadV2)
        """)

        # ── Signal ───────────────────────────────────────────────────
        print("--- Signal (requires signal-cli-rest-api) ---")
        print("""
        # First run signal-cli-rest-api:
        #   docker run -p 8080:8080 bbernhard/signal-cli-rest-api
        ch = await c.channel_add(
            name="signal-bot",
            channel_type="signal",
            phone_number="+1234567890",   # registered Signal number
            api_url="http://localhost:8080",
            poll_interval=2,              # seconds between polls
        )
        # Receives: text + attachments (id, contentType, filename)
        # Sends:    text + base64 attachments
        """)

        # ── Microsoft Teams ──────────────────────────────────────────
        print("--- Microsoft Teams (Bot Framework) ---")
        print("""
        ch = await c.channel_add(
            name="teams-bot",
            channel_type="teams",
            token="your-app-password",    # Azure Bot registration password
            app_id="your-microsoft-app-id",
        )
        # Configure Bot Framework messaging endpoint to:
        #   https://your-server.com/channels/webhook/{channel_id}
        # Receives: text + Bot Framework attachments (contentUrl)
        # Sends:    text + Bot Framework attachment objects
        """)

        # ── Email ────────────────────────────────────────────────────
        print("--- Email (IMAP + SMTP) ---")
        print("""
        ch = await c.channel_add(
            name="email-assistant",
            channel_type="email",
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            imap_host="imap.gmail.com",
            imap_port=993,
            username="assistant@gmail.com",
            password="${GMAIL_APP_PASSWORD}",  # supports credential store
            poll_interval=30,                  # seconds between IMAP polls
            subject_prefix="[Numel]",          # optional filter
            max_body_len=4000,
            auto_start=True,
        )
        # Receives: text body + MIME attachments (any type, as data URIs)
        # Sends:    text + MIME file attachments (MIMEBase parts)
        # Threading: replies use In-Reply-To/References headers
        """)

        # ── Webhook (generic) ────────────────────────────────────────
        print("--- Webhook (generic HTTP) ---")
        print("""
        ch = await c.channel_add(
            name="custom-webhook",
            channel_type="webhook",
            secret="shared-secret",
            callback_url="https://your-app.com/callback",
            response_format="json",  # or "text"
        )
        # Incoming POST body (flexible):
        #   {"text": "...", "sender_id": "...", "attachments": [{url, mime_type, filename}]}
        # Outgoing callback POST:
        #   {"text": "...", "recipient": "...", "attachments": [{url, mime_type, filename}]}
        """)

        # ── Sending attachments via any channel ──────────────────────
        print("--- Sending attachments (works on all channels) ---")
        print("""
        await c.channel_send(
            channel_id="ch_abc123",
            recipient_id="user-or-chat-id",
            text="Here are the files you requested.",
            attachments=[
                {"url": "https://example.com/doc.pdf", "mime_type": "application/pdf", "filename": "doc.pdf"},
                {"url": "https://example.com/img.jpg", "mime_type": "image/jpeg", "filename": "photo.jpg"},
                {"url": "data:audio/mp3;base64,//uQx...", "mime_type": "audio/mp3", "filename": "clip.mp3"},
            ],
        )
        # Each adapter sends via its native API:
        #   Telegram:  send_photo / send_document / send_audio / send_video
        #   Discord:   discord.File uploads
        #   Slack:     files.uploadV2
        #   WhatsApp:  media message with link + caption
        #   Signal:    base64_attachments in JSON payload
        #   Teams:     Bot Framework attachment objects
        #   Email:     MIME multipart with file parts
        #   Webhook:   JSON payload with attachments array
        """)

        print("=== Channel example complete ===")


if __name__ == "__main__":
    asyncio.run(main())
