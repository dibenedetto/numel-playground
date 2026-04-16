from __future__ import annotations

import asyncio
import sys
import time
import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from console import ConsoleAgentManager, PlannerState
from event_bus import EventBus
from prompt_stack import PLANNER_MODE_DIRECTIVE


class ConsolePlannerPauseTests(unittest.IsolatedAsyncioTestCase):
	async def asyncSetUp(self) -> None:
		self.manager = ConsoleAgentManager(
			workspace_mgr=None,
			event_bus=EventBus(),
			port=11361,
		)
		self.state = PlannerState("user_a_tab_a", user_id="user_a", browser_session_id="tab_a")
		self.state.enabled = True
		self.state.pending = [{"type": "manager.workflow_added", "data": {"source": "planner"}}]
		self.state.timer = asyncio.get_running_loop().call_later(60, lambda: None)
		self.manager._planners[self.state.key] = self.state

	def test_pause_clears_pending_and_cancels_timer(self) -> None:
		paused = self.manager.pause_planner_for_manual_run(user_id="user_a", session_id="tab_a", duration_s=90)
		self.assertTrue(paused)
		self.assertEqual(self.state.pending, [])
		self.assertIsNone(self.state.timer)
		self.assertGreater(self.state.pause_until, 0.0)

	async def test_pause_ignores_workflow_added_during_window(self) -> None:
		self.manager.pause_planner_for_manual_run(user_id="user_a", session_id="tab_a", duration_s=90)
		event = SimpleNamespace(event_type="manager.workflow_added", data={"source": "planner"})
		await self.manager._on_planner_event(event)
		self.assertEqual(self.state.pending, [])

	async def test_self_apply_suppression_ignores_workflow_added(self) -> None:
		self.state.pending.clear()
		if self.state.timer:
			self.state.timer.cancel()
			self.state.timer = None
		self.manager.suppress_planner_added_reaction(user_id="user_a", session_id="tab_a", duration_s=15)
		event = SimpleNamespace(event_type="manager.workflow_added", data={"source": "planner"})
		await self.manager._on_planner_event(event)
		self.assertEqual(self.state.pending, [])

	async def test_process_planner_events_uses_workflow_backed_turn(self) -> None:
		self.state.pending = [{"type": "workflow.completed", "data": {"status": "ok"}}]
		self.state.session_start = time.time()
		self.manager._run_workflow_backed_console_turn = AsyncMock(return_value={"response": "planner ok", "tool_calls": []})
		self.manager.push_proactive = AsyncMock()

		await self.manager._process_planner_events(self.state.key)

		self.manager._run_workflow_backed_console_turn.assert_awaited_once()
		call = self.manager._run_workflow_backed_console_turn.await_args
		self.assertEqual(call.kwargs["workflow_name"], "Planner Event Turn")
		self.assertEqual(call.kwargs["extra_instructions"], [PLANNER_MODE_DIRECTIVE])
		self.assertEqual(self.state.turn_count, 1)

	async def test_active_planner_event_is_coalesced_instead_of_dropped(self) -> None:
		self.state.active = True
		self.state.pending = []
		existing_timer = self.state.timer

		event = SimpleNamespace(event_type="workflow.completed", data={"status": "ok"})
		await self.manager._on_planner_event(event)
		await self.manager._on_planner_event(event)

		self.assertEqual(len(self.state.pending), 1)
		self.assertEqual(self.state.pending[0]["type"], "workflow.completed")
		self.assertEqual(self.state.pending[0]["count"], 2)
		self.assertIs(self.state.timer, existing_timer)

	async def test_process_planner_events_schedules_follow_up_for_events_arriving_while_active(self) -> None:
		self.state.pending = [{"type": "workflow.completed", "data": {"status": "ok"}}]
		self.state.session_start = time.time()
		self.state.debounce = 0.01
		self.manager.push_proactive = AsyncMock()

		calls = 0

		async def _fake_turn(**kwargs):
			nonlocal calls
			calls += 1
			if calls == 1:
				await self.manager._on_planner_event(SimpleNamespace(event_type="workflow.failed", data={"status": "bad"}))
			return {"response": f"planner {calls}", "tool_calls": []}

		self.manager._run_workflow_backed_console_turn = AsyncMock(side_effect=_fake_turn)

		await self.manager._process_planner_events(self.state.key)
		await asyncio.sleep(0.05)

		self.assertEqual(calls, 2)
		self.assertEqual(self.state.turn_count, 2)
		self.assertEqual(self.state.pending, [])

	def test_status_payload_reports_pause_debounce_and_pending(self) -> None:
		now = time.time()
		self.state.pause_until = now + 30
		self.state.suppress_added_until = now + 5
		self.state.debounce_until = now + 1.5
		self.state.last_event_type = "workflow.completed"
		self.state.last_event_at = now
		self.state.last_processed_at = now - 2
		self.state.last_pause_reason = "manual_run"
		self.state.last_suppressed_event = "manager.workflow_added"
		self.state.pending = [
			{"type": "workflow.completed", "count": 2, "data": {"status": "ok"}},
			{"type": "workflow.failed", "count": 1, "data": {"status": "bad"}},
		]

		payload = self.manager._planner_status_payload(self.state)

		self.assertTrue(payload["enabled"])
		self.assertEqual(payload["pending_event_count"], 3)
		self.assertEqual(payload["pending_event_types"], ["workflow.completed", "workflow.failed"])
		self.assertGreater(payload["pause_remaining_s"], 0.0)
		self.assertGreater(payload["suppress_added_remaining_s"], 0.0)
		self.assertGreater(payload["debounce_remaining_s"], 0.0)
		self.assertEqual(payload["last_event_type"], "workflow.completed")
		self.assertEqual(payload["last_pause_reason"], "manual_run")
		self.assertEqual(payload["last_suppressed_event"], "manager.workflow_added")


if __name__ == "__main__":
	unittest.main()
