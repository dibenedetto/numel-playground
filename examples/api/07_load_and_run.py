"""
Example 7: Load Existing Workflow JSON and Run
================================================
Load one of the tutorial/example JSON files from docs/
and execute it programmatically.

Run:
	python examples/api/07_load_and_run.py
"""

import asyncio
import os


from   client  import NumelClient, load_workflow


# Path to docs/ relative to this file
DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "docs")


async def main():
	# Load the tutorial-02-transform workflow from docs/
	wf_path = os.path.join(DOCS_DIR, "tutorial-02-transform.json")
	workflow = load_workflow(wf_path)
	wf_name = workflow.get("options", {}).get("name", "loaded-wf")
	print(f"Loaded: {wf_name} from {wf_path}")

	async with NumelClient() as c:
		# Upload
		r = await c.add(workflow, wf_name)
		print(f"Added: {r['name']} (status={r['status']})")

		# Execute
		exec_id = await c.start(wf_name)
		print(f"Started: {exec_id}")

		# Wait and get results
		results = await c.wait(exec_id)
		print(f"\nStatus: {results['status']}")
		print(f"Duration: {results.get('start_time', '?')} → {results.get('end_time', '?')}")

		# Print each node's outputs
		for node_idx, outputs in sorted(results["node_outputs"].items(), key=lambda x: x[0]):
			if outputs:
				print(f"\n  Node {node_idx}:")
				for key, value in outputs.items():
					print(f"    {key} = {value}")

		# Clean up
		await c.remove(wf_name)
		print("\nDone.")


if __name__ == "__main__":
	asyncio.run(main())
