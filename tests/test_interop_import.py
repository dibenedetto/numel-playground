from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))
if str(PROJECT_ROOT) not in sys.path:
	sys.path.insert(1, str(PROJECT_ROOT))


from interop_import import detect_workflow_source, import_workflow_document


def _native_numel_workflow() -> dict:
	return {
		"type": "workflow",
		"options": {"type": "workflow_options", "name": "Native Import"},
		"nodes": [
			{"type": "start_flow", "extra": {"name": "Start"}},
			{"type": "end_flow", "extra": {"name": "End"}},
		],
		"edges": [
			{"source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in"},
		],
	}


def _n8n_set_workflow() -> dict:
	return {
		"name": "n8n Set Demo",
		"nodes": [
			{
				"id": "1",
				"name": "Manual Trigger",
				"type": "n8n-nodes-base.manualTrigger",
				"position": [80, 180],
				"parameters": {},
			},
			{
				"id": "2",
				"name": "Set Fields",
				"type": "n8n-nodes-base.set",
				"position": [360, 180],
				"parameters": {
					"keepOnlySet": True,
					"values": {
						"string": [{"name": "message", "value": "Hello from n8n"}],
						"number": [{"name": "count", "value": 2}],
					},
				},
			},
		],
		"connections": {
			"Manual Trigger": {
				"main": [[{"node": "Set Fields", "type": "main", "index": 0}]],
			},
		},
	}


def _n8n_http_workflow() -> dict:
	return {
		"name": "n8n HTTP Demo",
		"nodes": [
			{
				"id": "1",
				"name": "Manual Trigger",
				"type": "n8n-nodes-base.manualTrigger",
				"position": [80, 180],
				"parameters": {},
			},
			{
				"id": "2",
				"name": "Set Payload",
				"type": "n8n-nodes-base.set",
				"position": [340, 180],
				"parameters": {
					"keepOnlySet": True,
					"values": {
						"string": [{"name": "message", "value": "payload"}],
					},
				},
			},
			{
				"id": "3",
				"name": "Send Request",
				"type": "n8n-nodes-base.httpRequest",
				"position": [640, 180],
				"parameters": {
					"method": "POST",
					"url": "https://example.com/hook",
					"headersUi": {
						"parameter": [
							{"name": "X-Test", "value": "yes"},
						],
					},
				},
			},
		],
		"connections": {
			"Manual Trigger": {
				"main": [[{"node": "Set Payload", "type": "main", "index": 0}]],
			},
			"Set Payload": {
				"main": [[{"node": "Send Request", "type": "main", "index": 0}]],
			},
		},
	}


def _n8n_if_workflow() -> dict:
	return {
		"name": "n8n If Demo",
		"nodes": [
			{
				"id": "1",
				"name": "Manual Trigger",
				"type": "n8n-nodes-base.manualTrigger",
				"position": [80, 200],
				"parameters": {},
			},
			{
				"id": "2",
				"name": "Set Status",
				"type": "n8n-nodes-base.set",
				"position": [320, 200],
				"parameters": {
					"keepOnlySet": True,
					"values": {
						"string": [{"name": "status", "value": "ok"}],
					},
				},
			},
			{
				"id": "3",
				"name": "Status Check",
				"type": "n8n-nodes-base.if",
				"position": [600, 200],
				"parameters": {
					"conditions": {
						"conditions": [
							{
								"leftValue": "={{$json.status}}",
								"rightValue": "ok",
								"operator": {"operation": "equal"},
							},
						],
						"combinator": "and",
					},
				},
			},
			{
				"id": "4",
				"name": "True Branch",
				"type": "n8n-nodes-base.set",
				"position": [900, 100],
				"parameters": {
					"keepOnlySet": False,
					"values": {
						"string": [{"name": "decision", "value": "approved"}],
					},
				},
			},
			{
				"id": "5",
				"name": "False Branch",
				"type": "n8n-nodes-base.set",
				"position": [900, 300],
				"parameters": {
					"keepOnlySet": False,
					"values": {
						"string": [{"name": "decision", "value": "rejected"}],
					},
				},
			},
		],
		"connections": {
			"Manual Trigger": {
				"main": [[{"node": "Set Status", "type": "main", "index": 0}]],
			},
			"Set Status": {
				"main": [[{"node": "Status Check", "type": "main", "index": 0}]],
			},
			"Status Check": {
				"main": [
					[{"node": "True Branch", "type": "main", "index": 0}],
					[{"node": "False Branch", "type": "main", "index": 0}],
				],
			},
		},
	}


