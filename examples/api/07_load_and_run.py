"""
Example 7: Load Workflow JSON from Disk and Run It
==================================================
Load one of the tutorial JSON files from docs/, save it as the current
workflow in a new space, and execute it.

Run:
	python examples/api/07_load_and_run.py
"""

import asyncio
import os
import uuid


from client import NumelClient, load_workflow


DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs")


async def main():
	wf_path = os.path.join(DOCS_DIR, "tutorial-02-transform.json")
	workflow = load_workflow(wf_path)
	wf_name = workflow.get("options", {}).get("name", "loaded-wf")
	print(f"Loaded: {wf_name} from {wf_path}")

	async with NumelClient() as c:
		await c.ensure_auth()
		suffix = uuid.uuid4().hex[:6]
		space = await c.create_space(title="Load and Run Demo", slug=f"load-run-{suffix}")
		await c.select_space(space["space"]["id"])

		saved = await c.replace_current_workflow(workflow, name=wf_name)
		print(f"Saved into current space: {saved['name']} (status={saved['status']})")

		started = await c.start_workflow()
		print(f"Started: {started['execution_id']}")

		results = await c.wait(started["execution_id"])
		print(f"\nStatus: {results['status']}")
		print(f"Duration: {results.get('start_time', '?')} -> {results.get('end_time', '?')}")

		for node_idx, outputs in sorted(results["node_outputs"].items(), key=lambda x: x[0]):
			if outputs:
				print(f"\nNode {node_idx}:")
				for key, value in outputs.items():
					print(f"  {key} = {value}")

		await c.delete_space(space["space"]["id"])
		print("\nDone.")


if __name__ == "__main__":
	asyncio.run(main())
