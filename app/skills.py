# skills.py — Markdown-based Skill System
#
# Skills are instructional packages (SKILL.md) that teach the console agent
# how to use external tools, APIs, and system environments.
# Complementary to the typed Python toolkit system — skills are natural
# language instructions, not code.
#
# Directory layout:
#   app/skills/
#     my-skill/
#       SKILL.md          (required — YAML frontmatter + markdown body)
#       scripts/           (optional — helper scripts)
#       references/        (optional — supplementary docs)

import json
import os
import re
import time
import uuid

from   typing  import Any, Dict, List, Optional
from   fastapi import FastAPI
from   pydantic import BaseModel

from   utils import log_print


_APP_DIR    = os.path.dirname(os.path.abspath(__file__))
_SKILLS_DIR = os.path.join(_APP_DIR, "skills")


# =============================================================================
# DATA MODELS
# =============================================================================

class Skill(BaseModel):
	"""A loaded skill definition."""
	id:          str            = ""
	name:        str            = ""
	description: str            = ""
	version:     str            = "1.0.0"
	author:      str            = ""
	tags:        List[str]      = []
	requires:    Dict[str, Any] = {}   # {env: [], bins: [], toolkits: []}
	enabled:     bool           = True
	body:        str            = ""    # Markdown instruction body
	path:        str            = ""    # Directory path
	examples:    List[str]      = []    # Example prompts extracted from body


# =============================================================================
# SKILL PARSER
# =============================================================================

def parse_skill_md(text: str) -> dict:
	"""Parse a SKILL.md file: YAML frontmatter + markdown body.

	Returns dict with frontmatter fields + 'body' (markdown content).
	Uses simple parsing to avoid PyYAML dependency.
	"""
	text = text.strip()
	if not text.startswith("---"):
		return {"body": text}

	# Split frontmatter from body
	end = text.find("---", 3)
	if end == -1:
		return {"body": text}

	fm_text = text[3:end].strip()
	body    = text[end + 3:].strip()

	# Simple YAML-subset parser (key: value, key: [list])
	result: Dict[str, Any] = {"body": body}
	current_key  = None
	current_list = None

	for line in fm_text.split("\n"):
		stripped = line.strip()
		if not stripped or stripped.startswith("#"):
			continue

		# List item under a key
		if stripped.startswith("- ") and current_key and current_list is not None:
			current_list.append(stripped[2:].strip().strip('"').strip("'"))
			result[current_key] = current_list
			continue

		# Nested key (indented, part of a dict)
		indent = len(line) - len(line.lstrip())
		if indent >= 2 and current_key and isinstance(result.get(current_key), dict):
			m = re.match(r'^(\w[\w-]*)\s*:\s*(.*)', stripped)
			if m:
				sub_key = m.group(1)
				sub_val = m.group(2).strip()
				if sub_val.startswith("[") and sub_val.endswith("]"):
					result[current_key][sub_key] = [
						v.strip().strip('"').strip("'")
						for v in sub_val[1:-1].split(",") if v.strip()
					]
				elif sub_val:
					result[current_key][sub_key] = sub_val.strip('"').strip("'")
				else:
					result[current_key][sub_key] = []
					current_list = result[current_key][sub_key]
				continue

		# Top-level key: value
		m = re.match(r'^(\w[\w-]*)\s*:\s*(.*)', stripped)
		if m:
			key = m.group(1)
			val = m.group(2).strip()
			current_list = None

			if val.startswith("[") and val.endswith("]"):
				# Inline list
				result[key] = [
					v.strip().strip('"').strip("'")
					for v in val[1:-1].split(",") if v.strip()
				]
				current_key = key
			elif val == "" or val == "{}":
				# Could be start of nested dict or list
				if key in ("requires", "metadata"):
					result[key] = {}
				else:
					result[key] = []
					current_list = result[key]
				current_key = key
			elif val.lower() in ("true", "false"):
				result[key] = val.lower() == "true"
				current_key = key
			else:
				result[key] = val.strip('"').strip("'")
				current_key = key

	return result


