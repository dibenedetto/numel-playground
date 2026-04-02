"""
Example 6: WebSocket Event Stream
=================================
Connect to the event WebSocket, filter events to one execution, and
watch the current workflow run in real time.

Run:
	python examples/api/06_event_stream.py
"""

import asyncio
import json
import os
import uuid


import websockets


from client import NumelClient


BASE_URL = os.environ.get("NUMEL_URL", "http://localhost:11360")
WS_URL = BASE_URL.replace("http://", "ws://").replace("https://", "wss://") + "/events"


WORKFLOW = {
	"options": {"type": "workflow_options", "name": "event-demo"},
	"nodes": [
		{"type": "start_flow", "extra": {"name": "Start"}},
		{"type": "transform_flow", "extra": {"name": "Step A"}, "lang": "python", "script": 'output = {"a": 1}'},
		{"type": "transform_flow", "extra": {"name": "Step B"}, "lang": "python", "script": 'output = {"b": 2}'},
		{"type": "end_flow", "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output", "target_slot": "flow_in"},
		{"source": 2, "target": 3, "source_slot": "output", "target_slot": "flow_in"},
	],
}


async def event_listener(execution_id: str):
	async with websockets.connect(WS_URL) as ws:
		await ws.send(json.dumps({"type": "subscribe", "filters": {"execution_id": execution_id}}))
		ack = json.loads(await ws.recv())
		print(f"  [WS] Subscribed: {ack}")

		while True:
			msg = json.loads(await ws.recv())
			if msg.get("type") != "workflow_event":
				continue
			ev = msg["event"]
			node_id = str(ev.get("node_id", "-"))
			print(f"  [WS] {ev['event_type']:30s} node={node_id}")
			if ev["event_type"] in ("workflow.completed", "workflow.failed", "workflow.cancelled"):
				break


async def main():
	async with NumelClient(BASE_URL) as c:
		await c.ensure_auth()
		suffix = uuid.uuid4().hex[:6]
		space = await c.create_space(title="Event Demo", slug=f"event-demo-{suffix}")
		await c.select_space(space["space"]["id"])
		await c.replace_current_workflow(WORKFLOW, name="event-demo")
		print("Current workflow saved.")

		started = await c.start_workflow()
		exec_id = started["execution_id"]
		print(f"Execution started: {exec_id}\n")

		await event_listener(exec_id)

		results = await c.execution_results(exec_id)
		print(f"\nFinal status: {results['status']}")
		print(f"Outputs: {results['node_outputs']}")

		await c.delete_space(space["space"]["id"])
		print("Done.")


if __name__ == "__main__":
	asyncio.run(main())
