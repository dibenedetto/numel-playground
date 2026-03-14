"""
Example 5: Save and Load Workflows
====================================
Demonstrate saving workflows to disk and loading them back.

Run:
	python examples/api/05_persistence.py
"""

import asyncio


from   client  import NumelClient


WORKFLOW = {
	"options": {"type": "workflow_options", "name": "persistent-wf"},
	"nodes": [
		{"type": "start_flow",     "extra": {"name": "Start"}},
		{"type": "transform_flow", "extra": {"name": "Compute"},
		"lang": "python",
		"script": 'output = {"saved": True, "message": "I survived a restart!"}'},
		{"type": "end_flow",       "extra": {"name": "End"}},
	],
	"edges": [
		{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		{"source": 1, "target": 2, "source_slot": "output",   "target_slot": "flow_in"},
	],
}


async def main():
	async with NumelClient() as c:
		# Add a workflow
		await c.add(WORKFLOW, "persistent-wf")
		print("Added: persistent-wf")

		# Save it to disk
		r = await c.save("persistent-wf")
		print(f"Saved: {r}")

		# Save all workflows
		r = await c.save_all()
		print(f"Save all: {r}")

		# List current workflows
		names = await c.list()
		print(f"Current workflows: {names}")

		# Remove it from memory
		await c.remove("persistent-wf")
		names = await c.list()
		print(f"After remove: {names}")

		# Load all from disk (restores saved workflows)
		r = await c.load_all()
		print(f"Load all: {r}")

		# Verify it's back
		names = await c.list()
		print(f"After load_all: {names}")

		# Run it to prove it works
		if "persistent-wf" in names:
			exec_id = await c.start("persistent-wf")
			results = await c.wait(exec_id)
			print(f"Execution result: {results['status']}")
			for idx, outputs in results["node_outputs"].items():
				if outputs:
					print(f"  node {idx}: {outputs}")

		# Clean up
		await c.remove("persistent-wf")
		print("Done.")


if __name__ == "__main__":
	asyncio.run(main())
