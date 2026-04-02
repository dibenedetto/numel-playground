"""
Example 5: Workflow Persistence Inside a Space
==============================================
Saving a current workflow writes it to the selected space. When you
leave that space and come back, the workflow is still there.

Run:
	python examples/api/05_persistence.py
"""

import asyncio
import uuid


from client import NumelClient


WORKFLOW = {
	"options": {"type": "workflow_options", "name": "persistent-wf"},
	"nodes": [
		{"type": "start_flow", "extra": {"name": "Start"}},
		{
			"type": "transform_flow",
			"extra": {"name": "Compute"},
			"lang": "python",
			"script": 'output = {"saved": True, "message": "I survived a space switch!"}',
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
		suffix = uuid.uuid4().hex[:6]

		primary = await c.create_space(title="Persistence Demo", slug=f"persist-demo-{suffix}")
		secondary = await c.create_space(title="Scratch Space", slug=f"scratch-demo-{suffix}")
		primary_id = primary["space"]["id"]
		secondary_id = secondary["space"]["id"]

		await c.select_space(primary_id)
		await c.replace_current_workflow(WORKFLOW, name="persistent-wf")
		print("Saved workflow in the primary space.")

		await c.select_space(secondary_id)
		empty = await c.get_workflow()
		print(f"Secondary space current workflow: {empty['name']}")

		await c.select_space(primary_id)
		restored = await c.get_workflow()
		print(f"Restored workflow: {restored['name']}")

		started = await c.start_workflow()
		results = await c.wait(started["execution_id"])
		print(f"Execution result: {results['status']}")
		print(f"Outputs: {results['node_outputs']}")

		await c.delete_space(primary_id)
		await c.delete_space(secondary_id)
		print("Done.")


if __name__ == "__main__":
	asyncio.run(main())
