"""
Example 4: Space Isolation
==========================
Create separate spaces, save a different current workflow in each, and
verify that switching spaces swaps the saved workflow.

Run:
	python examples/api/04_workspaces.py
"""

import asyncio
import copy
import uuid


from client import NumelClient


WF_TEMPLATE = {
	"options": {"type": "workflow_options", "name": "counter"},
	"nodes": [
		{"type": "start_flow", "extra": {"name": "Start"}},
		{"type": "transform_flow", "extra": {"name": "Count"}, "lang": "python", "script": ""},
		{"type": "end_flow", "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output", "target_slot": "flow_in"},
	],
}


def make_wf(label: str, value: int) -> dict:
	wf = copy.deepcopy(WF_TEMPLATE)
	wf["options"]["name"] = label
	wf["nodes"][1]["script"] = f'output = {{"label": "{label}", "value": {value}}}'
	return wf


async def main():
	async with NumelClient() as c:
		await c.ensure_auth()

		suffix = uuid.uuid4().hex[:6]
		alpha = await c.create_space(title="Project Alpha", slug=f"project-alpha-{suffix}")
		beta = await c.create_space(title="Project Beta", slug=f"project-beta-{suffix}")
		alpha_id = alpha["space"]["id"]
		beta_id = beta["space"]["id"]

		await c.select_space(alpha_id)
		await c.replace_current_workflow(make_wf("alpha-task", 42), name="alpha-task")
		alpha_saved = await c.get_workflow()
		print(f"Alpha current workflow: {alpha_saved['name']}")

		await c.select_space(beta_id)
		await c.replace_current_workflow(make_wf("beta-task", 99), name="beta-task")
		beta_saved = await c.get_workflow()
		print(f"Beta current workflow:  {beta_saved['name']}")

		await c.select_space(alpha_id)
		alpha_loaded = await c.get_workflow()
		print(f"Reloaded alpha workflow: {alpha_loaded['name']}")

		await c.select_space(beta_id)
		beta_loaded = await c.get_workflow()
		print(f"Reloaded beta workflow:  {beta_loaded['name']}")

		await c.select_space(alpha_id)
		alpha_exec = await c.start_workflow()
		await c.select_space(beta_id)
		beta_exec = await c.start_workflow()

		await c.select_space(alpha_id)
		alpha_results = await c.wait(alpha_exec["execution_id"])
		await c.select_space(beta_id)
		beta_results = await c.wait(beta_exec["execution_id"])

		print(f"\nAlpha result: {alpha_results['status']} — {alpha_results['node_outputs']}")
		print(f"Beta result:  {beta_results['status']} — {beta_results['node_outputs']}")

		await c.delete_space(alpha_id)
		await c.delete_space(beta_id)
		print("\nExample spaces deleted.")


if __name__ == "__main__":
	asyncio.run(main())
