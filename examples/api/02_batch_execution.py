"""
Example 2: Parallel Executions Across Spaces
===========================================
Start several workflows in different spaces. Each space keeps its own
current workflow, but the executions run in parallel.

Run:
	python examples/api/02_batch_execution.py
"""

import asyncio
import uuid


from client import NumelClient


def make_transform_workflow(name: str, script: str) -> dict:
	return {
		"options": {"type": "workflow_options", "name": name},
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


async def main():
	async with NumelClient() as c:
		await c.ensure_auth()

		run_specs = [
			("squares", 'output = {"result": [x**2 for x in range(10)]}'),
			("cubes", 'output = {"result": [x**3 for x in range(10)]}'),
			("factorials", 'import math; output = {"result": [math.factorial(x) for x in range(10)]}'),
		]

		started_runs = []
		for name, script in run_specs:
			suffix = uuid.uuid4().hex[:6]
			space = await c.create_space(title=f"Batch Demo: {name}", slug=f"batch-{name}-{suffix}")
			space_id = space["space"]["id"]
			await c.select_space(space_id)
			await c.replace_current_workflow(make_transform_workflow(name, script), name=name)
			started = await c.start_workflow()
			started_runs.append({"name": name, "space_id": space_id, "execution_id": started["execution_id"]})
			print(f"Started {name} in {space_id}: {started['execution_id']}")

		print("\nWaiting for parallel executions...")
		for item in started_runs:
			await c.select_space(item["space_id"])
			results = await c.wait(item["execution_id"])
			print(f"\n{item['name']}: {results['status']}")
			for node_idx, outputs in results["node_outputs"].items():
				if "result" in outputs:
					print(f"  node {node_idx}: {outputs['result']}")

		for item in started_runs:
			await c.delete_space(item["space_id"])
		print("\nCleaned up example spaces.")


if __name__ == "__main__":
	asyncio.run(main())
