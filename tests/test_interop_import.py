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


if __name__ == "__main__":
	unittest.main()
