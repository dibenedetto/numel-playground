"""
Example 6: WebSocket Event Stream with Filtering
==================================================
Connect to the event WebSocket, subscribe to a specific
execution, and print events in real time.

Run:
	python examples/api/06_event_stream.py
"""

import asyncio
import json


import httpx
import websockets


BASE   = "http://localhost:11360"
WS_URL = "ws://localhost:11360/events"


WORKFLOW = {
	"options": {"type": "workflow_options", "name": "event-demo"},
	"nodes": [
		{"type": "start_flow",     "extra": {"name": "Start"}},
		{"type": "transform_flow", "extra": {"name": "Step A"},
		"lang": "python", "script": 'output = {"a": 1}'},
		{"type": "transform_flow", "extra": {"name": "Step B"},
		"lang": "python", "script": 'output = {"b": 2}'},
		{"type": "end_flow",       "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output",   "target_slot": "flow_in"},
		{"source": 2, "target": 3, "source_slot": "output",   "target_slot": "flow_in"},
	],
}


async def event_listener(execution_id: str):
	"""Connect to WebSocket and listen for events filtered to our execution."""
	async with websockets.connect(WS_URL) as ws:
		# Subscribe to only our execution's events
		await ws.send(json.dumps({
			"type": "subscribe",
			"filters": {"execution_id": execution_id},
		}))

		# Read the subscription confirmation
		ack = json.loads(await ws.recv())
		print(f"  [WS] Subscribed: {ack}")

		# Listen for events until workflow completes
		while True:
			msg = json.loads(await ws.recv())
			if msg.get("type") == "workflow_event":
				ev = msg["event"]
				print(f"  [WS] {ev['event_type']:30s}  node={ev.get('node_id', '-'):>4s}")
				if ev["event_type"] in ("workflow.completed", "workflow.failed", "workflow.cancelled"):
					break


async def main():
	async with httpx.AsyncClient(base_url=BASE, timeout=60) as http:
		# Upload workflow
		r = await http.post("/add", json={"workflow": WORKFLOW, "name": "event-demo"})
		r.raise_for_status()
		print("Workflow uploaded.")

		# Start execution
		r = await http.post("/start", json={"name": "event-demo"})
		r.raise_for_status()
		exec_id = r.json()["execution_id"]
		print(f"Execution started: {exec_id}\n")

		# Listen to filtered events
		await event_listener(exec_id)

		# Get final results
		r = await http.post(f"/exec_results/{exec_id}")
		r.raise_for_status()
		results = r.json()
		print(f"\nFinal status: {results['status']}")
		print(f"Outputs: {results['node_outputs']}")

		# Clean up
		await http.post("/remove/event-demo")
		print("Done.")


if __name__ == "__main__":
	asyncio.run(main())
