from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from event_bus import EventBus
from manager import WorkflowManager


class WorkflowManagerImplTests(unittest.IsolatedAsyncioTestCase):
	@staticmethod
	def _workflow_with_nodes(*node_types):
		wf = SimpleNamespace(
			nodes=[SimpleNamespace(type=node_type, port=None) for node_type in node_types],
			options=SimpleNamespace(name="wf"),
		)
		wf.link = lambda: None
		return wf

	async def test_impl_serializes_concurrent_agent_startup(self):
		event_bus = EventBus()
		manager = WorkflowManager(port=15000, event_bus=event_bus)
		workflow = self._workflow_with_nodes("agent_config")
		fake_backend = SimpleNamespace(
			handles=[object()],
			get_agent_app=lambda _handle: object(),
		)
		manager._workflows["wf"] = manager._make_workflow(workflow)
		manager._build_backend = lambda _workflow: fake_backend

		server_instances = []

		class FakeServer:
			def __init__(self, config):
				self.config = config
				self.started = False
				self.should_exit = False
				server_instances.append(self)

			async def serve(self):
				await asyncio.sleep(0.05)
				self.started = True
				while not self.should_exit:
					await asyncio.sleep(0.01)

		with patch("manager.uvicorn.Server", FakeServer):
			first, second = await asyncio.gather(
				manager.impl("wf"),
				manager.impl("wf"),
			)

		self.assertIs(first, second)
		self.assertIs(first["backend"], fake_backend)
		self.assertEqual(len(server_instances), 1)
		self.assertEqual(workflow.nodes[0].port, 15001)

		await manager.remove()

	async def test_impl_surfaces_startup_failure_without_caching_backend(self):
		event_bus = EventBus()
		manager = WorkflowManager(port=16000, event_bus=event_bus)
		workflow = self._workflow_with_nodes("agent_config")
		fake_backend = SimpleNamespace(
			handles=[object()],
			get_agent_app=lambda _handle: object(),
		)
		manager._workflows["wf"] = manager._make_workflow(workflow)
		manager._build_backend = lambda _workflow: fake_backend

		class FailingServer:
			def __init__(self, config):
				self.config = config
				self.started = False
				self.should_exit = False

			async def serve(self):
				raise OSError("bind failed")

		with patch("manager.uvicorn.Server", FailingServer):
			with self.assertRaisesRegex(RuntimeError, "Agent server failed on port 16001"):
				await manager.impl("wf")

		self.assertIsNone(manager._workflows["wf"]["backend"])
		self.assertIsNone(manager._workflows["wf"]["apps"])

	async def test_add_waits_for_impl_before_replacing_workflow(self):
		event_bus = EventBus()
		manager = WorkflowManager(port=17000, event_bus=event_bus)
		first_workflow = self._workflow_with_nodes("agent_config")
		second_workflow = self._workflow_with_nodes("agent_config")
		fake_backend = SimpleNamespace(
			handles=[object()],
			get_agent_app=lambda _handle: object(),
		)
		manager._workflows["wf"] = manager._make_workflow(first_workflow)
		manager._build_backend = lambda _workflow: fake_backend

		wait_entered = asyncio.Event()
		allow_continue = asyncio.Event()

		async def fake_wait_for_agent_servers(_servers, timeout_s=2.0):
			wait_entered.set()
			await allow_continue.wait()

		class FakeServer:
			def __init__(self, config):
				self.config = config
				self.started = True
				self.should_exit = False

			async def serve(self):
				while not self.should_exit:
					await asyncio.sleep(0.01)

		with patch("manager.uvicorn.Server", FakeServer):
			with patch.object(manager, "_wait_for_agent_servers", fake_wait_for_agent_servers):
				impl_task = asyncio.create_task(manager.impl("wf"))
				await wait_entered.wait()

				add_task = asyncio.create_task(manager.add(second_workflow, "wf"))
				await asyncio.sleep(0.05)
				self.assertFalse(add_task.done(), "Workflow replacement should wait for impl lock")

				allow_continue.set()
				await impl_task
				await add_task

		self.assertIsNone(manager._workflows["wf"]["backend"])
		await manager.remove()


if __name__ == "__main__":
	unittest.main()