def _n8n_merge_workflow() -> dict:
	return {
		"name": "n8n Merge Demo",
		"nodes": [
			{
				"id": "1",
				"name": "Manual Trigger",
				"type": "n8n-nodes-base.manualTrigger",
				"position": [80, 200],
				"parameters": {},
			},
			{
				"id": "2",
				"name": "Left Payload",
				"type": "n8n-nodes-base.set",
				"position": [320, 120],
				"parameters": {
					"keepOnlySet": True,
					"values": {
						"string": [{"name": "side", "value": "left"}],
					},
				},
			},
			{
				"id": "3",
				"name": "Right Payload",
				"type": "n8n-nodes-base.set",
				"position": [320, 300],
				"parameters": {
					"keepOnlySet": True,
					"values": {
						"string": [{"name": "side", "value": "right"}],
					},
				},
			},
			{
				"id": "4",
				"name": "Join Results",
				"type": "n8n-nodes-base.merge",
				"position": [620, 200],
				"parameters": {"mode": "append"},
			},
		],
		"connections": {
			"Manual Trigger": {
				"main": [
					[{"node": "Left Payload", "type": "main", "index": 0}],
					[{"node": "Right Payload", "type": "main", "index": 0}],
				],
			},
			"Left Payload": {
				"main": [[{"node": "Join Results", "type": "main", "index": 0}]],
			},
			"Right Payload": {
				"main": [[{"node": "Join Results", "type": "main", "index": 1}]],
			},
		},
	}


def _n8n_switch_workflow() -> dict:
	return {
		"name": "n8n Switch Demo",
		"nodes": [
			{
				"id": "1",
				"name": "Manual Trigger",
				"type": "n8n-nodes-base.manualTrigger",
				"position": [80, 200],
				"parameters": {},
			},
			{
				"id": "2",
				"name": "Set Stage",
				"type": "n8n-nodes-base.set",
				"position": [320, 200],
				"parameters": {
					"keepOnlySet": True,
					"values": {
						"string": [{"name": "stage", "value": "review"}],
					},
				},
			},
			{
				"id": "3",
				"name": "Stage Switch",
				"type": "n8n-nodes-base.switch",
				"position": [620, 200],
				"parameters": {
					"rules": {
						"values": [
							{
								"leftValue": "={{$json.stage}}",
								"rightValue": "review",
								"operator": {"operation": "equal"},
								"label": "review",
							},
							{
								"leftValue": "={{$json.stage}}",
								"rightValue": "approved",
								"operator": {"operation": "equal"},
								"label": "approved",
							},
						],
					},
				},
			},
			{
				"id": "4",
				"name": "Review Branch",
				"type": "n8n-nodes-base.set",
				"position": [920, 120],
				"parameters": {
					"keepOnlySet": False,
					"values": {
						"string": [{"name": "decision", "value": "review-path"}],
					},
				},
			},
			{
				"id": "5",
				"name": "Approved Branch",
				"type": "n8n-nodes-base.set",
				"position": [920, 220],
				"parameters": {
					"keepOnlySet": False,
					"values": {
						"string": [{"name": "decision", "value": "approved-path"}],
					},
				},
			},
			{
				"id": "6",
				"name": "Default Branch",
				"type": "n8n-nodes-base.set",
				"position": [920, 320],
				"parameters": {
					"keepOnlySet": False,
					"values": {
						"string": [{"name": "decision", "value": "default-path"}],
					},
				},
			},
		],
		"connections": {
			"Manual Trigger": {
				"main": [[{"node": "Set Stage", "type": "main", "index": 0}]],
			},
			"Set Stage": {
				"main": [[{"node": "Stage Switch", "type": "main", "index": 0}]],
			},
			"Stage Switch": {
				"main": [
					[{"node": "Review Branch", "type": "main", "index": 0}],
					[{"node": "Approved Branch", "type": "main", "index": 0}],
					[{"node": "Default Branch", "type": "main", "index": 0}],
				],
			},
		},
	}


