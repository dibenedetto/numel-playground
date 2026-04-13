from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys
import shutil

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(1, str(PROJECT_ROOT))

from channels.base import ChannelAdapter, ChannelConfig, ChannelStatus
from channels.registry import ChannelRegistry


class _DummyAdapter(ChannelAdapter):
    start_calls = 0
    stop_calls = 0

    @property
    def type(self) -> str:
        return "dummy"

    async def start(self):
        type(self).start_calls += 1
        self.status = ChannelStatus.RUNNING

    async def stop(self):
        type(self).stop_calls += 1
        self.status = ChannelStatus.STOPPED

    async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
        return True


class ChannelRegistryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        _DummyAdapter.start_calls = 0
        _DummyAdapter.stop_calls = 0
        self._runtime_root = PROJECT_ROOT / "storage" / "_test_runs" / f"channel_registry_{next(tempfile._get_candidate_names())}"
        self._runtime_root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(self._runtime_root, ignore_errors=True))
        self._config_path = str(self._runtime_root / "channels.json")
        self._original_types = dict(ChannelRegistry._adapter_types)
        ChannelRegistry._adapter_types = dict(self._original_types)
        ChannelRegistry.register_type("dummy", _DummyAdapter)
        self.registry = ChannelRegistry(config_path=self._config_path)
        await self.registry.add(ChannelConfig(name="Dummy", channel_type="dummy"))
        self.channel_id = next(iter(self.registry._adapters))

    async def asyncTearDown(self) -> None:
        ChannelRegistry._adapter_types = self._original_types

    async def test_start_is_idempotent_for_running_channel(self) -> None:
        started = await self.registry.start(self.channel_id)
        self.assertTrue(started)
        self.assertEqual(_DummyAdapter.start_calls, 1)

        started_again = await self.registry.start(self.channel_id)
        self.assertTrue(started_again)
        self.assertEqual(_DummyAdapter.start_calls, 1)

    async def test_stop_is_idempotent_for_stopped_channel(self) -> None:
        started = await self.registry.start(self.channel_id)
        self.assertTrue(started)
        self.assertEqual(_DummyAdapter.start_calls, 1)

        stopped = await self.registry.stop(self.channel_id)
        self.assertTrue(stopped)
        self.assertEqual(_DummyAdapter.stop_calls, 1)

        stopped_again = await self.registry.stop(self.channel_id)
        self.assertTrue(stopped_again)
        self.assertEqual(_DummyAdapter.stop_calls, 1)
