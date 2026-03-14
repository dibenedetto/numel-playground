"""
Example 1: Run a Simple Workflow
================================
Load a workflow JSON, upload it, execute it, and retrieve results.

Prerequisites:
	pip install httpx
	python app/app.py          # start the server (default port 11360)

Run:
	python examples/api/01_run_workflow.py
"""

import asyncio


from   client  import NumelClient


# A minimal workflow defined inline: Start → Transform → End
WORKFLOW = {
	"options": {
		"type": "workflow_options",
		"name": "api-hello",
		"description": "Minimal API test workflow",
	},
	"nodes": [
		{"type": "start_flow",     "extra": {"name": "Start"}},
		{"type": "transform_flow", "extra": {"name": "Greet"},
		"lang": "python",
		"script": 'output = {"greeting": "Hello from the API!", "numbers": list(range(5))}'},
		{"type": "end_flow",       "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output",   "target_slot": "flow_in"},
	],
}


async def main():
	async with NumelClient() as c:
		# 1. Upload the workflow
		r = await c.add(WORKFLOW, "api-hello")
		print(f"Added workflow: {r['name']}  status={r['status']}")

		# 2. Start execution
		exec_id = await c.start("api-hello")
		print(f"Started execution: {exec_id}")

		# 3. Wait for completion and get results
		results = await c.wait(exec_id)
		print(f"Status: {results['status']}")
		print(f"Outputs: {results['node_outputs']}")

		# 4. Clean up
		await c.remove("api-hello")
		print("Workflow removed.")


if __name__ == "__main__":
	asyncio.run(main())
