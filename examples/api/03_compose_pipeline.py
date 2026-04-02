"""
Example 3: Compose a Multi-Step Pipeline in One Current Workflow
================================================================
The old multi-workflow compose flow is no longer the primary interface.
This example shows the same idea using one current workflow inside one
space: multiple transform steps wired into a single pipeline.

Run:
	python examples/api/03_compose_pipeline.py
"""

import asyncio


from client import NumelClient


PIPELINE_WORKFLOW = {
	"options": {
		"type": "workflow_options",
		"name": "pipeline-demo",
		"description": "Generate data, process it, and preview a summary.",
	},
	"nodes": [
		{"type": "start_flow", "extra": {"name": "Start"}},
		{
			"type": "transform_flow",
			"extra": {"name": "Generate"},
			"lang": "python",
			"script": 'output = {"items": ["apple", "banana", "cherry", "date"]}',
		},
		{
			"type": "transform_flow",
			"extra": {"name": "Process"},
			"lang": "python",
			"script": (
				'items = input.get("items", [])\n'
				'output = {"summary": f"Processed {len(items)} items", "upper": [item.upper() for item in items]}'
			),
		},
		{"type": "preview_flow", "extra": {"name": "Preview"}},
		{"type": "end_flow", "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output", "target_slot": "flow_in"},
		{"source": 2, "target": 3, "source_slot": "output", "target_slot": "flow_in"},
		{"source": 3, "target": 4, "source_slot": "output", "target_slot": "flow_in"},
	],
}


async def main():
	async with NumelClient() as c:
		await c.ensure_auth()
		space = await c.ensure_space("API Example 03", slug="api-example-03", description="Single-workflow pipeline")
		print(f"Using space: {space['id']} ({space['title']})")

		await c.replace_current_workflow(PIPELINE_WORKFLOW, name="pipeline-demo")
		started = await c.start_workflow()
		results = await c.wait(started["execution_id"])

		print(f"Execution status: {results['status']}")
		for node_idx, outputs in results["node_outputs"].items():
			if outputs:
				print(f"Node {node_idx}: {outputs}")

		await c.delete_workflow()
		print("Done.")


if __name__ == "__main__":
	asyncio.run(main())
