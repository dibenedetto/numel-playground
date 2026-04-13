from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))

from channels.base import ChannelConfig, ChannelStatus
from channels.telegram_adapter import TelegramAdapter


class TelegramAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_conflict_error_sets_clean_state_and_schedules_shutdown(self) -> None:
        from telegram.error import Conflict

        adapter = TelegramAdapter(ChannelConfig(name="Telegram", channel_type="telegram", token="test"))
        adapter.status = ChannelStatus.RUNNING

        shutdown_calls: list[str] = []

        async def _fake_shutdown():
            shutdown_calls.append("shutdown")

        adapter._shutdown_after_polling_error = _fake_shutdown  # type: ignore[method-assign]

        adapter._handle_polling_error(Conflict("terminated by other getUpdates request"))
        await asyncio.sleep(0)

        self.assertEqual(adapter.status, ChannelStatus.ERROR)
        self.assertIn("another bot instance", str(adapter._error))
        self.assertEqual(shutdown_calls, ["shutdown"])

