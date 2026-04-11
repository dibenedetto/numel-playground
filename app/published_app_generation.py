from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend_factory import generate_text


_DEFAULT_PAGE_PROMPT = (
	"Create a friendly published web app page for this workflow. "
	"Make it feel purposeful and easy to use, with copy and layout that match the workflow."
)

_SYSTEM_PROMPT = """You generate stored web app bundles for Numel published apps.

Return JSON only. Do not include markdown fences or extra commentary.

Required schema:
{
  "summary": "short explanation of the generated page",
  "files": [
    {"path": "index.html", "content": "<!doctype html>...<!-- NUMEL_APP_RUNTIME -->..."},
    {"path": "styles.css", "content": "CSS..."},
    {"path": "app.js", "content": "JavaScript..."}
  ]
}

Rules:
- Always return at least index.html and styles.css.
- index.html must be a complete HTML document.
- index.html must contain the exact placeholder <!-- NUMEL_APP_RUNTIME --> once.
- app.js is optional, but helpful for small UI polish.
- Do not inline large CSS or JS into index.html when they can live in separate files.
- Do not reference external network assets, CDNs, or frameworks.
- Use only relative asset references.
- Keep the generated page static and frontend-only. The execution runtime will be injected separately.
- The generated content must reflect the workflow purpose, inputs, and likely outputs.
"""


@dataclass
class PublishedAppGenerationConfig:
	model_source: str = "ollama"
	model_name: str = "qwen3.5:cloud"
	temperature: float = 0.3
	max_tokens: int = 4096
	page_prompt: str = _DEFAULT_PAGE_PROMPT

	def to_dict(self) -> Dict[str, Any]:
		return {
			"model_source": self.model_source,
			"model_name": self.model_name,
			"temperature": self.temperature,
			"max_tokens": self.max_tokens,
			"page_prompt": self.page_prompt,
		}


def detect_workflow_inputs(workflow: Dict[str, Any]) -> List[dict]:
	inputs: List[dict] = []
	for node in workflow.get("nodes", []) or []:
		if not isinstance(node, dict) or node.get("type") != "start_flow":
			continue
		for key, value in node.items():
			if key in ("type", "extra", "flow_in", "flow_out", "name"):
				continue
			inp_type = "text"
			if isinstance(value, bool):
				inp_type = "bool"
			elif isinstance(value, (int, float)):
				inp_type = "number"
			inputs.append(
				{
					"name": key,
					"label": key.replace("_", " ").title(),
					"type": inp_type,
					"default": value if value is not None else "",
					"required": True,
				}
			)
	return inputs


def summarize_workflow_for_published_app(workflow: Dict[str, Any], inputs: Optional[List[dict]] = None) -> Dict[str, Any]:
	nodes = workflow.get("nodes", []) or []
	edges = workflow.get("edges", []) or []
	options = workflow.get("options", {}) or {}
	node_types: Dict[str, int] = {}
	toolkits: List[str] = []
	skills: List[str] = []
	for node in nodes:
		if not isinstance(node, dict):
			continue
		node_type = str(node.get("type", "") or "").strip()
		if not node_type:
			continue
		node_types[node_type] = node_types.get(node_type, 0) + 1
		if node_type == "toolkit_config":
			name = str(node.get("name") or ((node.get("extra") or {}).get("name")) or "").strip()
			if name:
				toolkits.append(name)
		if node_type == "skill_config":
			name = str(node.get("name") or "").strip()
			if name:
				skills.append(name)
	return {
		"name": str(options.get("name", "") or ""),
		"description": str(options.get("description", "") or ""),
		"node_count": len(nodes),
		"edge_count": len(edges),
		"inputs": list(inputs or detect_workflow_inputs(workflow)),
		"node_types": node_types,
		"toolkits": sorted(set(toolkits)),
		"skills": sorted(set(skills)),
	}


def _extract_json_object(raw: str) -> Dict[str, Any]:
	text = str(raw or "").strip()
	if not text:
		raise ValueError("The page generator returned an empty response")
	if text.startswith("```"):
		text = re.sub(r"^```(?:json)?\s*", "", text)
		text = re.sub(r"\s*```$", "", text)
	try:
		return json.loads(text)
	except json.JSONDecodeError:
		match = re.search(r"\{[\s\S]*\}", text)
		if not match:
			raise ValueError("The page generator did not return valid JSON")
		try:
			return json.loads(match.group(0))
		except json.JSONDecodeError as exc:
			raise ValueError(f"The page generator returned invalid JSON: {exc}") from exc


def _normalize_file_entry(entry: Dict[str, Any]) -> Dict[str, str]:
	path = str(entry.get("path", "") or "").strip().replace("\\", "/")
	if not path or path.startswith("/") or ".." in path.split("/"):
		raise ValueError(f"Invalid generated file path: {path or '<empty>'}")
	content = entry.get("content")
	if content is None:
		raise ValueError(f"Generated file '{path}' is missing content")
	return {"path": path, "content": str(content)}


def normalize_generated_bundle(raw: str) -> Dict[str, Any]:
	payload = _extract_json_object(raw)
	files = payload.get("files")
	if not isinstance(files, list) or not files:
		raise ValueError("Generated bundle must include a non-empty 'files' array")
	normalized = [_normalize_file_entry(item) for item in files if isinstance(item, dict)]
	if not normalized:
		raise ValueError("Generated bundle did not contain any valid files")
	index_file = next((item for item in normalized if item["path"] == "index.html"), None)
	if index_file is None:
		raise ValueError("Generated bundle must include index.html")
	if "<!-- NUMEL_APP_RUNTIME -->" not in index_file["content"]:
		raise ValueError("index.html must contain the <!-- NUMEL_APP_RUNTIME --> placeholder")
	return {
		"summary": str(payload.get("summary", "") or "").strip(),
		"files": normalized,
	}


def _build_user_prompt(
	*,
	app_name: str,
	app_slug: str,
	description: str,
	workflow: Dict[str, Any],
	workflow_summary: Dict[str, Any],
	generation_config: PublishedAppGenerationConfig,
) -> str:
	page_prompt = (generation_config.page_prompt or _DEFAULT_PAGE_PROMPT).strip()
	return (
		f"App title: {app_name}\n"
		f"App slug: {app_slug}\n"
		f"App description: {description or '(none)'}\n"
		f"Page design brief: {page_prompt}\n\n"
		"Workflow summary:\n"
		f"{json.dumps(workflow_summary, indent=2)}\n\n"
		"Full workflow JSON:\n"
		f"{json.dumps(workflow, indent=2)}\n"
	)


async def generate_published_app_bundle(
	*,
	app_name: str,
	app_slug: str,
	description: str,
	workflow: Dict[str, Any],
	inputs: Optional[List[dict]] = None,
	generation_config: Optional[PublishedAppGenerationConfig] = None,
	backend_name: Optional[str] = None,
) -> Dict[str, Any]:
	config = generation_config or PublishedAppGenerationConfig()
	workflow_summary = summarize_workflow_for_published_app(workflow, inputs=inputs)
	raw = await generate_text(
		system_message=_SYSTEM_PROMPT,
		user_message=_build_user_prompt(
			app_name=app_name,
			app_slug=app_slug,
			description=description,
			workflow=workflow,
			workflow_summary=workflow_summary,
			generation_config=config,
		),
		model_source=config.model_source,
		model_name=config.model_name,
		temperature=config.temperature,
		max_tokens=config.max_tokens,
		backend_name=backend_name,
	)
	bundle = normalize_generated_bundle(raw)
	bundle["workflow_summary"] = workflow_summary
	return bundle
