from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = PROJECT_ROOT / "app"
if str(APP_DIR) not in sys.path:
	sys.path.insert(0, str(APP_DIR))

from published_app_generation import (  # noqa: E402
	PublishedAppGenerationConfig,
	_build_user_prompt,
	summarize_workflow_for_published_app,
)


class PublishedAppGenerationPromptTests(unittest.TestCase):
	def test_generation_config_allows_backend_defaults(self) -> None:
		config = PublishedAppGenerationConfig(
			model_source="ollama",
			model_name="qwen3.5:cloud",
			temperature=None,
			max_tokens=None,
		)

		self.assertIsNone(config.temperature)
		self.assertIsNone(config.max_tokens)
		self.assertEqual(config.to_dict()["temperature"], None)
		self.assertEqual(config.to_dict()["max_tokens"], None)

	def test_workflow_summary_captures_interactive_and_output_hints(self) -> None:
		workflow = {
			"type": "workflow",
			"id": "wf_mesh_preview",
			"options": {
				"name": "Mesh Preview",
				"description": "Simplify and preview a mesh",
			},
			"nodes": [
				{"type": "start_flow", "mesh_path": "input.obj"},
				{"type": "toolkit_config", "name": "contrib.toolkits.mesh_toolkit"},
				{"type": "user_input_flow", "query": "Choose the target face count"},
				{"type": "preview_flow"},
				{"type": "end_flow"},
			],
			"edges": [],
		}

		summary = summarize_workflow_for_published_app(workflow)
		self.assertEqual(summary["id"], "wf_mesh_preview")
		self.assertEqual(summary["toolkits"], ["contrib.toolkits.mesh_toolkit"])
		self.assertIn("Choose the target face count", summary["interactive_prompts"])
		self.assertIn("preview_flow", summary["output_hints"])
		self.assertIn("end_flow", summary["output_hints"])

	def test_user_prompt_includes_time_detail_and_consistency_guidance(self) -> None:
		workflow = {
			"type": "workflow",
			"id": "wf_publish_prompt",
			"options": {"name": "Publish Prompt Workflow"},
			"nodes": [{"type": "start_flow"}],
			"edges": [],
		}
		summary = summarize_workflow_for_published_app(workflow)
		prompt = _build_user_prompt(
			app_name="Prompted App",
			app_slug="prompted-app",
			description="A generated page for a workflow",
			workflow=workflow,
			workflow_summary=summary,
			generation_config=PublishedAppGenerationConfig(),
		)

		self.assertIn("Current date and time:", prompt)
		self.assertIn("Current timestamp (ISO):", prompt)
		self.assertRegex(prompt, r"Current year: \d{4}")
		self.assertIn("Details button or disclosure", prompt)
		self.assertIn("Keep the visual style coherent", prompt)
		self.assertIn("Full workflow JSON:", prompt)
		self.assertIn('"id": "wf_publish_prompt"', prompt)
		self.assertTrue(re.search(r'"id": "wf_publish_prompt"', prompt))


if __name__ == "__main__":
	unittest.main()
