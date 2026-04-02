"""
Example 8: Full API Showcase
============================
A guided tour of the current Numel interface:

  1. Connection and auth
  2. Spaces
  3. Current workflow save/load
  4. Executions
  5. WebSocket events
  6. Toolkits, skills, docs, gallery
  7. Console and memory
  8. Channels
  9. Event sources and templates
  10. Published apps

Run:
	python examples/api/08_full_api_showcase.py
"""

import asyncio
import json
import os
import sys
import traceback
import uuid

import websockets

from client import NumelClient


BASE_URL = os.environ.get("NUMEL_URL", "http://localhost:11360")
WS_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/events"

_PASS = 0
_FAIL = 0


def section(title: str):
	print(f"\n{'=' * 60}")
	print(f"  {title}")
	print(f"{'=' * 60}")


def ok(msg: str):
	global _PASS
	_PASS += 1
	print(f"  [OK] {msg}")


def fail(msg: str, err=None):
	global _FAIL
	_FAIL += 1
	print(f"  [FAIL] {msg}")
	if err:
		for line in traceback.format_exception_only(type(err), err):
			print(f"         {line.rstrip()}")


def preview(data, max_len=120):
	s = json.dumps(data, default=str) if not isinstance(data, str) else data
	return s[:max_len] + ("..." if len(s) > max_len else "")