def _extract_examples(body: str) -> List[str]:
	"""Extract example prompts from '## Example Prompts' section.

	Looks for bold-quoted text in list items: - **"prompt text"** or - **"prompt text"**
	"""
	examples = []
	in_examples = False
	for line in body.split("\n"):
		stripped = line.strip()
		# Detect section header
		if stripped.lower().startswith("## example"):
			in_examples = True
			continue
		if in_examples and stripped.startswith("## "):
			break  # Next section
		if not in_examples:
			continue
		# Extract bold-quoted prompt: - **"text"** — description
		m = re.match(r'^-\s+\*\*["\u201c](.+?)["\u201d]\*\*', stripped)
		if m:
			examples.append(m.group(1))
	return examples


# =============================================================================
# SKILL MANAGER
# =============================================================================

class SkillManager:
	"""Manages skills loaded from app/skills/ directory."""

	def __init__(self, skills_dir: str = _SKILLS_DIR):
		self._dir = skills_dir
		self._skills: Dict[str, Skill] = {}
		self._state_path = os.path.join(skills_dir, "_state.json")

	def initialize(self):
		"""Load all skills from disk."""
		os.makedirs(self._dir, exist_ok=True)
		self._load_state()
		self._scan()
		log_print(f"Skills: loaded {len(self._skills)} skills from {self._dir}")

	# ── Persistence ───────────────────────────────────────────

	def _load_state(self):
		"""Load enabled/disabled state."""
		self._enabled_state: Dict[str, bool] = {}
		if os.path.exists(self._state_path):
			try:
				with open(self._state_path) as f:
					self._enabled_state = json.load(f)
			except Exception:
				pass

	def _save_state(self):
		"""Persist enabled/disabled state."""
		state = {s.name: s.enabled for s in self._skills.values()}
		with open(self._state_path, "w") as f:
			json.dump(state, f, indent=2)

	def _scan(self):
		"""Scan skills directory for SKILL.md files."""
		if not os.path.isdir(self._dir):
			return
		for entry in sorted(os.listdir(self._dir)):
			if entry.startswith("_"):
				continue
			skill_dir = os.path.join(self._dir, entry)
			if not os.path.isdir(skill_dir):
				continue
			md_path = os.path.join(skill_dir, "SKILL.md")
			if not os.path.exists(md_path):
				continue
			try:
				self._load_skill(skill_dir, md_path)
			except Exception as e:
				log_print(f"Skills: failed to load {entry}: {e}")

	def _load_skill(self, skill_dir: str, md_path: str):
		"""Load a single skill from its SKILL.md file."""
		with open(md_path, encoding="utf-8") as f:
			text = f.read()
		parsed = parse_skill_md(text)

		name = parsed.get("name", os.path.basename(skill_dir))
		sid  = name  # Use name as ID for simplicity

		# Parse requires block
		requires = parsed.get("requires", {})
		if isinstance(requires, str):
			requires = {}

		body = parsed.get("body", "")
		skill = Skill(
			id          = sid,
			name        = name,
			description = parsed.get("description", ""),
			version     = parsed.get("version", "1.0.0"),
			author      = parsed.get("author", ""),
			tags        = parsed.get("tags", []),
			requires    = requires,
			enabled     = self._enabled_state.get(name, False),
			body        = body,
			path        = skill_dir,
			examples    = parsed.get("examples", []) or _extract_examples(body),
		)
		self._skills[sid] = skill

	# ── Public API ────────────────────────────────────────────

	def list(self, tag: Optional[str] = None, search: Optional[str] = None,
	         enabled_only: bool = False) -> List[dict]:
		"""List skills, optionally filtered."""
		items = list(self._skills.values())
		if tag:
			items = [s for s in items if tag in s.tags]
		if search:
			q = search.lower()
			items = [s for s in items
			         if q in s.name.lower() or q in s.description.lower()
			         or any(q in t.lower() for t in s.tags)]
		if enabled_only:
			items = [s for s in items if s.enabled]
		return [self._to_summary(s) for s in items]

	def get(self, name: str) -> Optional[dict]:
		"""Get full skill details including body."""
		skill = self._skills.get(name)
		if not skill:
			return None
		return skill.model_dump()

	def enable(self, name: str) -> bool:
		skill = self._skills.get(name)
		if not skill:
			return False
		skill.enabled = True
		self._save_state()
		return True

	def disable(self, name: str) -> bool:
		skill = self._skills.get(name)
		if not skill:
			return False
		skill.enabled = False
		self._save_state()
		return True

	def add(self, name: str, content: str) -> dict:
		"""Add a new skill from SKILL.md content string."""
		# Sanitize name
		safe_name = re.sub(r'[^a-z0-9_-]', '-', name.lower()).strip('-')
		if not safe_name:
			safe_name = f"skill-{uuid.uuid4().hex[:6]}"

		skill_dir = os.path.join(self._dir, safe_name)
		os.makedirs(skill_dir, exist_ok=True)

		md_path = os.path.join(skill_dir, "SKILL.md")
		with open(md_path, "w", encoding="utf-8") as f:
			f.write(content)

		self._load_skill(skill_dir, md_path)
		self._save_state()
		return self.get(safe_name) or {"name": safe_name, "ok": True}

	def remove(self, name: str) -> bool:
		"""Remove a skill by name."""
		skill = self._skills.pop(name, None)
		if not skill:
			return False
		# Remove directory
		import shutil
		if os.path.isdir(skill.path):
			shutil.rmtree(skill.path, ignore_errors=True)
		self._save_state()
		return True

	def get_active_instructions(self) -> List[str]:
		"""Return instruction bodies of all enabled skills, for injection into agent context."""
		instructions = []
		for skill in self._skills.values():
			if skill.enabled and skill.body.strip():
				header = f"[Skill: {skill.name}]"
				if skill.description:
					header += f" — {skill.description}"
				instructions.append(f"{header}\n{skill.body}")
		return instructions

	def get_active_requirements(self) -> Dict[str, List[str]]:
		"""Return aggregated requirements from all enabled skills."""
		reqs: Dict[str, List[str]] = {"env": [], "bins": [], "toolkits": []}
		for skill in self._skills.values():
			if not skill.enabled:
				continue
			for key in ("env", "bins", "toolkits"):
				vals = skill.requires.get(key, [])
				if isinstance(vals, list):
					for v in vals:
						if v not in reqs[key]:
							reqs[key].append(v)
		return reqs

	def check_requirements(self, name: str) -> Dict[str, Any]:
		"""Check if a skill's requirements are satisfied."""
		skill = self._skills.get(name)
		if not skill:
			return {"error": "skill not found"}
		result: Dict[str, Any] = {"ok": True, "missing": []}
		reqs = skill.requires

		# Check env vars
		for var in reqs.get("env", []):
			if not os.environ.get(var):
				result["missing"].append({"type": "env", "name": var})
				result["ok"] = False

		# Check bins
		import shutil
		for bin_name in reqs.get("bins", []):
			if not shutil.which(bin_name):
				result["missing"].append({"type": "bin", "name": bin_name})
				result["ok"] = False

		return result

	# ── Helpers ───────────────────────────────────────────────

	@staticmethod
	def _to_summary(skill: Skill) -> dict:
		return {
			"name":        skill.name,
			"description": skill.description,
			"version":     skill.version,
			"author":      skill.author,
			"tags":        skill.tags,
			"enabled":     skill.enabled,
			"requires":    skill.requires,
			"examples":    skill.examples,
		}