def _n8n_wait_workflow() -> dict:
	return {
		"name": "n8n Wait Demo",
		"nodes": [
			{
				"id": "1",
				"name": "Manual Trigger",
				"type": "n8n-nodes-base.manualTrigger",
				"position": [80, 180],
				"parameters": {},
			},
			{
				"id": "2",
				"name": "Pause Briefly",
				"type": "n8n-nodes-base.wait",
				"position": [360, 180],
				"parameters": {
					"resume": "timeInterval",
					"amount": 2,
					"unit": "seconds",
				},
			},
		],
		"connections": {
			"Manual Trigger": {
				"main": [[{"node": "Pause Briefly", "type": "main", "index": 0}]],
			},
		},
	}


def _n8n_code_workflow() -> dict:
	return {
		"name": "n8n Code Demo",
		"nodes": [
			{
				"id": "1",
				"name": "Manual Trigger",
				"type": "n8n-nodes-base.manualTrigger",
				"position": [80, 180],
				"parameters": {},
			},
			{
				"id": "2",
				"name": "Set Count",
				"type": "n8n-nodes-base.set",
				"position": [320, 180],
				"parameters": {
					"keepOnlySet": True,
					"values": {
						"number": [{"name": "count", "value": 2}],
					},
				},
			},
			{
				"id": "3",
				"name": "Increase Count",
				"type": "n8n-nodes-base.code",
				"position": [620, 180],
				"parameters": {
					"language": "javascript",
					"jsCode": "const base = $json.count || 0;\nreturn {\"count\": base + 1, \"status\": \"ready\"};",
				},
			},
		],
		"connections": {
			"Manual Trigger": {
				"main": [[{"node": "Set Count", "type": "main", "index": 0}]],
			},
			"Set Count": {
				"main": [[{"node": "Increase Count", "type": "main", "index": 0}]],
			},
		},
	}


