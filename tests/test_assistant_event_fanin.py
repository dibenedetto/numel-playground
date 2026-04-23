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


from assistant_network_workflow import build_assistant_network_workflow, parse_assistant_network_workflow_import
from assistant_proactive_workflow import build_assistant_proactive_workflow


class AssistantEventFanInTests(unittest.TestCase):
	def test_network_workflow_export_keeps_multi_source_task_on_single_listener(self):
		payload = build_assistant_network_workflow(
			deployments=[
				{
					"id": "deploy_support",
					"name": "Support Front Door",
					"profile": "support",
					"enabled": True,
					"channel_ids": ["channel_ops"],
					"proactive_tasks": [
						{
							"id": "task_digest",
							"name": "Daily Digest",
							"prompt": "Summarize new support events.",
							"trigger_kind": "webhook",
							"trigger_mode": "all",
							"trigger_sources": [
								{
									"kind": "webhook",
									"source_id": "source_digest_webhook",
									"trigger": {"endpoint": "/hook/digest", "methods": "POST"},
									"interval_sec": 0,
								},
								{
									"kind": "channel",
									"source_id": "source_digest_channel",
									"trigger": {"channel_id": "channel_ops", "sender_filter": "^ops_"},
									"interval_sec": 0,
								},
							],
							"channel_id": "channel_ops",
							"recipient_id": "ops-room",
							"enabled": True,
							"send_response": True,
						}
					],
				}
			],
			channels=[
				{"id": "channel_ops", "name": "Ops Channel", "channel_type": "webhook", "status": "running", "enabled": True},
			],
		)
		workflow = payload["workflow"]
		nodes = workflow["nodes"]
		edges = workflow["edges"]

		listener_index = next(index for index, node in enumerate(nodes) if node.get("type") == "event_listener_flow")
		listener = nodes[listener_index]
		self.assertEqual(listener["mode"], "all")

		task_node = next(node for node in nodes if node.get("type") == "assistant_proactive_runtime_config")
		self.assertEqual(task_node["trigger_mode"], "all")
		self.assertEqual(len(task_node["trigger_sources"]), 2)

		registered_edges = [
			edge for edge in edges
			if edge.get("target") == listener_index and str(edge.get("target_slot") or "").startswith("sources.")
		]
		self.assertEqual(len(registered_edges), 2)

		source_node_types = sorted(
			node.get("type")
			for node in nodes
			if node.get("type") in {"webhook_source_flow", "channel_receive_flow"}
		)
		self.assertEqual(source_node_types, ["channel_receive_flow", "webhook_source_flow"])

	def test_network_workflow_import_preserves_multi_source_listener_mode(self):
		workflow = {
			"type": "workflow",
			"options": {"name": "Assistant Deployment Network"},
			"nodes": [
				{
					"type": "assistant_deployment_runtime_config",
					"deployment_id": "deploy_support",
					"name": "Support Front Door",
				},
				{
					"type": "assistant_proactive_runtime_config",
					"task_id": "task_digest",
					"name": "Daily Digest",
					"prompt": "Summarize new support events.",
					"trigger_kind": "webhook",
					"trigger": {"endpoint": "/hook/digest", "methods": "POST"},
					"trigger_mode": "all",
					"channel_id": "channel_ops",
					"recipient_id": "ops-room",
					"enabled": True,
					"send_response": True,
				},
				{
					"type": "event_listener_flow",
					"mode": "all",
				},
				{
					"type": "webhook_source_flow",
					"source_id": "source_digest_webhook",
					"endpoint": "/hook/digest",
					"methods": "POST",
				},
				{
					"type": "channel_receive_flow",
					"source_id": "source_digest_channel",
					"channel_id": "channel_ops",
					"sender_filter": "^ops_",
				},
			],
			"edges": [
				{"source": 1, "target": 0, "source_slot": "config", "target_slot": "proactive_tasks.daily_digest"},
				{"source": 3, "target": 2, "source_slot": "registered_id", "target_slot": "sources.webhook"},
				{"source": 3, "target": 2, "source_slot": "flow_out", "target_slot": "flow_in"},
				{"source": 4, "target": 2, "source_slot": "registered_id", "target_slot": "sources.channel"},
				{"source": 4, "target": 2, "source_slot": "flow_out", "target_slot": "flow_in"},
				{"source": 2, "target": 1, "source_slot": "event", "target_slot": "trigger_event"},
				{"source": 2, "target": 1, "source_slot": "source_id", "target_slot": "trigger_source_id"},
			],
		}

		parsed = parse_assistant_network_workflow_import(workflow)
		self.assertFalse(any("using the first one" in warning for warning in parsed["warnings"]))
		deployment = parsed["deployments"][0]
		task = deployment["proactive_tasks"][0]
		self.assertEqual(task["trigger_mode"], "all")
		self.assertEqual(task["trigger_kind"], "webhook")
		self.assertEqual(task["trigger"]["endpoint"], "/hook/digest")
		self.assertEqual(len(task["trigger_sources"]), 2)
		self.assertEqual(
			[source["kind"] for source in task["trigger_sources"]],
			["webhook", "channel"],
		)

	def test_proactive_runtime_builder_supports_multi_source_listener(self):
		payload = build_assistant_proactive_workflow(
			deployment_name="Support Front Door",
			deployment_profile="support",
			deployment_description="Handles support traffic.",
			deployment_instructions="Summarize important events.",
			task_name="Daily Digest",
			task_prompt="Summarize new support events.",
			task_interval_sec=900,
			model_source="ollama",
			model_name="mistral:latest",
			toolkit_names=[],
			skill_names=[],
			trigger_sources=[
				{
					"kind": "webhook",
					"trigger_config": {"source_id": "source_digest_webhook", "endpoint": "/hook/digest", "methods": "POST"},
					"interval_sec": 0,
				},
				{
					"kind": "channel",
					"trigger_config": {"source_id": "source_digest_channel", "channel_id": "channel_ops", "sender_filter": "^ops_"},
					"interval_sec": 0,
				},
			],
			trigger_mode="all",
		)
		workflow = payload["workflow"]
		nodes = workflow["nodes"]
		edges = workflow["edges"]

		listener_index = next(index for index, node in enumerate(nodes) if node.get("type") == "event_listener_flow")
		self.assertEqual(nodes[listener_index]["mode"], "all")
		self.assertEqual(payload["source_ids"], ["source_digest_webhook", "source_digest_channel"])

		registered_edges = [
			edge for edge in edges
			if edge.get("target") == listener_index and str(edge.get("target_slot") or "").startswith("sources.")
		]
		self.assertEqual(len(registered_edges), 2)


if __name__ == "__main__":
	unittest.main()