# =============================================================================
# API ENDPOINTS
# =============================================================================

def setup_skills_api(app: FastAPI, mgr: SkillManager):

	class ListReq(BaseModel):
		tag:          Optional[str] = None
		search:       Optional[str] = None
		enabled_only: bool          = False

	class NameReq(BaseModel):
		name: str

	class AddReq(BaseModel):
		name:    str
		content: str   # Full SKILL.md text

	@app.post("/skills/list")
	async def skills_list(req: ListReq):
		return mgr.list(tag=req.tag, search=req.search, enabled_only=req.enabled_only)

	@app.post("/skills/get")
	async def skills_get(req: NameReq):
		skill = mgr.get(req.name)
		if not skill:
			return {"error": f"Skill '{req.name}' not found"}
		return skill

	@app.post("/skills/enable")
	async def skills_enable(req: NameReq):
		ok = mgr.enable(req.name)
		return {"ok": ok, "name": req.name}

	@app.post("/skills/disable")
	async def skills_disable(req: NameReq):
		ok = mgr.disable(req.name)
		return {"ok": ok, "name": req.name}

	@app.post("/skills/add")
	async def skills_add(req: AddReq):
		return mgr.add(req.name, req.content)

	@app.post("/skills/remove")
	async def skills_remove(req: NameReq):
		ok = mgr.remove(req.name)
		return {"ok": ok}

	@app.post("/skills/check")
	async def skills_check(req: NameReq):
		return mgr.check_requirements(req.name)
