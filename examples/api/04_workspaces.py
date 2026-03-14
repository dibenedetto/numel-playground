"""
Example 4: Workspace Isolation
================================
Create separate workspaces, run workflows in each,
and verify they don't interfere with each other.

Run:
	python examples/api/04_workspaces.py
"""

import asyncio


from   client  import NumelClient


WF_TEMPLATE = {
	"options": {"type": "workflow_options", "name": "counter"},
	"nodes": [
		{"type": "start_flow",     "extra": {"name": "Start"}},
		{"type": "transform_flow", "extra": {"name": "Count"},
		"lang": "python", "script": ""},
		{"type": "end_flow",       "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output",   "target_slot": "flow_in"},
	],
}


def make_wf(label: str, value: int) -> dict:
	"""Create a workflow that outputs a labeled value."""
	import copy
	wf = copy.deepcopy(WF_TEMPLATE)
	wf["options"]["name"] = label
	wf["nodes"][1]["script"] = f'output = {{"label": "{label}", "value": {value}}}'
	return wf


async def main():
	async with NumelClient() as c:
		# List initial workspaces (should have "default")
		ws_list = await c.workspace_list()
		print("Initial workspaces:")
		for ws in ws_list.get("workspaces", []):
			print(f"  {ws['workspace_id']}: {ws['name']}")

		# Create two project workspaces
		# (workspace/create uses query params, so we use _post directly)
		r1 = await c._post("/workspace/create?name=project-alpha&description=Alpha%20project")
		r2 = await c._post("/workspace/create?name=project-beta&description=Beta%20project")
		ws1_id = r1["workspace_id"]
		ws2_id = r2["workspace_id"]
		print(f"\nCreated: {ws1_id} (project-alpha)")
		print(f"Created: {ws2_id} (project-beta)")

		# Add different workflows to each workspace
		await c.ws_add(ws1_id, make_wf("alpha-task", 42), "alpha-task")
		await c.ws_add(ws2_id, make_wf("beta-task", 99),  "beta-task")
		print("\nAdded alpha-task to project-alpha")
		print("Added beta-task to project-beta")

		# Verify isolation: each workspace only sees its own workflows
		r1_list = await c._post(f"/workspace/{ws1_id}/list")
		r2_list = await c._post(f"/workspace/{ws2_id}/list")
		print(f"\nproject-alpha workflows: {r1_list['names']}")
		print(f"project-beta workflows:  {r2_list['names']}")

		# Run workflows in each workspace
		exec1 = await c.ws_start(ws1_id, "alpha-task")
		exec2 = await c.ws_start(ws2_id, "beta-task")
		print(f"\nStarted alpha: {exec1}")
		print(f"Started beta:  {exec2}")

		# Wait for both
		await asyncio.sleep(2)

		r1 = await c.ws_results(ws1_id, exec1)
		r2 = await c.ws_results(ws2_id, exec2)
		print(f"\nAlpha result: {r1['status']} — {r1['node_outputs']}")
		print(f"Beta result:  {r2['status']} — {r2['node_outputs']}")

		# Clean up workspaces
		await c.workspace_delete(ws1_id)
		await c.workspace_delete(ws2_id)
		print("\nWorkspaces deleted.")

		# Final workspace list
		ws_final = await c.workspace_list()
		print(f"Remaining workspaces: {[w['name'] for w in ws_final.get('workspaces', [])]}")


if __name__ == "__main__":
	asyncio.run(main())
