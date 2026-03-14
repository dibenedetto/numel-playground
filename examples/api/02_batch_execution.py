"""
Example 2: Batch Execution
===========================
Run multiple workflows in parallel and collect all results.

Run:
	python examples/api/02_batch_execution.py
"""

import asyncio


from   client  import NumelClient


def make_transform_workflow(name: str, script: str) -> dict:
	"""Helper to build a simple Start → Transform → End workflow."""
	return {
		"options": {"type": "workflow_options", "name": name},
		"nodes": [
			{"type": "start_flow",     "extra": {"name": "Start"}},
			{"type": "transform_flow", "extra": {"name": "Compute"},
			"lang": "python", "script": script},
			{"type": "end_flow",       "extra": {"name": "End"}},
		],
		"edges": [
			{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": 1, "target": 2, "source_slot": "output",   "target_slot": "flow_in"},
		],
	}


async def main():
	async with NumelClient() as c:
		# Upload three workflows that each compute something different
		workflows = [
			("squares",    'output = {"result": [x**2 for x in range(10)]}'),
			("cubes",      'output = {"result": [x**3 for x in range(10)]}'),
			("factorials", 'import math; output = {"result": [math.factorial(x) for x in range(10)]}'),
		]

		for name, script in workflows:
			wf = make_transform_workflow(name, script)
			await c.add(wf, name)
			print(f"  Added: {name}")

		# Start all three in parallel via batch API
		batch = await c.batch_start([
			{"name": "squares"},
			{"name": "cubes"},
			{"name": "factorials"},
		])
		batch_id = batch["batch_id"]
		print(f"\nBatch started: {batch_id}")
		print(f"Execution IDs: {batch['execution_ids']}")

		# Wait for all to complete
		result = await c.batch_wait(batch_id)
		print(f"\nBatch status: {result['status']}")

		# Fetch individual results
		for exec_id in batch["execution_ids"]:
			r = await c.results(exec_id)
			print(f"\n  {r['workflow_id']}: {r['status']}")
			for node_idx, outputs in r["node_outputs"].items():
				if "result" in outputs:
					print(f"    result = {outputs['result']}")

		# Clean up
		for name, _ in workflows:
			await c.remove(name)
		print("\nCleaned up.")


if __name__ == "__main__":
	asyncio.run(main())
