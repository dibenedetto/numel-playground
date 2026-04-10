from __future__ import annotations

import sys
import unittest
from pathlib import Path
import shutil
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from workflow_validation import validate_workflow_payload


def _planner_like_toolkit_workflow(root: str, *, method: str = "list_directory") -> dict:
	return {
		"type": "workflow",
		"options": {"name": "Planner Toolkit Workflow"},
		"nodes": [
			{"type": "start_flow", "extra": {"pos": [0, 0], "name": "Start"}},
			{
				"type": "toolkit_config",
				"args": {"root": root},
				"extra": {"pos": [0, 120], "name": "toolkits.file_toolkit"},
			},
			{
				"type": "tool_flow",
				"method": method,
				"args": {"path": "."},
				"extra": {"pos": [260, 0], "name": "List"},
			},
			{"type": "end_flow", "extra": {"pos": [520, 0], "name": "End"}},
		],
		"edges": [
			{"source": 0, "target": 2, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": 1, "target": 2, "source_slot": "config", "target_slot": "config"},
			{"source": 2, "target": 3, "source_slot": "flow_out", "target_slot": "flow_in"},
		],
	}


def _planner_like_slot_workflow() -> dict:
	return {
		"type": "workflow",
		"options": {"name": "Planner Slot Workflow"},
		"nodes": [
			{"type": "start_flow", "extra": {"pos": [0, 0], "name": "Start"}},
			{"type": "native_string", "raw": "mesh.obj", "extra": {"pos": [0, 120], "name": "Path"}},
			{
				"type": "transform_flow",
				"script": "output = {'path': input}",
				"extra": {"pos": [260, 0], "name": "Wrap"},
			},
			{"type": "end_flow", "extra": {"pos": [520, 0], "name": "End"}},
		],
		"edges": [
			{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": 0, "target": 2, "source_slot": "flow_out", "target_slot": "flow_in"},
			{"source": 1, "target": 2, "source_slot": "flow_out", "target_slot": "input"},
			{"source": 2, "target": 3, "source_slot": "output", "target_slot": "flow_in"},
		],
	}


class WorkflowValidationTests(unittest.TestCase):
	def _scratch_root(self) -> str:
		root = PROJECT_ROOT / "storage" / "_test_runs" / f"wf_validate_{uuid.uuid4().hex[:8]}"
		root.mkdir(parents=True, exist_ok=True)
		self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
		return str(root)

	def test_repairs_toolkit_name_from_display_label(self):
		payload = _planner_like_toolkit_workflow(self._scratch_root())
		result = validate_workflow_payload(payload, apply_repairs=True)
		self.assertTrue(result["valid"], result)
		self.assertTrue(result["repaired"])
		self.assertIn("recovered toolkit_config.name from extra.name", " | ".join(result["repairs"]))
		self.assertEqual(result["workflow"]["nodes"][1]["name"], "toolkits.file_toolkit")

	def test_rejects_unknown_toolkit_method(self):
		payload = _planner_like_toolkit_workflow(self._scratch_root(), method="not_a_real_method")
		result = validate_workflow_payload(payload, apply_repairs=True)
		self.assertFalse(result["valid"])
		self.assertTrue(any("unknown toolkit method" in err.lower() for err in result["errors"]))

	def test_repairs_invalid_flow_edges_for_non_flow_nodes(self):
		payload = _planner_like_slot_workflow()
		result = validate_workflow_payload(payload, apply_repairs=True)
		self.assertTrue(result["valid"], result)
		self.assertTrue(result["repaired"])
		repair_text = " | ".join(result["repairs"])
		self.assertIn("removed invalid flow edge into non-flow node native_string.flow_in", repair_text)
		self.assertIn("rewired source slot native_string.flow_out -> native_string.value", repair_text)
		self.assertEqual(len(result["workflow"]["edges"]), 3)
		self.assertEqual(result["workflow"]["edges"][1]["source_slot"], "value")


if __name__ == "__main__":
	unittest.main()
