"""
Example 3: Workflow Composition (Pipeline)
==========================================
Chain two workflows sequentially: the output of step 1
feeds into step 2 via input_map.

Pipeline:
	generate-data  →  process-data
	(produces list)    (receives & transforms it)

Run:
	python examples/api/03_compose_pipeline.py
"""

import asyncio


from   client  import NumelClient


GENERATE_WF = {
	"options": {"type": "workflow_options", "name": "generate-data"},
	"nodes": [
		{"type": "start_flow",     "extra": {"name": "Start"}},
		{"type": "transform_flow", "extra": {"name": "Generate"},
		"lang": "python",
		"script": 'output = {"items": ["apple", "banana", "cherry", "date"]}'},
		{"type": "end_flow",       "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output",   "target_slot": "flow_in"},
	],
}

PROCESS_WF = {
	"options": {"type": "workflow_options", "name": "process-data"},
	"nodes": [
		{"type": "start_flow",     "extra": {"name": "Start"}},
		{"type": "transform_flow", "extra": {"name": "Process"},
		"lang": "python",
		"script": 'output = {"summary": f"Processed {len(context.get(\"items\", []))} items", "upper": [x.upper() for x in context.get("items", [])]}',
		"context": {"items": []}},
		{"type": "end_flow",       "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output",   "target_slot": "flow_in"},
	],
}


async def main():
	async with NumelClient() as c:
		# Upload both workflows
		await c.add(GENERATE_WF, "generate-data")
		await c.add(PROCESS_WF,  "process-data")
		print("Uploaded: generate-data, process-data")

		# Compose: run generate-data first, then process-data
		# input_map wires the "items" output from step 1 into step 2
		r = await c.compose([
			{"workflow_name": "generate-data"},
			{"workflow_name": "process-data",
			"input_map": {"items": "items"}},
		])
		compose_id = r["compose_id"]
		print(f"Compose started: {compose_id}")

		# Poll until done
		while True:
			state = await c.compose_state(compose_id)
			if state["status"] in ("completed", "failed", "cancelled"):
				break
			await asyncio.sleep(0.5)

		print(f"Pipeline status: {state['status']}")
		for step in state.get("steps", []):
			print(f"  Step {step['index']} ({step['workflow_name']}): {step['status']}")
			if step.get("execution_id"):
				results = await c.results(step["execution_id"])
				for idx, outputs in results["node_outputs"].items():
					if outputs:
						print(f"    outputs: {outputs}")

		# Clean up
		await c.remove("generate-data")
		await c.remove("process-data")
		print("\nCleaned up.")


if __name__ == "__main__":
	asyncio.run(main())
