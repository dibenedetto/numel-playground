"""
Example 1: Run the Current Workflow in a Space
==============================================
Authenticate, create a space, save one workflow as that space's current
workflow, execute it, and print the results.

Run:
	python examples/api/01_run_workflow.py
"""

import asyncio


from client import NumelClient


WORKFLOW = {
	"options": {
		"type": "workflow_options",
		"name": "api-hello",
		"description": "Minimal API test workflow",
	},
	"nodes": [
		{"type": "start_flow", "extra": {"name": "Start"}},
		{
			"type": "transform_flow",
			"extra": {"name": "Greet"},
			"lang": "python",
			"script": 'output = {"greeting": "Hello from the API!", "numbers": list(range(5))}',
		},
		{"type": "end_flow", "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output", "target_slot": "flow_in"},
	],
}


async def main():
	async with NumelClient() as c:
		await c.ensure_auth()
		space = await c.ensure_space("API Example 01", slug="api-example-01", description="Current workflow demo")
		print(f"Using space: {space['id']} ({space['title']})")

		saved = await c.replace_current_workflow(WORKFLOW, name="api-hello")
		print(f"Saved workflow: {saved['name']}  status={saved['status']}")

		started = await c.start_workflow()
		exec_id = started["execution_id"]
		print(f"Started execution: {exec_id}")

		results = await c.wait(exec_id)
		print(f"Status: {results['status']}")
		print(f"Outputs: {results['node_outputs']}")

		await c.delete_workflow()
		print("Current workflow deleted from the example space.")


if __name__ == "__main__":
	asyncio.run(main())