class InteropImportTests(unittest.TestCase):
	def test_detects_native_numel_workflow(self) -> None:
		self.assertEqual(detect_workflow_source(_native_numel_workflow()), "numel")

	def test_imports_n8n_set_workflow_into_runnable_numel_graph(self) -> None:
		imported = import_workflow_document(_n8n_set_workflow(), file_name="set-demo.json")

		self.assertEqual(imported["source_format"], "n8n")
		self.assertEqual(imported["name"], "n8n Set Demo")
		self.assertEqual(imported["warnings"], [])
		node_types = [node["type"] for node in imported["workflow"]["nodes"]]
		self.assertIn("start_flow", node_types)
		self.assertIn("transform_flow", node_types)
		self.assertIn("preview_flow", node_types)
		self.assertIn("end_flow", node_types)

	def test_imports_n8n_http_request_with_shared_http_toolkit(self) -> None:
		imported = import_workflow_document(_n8n_http_workflow(), file_name="http-demo.json")
		node_types = [node["type"] for node in imported["workflow"]["nodes"]]
		self.assertIn("toolkit_config", node_types)
		self.assertIn("tool_flow", node_types)
		self.assertGreaterEqual(node_types.count("transform_flow"), 2)

		toolkit_node = next(node for node in imported["workflow"]["nodes"] if node["type"] == "toolkit_config")
		self.assertEqual(toolkit_node["name"], "toolkits.http_toolkit")
		http_node = next(node for node in imported["workflow"]["nodes"] if node["type"] == "tool_flow")
		self.assertEqual(http_node["method"], "request")
		self.assertTrue(any("Request Args" in (node.get("extra", {}).get("name") or "") for node in imported["workflow"]["nodes"] if node["type"] == "transform_flow"))

	def test_imports_n8n_if_node_into_native_branching_nodes(self) -> None:
		imported = import_workflow_document(_n8n_if_workflow(), file_name="if-demo.json")
		node_types = [node["type"] for node in imported["workflow"]["nodes"]]
		self.assertIn("route_flow", node_types)
		self.assertGreaterEqual(node_types.count("transform_flow"), 3)
		route_node = next(node for node in imported["workflow"]["nodes"] if node["type"] == "route_flow")
		self.assertEqual(route_node["output"], {"true": None, "false": None})
		edge_slots = {(edge["source_slot"], edge["target_slot"]) for edge in imported["workflow"]["edges"]}
		self.assertIn(("output.true", "input"), edge_slots)
		self.assertIn(("output.false", "input"), edge_slots)

	def test_imports_n8n_merge_node_into_native_merge_flow(self) -> None:
		imported = import_workflow_document(_n8n_merge_workflow(), file_name="merge-demo.json")
		node_types = [node["type"] for node in imported["workflow"]["nodes"]]
		self.assertIn("merge_flow", node_types)
		merge_node = next(node for node in imported["workflow"]["nodes"] if node["type"] == "merge_flow")
		self.assertEqual(merge_node["strategy"], "all")
		merge_edges = [edge for edge in imported["workflow"]["edges"] if edge["target"] == imported["workflow"]["nodes"].index(merge_node)]
		self.assertTrue(any(str(edge["target_slot"]).startswith("input.left_payload") for edge in merge_edges))
		self.assertTrue(any(str(edge["target_slot"]).startswith("input.right_payload") for edge in merge_edges))

	def test_imports_n8n_switch_node_into_native_route_flow(self) -> None:
		imported = import_workflow_document(_n8n_switch_workflow(), file_name="switch-demo.json")
		node_types = [node["type"] for node in imported["workflow"]["nodes"]]
		self.assertIn("route_flow", node_types)
		route_node = next(node for node in imported["workflow"]["nodes"] if node["type"] == "route_flow")
		self.assertEqual(route_node["output"], {"review": None, "approved": None})
		edge_slots = {(edge["source_slot"], edge["target_slot"]) for edge in imported["workflow"]["edges"]}
		self.assertIn(("output.review", "input"), edge_slots)
		self.assertIn(("output.approved", "input"), edge_slots)
		self.assertIn(("default", "input"), edge_slots)

	def test_imports_n8n_wait_node_into_delay_flow(self) -> None:
		imported = import_workflow_document(_n8n_wait_workflow(), file_name="wait-demo.json")
		node_types = [node["type"] for node in imported["workflow"]["nodes"]]
		self.assertIn("delay_flow", node_types)
		delay_node = next(node for node in imported["workflow"]["nodes"] if node["type"] == "delay_flow")
		self.assertEqual(delay_node["duration_ms"], 2000)

	def test_imports_simple_n8n_code_node_into_transform_flow(self) -> None:
		imported = import_workflow_document(_n8n_code_workflow(), file_name="code-demo.json")
		code_node = next(
			node
			for node in imported["workflow"]["nodes"]
			if node["type"] == "transform_flow" and (node.get("extra", {}).get("name") or "") == "Increase Count"
		)
		self.assertIn("output =", code_node["script"])
		self.assertIn("input.get('count')", code_node["script"])
		self.assertTrue(any("best-effort" in warning.lower() for warning in imported["warnings"]))


if __name__ == "__main__":
	unittest.main()