def make_workflow(name: str, script: str, description: str = "") -> dict:
	return {
		"options": {"type": "workflow_options", "name": name, "description": description},
		"nodes": [
			{"type": "start_flow", "extra": {"name": "Start"}},
			{"type": "transform_flow", "extra": {"name": "Compute"}, "lang": "python", "script": script},
			{"type": "end_flow", "extra": {"name": "End"}},
		],
		"edges": [
			{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": 1, "target": 2, "source_slot": "output", "target_slot": "flow_in"},
		],
	}


async def test_connection_and_auth(c: NumelClient):
	section("1. Connection and Auth")

	try:
		r = await c.ping()
		ok(f"ping -> {r['message']}")
	except Exception as e:
		fail("ping", e)
		return False

	try:
		r = await c.status()
		ok(f"status -> executions={len(r.get('executions', {}))}")
	except Exception as e:
		fail("status", e)

	try:
		r = await c.schema()
		ok(f"schema -> {len(r.get('schema', ''))} chars of source")
	except Exception as e:
		fail("schema", e)

	try:
		result = await c.ensure_auth()
		user = result.get("user", {})
		ok(f"auth -> {user.get('username', '?')} ({user.get('role', '?')})")
	except Exception as e:
		fail("auth", e)
		return False

	return True


async def test_spaces(c: NumelClient):
	section("2. Spaces")
	suffix = uuid.uuid4().hex[:6]
	created_id = None

	try:
		r = await c.list_spaces()
		ok(f"list_spaces -> {len(r.get('spaces', []))} space(s)")
	except Exception as e:
		fail("list_spaces", e)

	try:
		r = await c.create_space(title="Showcase Space", slug=f"showcase-space-{suffix}", description="API showcase")
		created_id = r["space"]["id"]
		ok(f"create_space -> {created_id}")
	except Exception as e:
		fail("create_space", e)
		return None

	try:
		r = await c.current_space()
		ok(f"current_space -> {r.get('space', {}).get('id')}")
	except Exception as e:
		fail("current_space", e)

	return created_id


async def test_current_workflow(c: NumelClient):
	section("3. Current Workflow")
	wf = make_workflow("showcase-current", 'output = {"hello": "world"}', "Current workflow demo")

	try:
		r = await c.save_workflow(wf)
		ok(f"save_workflow -> {r.get('name')}")
	except Exception as e:
		fail("save_workflow", e)
		return None

	try:
		r = await c.get_workflow()
		node_count = len((r.get("workflow") or {}).get("nodes", []))
		ok(f"get_workflow -> {node_count} nodes")
	except Exception as e:
		fail("get_workflow", e)

	return wf


async def test_execution(c: NumelClient):
	section("4. Executions")

	try:
		started = await c.start_workflow()
		exec_id = started["execution_id"]
		ok(f"start_workflow -> {exec_id[:12]}...")
	except Exception as e:
		fail("start_workflow", e)
		return None

	try:
		state = await c.execution_state(exec_id)
		ok(f"execution_state -> {state.get('state', {}).get('status', '?')}")
	except Exception as e:
		fail("execution_state", e)

	try:
		results = await c.wait(exec_id)
		ok(f"execution_results -> {results.get('status')} {preview(results.get('node_outputs', {}), 80)}")
	except Exception as e:
		fail("execution_results", e)

	try:
		items = await c.list_executions()
		ok(f"list_executions -> {len(items.get('execution_ids', []))} visible execution(s)")
	except Exception as e:
		fail("list_executions", e)

	return exec_id


async def test_events(c: NumelClient):
	section("5. WebSocket Events")

	try:
		await c.save_workflow(make_workflow("showcase-events", 'output = {"step": "done"}'))
		started = await c.start_workflow()
		exec_id = started["execution_id"]
	except Exception as e:
		fail("prepare_events", e)
		return

	events_received = []
	try:
		async with websockets.connect(WS_URL) as ws:
			await ws.send(json.dumps({"type": "subscribe", "filters": {"execution_id": exec_id}}))
			await ws.recv()

			async def reader():
				while True:
					msg = json.loads(await ws.recv())
					if msg.get("type") != "workflow_event":
						continue
					ev = msg["event"]
					events_received.append(ev["event_type"])
					if ev["event_type"] in ("workflow.completed", "workflow.failed", "workflow.cancelled"):
						return

			await asyncio.wait_for(reader(), timeout=5.0)
		ok(f"events -> {events_received[:6]}{'...' if len(events_received) > 6 else ''}")
	except Exception as e:
		fail("events", e)


async def test_catalog_features(c: NumelClient):
	section("6. Toolkits, Skills, Docs, Gallery")

	try:
		toolkits = await c.toolkit_list()
		ok(f"toolkits -> {len(toolkits.get('toolkits', []))} toolkit(s)")
	except Exception as e:
		fail("toolkits", e)

	try:
		skills = await c.skills_list()
		ok(f"skills -> {len(skills.get('skills', []))} skill(s)")
	except Exception as e:
		fail("skills", e)

	try:
		docs = await c.docs_list()
		ok(f"docs -> {len(docs.get('files', []))} file(s)")
	except Exception as e:
		fail("docs", e)

	try:
		gallery = await c.gallery_list()
		ok(f"gallery -> {len(gallery)} item(s)")
	except Exception as e:
		fail("gallery", e)


async def test_console_and_memory(c: NumelClient):
	section("7. Console and Memory")

	try:
		stats = await c.memory_stats()
		ok(f"memory_stats -> total={stats.get('total', 0)}")
	except Exception as e:
		fail("memory_stats", e)

	try:
		record = await c.memory_add("Showcase memory entry", type="fact", importance=0.8)
		ok(f"memory_add -> {record.get('id')}")
		await c.memory_delete(record["id"])
	except Exception as e:
		fail("memory_add/delete", e)

	try:
		toolkits = await c.console_toolkits()
		ok(f"console_toolkits -> {len(toolkits)} toolkit(s)")
	except Exception as e:
		fail("console_toolkits", e)


async def test_channels(c: NumelClient):
	section("8. Channels")
	channel_id = None
	try:
		types = await c.channel_types()
		ok(f"channel_types -> {len(types)} type(s)")
	except Exception as e:
		fail("channel_types", e)
		return

	try:
		ch = await c.channel_add(
			name="showcase-webhook",
			channel_type="webhook",
			auto_start=False,
			secret="showcase-secret",
			response_format="json",
		)
		channel_id = ch["id"]
		ok(f"channel_add -> {channel_id}")
	except Exception as e:
		fail("channel_add", e)
		return

	try:
		status = await c.channel_start(channel_id)
		ok(f"channel_start -> {status.get('status')}")
	except Exception as e:
		fail("channel_start", e)

	try:
		await c.channel_stop(channel_id)
		await c.channel_remove(channel_id)
		ok("channel_remove -> removed")
	except Exception as e:
		fail("channel_stop/remove", e)


async def test_runtime_misc(c: NumelClient):
	section("9. Event Sources and Templates")

	try:
		sources = await c.event_sources_list()
		ok(f"event_sources_list -> {len(sources.get('sources', []))} source(s)")
	except Exception as e:
		fail("event_sources_list", e)

	try:
		templates = await c.templates_list()
		ok(f"templates_list -> {len(templates)} template(s)")
	except Exception as e:
		fail("templates_list", e)


async def test_apps(c: NumelClient, workflow: dict):
	section("10. Published Apps")
	slug = f"showcase-{uuid.uuid4().hex[:6]}"
	try:
		published = await c.apps_publish(workflow=workflow, slug=slug, title="Showcase App")
		ok(f"apps_publish -> {published.get('url')}")
		await c.apps_unpublish(slug)
		ok("apps_unpublish -> removed")
	except Exception as e:
		fail("apps_publish/unpublish", e)


async def main():
	print("Numel API Full Showcase")
	print(f"Server: {BASE_URL}")
	print("=" * 60)

	async with NumelClient(BASE_URL) as c:
		connected = await test_connection_and_auth(c)
		if not connected:
			print("\nServer not reachable or auth failed.")
			sys.exit(1)

		space_id = await test_spaces(c)
		if not space_id:
			sys.exit(1)

		workflow = await test_current_workflow(c)
		if workflow is not None:
			await test_execution(c)
			await test_events(c)
			await test_apps(c, workflow)

		await test_catalog_features(c)
		await test_console_and_memory(c)
		await test_channels(c)
		await test_runtime_misc(c)

		try:
			await c.delete_space(space_id)
		except Exception:
			pass

	print(f"\n{'=' * 60}")
	print(f"  SUMMARY: {_PASS} passed, {_FAIL} failed")
	print(f"{'=' * 60}")
	sys.exit(1 if _FAIL > 0 else 0)


if __name__ == "__main__":
	asyncio.run(main())
