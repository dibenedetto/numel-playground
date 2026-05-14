# api

import base64
from   contextlib import asynccontextmanager
import importlib
import io
import json
import os
import re

import numpy as np
from   PIL       import Image
from   pathlib   import Path
from   fastapi   import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, File, Form
from   fastapi.responses import FileResponse
from   inspect   import iscoroutinefunction, signature
from   pydantic  import BaseModel
from   typing    import Any, Dict, List, Optional


from   event_bus import EventType, EventBus
from   backend_factory import build_backend, get_text_generation_models, get_text_generation_sources, list_supported_backends, normalize_backend_name
from   interop_import import InteropImportError, import_workflow_document
from   platform_client import PlatformRequestError
from   runtime_settings import get_runtime_settings
from   schema    import DEFAULT_BACKEND_NAME, Workflow, WorkflowExecutionOptions
from   utils     import get_now_str, get_timestamp_str, log_print, serialize_result
from   workflow_validation import validate_workflow_payload
from   events    import (
	get_event_registry, init_event_registry, shutdown_event_registry,
	TimerSourceConfig, FSWatchSourceConfig,
	WebhookSourceConfig, BrowserSourceConfig, BrowserSource
)

# Tutorial extension (see docs/tutorial-extension.md)
from   tutorial_api import setup_tutorial_api


# ── Helpers ──────────────────────────────────────────────────────────────────

def _json_safe(obj):
	"""Make an object JSON-serializable, converting ndarrays to lists."""
	if isinstance(obj, np.ndarray):
		return obj.tolist()
	if isinstance(obj, dict):
		return {k: _json_safe(v) for k, v in obj.items()}
	if isinstance(obj, (list, tuple)):
		return [_json_safe(v) for v in obj]
	return obj


def _decode_frame_to_ndarray(frame_bytes: bytes) -> np.ndarray:
	"""Decode JPEG/WebP/PNG bytes into an RGB uint8 ndarray (h, w, 3)."""
	return np.array(Image.open(io.BytesIO(frame_bytes)).convert("RGB"))


class CurrentWorkflowSaveRequest(BaseModel):
	workflow : Workflow
	message  : Optional[str] = None


class CurrentWorkflowStartRequest(BaseModel):
	initial_data : WorkflowExecutionOptions = None


class WorkflowValidateRequest(BaseModel):
	workflow      : Dict[str, Any]
	apply_repairs : bool = True


class WorkflowInteropImportRequest(BaseModel):
	document      : Dict[str, Any]
	source_format : Optional[str] = None
	file_name     : Optional[str] = None


class UserInputRequest(BaseModel):
	node_id    : str
	input_data : Any


class ChatResponseRequest(BaseModel):
	node_id  : str
	response : str


class ToolCallRequest(BaseModel):
	node_index : int
	args       : Optional[Dict[str, Any]] = None


class ContentRemoveRequest(BaseModel):
	ids : List[str]


class TemplateSaveRequest(BaseModel):
	template : dict


class TemplateRenameRequest(BaseModel):
	name : str


class SpaceCreateRequest(BaseModel):
	title       : str
	slug        : Optional[str] = None
	description : Optional[str] = None
	visibility  : str = "private"


class SpaceSelectRequest(BaseModel):
	space_id : str


class SpaceUpdateRequest(BaseModel):
	space_id     : Optional[str] = None
	title        : Optional[str] = None
	slug         : Optional[str] = None
	description  : Optional[str] = None
	visibility   : Optional[str] = None


class SpaceResolveRequest(BaseModel):
	namespace : str
	slug      : str


class PublicNamespaceRequest(BaseModel):
	namespace : str


class PublicCreatorPageRequest(BaseModel):
	creator : str
	limit   : int = 12


class PublicRepoPageRequest(BaseModel):
	namespace : str
	slug      : str
	ref       : Optional[str] = None
	limit     : int = 12


class PublicRepoAssetReadRequest(BaseModel):
	namespace : str
	slug      : str
	path      : str
	ref       : Optional[str] = None


class PublicRepoCompareRequest(BaseModel):
	namespace : str
	slug      : str
	left      : str
	right     : Optional[str] = None
	path      : str = ""
	limit     : int = 200


class SpaceForkRequest(BaseModel):
	space_id : Optional[str] = None
	title    : Optional[str] = None
	slug     : Optional[str] = None


class WorkflowHistoryRequest(BaseModel):
	limit : int = 20


class WorkflowRestoreRequest(BaseModel):
	commit_id : str
	note      : Optional[str] = None


class WorkflowTemplatePublishRequest(BaseModel):
	title       : str
	description : str = ""
	category    : str = "templates"
	tags        : List[str] = []
	source_kind : str = "canvas"
	ref         : Optional[str] = None
	commit_id   : Optional[str] = None
	path        : Optional[str] = None
	workflow    : Optional[Dict[str, Any]] = None


class SpaceRepoHistoryRequest(BaseModel):
	limit : int = 20


class SpaceRepoAssetsRequest(BaseModel):
	prefix : str = ""


class SpaceRepoAssetReadRequest(BaseModel):
	path : str


class SpaceRepoAssetOpenRequest(BaseModel):
	path : str


class SpaceRepoAssetWriteRequest(BaseModel):
	path        : str
	text        : str = ""
	message     : str = ""
	title       : Optional[str] = None
	description : str = ""
	kind        : str = "data"
	executable  : bool = False


class SpaceRepoCompareRequest(BaseModel):
	left  : str
	right : Optional[str] = None
	path  : str = ""
	limit : int = 200


class SpaceRepoRestoreRequest(BaseModel):
	source : str
	note   : Optional[str] = None


class SpaceRefCreateRequest(BaseModel):
	name     : str
	kind     : str = "branch"
	from_ref : Optional[str] = None


class SpaceRefDeleteRequest(BaseModel):
	name : str


class SpaceRefSetRequest(BaseModel):
	name : str


class GenerateWorkflowRequest(BaseModel):
	prompt      : str
	# Agent subgraph config (each maps to a schema config type)
	backend     : Optional[dict] = None   # BackendConfig fields {engine}
	model       : Optional[dict] = None   # ModelConfig fields {source, name, version}
	options     : Optional[dict] = None   # AgentOptionsConfig fields {name, description, instructions, prompt_override, markdown}
	memory      : Optional[dict] = None   # MemoryManagerConfig fields {query, update, managed, prompt}
	session     : Optional[dict] = None   # SessionManagerConfig fields {query, update, history_size, prompt}
	tools       : Optional[List[dict]] = None  # List of ToolConfig fields [{name, args}]
	toolkits    : Optional[List[dict]] = None  # List of ToolkitConfig fields [{name, args}]
	knowledge   : Optional[dict] = None   # KnowledgeManagerConfig fields {query, description, max_results, urls, content_db, index_db}
	# LLM params (separate from model config)
	temperature : float = 0.3
	max_tokens  : int = 4096
	history     : Optional[List[dict]] = None


def setup_api(app: FastAPI, event_bus: EventBus, schema_code: str, workspace_mgr, skill_mgr=None, assistant_deployment_mgr=None):

	# Default workspace provides manager/engine for non-workspace-prefixed endpoints
	_default_ws = workspace_mgr.get_default_workspace()
	manager     = _default_ws.manager
	engine      = _default_ws.engine

	def _ws(req: Request):
		"""Return the per-user workspace set by the workspace middleware,
		falling back to the default workspace."""
		return getattr(req.state, 'workspace', _default_ws)

	_project_root = Path(__file__).resolve().parent.parent
	_runtime_settings = get_runtime_settings()
	_platform_backend_name = str(getattr(app.state, "platform_backend", "local") or "local").strip().lower()
	_platform_backend_config = getattr(app.state, "platform_backend_config", {}) or {}
	_platform_section = _platform_backend_config.get(_platform_backend_name, {}) if isinstance(_platform_backend_config, dict) else {}
	_admin_platform_roots: List[Path] = []
	for section_name, field_name in (("git", "repos_root"), ("artifacts", "root_path")):
		section = _platform_section.get(section_name, {})
		if not isinstance(section, dict):
			continue
		raw_path = str(section.get(field_name, "") or "").strip()
		if not raw_path:
			continue
		try:
			_admin_platform_roots.append(Path(raw_path).resolve())
		except Exception:
			continue

	def _current_user(req: Request):
		return getattr(req.state, "user", None)

	def _role_value(user) -> str:
		if not user:
			return ""
		role = getattr(user, "role", "")
		return str(getattr(role, "value", role)).lower()

	def _is_admin(user) -> bool:
		return _role_value(user) == "admin"

	def _require_auth(req: Request):
		user = _current_user(req)
		if not user:
			raise HTTPException(status_code=401, detail="Not authenticated")
		return user

	def _require_admin(req: Request):
		user = _require_auth(req)
		if not _is_admin(user):
			raise HTTPException(status_code=403, detail="Admin access required")
		return user

	def _path_within_root(path: Path, root: Path) -> bool:
		try:
			path.relative_to(root)
			return True
		except ValueError:
			return False

	def _allowed_file_roots(req: Request) -> List[Path]:
		roots: List[Path] = []
		ws = _ws(req)
		user = _current_user(req)
		ws_storage = getattr(ws.manager, "_storage_dir", None)
		if ws_storage:
			roots.append(Path(ws_storage).resolve())

		# Admins may inspect shared workspace and storage directories directly.
		if user and _is_admin(user):
			shared_storage = getattr(workspace_mgr, "_storage_root", None)
			if shared_storage:
				roots.append(Path(shared_storage).resolve())
			roots.extend(_admin_platform_roots)
			roots.append(_runtime_settings.data_root.resolve())
			for extra_dir in ("tmp", "models", "docs"):
				path = (_project_root / extra_dir)
				if path.exists():
					roots.append(path.resolve())
		else:
			for extra_dir in ("tmp", "docs"):
				path = (_project_root / extra_dir)
				if path.exists():
					roots.append(path.resolve())

		# Preserve order while removing duplicates.
		unique: List[Path] = []
		seen = set()
		for root in roots:
			key = str(root).lower()
			if key in seen:
				continue
			seen.add(key)
			unique.append(root)
		return unique

	def _resolve_file_for_request(req: Request, file_path: str) -> Path:
		raw_path = (file_path or "").strip()
		if not raw_path:
			raise HTTPException(status_code=400, detail="file_path is required")

		requested = Path(raw_path)
		roots = _allowed_file_roots(req)
		if not roots:
			raise HTTPException(status_code=500, detail="No allowed file roots are configured")

		if requested.is_absolute():
			target = requested.resolve()
			if not any(_path_within_root(target, root) for root in roots):
				raise HTTPException(status_code=403, detail="File path is outside allowed roots")
			if not target.exists() or not target.is_file():
				raise HTTPException(status_code=404, detail=f"File not found: {file_path}")
			return target

		if ".." in requested.parts:
			raise HTTPException(status_code=403, detail="Path traversal is not allowed")

		search_bases = [*roots, _project_root]
		seen = set()
		for base in search_bases:
			try:
				candidate = (base / requested).resolve()
			except Exception:
				continue
			if not any(_path_within_root(candidate, root) for root in roots):
				continue
			key = str(candidate).lower()
			if key in seen:
				continue
			seen.add(key)
			if candidate.exists() and candidate.is_file():
				return candidate

		raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

	_CURRENT_WORKFLOW_PATH = "workflow.json"

	def _platform(req: Request):
		platform = getattr(req.state, "auth", None) or getattr(req.app.state, "platform", None)
		if platform is None:
			raise HTTPException(status_code=500, detail="Platform client is not available")
		return platform

	async def _refresh_user(req: Request):
		user = _require_auth(req)
		try:
			fresh = await _platform(req).get_user(user.id)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		if fresh is not None:
			req.state.user = fresh
			return fresh
		return user

	def _space_slug(value: str) -> str:
		slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", (value or "").strip().lower()).strip("-._")
		return slug or "space"

	async def _list_owned_spaces(req: Request, user_id: str) -> List[Dict[str, Any]]:
		try:
			data = await _platform(req).post_json(
				"/platform/spaces/list-owned",
				{"user_id": user_id, "owner_user_id": user_id},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return data.get("spaces", []) or []

	async def _list_accessible_spaces(req: Request, user_id: str) -> List[Dict[str, Any]]:
		try:
			data = await _platform(req).post_json(
				"/platform/spaces/list-accessible",
				{"user_id": user_id},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return data.get("spaces", []) or []

	async def _decorate_space_records(
		req: Request,
		spaces: List[Dict[str, Any]],
		*,
		viewer_user_id: str,
		active_ref_overrides: Optional[Dict[str, str]] = None,
		active_asset_overrides: Optional[Dict[str, str]] = None,
	) -> List[Dict[str, Any]]:
		platform = _platform(req)
		owner_cache: Dict[str, str] = {}
		ref_overrides = dict(active_ref_overrides or {})
		asset_overrides = dict(active_asset_overrides or {})
		decorated: List[Dict[str, Any]] = []
		for raw_space in spaces or []:
			space = dict(raw_space or {})
			owner_user_id = str(space.get("owner_user_id", "") or "").strip()
			owner_username = owner_cache.get(owner_user_id, "")
			if owner_user_id and not owner_username:
				try:
					owner = await platform.get_user(owner_user_id)
				except PlatformRequestError:
					owner = None
				owner_username = str(getattr(owner, "username", "") or "").strip()
				if owner_user_id:
					owner_cache[owner_user_id] = owner_username
			slug = str(space.get("slug", "") or "").strip()
			visibility = str(space.get("visibility", "") or "private").strip().lower() or "private"
			is_owned = owner_user_id == viewer_user_id
			view = "mine" if is_owned else ("public" if visibility == "public" else "shared")
			namespace = owner_username or owner_user_id or "unknown"
			space_id = str(space.get("id", "") or "").strip()
			default_ref = str(space.get("default_ref", "") or "main").strip() or "main"
			active_ref = str(ref_overrides.get(space_id, "") or default_ref).strip() or default_ref
			active_asset_path = str(asset_overrides.get(space_id, "") or _CURRENT_WORKFLOW_PATH).strip() or _CURRENT_WORKFLOW_PATH
			space["owner_username"] = owner_username or None
			space["namespace"] = namespace
			space["namespace_slug"] = f"{namespace}/{slug}" if slug else namespace
			space["is_owned"] = is_owned
			space["is_public"] = visibility == "public"
			space["space_view"] = view
			space["default_ref"] = default_ref
			space["active_ref"] = active_ref
			space["active_ref_source"] = "viewer" if space_id in ref_overrides else "default"
			space["active_asset_path"] = active_asset_path
			space["active_asset_name"] = Path(active_asset_path).name if active_asset_path else _CURRENT_WORKFLOW_PATH
			space["active_asset_source"] = "viewer" if space_id in asset_overrides else "default"
			decorated.append(space)
		return decorated

	def _sort_space_records(spaces: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
		def _numeric_timestamp(item: Dict[str, Any], key: str) -> float:
			try:
				return float(item.get(key, 0.0) or 0.0)
			except Exception:
				return 0.0

		return sorted(
			spaces or [],
			key=lambda item: (
				0 if bool(item.get("is_owned")) else 1,
				-_numeric_timestamp(item, "updated_at"),
				-_numeric_timestamp(item, "created_at"),
				str(item.get("title", "") or item.get("slug", "") or item.get("id", "")),
			),
		)

	async def _set_current_space_id(req: Request, user_id: str, space_id: str):
		user = await _platform(req).get_user(user_id)
		metadata = dict(getattr(user, "metadata", {}) or {})
		metadata["current_space_id"] = space_id
		try:
			await _platform(req).post_json(
				f"/platform/users/{user_id}/update",
				{"metadata": metadata},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		if getattr(req.state, "user", None) and req.state.user.id == user_id:
			req.state.user.metadata = metadata
		return metadata

	def _space_ref_overrides(user) -> Dict[str, str]:
		metadata = dict(getattr(user, "metadata", {}) or {})
		raw = metadata.get("space_active_refs", {})
		if not isinstance(raw, dict):
			return {}
		result: Dict[str, str] = {}
		for raw_space_id, raw_ref in raw.items():
			space_id = str(raw_space_id or "").strip()
			ref_name = str(raw_ref or "").strip()
			if space_id and ref_name:
				result[space_id] = ref_name
		return result

	async def _set_current_space_ref(req: Request, user_id: str, space_id: str, ref_name: str):
		user = await _platform(req).get_user(user_id)
		metadata = dict(getattr(user, "metadata", {}) or {})
		ref_overrides = dict(metadata.get("space_active_refs", {}) or {})
		if ref_name:
			ref_overrides[str(space_id)] = str(ref_name)
		else:
			ref_overrides.pop(str(space_id), None)
		metadata["space_active_refs"] = ref_overrides
		try:
			await _platform(req).post_json(
				f"/platform/users/{user_id}/update",
				{"metadata": metadata},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		if getattr(req.state, "user", None) and req.state.user.id == user_id:
			req.state.user.metadata = metadata
		return metadata

	def _space_asset_overrides(user) -> Dict[str, str]:
		metadata = dict(getattr(user, "metadata", {}) or {})
		raw = metadata.get("space_active_assets", {})
		if not isinstance(raw, dict):
			return {}
		result: Dict[str, str] = {}
		for raw_space_id, raw_path in raw.items():
			space_id = str(raw_space_id or "").strip()
			asset_path = str(raw_path or "").strip()
			if space_id and asset_path:
				result[space_id] = asset_path
		return result

	async def _set_current_space_asset_path(req: Request, user_id: str, space_id: str, asset_path: str):
		user = await _platform(req).get_user(user_id)
		metadata = dict(getattr(user, "metadata", {}) or {})
		asset_overrides = dict(metadata.get("space_active_assets", {}) or {})
		if asset_path:
			asset_overrides[str(space_id)] = str(asset_path)
		else:
			asset_overrides.pop(str(space_id), None)
		metadata["space_active_assets"] = asset_overrides
		try:
			await _platform(req).post_json(
				f"/platform/users/{user_id}/update",
				{"metadata": metadata},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		if getattr(req.state, "user", None) and req.state.user.id == user_id:
			req.state.user.metadata = metadata
		return metadata

	async def _create_default_space(req: Request, user) -> Dict[str, Any]:
		payload = {
			"user_id": user.id,
			"owner_user_id": user.id,
			"slug": "home",
			"title": f"{user.username} Space",
			"description": f"Home space for {user.username}",
			"visibility": "private",
		}
		try:
			data = await _platform(req).post_json("/platform/spaces/create", payload)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		space = data.get("space") or {}
		await _set_current_space_id(req, user.id, str(space.get("id", "") or ""))
		return space

	async def _ensure_current_space(req: Request):
		user = await _refresh_user(req)
		owned_spaces = await _list_owned_spaces(req, user.id)
		if not owned_spaces:
			space = await _create_default_space(req, user)
			current_decorated = await _decorate_space_records(
				req,
				[space],
				viewer_user_id=user.id,
				active_ref_overrides=_space_ref_overrides(user),
				active_asset_overrides=_space_asset_overrides(user),
			)
			return user, (current_decorated[0] if current_decorated else space)

		accessible_spaces = await _list_accessible_spaces(req, user.id)
		current_space_id = str((getattr(user, "metadata", {}) or {}).get("current_space_id", "") or "").strip()
		current = next((item for item in accessible_spaces if item.get("id") == current_space_id), None)
		if current is None:
			owned_spaces = sorted(owned_spaces, key=lambda item: float(item.get("created_at", 0.0) or 0.0))
			current = owned_spaces[0]
			await _set_current_space_id(req, user.id, str(current.get("id", "") or ""))
		current_decorated = await _decorate_space_records(
			req,
			[current],
			viewer_user_id=user.id,
			active_ref_overrides=_space_ref_overrides(user),
			active_asset_overrides=_space_asset_overrides(user),
		)
		return user, (current_decorated[0] if current_decorated else current)

	def _space_active_ref(space: Optional[Dict[str, Any]]) -> str:
		if not isinstance(space, dict):
			return "main"
		ref_name = str(space.get("active_ref", "") or space.get("default_ref", "") or "main").strip()
		return ref_name or "main"

	def _space_default_ref(space: Optional[Dict[str, Any]]) -> str:
		if not isinstance(space, dict):
			return "main"
		ref_name = str(space.get("default_ref", "") or "main").strip()
		return ref_name or "main"

	def _space_active_asset_path(space: Optional[Dict[str, Any]]) -> str:
		if not isinstance(space, dict):
			return _CURRENT_WORKFLOW_PATH
		asset_path = str(space.get("active_asset_path", "") or _CURRENT_WORKFLOW_PATH).strip()
		return asset_path or _CURRENT_WORKFLOW_PATH

	def _is_workflow_asset_record(asset: Optional[Dict[str, Any]]) -> bool:
		return str((asset or {}).get("kind", "") or "").strip().lower() == "workflow"

	def _pick_workbench_asset_path(
		assets: List[Dict[str, Any]],
		preferred_path: str = _CURRENT_WORKFLOW_PATH,
	) -> Optional[str]:
		workflow_assets = [asset for asset in (assets or []) if _is_workflow_asset_record(asset)]
		if not workflow_assets:
			return None
		preferred = str(preferred_path or "").strip()
		if preferred and any(str(item.get("path", "") or "").strip() == preferred for item in workflow_assets):
			return preferred
		if any(str(item.get("path", "") or "").strip() == _CURRENT_WORKFLOW_PATH for item in workflow_assets):
			return _CURRENT_WORKFLOW_PATH
		workflow_assets.sort(key=lambda item: str(item.get("path", "") or ""))
		return str(workflow_assets[0].get("path", "") or "").strip() or None

	def _workflow_name_from_doc(doc: Optional[Dict[str, Any]]) -> Optional[str]:
		if not isinstance(doc, dict):
			return None
		options = doc.get("options")
		if not isinstance(options, dict):
			return None
		name = str(options.get("name", "") or "").strip()
		return name or None

	def _gallery_manager(req: Request):
		manager = getattr(req.app.state, "gallery_manager", None)
		if manager is None:
			raise HTTPException(status_code=500, detail="Gallery manager is not available")
		return manager

	def _default_publish_description(space: Dict[str, Any], source_kind: str, selector: str) -> str:
		space_title = str(space.get("title", "") or space.get("slug", "") or "current repo").strip()
		if source_kind == "ref":
			return f'Reusable workflow template published from ref "{selector}" in the "{space_title}" repo.'
		if source_kind == "commit":
			return f'Reusable workflow template published from snapshot "{selector[:8]}" in the "{space_title}" repo.'
		return f'Reusable workflow template published from the current workbench in the "{space_title}" repo.'

	def _workflow_doc_from_model(workflow: Workflow, *, keep_runtime_state: bool = False) -> Dict[str, Any]:
		doc = workflow.model_dump()
		doc["type"] = "workflow"
		if not keep_runtime_state:
			for node in doc.get("nodes", []) or []:
				if isinstance(node, dict) and node.get("type") == "agent_config":
					node.pop("port", None)
		return doc

	def _workflow_model_from_doc(doc: Dict[str, Any]) -> Workflow:
		payload = dict(doc or {})
		payload.pop("type", None)
		if hasattr(Workflow, "model_validate"):
			return Workflow.model_validate(payload)
		if hasattr(Workflow, "parse_obj"):
			return Workflow.parse_obj(payload)
		return Workflow(**payload)

	async def _read_workflow_asset_doc(
		req: Request,
		user_id: str,
		space_id: str,
		path: str,
		ref: str = "main",
	) -> Optional[Dict[str, Any]]:
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space_id}/assets/read",
				{
					"user_id": user_id,
					"path": path,
					"ref": ref,
				},
			)
		except PlatformRequestError as exc:
			if exc.status_code == 404:
				return None
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		text = data.get("text")
		if text is None:
			content = base64.b64decode(str(data.get("content_base64", "") or "").encode("ascii"))
			text = content.decode("utf-8")
		try:
			return json.loads(text)
		except json.JSONDecodeError as exc:
			raise HTTPException(status_code=500, detail=f"Saved workflow asset '{path}' is invalid JSON: {exc}")

	def _workflow_cache_key(space_id: str, asset_path: str, ref: str) -> str:
		return f"{space_id}::{ref or 'main'}::{asset_path or 'workflow.json'}"

	async def _cache_current_workflow(req: Request, workflow: Workflow, *, cache_key: Optional[str] = None) -> str:
		ws = _ws(req)
		# Runtime-allocated agent ports may have leaked in from persisted JSON.
		# Clear them so impl() re-allocates against the live uvicorn instance
		# and no stale value reaches the client before servers are bound.
		for node in getattr(workflow, "nodes", None) or []:
			if getattr(node, "type", None) == "agent_config" and hasattr(node, "port"):
				node.port = None
		name = (
			workflow.options.name
			if getattr(workflow, "options", None) is not None and workflow.options.name
			else "workflow"
		)
		await ws.manager.replace_cached(workflow, name)
		if cache_key is not None:
			setattr(ws.manager, "_numel_cached_workflow_key", cache_key)
		return name

	async def _clear_cached_workflow(req: Request) -> None:
		ws = _ws(req)
		await ws.manager.remove()
		setattr(ws.manager, "_numel_cached_workflow_key", None)

	def _request_session_id(req: Request) -> Optional[str]:
		value = str(req.headers.get("x-session-id", "") or "").strip()
		return value or None

	async def _emit_workflow_changed(name: str = "", source_session_id: Optional[str] = None) -> None:
		data = {"name": name}
		if source_session_id:
			data["source_session_id"] = source_session_id
		await event_bus.emit(
			event_type = EventType.WORKSPACE_CHANGED,
			data       = data,
		)

	def _execution_public_id(record: Dict[str, Any]) -> str:
		metadata = record.get("metadata", {}) or {}
		engine_execution_id = str(metadata.get("engine_execution_id", "") or "").strip()
		return engine_execution_id or str(record.get("execution_id", "") or "")

	def _workflow_graph_payload(
		doc: Dict[str, Any],
		*,
		asset_path: str = "",
		ref: str = "",
		workflow_name: str = "",
	) -> Optional[Dict[str, Any]]:
		if not isinstance(doc, dict):
			return None
		raw_nodes = doc.get("nodes")
		raw_edges = doc.get("edges")
		if not isinstance(raw_nodes, list) or not raw_nodes:
			return None
		nodes: List[Dict[str, Any]] = []
		for index, node in enumerate(raw_nodes):
			if not isinstance(node, dict):
				continue
			extra = node.get("extra") if isinstance(node.get("extra"), dict) else {}
			raw_pos = extra.get("pos") if isinstance(extra.get("pos"), list) else None
			x = 180 * (index % 4)
			y = 140 * (index // 4)
			if raw_pos and len(raw_pos) >= 2:
				try:
					x = int(float(raw_pos[0]))
					y = int(float(raw_pos[1]))
				except Exception:
					pass
			label = (
				str(extra.get("name") or "").strip()
				or str(node.get("name") or "").strip()
				or str(node.get("type") or "").strip()
				or f"Node {index}"
			)
			nodes.append(
				{
					"id": str(index),
					"node_index": index,
					"workflow_node_id": str(node.get("id") or "").strip() or None,
					"type": str(node.get("type") or "").strip() or "node",
					"label": label,
					"pos": [x, y],
				}
			)
		edges: List[Dict[str, Any]] = []
		if isinstance(raw_edges, list):
			for edge in raw_edges:
				if not isinstance(edge, dict):
					continue
				source = edge.get("source")
				target = edge.get("target")
				if source is None or target is None:
					continue
				edges.append(
					{
						"source": str(source),
						"target": str(target),
						"source_slot": str(edge.get("source_slot") or "").strip() or None,
						"target_slot": str(edge.get("target_slot") or "").strip() or None,
					}
				)
		return {
			"type": "workflow_runtime_graph",
			"name": workflow_name or _workflow_name_from_doc(doc) or Path(asset_path or "workflow.json").stem or "Workflow",
			"asset_path": str(asset_path or "").strip() or "workflow.json",
			"ref": str(ref or "").strip() or "main",
			"nodes": nodes,
			"edges": edges,
		}

	def _execution_graph_payload(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
		metadata = record.get("metadata", {}) or {}
		graph = metadata.get("workflow_graph")
		return graph if isinstance(graph, dict) else None

	async def _find_execution_record(req: Request, execution_id: str) -> Optional[Dict[str, Any]]:
		user = _require_auth(req)
		try:
			data = await _platform(req).post_json(
				"/platform/executions/list",
				{"user_id": user.id, "limit": 200},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		for record in data.get("executions", []) or []:
			if str(record.get("execution_id", "") or "") == execution_id:
				return record
			if _execution_public_id(record) == execution_id:
				return record
		return None

	async def _resolve_engine_execution_id(req: Request, execution_id: str) -> str:
		record = await _find_execution_record(req, execution_id)
		if not record:
			return execution_id
		return _execution_public_id(record)

	def _execution_state_payload(record: Dict[str, Any]) -> Dict[str, Any]:
		return {
			"execution_id": _execution_public_id(record),
			"platform_execution_id": record.get("execution_id"),
			"graph": _execution_graph_payload(record),
			"state": {
				"status": record.get("status"),
				"start_time": record.get("started_at"),
				"end_time": record.get("finished_at"),
				"error": record.get("error"),
				"node_outputs": record.get("outputs", {}) or {},
				"metadata": record.get("metadata", {}) or {},
			},
		}

	def _execution_results_payload(record: Dict[str, Any]) -> Dict[str, Any]:
		public_id = _execution_public_id(record)
		return {
			"execution_id": public_id,
			"platform_execution_id": record.get("execution_id"),
			"workflow_id": record.get("asset_path"),
			"graph": _execution_graph_payload(record),
			"status": record.get("status"),
			"start_time": record.get("started_at"),
			"end_time": record.get("finished_at"),
			"error": record.get("error"),
			"node_outputs": record.get("outputs", {}) or {},
			"metadata": record.get("metadata", {}) or {},
		}

	# Setup tutorial extension API (see docs/tutorial-extension.md)
	setup_tutorial_api(app, manager)

	@app.post("/spaces/current")
	async def current_space(req: Request):
		user, space = await _ensure_current_space(req)
		return {"space": space}

	@app.post("/spaces/list")
	async def list_spaces(req: Request):
		user, current = await _ensure_current_space(req)
		owned = await _list_owned_spaces(req, user.id)
		accessible = await _list_accessible_spaces(req, user.id)
		ref_overrides = _space_ref_overrides(user)
		decorated = _sort_space_records(
			await _decorate_space_records(
				req,
				accessible,
				viewer_user_id=user.id,
				active_ref_overrides=ref_overrides,
				active_asset_overrides=_space_asset_overrides(user),
			)
		)
		mine = [space for space in decorated if space.get("space_view") == "mine"]
		shared = [space for space in decorated if space.get("space_view") == "shared"]
		public = [space for space in decorated if space.get("space_view") == "public"]
		return {
			"spaces": decorated,
			"mine": mine,
			"shared": shared,
			"public": public,
			"owned_count": len(owned),
			"current_space_id": current.get("id"),
			"current_space": current,
		}

	@app.post("/spaces/create")
	async def create_space(request: SpaceCreateRequest, req: Request):
		user = await _refresh_user(req)
		slug = _space_slug(request.slug or request.title)
		try:
			data = await _platform(req).post_json(
				"/platform/spaces/create",
				{
					"user_id": user.id,
					"owner_user_id": user.id,
					"slug": slug,
					"title": request.title.strip(),
					"description": request.description or "",
					"visibility": request.visibility or "private",
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		space = data.get("space") or {}
		await _set_current_space_id(req, user.id, str(space.get("id", "") or ""))
		await _clear_cached_workflow(req)
		decorated = await _decorate_space_records(
			req,
			[space],
			viewer_user_id=user.id,
			active_ref_overrides=_space_ref_overrides(user),
			active_asset_overrides=_space_asset_overrides(user),
		)
		return {"space": decorated[0] if decorated else space}

	@app.post("/spaces/select")
	async def select_space(request: SpaceSelectRequest, req: Request):
		user = await _refresh_user(req)
		spaces = await _list_accessible_spaces(req, user.id)
		space = next((item for item in spaces if item.get("id") == request.space_id), None)
		if space is None:
			raise HTTPException(status_code=404, detail=f"Space '{request.space_id}' not found")
		await _set_current_space_id(req, user.id, request.space_id)
		await _clear_cached_workflow(req)
		decorated = await _decorate_space_records(
			req,
			[space],
			viewer_user_id=user.id,
			active_ref_overrides=_space_ref_overrides(user),
			active_asset_overrides=_space_asset_overrides(user),
		)
		return {"space": decorated[0] if decorated else space}

	@app.post("/spaces/update")
	async def update_space(request: SpaceUpdateRequest, req: Request):
		user = await _refresh_user(req)
		target_space_id = str(request.space_id or await _current_space_id(req, user.id) or "").strip()
		if not target_space_id:
			raise HTTPException(status_code=400, detail="space_id is required")
		updates = {}
		if request.title is not None:
			updates["title"] = request.title.strip()
		if request.slug is not None:
			updates["slug"] = _space_slug(request.slug)
		if request.description is not None:
			updates["description"] = request.description
		if request.visibility is not None:
			updates["visibility"] = str(request.visibility or "private").strip().lower() or "private"
		if not updates:
			raise HTTPException(status_code=400, detail="At least one field must be updated")
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{target_space_id}/update",
				updates,
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		space = data.get("space") or {}
		decorated = await _decorate_space_records(
			req,
			[space],
			viewer_user_id=user.id,
			active_ref_overrides=_space_ref_overrides(user),
			active_asset_overrides=_space_asset_overrides(user),
		)
		return {"space": decorated[0] if decorated else space}

	@app.post("/spaces/public/resolve")
	async def resolve_public_space(request: SpaceResolveRequest, req: Request):
		user = await _refresh_user(req)
		namespace = str(request.namespace or "").strip().lower()
		slug = str(request.slug or "").strip().lower()
		if not namespace or not slug:
			raise HTTPException(status_code=400, detail="namespace and slug are required")
		spaces = await _list_accessible_spaces(req, user.id)
		decorated = await _decorate_space_records(
			req,
			spaces,
			viewer_user_id=user.id,
			active_ref_overrides=_space_ref_overrides(user),
			active_asset_overrides=_space_asset_overrides(user),
		)
		space = next(
			(
				item for item in decorated
				if item.get("is_public")
				and str(item.get("slug", "") or "").strip().lower() == slug
				and str(item.get("namespace", "") or item.get("owner_username", "") or item.get("owner_user_id", "")).strip().lower() == namespace
			),
			None,
		)
		if space is None:
			raise HTTPException(status_code=404, detail=f"Public space '{namespace}/{slug}' not found")
		return {"space": space}

	@app.post("/spaces/public/namespace")
	async def list_public_namespace_spaces(request: PublicNamespaceRequest, req: Request):
		user = await _refresh_user(req)
		namespace = str(request.namespace or "").strip().lower()
		if not namespace:
			raise HTTPException(status_code=400, detail="namespace is required")
		spaces = await _list_accessible_spaces(req, user.id)
		decorated = _sort_space_records(
			await _decorate_space_records(
				req,
				spaces,
				viewer_user_id=user.id,
				active_ref_overrides=_space_ref_overrides(user),
				active_asset_overrides=_space_asset_overrides(user),
			)
		)
		public_spaces = [
			item
			for item in decorated
			if item.get("is_public")
			and str(item.get("namespace", "") or item.get("owner_username", "") or item.get("owner_user_id", "")).strip().lower() == namespace
		]
		return {
			"namespace": namespace,
			"repo_count": len(public_spaces),
			"spaces": public_spaces,
		}

	@app.post("/spaces/public/creator")
	async def public_creator_page(request: PublicCreatorPageRequest, req: Request):
		user = await _refresh_user(req)
		creator = str(request.creator or "").strip().lower()
		if not creator:
			raise HTTPException(status_code=400, detail="creator is required")
		limit = max(1, min(int(request.limit or 12), 50))
		spaces = await _list_accessible_spaces(req, user.id)
		decorated = _sort_space_records(
			await _decorate_space_records(
				req,
				spaces,
				viewer_user_id=user.id,
				active_ref_overrides=_space_ref_overrides(user),
				active_asset_overrides=_space_asset_overrides(user),
			)
		)
		public_spaces = [
			item
			for item in decorated
			if item.get("is_public")
			and str(item.get("namespace", "") or item.get("owner_username", "") or item.get("owner_user_id", "")).strip().lower() == creator
		]
		all_gallery_items = _gallery_manager(req).list(author=creator)
		gallery_items = sorted(
			all_gallery_items,
			key=lambda item: (
				0 if (item.get("provenance", {}) or {}).get("featured") else 1,
				0 if (item.get("provenance", {}) or {}).get("curated") else 1,
				0 if (item.get("provenance", {}) or {}).get("repo_backed") else 1,
				-float(item.get("created_at") or 0.0),
				str(item.get("title", "") or "").lower(),
			),
		)[:limit]
		return {
			"creator": creator,
			"repo_count": len(public_spaces),
			"template_count": len(all_gallery_items),
			"featured_template_count": sum(1 for item in all_gallery_items if (item.get("provenance", {}) or {}).get("featured")),
			"curated_template_count": sum(1 for item in all_gallery_items if (item.get("provenance", {}) or {}).get("curated")),
			"spaces": public_spaces,
			"gallery_items": gallery_items,
		}

	@app.post("/spaces/public/repo")
	async def public_repo_page(request: PublicRepoPageRequest, req: Request):
		user = await _refresh_user(req)
		namespace = str(request.namespace or "").strip().lower()
		slug = str(request.slug or "").strip().lower()
		if not namespace or not slug:
			raise HTTPException(status_code=400, detail="namespace and slug are required")
		spaces = await _list_accessible_spaces(req, user.id)
		decorated = _sort_space_records(
			await _decorate_space_records(
				req,
				spaces,
				viewer_user_id=user.id,
				active_ref_overrides=_space_ref_overrides(user),
				active_asset_overrides=_space_asset_overrides(user),
			)
		)
		space = next(
			(
				item for item in decorated
				if item.get("is_public")
				and str(item.get("slug", "") or "").strip().lower() == slug
				and str(item.get("namespace", "") or item.get("owner_username", "") or item.get("owner_user_id", "")).strip().lower() == namespace
			),
			None,
		)
		if space is None:
			raise HTTPException(status_code=404, detail=f"Public space '{namespace}/{slug}' not found")
		active_ref = str(request.ref or _space_default_ref(space)).strip() or _space_default_ref(space)
		limit = max(1, min(int(request.limit or 12), 50))
		try:
			refs_data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/refs/list",
				{"user_id": user.id},
			)
			history_data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/history",
				{
					"user_id": user.id,
					"path": "",
					"limit": limit,
					"ref": active_ref,
				},
			)
			assets_data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/assets/list",
				{
					"user_id": user.id,
					"prefix": "",
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		namespace_spaces = [
			item
			for item in decorated
			if item.get("is_public")
			and str(item.get("namespace", "") or item.get("owner_username", "") or item.get("owner_user_id", "")).strip().lower() == namespace
		]
		return {
			"space": space,
			"active_ref": active_ref,
			"default_ref": _space_default_ref(space),
			"refs": refs_data.get("refs", []) or [],
			"commits": history_data.get("commits", []) or [],
			"assets": assets_data.get("assets", []) or [],
			"namespace": namespace,
			"namespace_repo_count": len(namespace_spaces),
			"namespace_spaces": namespace_spaces,
		}

	@app.post("/spaces/public/repo/assets/read")
	async def public_repo_asset_read(request: PublicRepoAssetReadRequest, req: Request):
		user = await _refresh_user(req)
		namespace = str(request.namespace or "").strip().lower()
		slug = str(request.slug or "").strip().lower()
		path = str(request.path or "").strip()
		if not namespace or not slug:
			raise HTTPException(status_code=400, detail="namespace and slug are required")
		if not path:
			raise HTTPException(status_code=400, detail="path is required")
		spaces = await _list_accessible_spaces(req, user.id)
		decorated = _sort_space_records(
			await _decorate_space_records(
				req,
				spaces,
				viewer_user_id=user.id,
				active_ref_overrides=_space_ref_overrides(user),
				active_asset_overrides=_space_asset_overrides(user),
			)
		)
		space = next(
			(
				item for item in decorated
				if item.get("is_public")
				and str(item.get("slug", "") or "").strip().lower() == slug
				and str(item.get("namespace", "") or item.get("owner_username", "") or item.get("owner_user_id", "")).strip().lower() == namespace
			),
			None,
		)
		if space is None:
			raise HTTPException(status_code=404, detail=f"Public space '{namespace}/{slug}' not found")
		active_ref = str(request.ref or _space_default_ref(space)).strip() or _space_default_ref(space)
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/assets/read",
				{
					"user_id": user.id,
					"path": path,
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"active_ref": active_ref,
			"path": path,
			"text": data.get("text"),
			"content_base64": data.get("content_base64"),
		}

	@app.post("/spaces/public/repo/compare")
	async def public_repo_compare(request: PublicRepoCompareRequest, req: Request):
		user = await _refresh_user(req)
		namespace = str(request.namespace or "").strip().lower()
		slug = str(request.slug or "").strip().lower()
		left = str(request.left or "").strip()
		if not namespace or not slug:
			raise HTTPException(status_code=400, detail="namespace and slug are required")
		if not left:
			raise HTTPException(status_code=400, detail="left is required")
		spaces = await _list_accessible_spaces(req, user.id)
		decorated = _sort_space_records(
			await _decorate_space_records(
				req,
				spaces,
				viewer_user_id=user.id,
				active_ref_overrides=_space_ref_overrides(user),
				active_asset_overrides=_space_asset_overrides(user),
			)
		)
		space = next(
			(
				item for item in decorated
				if item.get("is_public")
				and str(item.get("slug", "") or "").strip().lower() == slug
				and str(item.get("namespace", "") or item.get("owner_username", "") or item.get("owner_user_id", "")).strip().lower() == namespace
			),
			None,
		)
		if space is None:
			raise HTTPException(status_code=404, detail=f"Public space '{namespace}/{slug}' not found")
		right = str(request.right or _space_default_ref(space)).strip() or _space_default_ref(space)
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/compare",
				{
					"user_id": user.id,
					"left": left,
					"right": right,
					"path": str(request.path or ""),
					"limit": max(1, min(int(request.limit or 200), 500)),
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"namespace": namespace,
			"active_ref": right,
			"comparison": data.get("comparison", {}) or {},
		}

	@app.post("/spaces/delete")
	async def delete_space(request: SpaceSelectRequest, req: Request):
		user = await _refresh_user(req)
		spaces = await _list_owned_spaces(req, user.id)
		space = next((item for item in spaces if item.get("id") == request.space_id), None)
		if space is None:
			raise HTTPException(status_code=404, detail=f"Space '{request.space_id}' not found")
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{request.space_id}/delete",
				{"user_id": user.id},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		if not data.get("ok"):
			raise HTTPException(status_code=404, detail=f"Space '{request.space_id}' not found")
		await _clear_cached_workflow(req)
		_, current = await _ensure_current_space(req)
		return {"ok": True, "current_space_id": current.get("id")}

	@app.post("/spaces/fork")
	async def fork_space(request: SpaceForkRequest, req: Request):
		user, current = await _ensure_current_space(req)
		source_space_id = str(request.space_id or current.get("id") or "").strip()
		if not source_space_id:
			raise HTTPException(status_code=400, detail="space_id is required")
		payload = {
			"user_id": user.id,
			"new_owner_user_id": user.id,
		}
		title = str(request.title or "").strip()
		if title:
			payload["title"] = title
		raw_slug = str(request.slug or "").strip()
		if raw_slug or title:
			slug = _space_slug(raw_slug or title)
			payload["slug"] = slug
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{source_space_id}/fork",
				payload,
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		space = data.get("space") or {}
		space_id = str(space.get("id", "") or "").strip()
		if space_id:
			await _set_current_space_id(req, user.id, space_id)
			source_active_ref = _space_active_ref(current)
			if source_active_ref:
				await _set_current_space_ref(req, user.id, space_id, source_active_ref)
			source_active_asset = _space_active_asset_path(current)
			if source_active_asset:
				await _set_current_space_asset_path(req, user.id, space_id, source_active_asset)
		await _clear_cached_workflow(req)
		decorated = await _decorate_space_records(
			req,
			[space],
			viewer_user_id=user.id,
			active_ref_overrides=_space_ref_overrides(user),
			active_asset_overrides=_space_asset_overrides(user),
		)
		return {"space": decorated[0] if decorated else space}

	@app.post("/spaces/repo/refs")
	async def current_space_repo_refs(req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/refs/list",
				{"user_id": user.id},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"active_ref": active_ref,
			"default_ref": str(space.get("default_ref", "") or "main").strip() or "main",
			"refs": data.get("refs", []) or [],
		}

	@app.post("/spaces/repo/ref/set")
	async def current_space_set_repo_ref(request: SpaceRefSetRequest, req: Request):
		user, space = await _ensure_current_space(req)
		ref_name = str(request.name or "").strip()
		if not ref_name:
			raise HTTPException(status_code=400, detail="name is required")
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/refs/list",
				{"user_id": user.id},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		refs = data.get("refs", []) or []
		if not any(str(item.get("name", "") or "").strip() == ref_name for item in refs):
			raise HTTPException(status_code=404, detail=f"Ref '{ref_name}' not found")
		await _set_current_space_ref(req, user.id, str(space.get("id", "") or ""), ref_name)
		await _clear_cached_workflow(req)
		_, updated_space = await _ensure_current_space(req)
		return {
			"space": updated_space,
			"active_ref": _space_active_ref(updated_space),
			"refs": refs,
		}

	@app.post("/spaces/repo/refs/create")
	async def current_space_create_repo_ref(request: SpaceRefCreateRequest, req: Request):
		user, space = await _ensure_current_space(req)
		name = str(request.name or "").strip()
		if not name:
			raise HTTPException(status_code=400, detail="name is required")
		kind = str(request.kind or "branch").strip().lower() or "branch"
		if kind not in {"branch", "tag"}:
			raise HTTPException(status_code=400, detail="kind must be 'branch' or 'tag'")
		from_ref = str(request.from_ref or _space_active_ref(space)).strip() or _space_active_ref(space)
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/refs/create",
				{
					"user_id": user.id,
					"name": name,
					"kind": kind,
					"from_ref": from_ref,
				},
			)
			refs_data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/refs/list",
				{"user_id": user.id},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"active_ref": _space_active_ref(space),
			"ref": data.get("ref"),
			"refs": refs_data.get("refs", []) or [],
		}

	@app.post("/spaces/repo/refs/delete")
	async def current_space_delete_repo_ref(request: SpaceRefDeleteRequest, req: Request):
		user, space = await _ensure_current_space(req)
		name = str(request.name or "").strip()
		if not name:
			raise HTTPException(status_code=400, detail="name is required")
		active_ref = _space_active_ref(space)
		default_ref = str(space.get("default_ref", "") or "main").strip() or "main"
		if name == active_ref:
			raise HTTPException(status_code=400, detail="Switch away from the active ref before deleting it")
		if name == default_ref:
			raise HTTPException(status_code=400, detail="Delete or rename the repo default ref only after changing the default")
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/refs/delete",
				{"user_id": user.id, "name": name},
			)
			refs_data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/refs/list",
				{"user_id": user.id},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"active_ref": active_ref,
			"ok": bool(data.get("ok")),
			"refs": refs_data.get("refs", []) or [],
		}

	@app.post("/spaces/repo/history")
	async def current_space_repo_history(request: SpaceRepoHistoryRequest, req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		limit = max(1, min(int(request.limit or 20), 100))
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/history",
				{
					"user_id": user.id,
					"path": "",
					"limit": limit,
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"active_ref": active_ref,
			"commits": data.get("commits", []) or [],
		}

	@app.post("/spaces/repo/compare")
	async def current_space_repo_compare(request: SpaceRepoCompareRequest, req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		left = str(request.left or "").strip()
		right = str(request.right or active_ref).strip() or active_ref
		if not left:
			raise HTTPException(status_code=400, detail="left is required")
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/compare",
				{
					"user_id": user.id,
					"left": left,
					"right": right,
					"path": str(request.path or ""),
					"limit": max(1, min(int(request.limit or 200), 500)),
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"active_ref": active_ref,
			"comparison": data.get("comparison", {}) or {},
		}

	@app.post("/spaces/repo/assets")
	async def current_space_repo_assets(request: SpaceRepoAssetsRequest, req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/assets/list",
				{
					"user_id": user.id,
					"prefix": str(request.prefix or ""),
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"active_ref": active_ref,
			"assets": data.get("assets", []) or [],
		}

	@app.post("/spaces/repo/assets/read")
	async def current_space_repo_asset_read(request: SpaceRepoAssetReadRequest, req: Request):
		user, space = await _ensure_current_space(req)
		path = str(request.path or "").strip()
		if not path:
			raise HTTPException(status_code=400, detail="path is required")
		active_ref = _space_active_ref(space)
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/assets/read",
				{
					"user_id": user.id,
					"path": path,
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"active_ref": active_ref,
			"path": path,
			"text": data.get("text"),
			"content_base64": data.get("content_base64"),
		}

	@app.post("/spaces/repo/assets/write")
	async def current_space_repo_asset_write(request: SpaceRepoAssetWriteRequest, req: Request):
		user, space = await _ensure_current_space(req)
		path = str(request.path or "").strip()
		if not path:
			raise HTTPException(status_code=400, detail="path is required")
		active_ref = _space_active_ref(space)
		title = request.title if request.title is not None else Path(path).name
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/assets/write",
				{
					"user_id": user.id,
					"path": path,
					"kind": str(request.kind or "data").strip() or "data",
					"title": str(title or "").strip(),
					"description": str(request.description or "").strip(),
					"executable": bool(request.executable),
					"text": str(request.text or ""),
					"message": str(request.message or "").strip() or f"Update asset '{path}'",
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"active_ref": active_ref,
			"path": path,
			"commit": data.get("commit", {}) or {},
			"status": "saved",
		}

	@app.post("/spaces/repo/assets/open")
	async def current_space_repo_asset_open(request: SpaceRepoAssetOpenRequest, req: Request):
		user, space = await _ensure_current_space(req)
		path = str(request.path or "").strip()
		if not path:
			raise HTTPException(status_code=400, detail="path is required")
		active_ref = _space_active_ref(space)
		doc = await _read_workflow_asset_doc(req, user.id, str(space.get("id", "") or ""), path=path, ref=active_ref)
		if doc is None:
			raise HTTPException(status_code=404, detail=f"Workflow asset '{path}' was not found on ref '{active_ref}'")
		validation = validate_workflow_payload(doc, apply_repairs=True)
		if not validation["valid"]:
			raise HTTPException(
				status_code=400,
				detail={
					"message": f"Workflow asset '{path}' is not a valid runnable workflow",
					"errors": validation["errors"],
					"warnings": validation["warnings"],
					"repairs": validation["repairs"],
				},
			)
		doc = validation["workflow"]
		workflow = _workflow_model_from_doc(doc)
		await _set_current_space_asset_path(req, user.id, str(space.get("id", "") or ""), path)
		await _cache_current_workflow(
			req,
			workflow,
			cache_key=_workflow_cache_key(str(space.get("id", "") or ""), path, active_ref),
		)
		_, updated_space = await _ensure_current_space(req)
		return {
			"space": updated_space,
			"ref": active_ref,
			"asset_path": path,
			"name": _workflow_name_from_doc(doc) or Path(path).stem or "Workflow",
			"workflow": doc,
			"status": "opened",
		}

	@app.post("/spaces/repo/restore")
	async def current_space_repo_restore(request: SpaceRepoRestoreRequest, req: Request):
		user, space = await _ensure_current_space(req)
		source = str(request.source or "").strip()
		if not source:
			raise HTTPException(status_code=400, detail="source is required")
		active_ref = _space_active_ref(space)
		try:
			refs_data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/refs/list",
				{"user_id": user.id},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		ref_map = {
			str(item.get("name", "") or "").strip(): str(item.get("kind", "") or "").strip().lower()
			for item in (refs_data.get("refs", []) or [])
		}
		if ref_map.get(active_ref) != "branch":
			raise HTTPException(status_code=400, detail="Switch to a branch before restoring repo history into it")
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/restore",
				{
					"user_id": user.id,
					"source": source,
					"target_ref": active_ref,
					"message": str(request.note or "").strip(),
				},
			)
			assets_data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/assets/list",
				{
					"user_id": user.id,
					"prefix": "",
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		assets = assets_data.get("assets", []) or []
		asset_path = _pick_workbench_asset_path(assets, _space_active_asset_path(space)) or _space_active_asset_path(space)
		await _set_current_space_asset_path(req, user.id, str(space.get("id", "") or ""), asset_path)
		doc = await _read_workflow_asset_doc(req, user.id, str(space.get("id", "") or ""), path=asset_path, ref=active_ref)
		if doc is not None:
			await _cache_current_workflow(
				req,
				_workflow_model_from_doc(doc),
				cache_key=_workflow_cache_key(str(space.get("id", "") or ""), asset_path, active_ref),
			)
		else:
			await _clear_cached_workflow(req)
		_, updated_space = await _ensure_current_space(req)
		return {
			"space": updated_space,
			"ref": active_ref,
			"asset_path": asset_path,
			"name": _workflow_name_from_doc(doc) or (Path(asset_path).stem if doc is not None else "Workflow"),
			"workflow": doc,
			"commit": data.get("commit"),
			"status": "restored",
		}

	@app.post("/workflow/get")
	async def get_current_workflow(req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		asset_path = _space_active_asset_path(space)
		doc = await _read_workflow_asset_doc(req, user.id, str(space.get("id", "") or ""), path=asset_path, ref=active_ref)
		if doc is not None:
			cache_key = _workflow_cache_key(str(space.get("id", "") or ""), asset_path, active_ref)
			cached_key = getattr(_ws(req).manager, "_numel_cached_workflow_key", None)
			if cached_key != cache_key:
				try:
					await _cache_current_workflow(req, _workflow_model_from_doc(doc), cache_key=cache_key)
				except Exception:
					pass
		return {
			"space": space,
			"ref": active_ref,
			"asset_path": asset_path,
			"name": _workflow_name_from_doc(doc) or Path(asset_path).stem or "Workflow",
			"workflow": doc,
		}

	@app.post("/workflow/interop/import")
	async def interop_import_workflow(request: WorkflowInteropImportRequest):
		try:
			return import_workflow_document(
				request.document or {},
				file_name=request.file_name,
				source_format=request.source_format,
			)
		except InteropImportError as exc:
			raise HTTPException(status_code=400, detail=exc.detail)

	@app.post("/workflow/validate")
	async def validate_current_workflow(request: WorkflowValidateRequest):
		result = validate_workflow_payload(
			request.workflow or {},
			apply_repairs=bool(request.apply_repairs),
		)
		if not result["valid"]:
			raise HTTPException(
				status_code=400,
				detail={
					"message": "Workflow validation failed",
					"errors": result["errors"],
					"warnings": result["warnings"],
					"repairs": result["repairs"],
				},
			)
		return result

	@app.post("/workflow/save")
	async def save_current_workflow(request: CurrentWorkflowSaveRequest, req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		asset_path = _space_active_asset_path(space)
		validation = validate_workflow_payload(
			_workflow_doc_from_model(request.workflow),
			apply_repairs=True,
		)
		if not validation["valid"]:
			raise HTTPException(
				status_code=400,
				detail={
					"message": "Workflow validation failed before save",
					"errors": validation["errors"],
					"warnings": validation["warnings"],
					"repairs": validation["repairs"],
				},
			)
		doc = validation["workflow"]
		workflow = _workflow_model_from_doc(doc)
		name = (
			workflow.options.name
			if getattr(workflow, "options", None) is not None and workflow.options.name
			else "Untitled"
		)
		try:
			commit_message = str(request.message or "").strip() or f"Save workflow '{name}'"
			await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/assets/write",
				{
					"user_id": user.id,
					"path": asset_path,
					"kind": "workflow",
					"title": name,
					"description": getattr(getattr(workflow, "options", None), "description", "") or "",
					"executable": True,
					"text": json.dumps(doc, indent=2),
					"message": commit_message,
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		await _cache_current_workflow(
			req,
			workflow,
			cache_key=_workflow_cache_key(str(space.get("id", "") or ""), asset_path, active_ref),
		)
		await _emit_workflow_changed(name, source_session_id=_request_session_id(req))
		return {
			"space": space,
			"ref": active_ref,
			"asset_path": asset_path,
			"name": name,
			"workflow": doc,
			"status": "saved",
			"message": commit_message,
		}

	@app.post("/workflow/impl")
	async def ensure_current_workflow_impl(req: Request):
		user, space = await _ensure_current_space(req)
		asset_path = _space_active_asset_path(space)
		ws = _ws(req)
		impl = await ws.manager.impl()
		if not impl:
			raise HTTPException(status_code=404, detail="No active workflow")
		workflow = impl.get("workflow")
		if workflow is None:
			raise HTTPException(status_code=404, detail="No active workflow")
		doc = _workflow_doc_from_model(workflow, keep_runtime_state=True)
		return {
			"space": space,
			"asset_path": asset_path,
			"name": _workflow_name_from_doc(doc),
			"workflow": doc,
			"status": "implemented",
		}

	@app.post("/workflow/delete")
	async def delete_current_workflow(req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		asset_path = _space_active_asset_path(space)
		try:
			await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/assets/delete",
				{
					"user_id": user.id,
					"path": asset_path,
					"message": "Delete current workflow",
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			if exc.status_code != 404:
				raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		await _clear_cached_workflow(req)
		await _emit_workflow_changed("", source_session_id=_request_session_id(req))
		return {"status": "deleted", "space": space, "ref": active_ref, "asset_path": asset_path}

	@app.post("/workflow/history")
	async def current_workflow_history(request: WorkflowHistoryRequest, req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		asset_path = _space_active_asset_path(space)
		limit = max(1, min(int(request.limit or 20), 100))
		try:
			data = await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/history",
				{
					"user_id": user.id,
					"path": asset_path,
					"limit": limit,
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"space": space,
			"ref": active_ref,
			"path": asset_path,
			"commits": data.get("commits", []) or [],
		}

	@app.post("/workflow/restore")
	async def restore_workflow_snapshot(request: WorkflowRestoreRequest, req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		asset_path = _space_active_asset_path(space)
		commit_id = str(request.commit_id or "").strip()
		if not commit_id:
			raise HTTPException(status_code=400, detail="commit_id is required")
		doc = await _read_workflow_asset_doc(req, user.id, str(space.get("id", "") or ""), path=asset_path, ref=commit_id)
		if doc is None:
			raise HTTPException(status_code=404, detail=f"Workflow snapshot '{commit_id}' was not found for '{asset_path}'")
		validation = validate_workflow_payload(doc, apply_repairs=True)
		if not validation["valid"]:
			raise HTTPException(
				status_code=400,
				detail={
					"message": "Workflow validation failed before restore",
					"errors": validation["errors"],
					"warnings": validation["warnings"],
					"repairs": validation["repairs"],
				},
			)
		doc = validation["workflow"]
		workflow = _workflow_model_from_doc(doc)
		name = (
			workflow.options.name
			if getattr(workflow, "options", None) is not None and workflow.options.name
			else "Untitled"
		)
		commit_note = str(request.note or "").strip()
		if not commit_note:
			commit_note = f"Restore workflow snapshot {commit_id[:8]}"
		try:
			await _platform(req).post_json(
				f"/platform/spaces/{space['id']}/assets/write",
				{
					"user_id": user.id,
					"path": asset_path,
					"kind": "workflow",
					"title": name,
					"description": getattr(getattr(workflow, "options", None), "description", "") or "",
					"executable": True,
					"text": json.dumps(doc, indent=2),
					"message": commit_note,
					"ref": active_ref,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		await _cache_current_workflow(
			req,
			workflow,
			cache_key=_workflow_cache_key(str(space.get("id", "") or ""), asset_path, active_ref),
		)
		await _emit_workflow_changed(name, source_session_id=_request_session_id(req))
		return {
			"space": space,
			"ref": active_ref,
			"asset_path": asset_path,
			"name": name,
			"workflow": doc,
			"status": "restored",
			"restored_from_commit": commit_id,
			"message": commit_note,
		}

	@app.post("/workflow/publish-template")
	async def publish_workflow_template(request: WorkflowTemplatePublishRequest, req: Request):
		user, space = await _ensure_current_space(req)
		title = str(request.title or "").strip()
		if not title:
			raise HTTPException(status_code=400, detail="title is required")
		source_kind = str(request.source_kind or "canvas").strip().lower() or "canvas"
		if source_kind not in {"canvas", "ref", "commit"}:
			raise HTTPException(status_code=400, detail="source_kind must be 'canvas', 'ref', or 'commit'")
		asset_path = str(request.path or _space_active_asset_path(space)).strip() or _space_active_asset_path(space)
		active_ref = _space_active_ref(space)
		source_selector = active_ref
		source_commit_id = None
		doc: Optional[Dict[str, Any]] = None

		if source_kind == "canvas":
			if not isinstance(request.workflow, dict):
				raise HTTPException(status_code=400, detail="workflow is required when publishing from the current canvas")
			validation = validate_workflow_payload(request.workflow, apply_repairs=True)
			if not validation["valid"]:
				raise HTTPException(
					status_code=400,
					detail={
						"message": "Workflow validation failed before publish",
						"errors": validation["errors"],
						"warnings": validation["warnings"],
						"repairs": validation["repairs"],
					},
				)
			doc = validation["workflow"]
		elif source_kind == "ref":
			source_selector = str(request.ref or active_ref).strip() or active_ref
			doc = await _read_workflow_asset_doc(
				req,
				user.id,
				str(space.get("id", "") or ""),
				path=asset_path,
				ref=source_selector,
			)
			if doc is None:
				raise HTTPException(status_code=404, detail=f"Workflow asset '{asset_path}' was not found on ref '{source_selector}'")
			validation = validate_workflow_payload(doc, apply_repairs=True)
			if not validation["valid"]:
				raise HTTPException(
					status_code=400,
					detail={
						"message": f"Workflow asset '{asset_path}' on ref '{source_selector}' is not a valid runnable workflow",
						"errors": validation["errors"],
						"warnings": validation["warnings"],
						"repairs": validation["repairs"],
					},
				)
			doc = validation["workflow"]
		else:
			source_commit_id = str(request.commit_id or "").strip()
			if not source_commit_id:
				raise HTTPException(status_code=400, detail="commit_id is required when publishing from a snapshot")
			source_selector = source_commit_id
			doc = await _read_workflow_asset_doc(
				req,
				user.id,
				str(space.get("id", "") or ""),
				path=asset_path,
				ref=source_commit_id,
			)
			if doc is None:
				raise HTTPException(status_code=404, detail=f"Workflow snapshot '{source_commit_id}' was not found for '{asset_path}'")
			validation = validate_workflow_payload(doc, apply_repairs=True)
			if not validation["valid"]:
				raise HTTPException(
					status_code=400,
					detail={
						"message": f"Workflow snapshot '{source_commit_id}' for '{asset_path}' is not a valid runnable workflow",
						"errors": validation["errors"],
						"warnings": validation["warnings"],
						"repairs": validation["repairs"],
					},
				)
			doc = validation["workflow"]

		description = str(request.description or "").strip() or _default_publish_description(space, source_kind, source_selector)
		author = str(getattr(user, "username", "") or user.id).strip() or "user"
		item = _gallery_manager(req).publish(
			workflow=doc or {},
			title=title,
			description=description,
			category=str(request.category or "templates").strip() or "templates",
			tags=list(request.tags or []),
			author=author,
			metadata={
				"source": {
					"type": source_kind,
					"space_id": str(space.get("id", "") or ""),
					"space_title": str(space.get("title", "") or ""),
					"namespace": str(space.get("namespace", "") or space.get("owner_username", "") or ""),
					"slug": str(space.get("slug", "") or ""),
					"namespace_slug": str(space.get("namespace_slug", "") or ""),
					"visibility": str(space.get("visibility", "") or "private").strip().lower() or "private",
					"is_public": bool(space.get("is_public")),
					"asset_path": asset_path,
					"active_ref": active_ref,
					"ref": None if source_kind == "commit" else source_selector,
					"commit_id": source_commit_id,
				},
			},
		)
		return {
			"item": item,
			"space": space,
			"source_kind": source_kind,
			"ref": None if source_kind == "commit" else source_selector,
			"commit_id": source_commit_id,
			"asset_path": asset_path,
		}

	@app.post("/workflow/start")
	async def start_current_workflow(request: CurrentWorkflowStartRequest, req: Request):
		user, space = await _ensure_current_space(req)
		active_ref = _space_active_ref(space)
		asset_path = _space_active_asset_path(space)
		doc = await _read_workflow_asset_doc(req, user.id, str(space.get("id", "") or ""), path=asset_path, ref=active_ref)
		if doc is None:
			raise HTTPException(status_code=404, detail=f"No workflow is saved at '{asset_path}' in the current space")
		validation = validate_workflow_payload(doc, apply_repairs=True)
		if not validation["valid"]:
			raise HTTPException(
				status_code=400,
				detail={
					"message": "Workflow validation failed before run",
					"errors": validation["errors"],
					"warnings": validation["warnings"],
					"repairs": validation["repairs"],
				},
			)
		doc = validation["workflow"]
		if validation["repaired"]:
			name = _workflow_name_from_doc(doc) or "Untitled"
			try:
				await _platform(req).post_json(
					f"/platform/spaces/{space['id']}/assets/write",
					{
						"user_id": user.id,
						"path": asset_path,
						"kind": "workflow",
						"title": name,
						"description": "",
						"executable": True,
						"text": json.dumps(doc, indent=2),
						"message": f"Repair workflow '{name}' before run",
						"ref": active_ref,
					},
				)
				await _cache_current_workflow(
					req,
					_workflow_model_from_doc(doc),
					cache_key=_workflow_cache_key(str(space.get("id", "") or ""), asset_path, active_ref),
				)
			except PlatformRequestError as exc:
				raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		options = request.initial_data or WorkflowExecutionOptions()
		inputs = options.model_dump() if options else {}
		workflow_name = ""
		if isinstance(doc, dict):
			raw_options = doc.get("options")
			if isinstance(raw_options, dict):
				workflow_name = str(raw_options.get("name", "") or "").strip()
		try:
			workflow_graph = _workflow_graph_payload(
				doc,
				asset_path=asset_path,
				ref=active_ref,
				workflow_name=workflow_name,
			)
			data = await _platform(req).post_json(
				"/platform/executions/start",
				{
					"user_id": user.id,
					"space_id": space["id"],
					"asset_path": asset_path,
					"ref": active_ref,
					"inputs": inputs,
					"resolve_credentials": True,
					"metadata": {
						**({"workflow_name": workflow_name} if workflow_name else {}),
						**({"workflow_graph": workflow_graph} if workflow_graph else {}),
					},
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		record = data.get("execution") or {}
		return {
			"execution_id": _execution_public_id(record),
			"platform_execution_id": record.get("execution_id"),
			"asset_path": asset_path,
			"status": "started",
		}

	@app.post("/executions/list")
	async def current_space_executions(req: Request):
		user, space = await _ensure_current_space(req)
		try:
			data = await _platform(req).post_json(
				"/platform/executions/list",
				{
					"user_id": user.id,
					"space_id": space["id"],
					"limit": 100,
				},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		records = data.get("executions", []) or []
		return {
			"execution_ids": [_execution_public_id(record) for record in records],
			"executions": records,
		}

	@app.post("/executions/{execution_id}")
	async def current_execution_state(execution_id: str, req: Request):
		record = await _find_execution_record(req, execution_id)
		if record is None:
			raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
		return _execution_state_payload(record)

	@app.post("/executions/{execution_id}/cancel")
	async def current_cancel_execution(execution_id: str, req: Request):
		record = await _find_execution_record(req, execution_id)
		if record is None:
			raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
		user = _require_auth(req)
		try:
			data = await _platform(req).post_json(
				f"/platform/executions/{record['execution_id']}/cancel",
				{"user_id": user.id},
			)
		except PlatformRequestError as exc:
			raise HTTPException(status_code=exc.status_code, detail=exc.detail)
		return {
			"execution_id": _execution_public_id(record),
			"platform_execution_id": record.get("execution_id"),
			"status": "cancelled" if data.get("ok") else "failed",
		}

	@app.post("/executions/{execution_id}/results")
	async def current_execution_results(execution_id: str, req: Request):
		record = await _find_execution_record(req, execution_id)
		if record is None:
			raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
		return _execution_results_payload(record)

	@app.post("/executions/{execution_id}/input")
	async def current_execution_input(execution_id: str, request: UserInputRequest, req: Request):
		ws = _ws(req)
		try:
			engine_execution_id = await _resolve_engine_execution_id(req, execution_id)
			await ws.engine.provide_user_input(
				execution_id = engine_execution_id,
				node_id      = request.node_id,
				user_input   = request.input_data,
			)
			return {
				"execution_id": execution_id,
				"platform_execution_id": engine_execution_id,
				"status": "input_received",
				"node_id": request.node_id,
				"input_data": request.input_data,
			}
		except Exception as e:
			raise HTTPException(status_code=500, detail=str(e))

	@app.post("/shutdown")
	async def shutdown_server(req: Request):
		_require_admin(req)
		ws = _ws(req)
		await ws.engine.cancel_execution()
		server = getattr(req.app.state, "uvicorn_server", None)
		if server and server.should_exit is False:
			server.should_exit = True
		req.app.state.uvicorn_server = None
		return {"status": "none", "message": "Server shut down"}


	@app.post("/status")
	async def server_status(req: Request):
		ws = _ws(req)
		return {"status": "ready", "executions": ws.engine.get_all_execution_states()}


	@app.post("/file/{file_path:path}")
	async def serve_file(file_path: str, req: Request):
		"""Serve a file from the workspace directory."""
		import mimetypes
		target = _resolve_file_for_request(req, file_path)
		media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
		return FileResponse(str(target), media_type=media_type, filename=target.name)


	@app.post("/ping")
	async def ping():
		result = {
			"message"   : "pong",
			"timestamp" : get_now_str(),
		}
		return result


	@app.post("/schema")
	async def export_schema():
		nonlocal schema_code
		result = {
			"schema": schema_code,
			"supported_backends": list_supported_backends(),
			"show_backend_config": len(list_supported_backends()) > 1,
		}
		return result

	@app.get("/schema-bootstrap")
	async def export_schema_bootstrap():
		nonlocal schema_code
		return {
			"schema": schema_code,
			"supported_backends": list_supported_backends(),
			"show_backend_config": len(list_supported_backends()) > 1,
		}


	# @app.post("/chat_open/{name}")
	# async def chat_open(name: str):
	# 	raise HTTPException(status_code=501, detail=f"Chat open not implemented")
	# 	result = {
	# 		"name"  : name,
	# 		"port"  : 0,
	# 		"error" : 501,
	# 	}
	# 	return result


	# @app.post("/chat_close")
	# @app.post("/chat_close/{name}")
	# async def chat_close(name: Optional[str] = None):
	# 	raise HTTPException(status_code=501, detail=f"Chat close not implemented")
	# 	result = {
	# 		"name"  : name,
	# 		"error" : 501,
	# 	}
	# 	return result


	@app.post("/tool_call")
	async def tool_call(request: ToolCallRequest, req: Request):
		ws = _ws(req)
		try:
			impl = await ws.manager.impl()
			if not impl:
				raise HTTPException(status_code=404, detail="No active workflow")

			workflow = impl["workflow"]
			backend  = impl["backend" ]

			if not backend:
				raise HTTPException(status_code=400, detail=f"Workflow has no backend implementation")

			node_index = request.node_index
			if node_index < 0 or node_index >= len(workflow.nodes):
				raise HTTPException(status_code=400, detail=f"Invalid node index: {node_index}")

			node = workflow.nodes[node_index]
			if node.type != "tool_config":
				raise HTTPException(status_code=400, detail=f"Node at index {node_index} is not a tool_config (got {node.type})")

			handle = backend.handles[node_index]
			if not handle:
				raise HTTPException(status_code=400, detail=f"Tool at index {node_index} has no implementation")

			# Merge default args from config with request args
			args = dict(node.args or {})
			if request.args:
				args.update(request.args)

			# Execute the tool
			result_data = await backend.run_tool(handle, **args)

			result = {
				"status"     : "success",
				"node_index" : node_index,
				"tool_name"  : node.name,
				"result"     : result_data,
			}
			return result

		except HTTPException:
			raise
		except Exception as e:
			log_print(f"[API] Tool call error: {str(e)}")
			raise HTTPException(status_code=500, detail=str(e))

	@app.post("/chat_response/{execution_id}")
	async def provide_chat_response(execution_id: str, request: ChatResponseRequest, req: Request):
		ws = _ws(req)
		try:
			execution_id = await _resolve_engine_execution_id(req, execution_id)
			await ws.engine.provide_chat_response(
				execution_id = execution_id,
				node_id      = request.node_id,
				response     = request.response
			)
			return {
				"execution_id" : execution_id,
				"status"       : "response_received",
				"node_id"      : request.node_id,
			}
		except Exception as e:
			log_print(f"Error providing chat response: {e}")
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/upload/{node_index}")
	async def upload_files(
		req        : Request,
		node_index : int,
		files      : List[UploadFile] = File(...),
		node_type  : str = Form(None),
		button_id  : str = Form(None),
	):
		"""Handle file uploads from node drop zones or buttons"""
		ws = _ws(req)
		
		upload_id = f"upload_{node_index}_{get_timestamp_str()}"
		
		try:
			# Get current workflow to find node info
			impl = await ws.manager.impl()
			if not impl:
				raise HTTPException(status_code=404, detail="No active workflow")
			
			workflow = impl["workflow"]
			if node_index < 0 or node_index >= len(workflow.nodes):
				raise HTTPException(status_code=404, detail=f"Node {node_index} not found")
			
			node = workflow.nodes[node_index]
			
			# === PHASE 1: UPLOAD ===
			await event_bus.emit(
				EventType.UPLOAD_STARTED,
				node_id = str(node_index),
				data    = {
					"upload_id"  : upload_id,
					"node_index" : node_index,
					"node_type"  : node_type or node.type,
					"file_count" : len(files),
					"filenames"  : [f.filename for f in files],
				}
			)
			
			# Read file contents
			uploaded   = []
			total_size = 0
			for file in files:
				content   = await file.read()
				file_size = len(content) if content else 0
				file_info = {
					"filename"     : file.filename,
					"content_type" : file.content_type,
					"size"         : file_size,
					"content"      : content,
					"file"         : file,
				}
				uploaded.append(file_info)
				total_size += file_size
			
			# Upload complete
			await event_bus.emit(
				EventType.UPLOAD_COMPLETED,
				node_id = str(node_index),
				data    = {
					"upload_id"  : upload_id,
					"node_index" : node_index,
					"file_count" : len(uploaded),
					"total_size" : total_size,
				}
			)
			
			# === PHASE 2: PROCESSING ===
			handler_result = None
			handler        = await ws.manager.get_upload_handler(node.type)
			
			if handler:
				await event_bus.emit(
					EventType.PROCESSING_STARTED,
					node_id = str(node_index),
					data    = {
						"upload_id"  : upload_id,
						"node_index" : node_index,
						"node_type"  : node.type,
						"handler"    : handler.__name__ if hasattr(handler, '__name__') else str(handler),
					}
				)
				
				try:
					if iscoroutinefunction(handler):
						handler_result = await handler(impl, node_index, button_id, uploaded)
					else:
						handler_result = handler(impl, node_index, button_id, uploaded)
					
					await event_bus.emit(
						EventType.PROCESSING_COMPLETED,
						node_id = str(node_index),
						data    = {
							"upload_id"  : upload_id,
							"node_index" : node_index,
							"result"     : serialize_result(handler_result),
						}
					)
					
				except Exception as e:
					log_print(f"Processing handler error: {e}")
					await event_bus.emit(
						EventType.PROCESSING_FAILED,
						node_id = str(node_index),
						error   = str(e),
						data    = {
							"upload_id"  : upload_id,
							"node_index" : node_index,
						}
					)
					raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
			
			result = {
				"status"         : "completed",
				"upload_id"      : upload_id,
				"node_index"     : node_index,
				"node_type"      : node.type,
				"files_count"    : len(uploaded),
				"total_size"     : total_size,
				"handler_result" : serialize_result(handler_result),
				"files"          : [
					{
						"filename"     : f["filename"],
						"content_type" : f["content_type"],
						"size"         : f["size"],
					}
					for f in uploaded
				],
			}
			return result
			
		except HTTPException:
			raise
		except Exception as e:
			log_print(f"Error in upload: {e}")
			await event_bus.emit(
				EventType.UPLOAD_FAILED,
				node_id = str(node_index),
				error   = str(e),
				data    = {
					"upload_id"  : upload_id,
					"node_index" : node_index,
				}
			)
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/contents/list/{node_index}")
	async def list_contents(node_index: int, req: Request):
		"""List all contents for a node (e.g., knowledge manager)"""
		ws = _ws(req)
		try:
			impl = await ws.manager.impl()
			if not impl:
				raise HTTPException(status_code=404, detail="No active workflow")

			workflow = impl["workflow"]
			if node_index < 0 or node_index >= len(workflow.nodes):
				raise HTTPException(status_code=404, detail=f"Node {node_index} not found")

			node    = workflow.nodes[node_index]
			backend = impl["backend"]
			handle  = backend.handles[node_index]

			if not handle:
				raise HTTPException(status_code=400, detail=f"Node {node_index} has no content handle")

			contents = await backend.list_contents(handle)

			result = {
				"status"     : "ok",
				"node_index" : node_index,
				"node_type"  : node.type,
				"contents"   : [
					{"id": id, "metadata": metadata}
					for id, metadata in contents
				],
			}
			return result

		except HTTPException:
			raise
		except Exception as e:
			log_print(f"Error listing contents: {e}")
			raise HTTPException(status_code=500, detail=str(e))


	@app.post("/contents/remove/{node_index}")
	async def remove_contents(node_index: int, request: ContentRemoveRequest, req: Request):
		"""Remove contents from a node by their IDs"""
		ws = _ws(req)
		try:
			impl = await ws.manager.impl()
			if not impl:
				raise HTTPException(status_code=404, detail="No active workflow")

			workflow = impl["workflow"]
			if node_index < 0 or node_index >= len(workflow.nodes):
				raise HTTPException(status_code=404, detail=f"Node {node_index} not found")

			node    = workflow.nodes[node_index]
			backend = impl["backend"]
			handle  = backend.handles[node_index]

			if not handle:
				raise HTTPException(status_code=400, detail=f"Node {node_index} has no content handle")

			await event_bus.emit(
				EventType.CONTENT_REMOVE_STARTED,
				node_id = str(node_index),
				data    = {
					"node_index" : node_index,
					"node_type"  : node.type,
					"ids"        : request.ids,
				}
			)

			removed = await backend.remove_contents(handle, request.ids)

			await event_bus.emit(
				EventType.CONTENT_REMOVE_COMPLETED,
				node_id = str(node_index),
				data    = {
					"node_index" : node_index,
					"node_type"  : node.type,
					"removed"    : removed,
				}
			)

			result = {
				"status"     : "ok",
				"node_index" : node_index,
				"node_type"  : node.type,
				"removed"    : [
					{"id": id, "success": success}
					for id, success in zip(request.ids, removed)
				],
			}
			return result

		except HTTPException:
			raise
		except Exception as e:
			log_print(f"Error removing contents: {e}")
			await event_bus.emit(
				EventType.CONTENT_REMOVE_FAILED,
				node_id = str(node_index),
				error   = str(e),
				data    = {
					"node_index" : node_index,
				}
			)
			raise HTTPException(status_code=500, detail=str(e))


	@app.websocket("/events")
	async def workflow_events(websocket: WebSocket):
		nonlocal event_bus
		await event_bus.add_websocket_client(websocket)
		try:
			while True:
				data = await websocket.receive_text()
				# Handle filter subscription messages
				try:
					msg = json.loads(data)
					if isinstance(msg, dict):
						msg_type = msg.get("type")
						if msg_type == "subscribe":
							filters = msg.get("filters", {})
							event_bus.set_websocket_filter(websocket, filters)
							await websocket.send_text(json.dumps({"type": "subscribed", "filters": filters}))
							continue
						elif msg_type == "unsubscribe":
							event_bus.set_websocket_filter(websocket, None)
							await websocket.send_text(json.dumps({"type": "unsubscribed"}))
							continue
				except (json.JSONDecodeError, TypeError):
					pass
				log_print(f"Received WebSocket message: {data}")
		except WebSocketDisconnect:
			log_print("WebSocket client disconnected")
		except Exception as e:
			log_print(f"WebSocket error: {e}")
		event_bus.remove_websocket_client(websocket)

	# =========================================================================
	# EVENT SOURCE MANAGEMENT API
	# =========================================================================

	_previous_lifespan = app.router.lifespan_context

	@asynccontextmanager
	async def _api_lifespan(_app: FastAPI):
		async with _previous_lifespan(_app):
			await init_event_registry()
			log_print("✅ Event source registry initialized")
			try:
				yield
			finally:
				await shutdown_event_registry()
				log_print("✅ Event source registry shut down")

	app.router.lifespan_context = _api_lifespan

	@app.post("/event-sources/list")
	async def list_event_sources():
		"""List all registered event sources"""
		registry = get_event_registry()
		return {
			"status": "ok",
			"sources": registry.list_sources()
		}

	@app.post("/event-sources/get/{source_id}")
	async def get_event_source(source_id: str):
		"""Get a specific event source"""
		registry = get_event_registry()
		source = registry.get(source_id)
		if not source:
			raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
		return {
			"status": "ok",
			"source": source.get_status()
		}

	@app.post("/event-sources/timer")
	async def create_timer_source(config: TimerSourceConfig):
		"""Create a new timer event source"""
		registry = get_event_registry()
		try:
			source = await registry.register(config)
			return {
				"status": "created",
				"source": source.get_status()
			}
		except ValueError as e:
			raise HTTPException(status_code=400, detail=str(e))

	@app.post("/event-sources/fswatch")
	async def create_fswatch_source(config: FSWatchSourceConfig):
		"""Create a new filesystem watcher event source"""
		registry = get_event_registry()
		try:
			source = await registry.register(config)
			return {
				"status": "created",
				"source": source.get_status()
			}
		except ValueError as e:
			raise HTTPException(status_code=400, detail=str(e))

	@app.post("/event-sources/webhook")
	async def create_webhook_source(config: WebhookSourceConfig):
		"""Create a new webhook event source"""
		registry = get_event_registry()
		try:
			source = await registry.register(config)
			return {
				"status": "created",
				"source": source.get_status()
			}
		except ValueError as e:
			raise HTTPException(status_code=400, detail=str(e))

	@app.post("/event-sources/browser")
	async def create_browser_source(config: BrowserSourceConfig):
		"""Create or update a browser event source (webcam, microphone, etc.)"""
		registry = get_event_registry()
		if registry.get(config.id):
			source = await registry.update(config.id, config)
			return {
				"status": "updated",
				"source": source.get_status()
			}
		try:
			source = await registry.register(config)
			return {
				"status": "created",
				"source": source.get_status()
			}
		except ValueError as e:
			raise HTTPException(status_code=400, detail=str(e))

	@app.post("/event-sources/browser/{source_id}/event")
	async def receive_browser_event(source_id: str, data: dict):
		"""Receive a browser media event (frame, audio chunk) from the frontend"""
		registry = get_event_registry()
		source = registry.get(source_id)
		if not source:
			raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
		if not isinstance(source, BrowserSource):
			raise HTTPException(status_code=400, detail=f"Source {source_id} is not a browser source")
		if not source.is_running:
			raise HTTPException(status_code=400, detail=f"Source {source_id} is not running")
		client_id = data.pop("client_id", None)
		# Decode data-url image to ndarray (event mode sends base64 data-urls)
		if "data" in data and isinstance(data["data"], str) and data["data"].startswith("data:image"):
			b64_part = data["data"].split(",", 1)[1]
			img_bytes = base64.b64decode(b64_part)
			frame_array = _decode_frame_to_ndarray(img_bytes)
			data["frame"]        = frame_array
			data["frame_format"] = "ndarray"
			data["frame_shape"]  = frame_array.shape
			data["frame_dtype"]  = str(frame_array.dtype)
			del data["data"]
		await source.receive_event(data, client_id=client_id)
		return {"status": "ok"}

	@app.websocket("/ws/stream/{source_id}")
	async def stream_websocket(websocket: WebSocket, source_id: str):
		"""Binary WebSocket for high-speed media streaming.

		Browser sends:
		  - Binary messages: raw JPEG/WebP frames (for backend inference)
		  - Text messages:   JSON data (keypoints from frontend inference, or control)

		Server sends:
		  - Text messages: JSON stream.display events (overlay data to render)
		"""
		registry = get_event_registry()
		source   = registry.get(source_id)

		if not source or not isinstance(source, BrowserSource):
			await websocket.close(code=4004, reason=f"Browser source not found: {source_id}")
			return

		await websocket.accept()
		client_id = f"ws_{id(websocket)}"
		source.add_client(client_id)

		# Forward STREAM_DISPLAY events that target this source back to the browser
		async def on_stream_display(ev):
			if ev.data and ev.data.get("source_id") == source_id:
				try:
					payload     = ev.data.get("payload")
					render_type = ev.data.get("render_type", "pose")

					if isinstance(payload, np.ndarray) and payload.ndim == 3:
						# Image ndarray -> JPEG bytes -> binary WebSocket
						img = Image.fromarray(payload)
						buf = io.BytesIO()
						img.save(buf, format="JPEG", quality=85)
						# Binary protocol: 1-byte type tag (0x01 = image) + JPEG
						await websocket.send_bytes(b'\x01' + buf.getvalue())
					else:
						await websocket.send_text(json.dumps({
							"type"        : "stream.display",
							"source_id"   : source_id,
							"render_type" : render_type,
							"payload"     : _json_safe(payload),
						}))
				except Exception:
					pass

		event_bus.subscribe(EventType.STREAM_DISPLAY, on_stream_display)

		try:
			while True:
				message = await websocket.receive()

				if message["type"] == "websocket.disconnect":
					break

				if message.get("bytes"):
					# Binary frame (JPEG / WebP) — decode to numpy ndarray
					frame_bytes = message["bytes"]
					frame_array = _decode_frame_to_ndarray(frame_bytes)
					await source.receive_event({
						"frame"        : frame_array,
						"frame_format" : "ndarray",
						"frame_size"   : len(frame_bytes),
						"frame_shape"  : frame_array.shape,
						"frame_dtype"  : str(frame_array.dtype),
					}, client_id=client_id)

				elif message.get("text"):
					# JSON payload (keypoints from frontend inference, metadata, etc.)
					try:
						data = json.loads(message["text"])
						await source.receive_event(data, client_id=client_id)
					except json.JSONDecodeError:
						pass

		except WebSocketDisconnect:
			pass
		finally:
			source.remove_client(client_id)
			event_bus.unsubscribe(EventType.STREAM_DISPLAY, on_stream_display)

	@app.post("/event-sources/delete/{source_id}")
	async def delete_event_source(source_id: str):
		"""Delete an event source"""
		registry = get_event_registry()
		try:
			await registry.unregister(source_id)
			return {
				"status": "deleted",
				"source_id": source_id
			}
		except ValueError as e:
			raise HTTPException(status_code=404, detail=str(e))

	@app.post("/event-sources/{source_id}/start")
	async def start_event_source(source_id: str):
		"""Manually start an event source"""
		registry = get_event_registry()
		source = registry.get(source_id)
		if not source:
			raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
		try:
			await source.start()
			return {
				"status": "started",
				"source": source.get_status()
			}
		except Exception as e:
			raise HTTPException(status_code=500, detail=str(e))

	@app.post("/event-sources/{source_id}/stop")
	async def stop_event_source(source_id: str):
		"""Manually stop an event source"""
		registry = get_event_registry()
		source = registry.get(source_id)
		if not source:
			raise HTTPException(status_code=404, detail=f"Source not found: {source_id}")
		try:
			await source.stop()
			return {
				"status": "stopped",
				"source": source.get_status()
			}
		except Exception as e:
			raise HTTPException(status_code=500, detail=str(e))

	@app.post("/event-sources/status")
	async def get_event_registry_status():
		"""Get overall event registry status"""
		registry = get_event_registry()
		return {
			"status": "ok",
			**registry.get_status()
		}


	# === Dynamic Options API ===

	_options_providers: Dict[str, callable] = {}

	def register_options_provider(key: str, fn: callable):
		_options_providers[key] = fn

	def _get_model_sources(context=None):
		return get_text_generation_sources()

	def _get_model_names(context=None):
		context = context or {}
		source = None
		if isinstance(context, dict):
			source = context.get("source") or context.get("model_source")
		return get_text_generation_models(model_source=source)

	def _get_agent_endpoint_kinds(context=None):
		return ["deployment", "a2a_remote"]

	def _get_agent_endpoint_modes(context=None):
		return ["consult", "delegate", "notify"]

	def _get_agent_endpoint_targets(request: Optional[Request] = None, context: Optional[Dict[str, Any]] = None):
		context = context or {}
		kind = str(context.get("kind") or "deployment").strip().lower() or "deployment"
		if kind != "deployment" or assistant_deployment_mgr is None:
			return []
		user = getattr(getattr(request, "state", None), "user", None) if request is not None else None
		if user is None:
			return []
		role = getattr(user, "role", None)
		role_value = getattr(role, "value", role)
		is_admin = str(role_value or "").lower() == "admin"
		items = assistant_deployment_mgr.list(user_id=user.id, is_admin=is_admin)
		options = []
		for item in items:
			deployment_id = str(item.get("id") or "").strip()
			if not deployment_id:
				continue
			name = str(item.get("name") or deployment_id).strip() or deployment_id
			status = str(item.get("status") or "").strip()
			description = str(item.get("description") or "").strip()
			label = name if name == deployment_id else f"{name} ({deployment_id})"
			meta_bits = []
			if status:
				meta_bits.append(status)
			if description:
				meta_bits.append(description)
			options.append(
				{
					"value": deployment_id,
					"label": label,
					"description": " · ".join(meta_bits),
				}
			)
		options.sort(key=lambda row: str(row.get("label") or "").lower())
		return options

	register_options_provider("model_sources", _get_model_sources)
	register_options_provider("model_names", _get_model_names)
	register_options_provider("published_app_model_sources", _get_model_sources)
	register_options_provider("published_app_model_names", _get_model_names)
	register_options_provider("agent_endpoint_kinds", _get_agent_endpoint_kinds)
	register_options_provider("agent_endpoint_modes", _get_agent_endpoint_modes)
	register_options_provider("agent_endpoint_targets", _get_agent_endpoint_targets)

	@app.post("/options/{provider_key}")
	async def get_options(provider_key: str, request: Request, context: Optional[Dict[str, Any]] = None):
		if provider_key not in _options_providers:
			raise HTTPException(status_code=404, detail=f"Unknown options provider: {provider_key}")
		fn = _options_providers[provider_key]
		try:
			param_count = len(signature(fn).parameters)
		except Exception:
			param_count = 1
		if param_count >= 2:
			options = await fn(request, context) if iscoroutinefunction(fn) else fn(request, context)
		else:
			options = await fn(context) if iscoroutinefunction(fn) else fn(context)
		return {"options": options}


	# === Proactive Substrate API (Phase 3 M3.3 — Vitals UI) ===

	@app.post("/proactive/vitals")
	async def proactive_vitals(body: Optional[Dict[str, Any]] = None):
		"""Compute Vitals from the persistent Ledger written by the proactive
		substrate workflows. Returns counts bucketed by trigger topic so
		observations and action attempts are tracked separately.
		"""
		from proactive.persistence import read_jsonl, state_dir
		ledger = read_jsonl("ledger")

		decisions       : Dict[str, int] = {}
		motor_states    : Dict[str, int] = {}
		trigger_topics  : Dict[str, int] = {}
		injection_hits  = 0
		consent_pending = 0
		latencies       : list             = []

		for entry in ledger:
			topic = (entry.get("trigger") or {}).get("topic", "unknown")
			trigger_topics[topic] = trigger_topics.get(topic, 0) + 1

			verdict = entry.get("governor_verdict")
			if verdict:
				d = verdict.get("decision", "unknown")
				decisions[d] = decisions.get(d, 0) + 1

			motor = entry.get("motor_status")
			if motor:
				motor_states[motor] = motor_states.get(motor, 0) + 1

			# Pull injection hits out of the provenance trail
			for prov in (entry.get("provenance") or []):
				if prov.get("stage") == "adversarial" and prov.get("injection_hits"):
					injection_hits += len(prov["injection_hits"])

			if (entry.get("social_consent_request") or {}).get("status") == "awaiting_user":
				consent_pending += 1

			ts_first = next((p.get("ts") for p in (entry.get("provenance") or []) if "ts" in p), None)
			if ts_first and entry.get("ts"):
				latencies.append(entry["ts"] - ts_first)

		import time as _t
		return {
			"updated_at":             _t.time(),
			"state_dir":              str(state_dir()),
			"ledger_count":           len(ledger),
			"trigger_topics":         trigger_topics,
			"governor_decisions":     decisions,
			"motor_status_counts":    motor_states,
			"injection_hits_total":   injection_hits,
			"consent_pending":        consent_pending,
			"avg_pipeline_latency_s": (sum(latencies) / len(latencies)) if latencies else 0.0,
		}


	@app.post("/proactive/ledger")
	async def proactive_ledger(body: Optional[Dict[str, Any]] = None):
		"""Tail of the persistent Ledger. Body: {limit?: int, since_id?: str}.
		Returns most recent entries first."""
		from proactive.persistence import read_jsonl
		body = body or {}
		try:
			limit = int(body.get("limit", 25))
		except (TypeError, ValueError):
			limit = 25
		limit = max(1, min(500, limit))

		entries = read_jsonl("ledger")
		since_id = str(body.get("since_id") or "").strip()
		if since_id:
			# Drop everything up to and including since_id
			cut = next((i for i, e in enumerate(entries) if e.get("id") == since_id), -1)
			if cut >= 0:
				entries = entries[cut + 1:]

		entries = list(reversed(entries))[:limit]
		return {"entries": entries, "count": len(entries)}


	# === Proactive Quarantine + Snapshots (Phase 3 M3.4) ===

	@app.post("/proactive/quarantine")
	async def proactive_quarantine_list(body: Optional[Dict[str, Any]] = None):
		from proactive.quarantine import list_keys
		return {"keys": list_keys()}


	@app.post("/proactive/quarantine/release")
	async def proactive_quarantine_release(body: Optional[Dict[str, Any]] = None):
		from proactive.quarantine import release
		body = body or {}
		key    = str(body.get("key") or "").strip()
		reason = str(body.get("reason") or "manual")
		if not key:
			raise HTTPException(status_code=400, detail="missing 'key'")
		released = release(key, reason=reason)
		return {"key": key, "released": released}


	@app.post("/proactive/snapshots")
	async def proactive_snapshots_list(body: Optional[Dict[str, Any]] = None):
		from proactive.quarantine import list_snapshots
		return {"snapshots": list_snapshots()}


	@app.post("/proactive/snapshot/take")
	async def proactive_snapshot_take(body: Optional[Dict[str, Any]] = None):
		from proactive.quarantine import take_snapshot
		body  = body or {}
		label = str(body.get("label") or "").strip()
		manifest = take_snapshot(label=label)
		return {"snapshot": manifest}


	@app.post("/proactive/snapshot/restore")
	async def proactive_snapshot_restore(body: Optional[Dict[str, Any]] = None):
		from proactive.quarantine import restore_snapshot
		body = body or {}
		snapshot_id = str(body.get("snapshot_id") or "").strip()
		if not snapshot_id:
			raise HTTPException(status_code=400, detail="missing 'snapshot_id'")
		try:
			result = restore_snapshot(snapshot_id)
		except FileNotFoundError as exc:
			raise HTTPException(status_code=404, detail=str(exc))
		return result


	@app.post("/proactive/snapshot/delete")
	async def proactive_snapshot_delete(body: Optional[Dict[str, Any]] = None):
		from proactive.quarantine import delete_snapshot
		body = body or {}
		snapshot_id = str(body.get("snapshot_id") or "").strip()
		if not snapshot_id:
			raise HTTPException(status_code=400, detail="missing 'snapshot_id'")
		deleted = delete_snapshot(snapshot_id)
		return {"snapshot_id": snapshot_id, "deleted": deleted}


	# === Proactive Evolution / Alignment (Phase 4 M4.1) ===

	@app.post("/proactive/feedback")
	async def proactive_feedback(body: Optional[Dict[str, Any]] = None):
		"""Record an Alignment signal. Body:
		   {target_id: str, kind: str, value: any, context?: dict}
		   kind in {"thumbs", "edit", "preference"}.
		"""
		from proactive.evolution import record_feedback, VALID_KINDS
		body = body or {}
		target_id = str(body.get("target_id") or "").strip()
		kind      = str(body.get("kind") or "").strip()
		if not target_id:
			raise HTTPException(status_code=400, detail="missing 'target_id'")
		if kind not in VALID_KINDS:
			raise HTTPException(status_code=400,
								 detail=f"kind must be one of {sorted(VALID_KINDS)}")
		entry = record_feedback(
			target_id = target_id,
			kind      = kind,
			value     = body.get("value"),
			context   = body.get("context") or {},
		)
		return {"entry": entry}


	@app.post("/proactive/feedback/list")
	async def proactive_feedback_list(body: Optional[Dict[str, Any]] = None):
		from proactive.evolution import list_feedback
		body  = body or {}
		try:
			limit = int(body.get("limit", 50))
		except (TypeError, ValueError):
			limit = 50
		since = body.get("since")
		if since is not None:
			try:
				since = float(since)
			except (TypeError, ValueError):
				since = None
		kind = body.get("kind") or None
		entries = list_feedback(since=since, kind=kind, limit=limit)
		return {"entries": entries, "count": len(entries)}


	@app.post("/proactive/feedback/implicit")
	async def proactive_feedback_implicit(body: Optional[Dict[str, Any]] = None):
		"""Record an implicit feedback signal derived from operator action.
		Body: {target_id: str, signal: str, context?: dict}.
		`signal` is one of the controlled vocabulary in
		_IMPLICIT_REJECT_SIGNALS / _IMPLICIT_ACCEPT_SIGNALS — see
		proactive.evolution. The signal name decides whether the entry is
		recorded as implicit_accept or implicit_reject."""
		from proactive.evolution import record_implicit_signal
		body = body or {}
		target_id = str(body.get("target_id") or "").strip()
		signal    = str(body.get("signal")    or "").strip()
		if not target_id:
			raise HTTPException(status_code=400, detail="missing 'target_id'")
		if not signal:
			raise HTTPException(status_code=400, detail="missing 'signal'")
		try:
			entry = record_implicit_signal(
				target_id = target_id,
				signal    = signal,
				context   = body.get("context") or {},
			)
		except ValueError as exc:
			raise HTTPException(status_code=400, detail=str(exc))
		return {"entry": entry}


	# === M5.9 — Proactive runtime config overlay ============================

	@app.post("/proactive/state_dir")
	async def proactive_state_dir(body: Optional[Dict[str, Any]] = None):
		"""Report the live proactive state directory + how it was resolved.

		`source` is one of:
		  - "override" — a per-run override is active in this task's context
		                  (X-Proactive-Dir HTTP header, workflow option,
		                  or proactive_state_dir_flow node).
		  - "env"      — picked up from NUMEL_PROACTIVE_DIR
		                  (set by `app.py --proactive-dir <path>` or by
		                  the operator's shell environment).
		  - "default"  — fell back to `<repo>/app/storage/proactive`.

		Pass `X-Proactive-Dir: <path>` on the request to test how a
		per-request override resolves — this endpoint reports the path it
		would actually use, not just the configured ones."""
		from proactive.persistence import state_dir, state_dir_source
		env_value = (os.environ.get("NUMEL_PROACTIVE_DIR") or "").strip()
		return {
			"path":      str(state_dir()),
			"source":    state_dir_source(),
			"env_var":   "NUMEL_PROACTIVE_DIR",
			"env_value": env_value or None,
		}


	@app.post("/proactive/config")
	async def proactive_config_get(body: Optional[Dict[str, Any]] = None):
		"""Return the live overlay file contents + the catalogue of paths the
		proactive modules consult (so operators can discover what's tunable).
		The overlay overrides in-code defaults; any path NOT in the overlay
		uses the constant defined in the module."""
		from proactive.config import get_overrides, list_known_paths
		return {
			"overrides":   get_overrides(),
			"known_paths": list_known_paths(),
		}


	@app.post("/proactive/config/set")
	async def proactive_config_set(body: Optional[Dict[str, Any]] = None):
		"""Body: {path: str, value: any}. Persist `value` at `path`. The new
		overlay is returned. Setting a path outside the known-paths list is
		allowed (forward-compat) but has no runtime effect unless a module
		reads it. Known paths: see /proactive/config."""
		from proactive.config import set_override
		body = body or {}
		path = str(body.get("path") or "").strip()
		if not path:
			raise HTTPException(status_code=400, detail="missing 'path'")
		if "value" not in body:
			raise HTTPException(status_code=400, detail="missing 'value'")
		try:
			overrides = set_override(path, body["value"])
		except ValueError as exc:
			raise HTTPException(status_code=400, detail=str(exc))
		return {"path": path, "overrides": overrides}


	@app.post("/proactive/config/clear")
	async def proactive_config_clear(body: Optional[Dict[str, Any]] = None):
		"""Body: {path?: str}. Clear a single override path, or the entire
		overlay when `path` is omitted. Returns the resulting overlay dict."""
		from proactive.config import clear_override
		body = body or {}
		path = body.get("path")
		if path is not None:
			path = str(path).strip() or None
		overrides = clear_override(path)
		return {"cleared": path, "overrides": overrides}


	@app.post("/proactive/evolution/proposer")
	async def proactive_evolution_proposer_status(body: Optional[Dict[str, Any]] = None):
		"""Status of the LLM-backed Evolution proposer (M5.8-B). Returns
		whether an `agent.evolution_proposer` Capability is registered;
		registration itself is Python-only (handlers are not
		JSON-serialisable). To wire one up: from your in-process code,
		`proactive.agents.register_agent_handler('evolution_proposer',
		<handler>, kind=KIND_LOCAL)` — typically backed by an Agno agent."""
		from proactive.optimization import (
			llm_proposer_registered, LLM_PROPOSER_ALIAS,
		)
		return {
			"alias":      LLM_PROPOSER_ALIAS,
			"cap_name":   f"agent.{LLM_PROPOSER_ALIAS}",
			"registered": llm_proposer_registered(),
		}


	@app.post("/proactive/motor/undo")
	async def proactive_motor_undo(body: Optional[Dict[str, Any]] = None):
		"""Convenience wrapper — records an `action_undone` implicit-reject
		signal against the action_id (and optionally the underlying
		capability) so the proposer can learn from manual reversals.
		Body: {action_id: str, capability?: str, reason?: str}.
		This endpoint records the signal only; reversing the side-effect of
		the original capability is the caller's responsibility (different
		capabilities have very different reversal semantics)."""
		from proactive.evolution import record_implicit_signal
		body = body or {}
		action_id  = str(body.get("action_id") or "").strip()
		capability = str(body.get("capability") or "").strip() or None
		reason     = str(body.get("reason")     or "").strip() or None
		if not action_id:
			raise HTTPException(status_code=400, detail="missing 'action_id'")
		ctx: Dict[str, Any] = {"action_id": action_id}
		if capability: ctx["capability"] = capability
		if reason:     ctx["reason"]     = reason
		entry = record_implicit_signal(
			target_id = action_id,
			signal    = "action_undone",
			context   = ctx,
		)
		return {"entry": entry}


	@app.post("/proactive/constitution")
	async def proactive_constitution(body: Optional[Dict[str, Any]] = None):
		from proactive.evolution import read_constitution
		return read_constitution()


	@app.post("/proactive/constitution/update")
	async def proactive_constitution_update(body: Optional[Dict[str, Any]] = None):
		from proactive.evolution import update_constitution
		body = body or {}
		patch = body.get("patch") if isinstance(body.get("patch"), dict) else body
		try:
			return update_constitution(patch or {})
		except ValueError as exc:
			raise HTTPException(status_code=400, detail=str(exc))


	@app.post("/proactive/alignment/validators")
	async def proactive_alignment_validators(body: Optional[Dict[str, Any]] = None):
		from proactive.evolution import list_validators
		return {"validators": list_validators()}


	@app.post("/proactive/alignment/check")
	async def proactive_alignment_check(body: Optional[Dict[str, Any]] = None):
		"""Run every registered Alignment validator over the candidate.
		Returns aggregate decision + per-validator verdict trail."""
		from proactive.evolution import run_alignment
		body = body or {}
		candidate = body.get("candidate") if isinstance(body.get("candidate"), dict) else body
		return run_alignment(candidate or {})


	# === Proactive Optimization (Phase 4 M4.2) ===

	@app.post("/proactive/optimization/propose")
	async def proactive_optimization_propose(body: Optional[Dict[str, Any]] = None):
		"""Run every built-in Self-Reflective strategy against current
		live state and return the resulting candidates."""
		from proactive.optimization import propose_from_state
		candidates = propose_from_state()
		return {"candidates": candidates, "count": len(candidates)}


	@app.post("/proactive/optimization/simulate")
	async def proactive_optimization_simulate(body: Optional[Dict[str, Any]] = None):
		"""Replay the historical Ledger against `candidate`. Body shape:
		{candidate: {kind, target, payload, ...}}. Returns a diff report;
		never applies the change."""
		from proactive.optimization import simulate_candidate
		body = body or {}
		candidate = body.get("candidate") if isinstance(body.get("candidate"), dict) else body
		if not candidate:
			raise HTTPException(status_code=400, detail="missing 'candidate'")
		return simulate_candidate(candidate)


	# === Proactive Promotion gate (Phase 4 M4.3) ===

	@app.post("/proactive/promotion/promote")
	async def proactive_promote(body: Optional[Dict[str, Any]] = None):
		"""Run the Promotion chain: simulate (optional) -> alignment chain
		-> apply (if every validator passed). Records a Ledger entry
		regardless of outcome. Body: {candidate: {...}, simulate?: bool}.
		"""
		from proactive.promotion import promote
		body = body or {}
		candidate = body.get("candidate") if isinstance(body.get("candidate"), dict) else body
		if not candidate:
			raise HTTPException(status_code=400, detail="missing 'candidate'")
		simulate = bool(body.get("simulate", True))
		try:
			return promote(candidate, simulate=simulate)
		except ValueError as exc:
			raise HTTPException(status_code=400, detail=str(exc))


	# === Proactive External Integrations (Phase 5 M5.1 — MCP) ===

	@app.post("/proactive/mcp/tools")
	async def proactive_mcp_tools(body: Optional[Dict[str, Any]] = None):
		"""Return the local Capability Registry in MCP tool-descriptor
		shape so an MCP client can fetch what Numel exposes."""
		from proactive.mcp import list_tools_as_mcp
		return {"tools": list_tools_as_mcp()}


	@app.post("/proactive/mcp/call")
	async def proactive_mcp_call(body: Optional[Dict[str, Any]] = None):
		"""Invoke a registered capability through the Substrate gates
		(Adversarial filter on args -> Alignment chain -> handler ->
		Privacy gate on response). Body: {name, arguments?: {...}}."""
		from proactive.mcp import call_tool
		body = body or {}
		name = str(body.get("name") or "").strip()
		if not name:
			raise HTTPException(status_code=400, detail="missing 'name'")
		args = body.get("arguments") if isinstance(body.get("arguments"), dict) else {}
		return call_tool(name, args)


	@app.post("/proactive/mcp/register_remote")
	async def proactive_mcp_register_remote(body: Optional[Dict[str, Any]] = None):
		"""Register a peer's MCP tool descriptor as a local capability,
		namespaced as `mcp.<server>.<tool.name>`. Body: {server, tool,
		scopes?: [str]}."""
		from proactive.mcp import register_remote
		body = body or {}
		server = str(body.get("server") or "").strip()
		tool   = body.get("tool")
		scopes = body.get("scopes")
		if not server or not isinstance(tool, dict):
			raise HTTPException(status_code=400, detail="missing 'server' or 'tool'")
		try:
			entry = register_remote(server, tool, scopes=scopes if isinstance(scopes, list) else None)
		except ValueError as exc:
			raise HTTPException(status_code=400, detail=str(exc))
		return {"entry": entry}


	@app.post("/proactive/mcp/remote_tools")
	async def proactive_mcp_remote_tools(body: Optional[Dict[str, Any]] = None):
		from proactive.mcp import list_remote
		return {"remote_tools": list_remote()}


	@app.post("/proactive/mcp/drop_remote")
	async def proactive_mcp_drop_remote(body: Optional[Dict[str, Any]] = None):
		from proactive.mcp import drop_remote
		body = body or {}
		name = str(body.get("name") or "").strip()
		if not name:
			raise HTTPException(status_code=400, detail="missing 'name'")
		return {"name": name, "dropped": drop_remote(name)}


	@app.post("/proactive/mcp/calls")
	async def proactive_mcp_calls(body: Optional[Dict[str, Any]] = None):
		"""Return the most-recent MCP-call traces (newest first)."""
		from proactive.mcp import list_calls
		body  = body or {}
		try:
			limit = int(body.get("limit", 25))
		except (TypeError, ValueError):
			limit = 25
		entries = list_calls(limit=limit)
		return {"entries": entries, "count": len(entries)}


	# === Proactive A2A Federation (Phase 5 M5.2) ===

	@app.post("/proactive/a2a/peers")
	async def proactive_a2a_peers(body: Optional[Dict[str, Any]] = None):
		from proactive.a2a import list_peers
		return {"peers": list_peers()}


	@app.post("/proactive/a2a/peers/register")
	async def proactive_a2a_peers_register(body: Optional[Dict[str, Any]] = None):
		"""Register or update a peer. Body: {peer_id, tier, name?, contact?}.
		tier in {peer, partner, federated}."""
		from proactive.a2a import register_peer
		body = body or {}
		peer_id = str(body.get("peer_id") or "").strip()
		tier    = str(body.get("tier")    or "").strip()
		if not peer_id:
			raise HTTPException(status_code=400, detail="missing 'peer_id'")
		try:
			entry = register_peer(
				peer_id,
				tier=tier,
				name=body.get("name"),
				contact=body.get("contact"),
			)
		except ValueError as exc:
			raise HTTPException(status_code=400, detail=str(exc))
		return {"entry": entry}


	@app.post("/proactive/a2a/peers/drop")
	async def proactive_a2a_peers_drop(body: Optional[Dict[str, Any]] = None):
		from proactive.a2a import drop_peer
		body = body or {}
		peer_id = str(body.get("peer_id") or "").strip()
		if not peer_id:
			raise HTTPException(status_code=400, detail="missing 'peer_id'")
		return {"peer_id": peer_id, "dropped": drop_peer(peer_id)}


	@app.post("/proactive/a2a/receive")
	async def proactive_a2a_receive(body: Optional[Dict[str, Any]] = None):
		"""Inbound message from a peer. Body: {peer_id, message, kind?}.
		Adversarial filter applied; quarantined on injection_hits."""
		from proactive.a2a import receive
		body = body or {}
		peer_id = str(body.get("peer_id") or "").strip()
		if not peer_id:
			raise HTTPException(status_code=400, detail="missing 'peer_id'")
		kind = str(body.get("kind") or "message")
		return receive(peer_id, body.get("message"), kind=kind)


	@app.post("/proactive/a2a/send")
	async def proactive_a2a_send(body: Optional[Dict[str, Any]] = None):
		"""Outbound message to a peer. Body: {peer_id, message, kind?}."""
		from proactive.a2a import send
		body = body or {}
		peer_id = str(body.get("peer_id") or "").strip()
		if not peer_id:
			raise HTTPException(status_code=400, detail="missing 'peer_id'")
		kind = str(body.get("kind") or "message")
		return send(peer_id, body.get("message"), kind=kind)


	@app.post("/proactive/a2a/share_state")
	async def proactive_a2a_share_state(body: Optional[Dict[str, Any]] = None):
		"""Share World Model excerpts with a peer. Body: {peer_id,
		namespaces: [str]}. Tier-gated; redacted via Privacy gate."""
		from proactive.a2a import share_state
		body = body or {}
		peer_id    = str(body.get("peer_id") or "").strip()
		namespaces = body.get("namespaces") if isinstance(body.get("namespaces"), list) else []
		if not peer_id:
			raise HTTPException(status_code=400, detail="missing 'peer_id'")
		return share_state(peer_id, namespaces)


	@app.post("/proactive/a2a/inbox")
	async def proactive_a2a_inbox(body: Optional[Dict[str, Any]] = None):
		from proactive.a2a import list_inbox
		body  = body or {}
		try:    limit = int(body.get("limit", 25))
		except (TypeError, ValueError): limit = 25
		entries = list_inbox(limit=limit)
		return {"entries": entries, "count": len(entries)}


	@app.post("/proactive/a2a/outbox")
	async def proactive_a2a_outbox(body: Optional[Dict[str, Any]] = None):
		from proactive.a2a import list_outbox
		body  = body or {}
		try:    limit = int(body.get("limit", 25))
		except (TypeError, ValueError): limit = 25
		entries = list_outbox(limit=limit)
		return {"entries": entries, "count": len(entries)}


	@app.post("/proactive/a2a/shared")
	async def proactive_a2a_shared(body: Optional[Dict[str, Any]] = None):
		from proactive.a2a import list_shared
		body  = body or {}
		try:    limit = int(body.get("limit", 25))
		except (TypeError, ValueError): limit = 25
		entries = list_shared(limit=limit)
		return {"entries": entries, "count": len(entries)}


	# === Proactive Generic Transports (Phase 5 M5.3) ===

	@app.post("/proactive/transports")
	async def proactive_transports_list(body: Optional[Dict[str, Any]] = None):
		from proactive.transports import list_transports
		return {"transports": list_transports()}


	@app.post("/proactive/transports/register")
	async def proactive_transports_register(body: Optional[Dict[str, Any]] = None):
		"""Body: {alias, kind, base_url, model, api_key_env?, scopes?, extra?}."""
		from proactive.transports import register_transport
		body = body or {}
		alias = str(body.get("alias") or "").strip()
		kind  = str(body.get("kind")  or "").strip()
		base_url = str(body.get("base_url") or "").strip()
		model    = str(body.get("model")    or "").strip()
		try:
			cfg = register_transport(
				alias,
				kind        = kind,
				base_url    = base_url,
				model       = model,
				api_key_env = body.get("api_key_env"),
				scopes      = body.get("scopes") if isinstance(body.get("scopes"), list) else None,
				extra       = body.get("extra")  if isinstance(body.get("extra"),  dict) else None,
			)
		except ValueError as exc:
			raise HTTPException(status_code=400, detail=str(exc))
		return {"transport": cfg}


	@app.post("/proactive/transports/drop")
	async def proactive_transports_drop(body: Optional[Dict[str, Any]] = None):
		from proactive.transports import drop_transport
		body  = body or {}
		alias = str(body.get("alias") or "").strip()
		if not alias:
			raise HTTPException(status_code=400, detail="missing 'alias'")
		return {"alias": alias, "dropped": drop_transport(alias)}


	@app.post("/proactive/transports/call")
	async def proactive_transports_call(body: Optional[Dict[str, Any]] = None):
		"""Invoke a registered transport. Body: {alias, prompt, dry_run?}.
		dry_run defaults to False; pass True to skip the HTTP call."""
		from proactive.transports import call_transport
		body  = body or {}
		alias = str(body.get("alias") or "").strip()
		prompt = body.get("prompt")
		if not alias:
			raise HTTPException(status_code=400, detail="missing 'alias'")
		dry_run = bool(body.get("dry_run", False))
		return call_transport(alias, prompt or "", dry_run=dry_run)


	@app.post("/proactive/transports/calls")
	async def proactive_transports_calls(body: Optional[Dict[str, Any]] = None):
		from proactive.transports import list_calls
		body  = body or {}
		try:    limit = int(body.get("limit", 25))
		except (TypeError, ValueError): limit = 25
		entries = list_calls(limit=limit)
		return {"entries": entries, "count": len(entries)}


	# === M5.4 — Local agent capability bridge ================================

	@app.post("/proactive/agents")
	async def proactive_agents_list(body: Optional[Dict[str, Any]] = None):
		from proactive.agents import list_agents
		return {"agents": list_agents()}


	@app.post("/proactive/agents/drop")
	async def proactive_agents_drop(body: Optional[Dict[str, Any]] = None):
		"""Body: {alias, kind?}. `kind` defaults to 'local'; pass 'endpoint'
		or 'a2a' to drop the namespaced cap. Idempotent."""
		from proactive.agents import drop_agent, KIND_LOCAL
		body  = body or {}
		alias = str(body.get("alias") or body.get("cap_name") or "").strip()
		kind  = str(body.get("kind") or KIND_LOCAL).strip() or KIND_LOCAL
		if not alias:
			raise HTTPException(status_code=400, detail="missing 'alias' or 'cap_name'")
		return {"alias": alias, "dropped": drop_agent(alias, kind=kind)}


	@app.post("/proactive/agents/call")
	async def proactive_agents_call(body: Optional[Dict[str, Any]] = None):
		"""Invoke a registered agent capability through the gate chain.
		Body: {alias, request, kind?, image?, extra_args?}."""
		from proactive.agents import call_agent, KIND_LOCAL
		body    = body or {}
		alias   = str(body.get("alias") or "").strip()
		request = body.get("request")
		kind    = str(body.get("kind") or KIND_LOCAL).strip() or KIND_LOCAL
		image   = body.get("image")
		extra   = body.get("extra_args") if isinstance(body.get("extra_args"), dict) else None
		if not alias:
			raise HTTPException(status_code=400, detail="missing 'alias'")
		if request is None:
			raise HTTPException(status_code=400, detail="missing 'request'")
		return call_agent(alias, request, image=image, kind=kind, extra_args=extra)


	@app.post("/proactive/agents/calls")
	async def proactive_agents_calls(body: Optional[Dict[str, Any]] = None):
		from proactive.agents import list_calls
		body  = body or {}
		try:    limit = int(body.get("limit", 25))
		except (TypeError, ValueError): limit = 25
		entries = list_calls(limit=limit)
		return {"entries": entries, "count": len(entries)}


	# === Sub-Graph Templates API ===

	_templates_path = str(Path(__file__).parent / "templates.json")

	def _load_templates() -> list:
		if not os.path.exists(_templates_path):
			return []
		try:
			with open(_templates_path, "r") as f:
				return json.load(f)
		except Exception as e:
			log_print(f"Error loading templates: {e}")
			return []

	def _save_templates(templates: list):
		try:
			with open(_templates_path, "w") as f:
				json.dump(templates, f, indent=2)
		except Exception as e:
			log_print(f"Error saving templates: {e}")

	@app.post("/templates/list")
	async def list_templates():
		templates = _load_templates()
		meta_list = []
		for t in templates:
			meta_list.append({
				"id":        t.get("id"),
				"name":      t.get("name", "Untitled"),
				"description": t.get("description", ""),
				"builtIn":   t.get("builtIn", False),
				"createdAt": t.get("createdAt", ""),
				"nodeCount": t.get("nodeCount", 0),
				"edgeCount": t.get("edgeCount", 0),
			})
		return {"templates": meta_list}

	@app.post("/templates/get/{template_id}")
	async def get_template(template_id: str):
		templates = _load_templates()
		for t in templates:
			if t.get("id") == template_id:
				return {"template": t}
		raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

	@app.post("/templates/save")
	async def save_template(request: TemplateSaveRequest):
		templates = _load_templates()
		tpl = request.template
		tpl_id = tpl.get("id")
		if not tpl_id:
			raise HTTPException(status_code=400, detail="Template must have an id")
		# Upsert
		found = False
		for i, t in enumerate(templates):
			if t.get("id") == tpl_id:
				if t.get("builtIn", False):
					raise HTTPException(status_code=403, detail="Cannot overwrite built-in template")
				templates[i] = tpl
				found = True
				break
		if not found:
			templates.append(tpl)
		_save_templates(templates)
		return {"status": "ok", "id": tpl_id}

	@app.post("/templates/delete/{template_id}")
	async def delete_template(template_id: str):
		templates = _load_templates()
		for t in templates:
			if t.get("id") == template_id:
				if t.get("builtIn", False):
					raise HTTPException(status_code=403, detail="Cannot delete built-in template")
				templates.remove(t)
				_save_templates(templates)
				return {"status": "ok"}
		raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

	@app.post("/templates/rename/{template_id}")
	async def rename_template(template_id: str, request: TemplateRenameRequest):
		templates = _load_templates()
		for t in templates:
			if t.get("id") == template_id:
				if t.get("builtIn", False):
					raise HTTPException(status_code=403, detail="Cannot rename built-in template")
				t["name"] = request.name
				_save_templates(templates)
				return {"status": "ok"}
		raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")


	# === Text-to-Workflow Generation API ===

	def _parse_nodeinfo_metadata(code: str) -> dict:
		"""Parse @node_info decorators from schema source. Returns {ClassName: {title,desc,section,visible,icon}}."""
		lines = code.split('\n')
		meta = {}
		i = 0
		while i < len(lines):
			s = lines[i].strip()
			if s.startswith('@node_info('):
				# Collect full decorator across lines (track paren depth)
				text  = s
				depth = s.count('(') - s.count(')')
				j     = i + 1
				while depth > 0 and j < len(lines):
					ns     = lines[j].strip()
					text  += ' ' + ns
					depth += ns.count('(') - ns.count(')')
					j     += 1
				# Look ahead past other decorators to find the class
				while j < len(lines):
					ns = lines[j].strip()
					cm = re.match(r'class\s+(\w+)', ns)
					if cm:
						cname   = cm.group(1)
						title_m = re.search(r'title\s*=\s*"([^"]+)"', text) or re.search(r"title\s*=\s*'([^']+)'", text)
						desc_m  = re.search(r'description\s*=\s*"([^"]+)"', text) or re.search(r"description\s*=\s*'([^']+)'", text)
						sect_m  = re.search(r'section\s*=\s*"([^"]+)"', text) or re.search(r"section\s*=\s*'([^']+)'", text)
						vis_m   = re.search(r'visible\s*=\s*(True|False)', text)
						icon_m  = re.search(r'icon\s*=\s*"([^"]+)"', text) or re.search(r"icon\s*=\s*'([^']+)'", text)
						meta[cname] = {
							'title':   title_m.group(1) if title_m else cname,
							'desc':    desc_m.group(1)  if desc_m  else '',
							'section': sect_m.group(1)  if sect_m  else 'Misc',
							'visible': not (vis_m and vis_m.group(1) == 'False'),
							'icon':    icon_m.group(1)  if icon_m  else '',
						}
						break
					elif ns and not ns.startswith(('@', '#', '"""', "'''")):
						break
					j += 1
			i += 1
		return meta

	def _build_node_catalog(code: str) -> str:
		"""Parse schema source code to build a detailed node catalog for the LLM."""
		node_meta = _parse_nodeinfo_metadata(code)
		lines     = code.split('\n')

		# ── Pre-parse DEFAULT_* constant values ───────────────────────────────
		defaults_map: dict = {}
		for line in lines:
			dm = re.match(r'^DEFAULT_(\w+)\s*:\s*\w+\s*=\s*(.+?)(?:\s*#.*)?$', line.strip())
			if dm:
				defaults_map[f'DEFAULT_{dm.group(1)}'] = dm.group(2).strip()

		# ── Type simplification helpers ────────────────────────────────────────
		def _simplify_type(ftype: str) -> str:
			ftype = re.sub(r'^Optional\[(.+)\]$', r'\1', ftype.strip())
			# Literal[...] → show all options as "a"|"b"|...
			lit_m = re.match(r'^Literal\[(.+)\]$', ftype)
			if lit_m:
				raw_opts = lit_m.group(1)
				opts = [o.strip().strip('"').strip("'") for o in raw_opts.split(',')]
				return '|'.join(f'"{o}"' for o in opts if o)
			return (ftype
				.replace('Dict[str, Any]',               'dict')
				.replace('Dict[Union[int, str], str]',   'dict')
				.replace('List[str]',                    'list[str]')
				.replace('List[Any]',                    'list')
				.replace('List[int]',                    'list[int]')
				.replace('Union[List, Dict]',            'dict|list')
				.replace('Union[int, str]',              'int|str')
				.replace('Union[List[str], Dict[str, Any]]', 'dict|list')
				.replace('Any',                          'any')
			)

		def _multi_item_type(ftype_raw: str) -> str:
			"""Extract item type T from Dict[str, T] for MULTI_INPUT/OUTPUT."""
			m = re.match(r'(?:Optional\[)?Dict\[(?:str|Union\[int,\s*str\]),\s*(.+?)\]', ftype_raw.strip())
			return m.group(1).strip() if m else ''

		def _resolve_default(raw: str):
			raw = raw.strip()
			if raw == 'None':
				return None
			# Field(default=...) — extract the default= argument
			fd_m = re.search(r'Field\(default\s*=\s*([^,\)]+)', raw)
			if fd_m:
				inner = fd_m.group(1).strip()
				return _resolve_default(inner)
			# Resolve DEFAULT_* reference
			if raw.startswith('DEFAULT_'):
				val = defaults_map.get(raw)
				if val is None:
					return None
				# val may itself be a quoted string; strip outer quotes for display
				return val
			if raw in ('True', 'False') or re.match(r'^["\'\d]', raw):
				return raw
			return None

		def _extract_description(rhs: str) -> str:
			"""Extract description= from a Field(...) RHS string."""
			m = re.search(r'description\s*=\s*"([^"]*)"', rhs)
			if not m:
				m = re.search(r"description\s*=\s*'([^']*)'" , rhs)
			return m.group(1) if m else ''

		# ── Per-class field parsing ────────────────────────────────────────────
		# Field tuple: (name, display_type, role, default, item_type, description)
		# item_type is only set for MULTI_INPUT/OUTPUT; others use ''
		# description extracted from Field(description="..."); empty string if absent
		nodes         = {}   # {ClassName: {type_val, fields, docstring, parent}}
		current_class  = None
		current_parent = None
		current_type   = None
		current_fields: list = []
		current_docstring    = None
		in_docstring         = False
		docstring_lines: list = []
		docstring_quote      = None
		expecting_doc        = False
		in_property          = False

		def _flush():
			nonlocal current_class, current_parent, current_type, current_fields
			nonlocal current_docstring, in_docstring, docstring_lines, docstring_quote
			nonlocal expecting_doc, in_property
			if current_class and current_type:
				nodes[current_class] = {
					'type':      current_type,
					'fields':    list(current_fields),
					'docstring': current_docstring,
					'parent':    current_parent,
				}
			current_class     = None
			current_parent    = None
			current_type      = None
			current_fields    = []
			current_docstring = None
			in_docstring      = False
			docstring_lines   = []
			docstring_quote   = None
			expecting_doc     = False
			in_property       = False

		for line in lines:
			s = line.strip()

			# New class
			cm = re.match(r'^class\s+(\w+)\s*\((\w+)', s)
			if cm:
				_flush()
				current_class  = cm.group(1)
				current_parent = cm.group(2)
				expecting_doc  = True
				continue

			if not current_class:
				continue

			# ── Multi-line docstring continuation ─────────────────────────────
			if in_docstring:
				if docstring_quote in s:
					idx  = s.index(docstring_quote)
					tail = s[:idx].strip()
					if tail:
						docstring_lines.append(tail)
					current_docstring = ' '.join(docstring_lines)
					in_docstring = False
				else:
					if s:
						docstring_lines.append(s)
				continue

			# ── Class docstring ────────────────────────────────────────────────
			if expecting_doc:
				if s.startswith(('"""', "'''")):
					q       = '"""' if s.startswith('"""') else "'''"
					content = s[len(q):]
					if q in content:
						# Single-line docstring
						current_docstring = content[:content.index(q)].strip()
						expecting_doc = False
					else:
						# Multi-line docstring — collect until closing quote
						docstring_lines = [content.strip()] if content.strip() else []
						docstring_quote = q
						in_docstring    = True
						expecting_doc   = False
					continue
				elif s and not s.startswith('#'):
					expecting_doc = False
				# fall through to field parsing

			# ── @property decorator ────────────────────────────────────────────
			if s == '@property':
				in_property = True
				continue

			# ── @property OUTPUT slot (any def name, not just 'get') ───────────
			pm = re.match(r'^def (\w+)\(self\)\s*->\s*Annotated\[(.+?),\s*FieldRole\.(OUTPUT)\]', s)
			if pm and in_property:
				fname = pm.group(1)
				ftype = re.sub(r'^Optional\[(.+)\]$', r'\1', pm.group(2).strip())
				current_fields.append((fname, _simplify_type(ftype), 'OUTPUT', None, '', ''))
				in_property = False
				continue

			# Reset in_property if something else appears between @property and def
			if in_property and s and not s.startswith(('#', 'def', '@')):
				in_property = False

			# ── Annotated field ────────────────────────────────────────────────
			fm = re.match(r'^(\w+)\s*:\s*Annotated\[(.+?),\s*FieldRole\.(\w+)', s)
			if fm:
				fname, ftype_raw, frole = fm.group(1), fm.group(2).strip(), fm.group(3)
				in_property = False

				if frole == 'CONSTANT' and 'Literal[' in ftype_raw:
					lm = re.search(r'Literal\["([^"]+)"\]', ftype_raw)
					if lm:
						current_type = lm.group(1)
					continue

				if frole == 'ANNOTATION':
					continue

				# Determine display type and item type
				if frole in ('MULTI_INPUT', 'MULTI_OUTPUT'):
					item_t  = _multi_item_type(ftype_raw)
					disp_t  = _simplify_type(ftype_raw)
				else:
					item_t = ''
					disp_t = _simplify_type(ftype_raw)

				# Resolve default value and description
				fdefault = None
				fdesc    = ''
				dm = re.search(r'\]\s*=\s*(.+?)(?:\s*#.*)?$', s)
				if dm:
					rhs      = dm.group(1).strip()
					fdefault = _resolve_default(rhs)
					fdesc    = _extract_description(rhs)

				current_fields.append((fname, disp_t, frole, fdefault, item_t, fdesc))

		_flush()

		# ── Inherit parent fields ──────────────────────────────────────────────
		# Fields declared on invisible base classes (FlowType, NativeType, etc.)
		# must be propagated to their visible children.
		# Blacklist: base-plumbing fields not useful for LLM wiring.
		_INHERIT_BLACKLIST = {'extra', 'id', 'raw'}

		def _get_all_fields(cname: str, visited=None) -> list:
			"""Return all fields (own + inherited) for a class, deduplicated by name."""
			if visited is None:
				visited = set()
			if cname in visited:
				return []
			visited.add(cname)
			info   = nodes.get(cname, {})
			own    = info.get('fields', [])   # own fields always included (no blacklist)
			parent = info.get('parent')
			if not parent or parent not in nodes:
				return own
			parent_fields = _get_all_fields(parent, visited)
			own_names     = {f[0] for f in own}
			# Blacklist applies only to *inherited* plumbing fields, never to own redeclarations
			inherited     = [f for f in parent_fields if f[0] not in own_names and f[0] not in _INHERIT_BLACKLIST]
			return inherited + own   # parent fields first, own last (own overrides)

		# ── Section grouping and formatting ───────────────────────────────────
		section_order = [
			'Endpoints', 'Native Types', 'Data Sources',
			'Configurations', 'Workflow', 'Loops', 'Event Sources',
			'Interactive', 'Tutorial',
		]
		section_labels = {
			'Endpoints':      '─── Endpoint Nodes',
			'Native Types':   '─── Native Value Nodes  (output their value on the "value" slot)',
			'Data Sources':   '─── Data Source Nodes',
			'Configurations': '─── Config Nodes  (wire using source_slot matching the "out:" slot name)',
			'Workflow':       '─── Flow Nodes',
			'Loops':          '─── Loop Nodes',
			'Event Sources':  '─── Event Source Nodes',
			'Interactive':    '─── Interactive Nodes',
			'Tutorial':       '─── Extension/Tutorial Nodes',
		}

		by_section: dict = {s: [] for s in section_order}
		for cname, info in nodes.items():
			m = node_meta.get(cname, {})
			if not m.get('visible', True):
				continue
			sect = m.get('section', 'Other')
			by_section.setdefault(sect, []).append((cname, info, m))

		def fmt_f(name: str, typ: str, dflt, desc: str = '') -> str:
			s = f'{name}({typ})'
			if dflt is not None:
				s += f'={dflt}'
			if desc:
				s += f' – {desc}'
			return s

		out_lines = []
		for sect in section_order:
			entries = by_section.get(sect, [])
			if not entries:
				continue
			out_lines.append(section_labels.get(sect, f'─── {sect}'))
			for cname, info, m in entries:
				type_val = info['type']
				all_fields = _get_all_fields(cname)
				desc = m.get('desc', '')
				icon = m.get('icon', '')

				in_f   = [f for f in all_fields if f[2] == 'INPUT']
				min_f  = [f for f in all_fields if f[2] == 'MULTI_INPUT']
				out_f  = [f for f in all_fields if f[2] == 'OUTPUT']
				mout_f = [f for f in all_fields if f[2] == 'MULTI_OUTPUT']

				header = (f'{icon} ' if icon else '') + type_val
				if desc:
					header += f' – {desc}'
				out_lines.append(header)

				doc = info.get('docstring', '')
				if doc:
					out_lines.append(f'  doc: {doc}')
				if in_f:
					out_lines.append('  in:  ' + ', '.join(fmt_f(f[0], f[1], f[3], f[5]) for f in in_f))
				for f in min_f:
					item_hint = f'(item:{f[4]})' if f[4] else ''
					dflt_hint = f'={f[3]}'        if f[3] is not None else ''
					desc_hint = f' – {f[5]}'      if f[5] else ''
					out_lines.append(f'  multi-in: {f[0]}{item_hint}{dflt_hint}{desc_hint} | wire each branch via target_slot="{f[0]}.<key>"')
				if out_f:
					out_lines.append('  out: ' + ', '.join(fmt_f(f[0], f[1], f[3], f[5]) for f in out_f))
				for f in mout_f:
					item_hint = f'(item:{f[4]})' if f[4] else ''
					dflt_hint = f'={f[3]}'        if f[3] is not None else ''
					desc_hint = f' – {f[5]}'      if f[5] else ''
					out_lines.append(f'  multi-out: {f[0]}{item_hint}{dflt_hint}{desc_hint} | declare in JSON as "{f[0]}": {{"key": null, ...}}; edge source_slot="{f[0]}.<key>"')
				out_lines.append('')

		return '\n'.join(out_lines)

	def _discover_all_toolkit_modules() -> List[str]:
		"""Scan app/toolkits/ and contrib/toolkits/ for *_toolkit.py modules."""
		import glob as _glob
		result = []
		try:
			_app_dir      = os.path.dirname(os.path.abspath(__file__))
			_project_root = os.path.dirname(_app_dir)
			for prefix, base_dir in [("toolkits.", os.path.join(_app_dir, "toolkits")),
			                         ("contrib.toolkits.", os.path.join(_project_root, "contrib", "toolkits"))]:
				for fpath in sorted(_glob.glob(os.path.join(base_dir, "*_toolkit.py"))):
					mod_name = prefix + os.path.basename(fpath).replace(".py", "")
					if mod_name not in result:
						result.append(mod_name)
		except Exception:
			pass
		return result


	def _build_tools_catalog(tool_names: Optional[List[str]] = None,
	                         toolkit_names: Optional[List[str]] = None) -> str:
		"""Build a catalog of available tool functions and toolkits for the LLM.

		Args:
			tool_names:    If provided, only list these tool module paths (e.g. ["tools.my_fn"]).
			               If None, list all tools from tools.py.
			toolkit_names: If provided, only list these toolkit modules (e.g. ["contrib.toolkits.mesh_toolkit"]).
			               If None, list all discovered toolkits.
		"""
		import inspect
		lines = []

		# Individual tools from tools.py
		lines.append("### Tools (use with tool_config, name='tools.<function>')")
		try:
			import tools as tools_mod
			for name in sorted(dir(tools_mod)):
				if name.startswith('_'):
					continue
				fn = getattr(tools_mod, name)
				if not callable(fn) or inspect.isclass(fn) or inspect.ismodule(fn):
					continue
				qualified = f"tools.{name}"
				if tool_names is not None and qualified not in tool_names:
					continue
				sig = ""
				try:
					sig = str(inspect.signature(fn))
				except (ValueError, TypeError):
					pass
				doc = (fn.__doc__ or "").strip().split('\n')[0]
				lines.append(f"  {qualified}{sig} – {doc}")
		except ImportError:
			if tool_names is None:
				lines.append("  (no tools module found)")
		lines.append("")

		# Toolkits
		lines.append("### Toolkits (use with toolkit_config, name='<module>'; wire to agent_config.toolkits.<key> or tool_flow.config with method='<method>')")
		if toolkit_names is not None:
			toolkit_modules = list(toolkit_names)
		else:
			toolkit_modules = _discover_all_toolkit_modules()
		for mod_name in toolkit_modules:
			# Try exact name, then fallback paths used by the workflow backend loader.
			md = None
			candidates = [mod_name]
			if "." not in mod_name:
				candidates += [f"toolkits.{mod_name}", f"contrib.toolkits.{mod_name}"]
			elif mod_name.startswith("toolkits.") and not mod_name.startswith("contrib."):
				candidates.append(f"contrib.{mod_name}")
			for candidate in candidates:
				try:
					md = importlib.import_module(candidate)
					mod_name = candidate  # use resolved name in catalog
					break
				except (ImportError, ModuleNotFoundError):
					continue
			try:
				if md is None:
					raise ImportError(mod_name)
				# Find toolkit class
				tk_cls = None
				for attr_name in dir(md):
					attr = getattr(md, attr_name)
					if isinstance(attr, type) and getattr(attr, '__toolkit__', False):
						tk_cls = attr
						break
				if tk_cls is None:
					continue
				# Full class docstring — the LLM needs the complete reference
				cls_doc = (tk_cls.__doc__ or "").strip()
				first_line = cls_doc.split('\n')[0]
				lines.append(f"  {mod_name} – {first_line}")
				if '\n' in cls_doc:
					for dl in cls_doc.split('\n')[1:]:
						lines.append(f"    {dl}")
				# List public methods with full docstrings
				for mname in sorted(dir(tk_cls)):
					if mname.startswith('_'):
						continue
					method = getattr(tk_cls, mname)
					if not callable(method):
						continue
					sig = ""
					try:
						sig = str(inspect.signature(method))
					except (ValueError, TypeError):
						pass
					mdoc = (method.__doc__ or "").strip()
					first_line = mdoc.split('\n')[0] if mdoc else ""
					lines.append(f"    .{mname}{sig} – {first_line}")
					# Include remaining docstring lines (Args, Returns, etc.)
					if '\n' in mdoc:
						for dl in mdoc.split('\n')[1:]:
							lines.append(f"      {dl}")
			except ImportError:
				lines.append(f"  {mod_name} – (not installed)")
		lines.append("")

		return '\n'.join(lines)

	_GENERATE_SYSTEM_PROMPT = """You are Numel Workflow Generator, the compiler that turns a user request into one valid Numel workflow JSON document.

## Purpose
- Convert the user's intent into the next best workflow for the current space.
- Produce a workflow that is valid, minimal, runnable, and easy to inspect.
- Prefer the simplest graph that fully satisfies the request.
- Treat the node catalog and tools catalog below as authoritative for this turn.
{toolkit_scope}

## Response Contract
- Return ONLY the workflow JSON object.
- Do NOT wrap it in markdown fences.
- Do NOT explain your reasoning.
- Do NOT invent node types, slot names, toolkit module names, or skill names.
- If the request is underspecified, make reasonable assumptions and encode them into the workflow.

## Runtime Model
A workflow is a directed acyclic graph executed node-by-node in topological order:
- Execution begins at `start_flow` (always index 0) and ends at `end_flow` or `sink_flow`.
- Each node reads from its INPUT slots (wired by edges or set inline in JSON).
- Each node writes to its OUTPUT slots at runtime; downstream nodes consume them via edges.
- Config nodes (model_config, agent_options_config, etc.) each expose their value through a named
  output slot shown in the catalog as "out:". Use that slot name as source_slot when wiring.
  Example: model_config exposes slot "config"; wire with source_slot="config".
- Data flows as: start_flow.flow_out → [transform/agent/route nodes] → end_flow.flow_in.

## Slot Types
- INPUT       – value consumed by the node; set inline in JSON if not connected via edge.
- OUTPUT      – value produced at runtime; referenced as source_slot in outgoing edges.
- MULTI_INPUT – a named set of sub-inputs. Each sub-input is a separate edge with a dotted
                target_slot, e.g. target_slot="tools.list_dir". Never include these keys inline
                in node JSON (null placeholders cause validation errors).
- MULTI_OUTPUT – named sub-outputs for conditional routing. Declare sub-keys inline in node
                JSON as a dict with null values, e.g. "output": {"support": null, "sales": null}.
                Each branch connects via a dotted source_slot, e.g. source_slot="output.support".

## JSON Format
Return ONLY valid JSON with no markdown fences or explanation:
{
  "type": "workflow",
  "nodes": [
    {
      "type": "node_type_snake_case",
      "field": value,
      "output": {"branch_a": null, "branch_b": null},
      "extra": {"pos": [x, y], "size": [w, h], "name": "Display label"}
    }
  ],
  "edges": [
    {
      "type": "edge",
      "source": 0,
      "target": 1,
      "source_slot": "output_field_name",
      "target_slot": "input_field_name"
    }
  ]
}

Field semantics:
- nodes[i].type        – snake_case type string matching the catalog entry.
- nodes[i].<field>     – INPUT field value; omit if default is acceptable.
- nodes[i].<field>     – MULTI_OUTPUT field: dict of {key: null} declaring route names.
- nodes[i].extra       – optional display metadata (pos, size, name, color); safe to omit.
- nodes[i].extra.name  – display label only. Never use it instead of real config fields like
                         toolkit_config.name, tool_config.name, skill_config.name, model_config.name, etc.
- edges[*].source      – 0-based index of the source node in the nodes array.
- edges[*].target      – 0-based index of the target node in the nodes array.
- edges[*].source_slot – OUTPUT field name on source node (or "output.key" for MULTI_OUTPUT).
- edges[*].target_slot – INPUT field name on target node (or "tools.key" for MULTI_INPUT).

## Common Patterns

### Agent subgraph
model_config.config    → agent_config.model      (source_slot="config")
agent_options_config.options → agent_config.options  (source_slot="options")
agent_config.config    → agent_flow.config       (source_slot="config")
Tool nodes connect via dotted target_slot: target_slot="tools.tool_a" → agent_config
When Numel exposes more than one backend, an optional `backend_config.config → agent_config.backend` edge can also be used.

### Conditional routing (route_flow)
Propagate input to the sub-output matching the target value, or to default otherwise.
Declare outputs in JSON: "output": {"branch_a": null, "branch_b": null}
Edges from upstream: source_slot=<key> → route_flow.target (string deciding the branch), source_slot=<key> → route_flow.input (value passed to output.<key>),
Edges from route_flow: route_flow.input → source_slot="output.branch_a" → downstream_node.<key>
Example:
{
	"type": "workflow",
	"nodes": [
		{
			"type": "start_flow"
		},
		{
			"type": "end_flow"
		},
		{
			"type": "native_string",
			"raw": "Plinko"
		},
		{
			"type": "user_input_flow",
			"query": "What kind is your animal?"
		},
		{
			"type": "route_flow",
			"output": {
				"cat": null,
				"dog": null
			}
		},
		{
			"type": "transform_flow",
			"lang": "python",
			"script": "output = f'Call your animal {input}!'"
		},
		{
			"type": "transform_flow",
			"lang": "python",
			"script": "output = f'Call your cat {input}!'"
		},
		{
			"type": "transform_flow",
			"lang": "python",
			"script": "output = f'Call your dog {input}!'"
		},
		{
			"type": "merge_flow",
			"strategy": "first"
		},
		{
			"type": "preview_flow"
		}
	],
	"edges": [
		{
			"type": "edge",
			"source": 2,
			"target": 4,
			"source_slot": "value",
			"target_slot": "input"
		},
		{
			"type": "edge",
			"source": 0,
			"target": 3,
			"source_slot": "flow_out",
			"target_slot": "flow_in"
		},
		{
			"type": "edge",
			"source": 3,
			"target": 4,
			"source_slot": "message",
			"target_slot": "target"
		},
		{
			"type": "edge",
			"source": 4,
			"target": 5,
			"source_slot": "default",
			"target_slot": "input"
		},
		{
			"type": "edge",
			"source": 4,
			"target": 6,
			"source_slot": "output.cat",
			"target_slot": "input"
		},
		{
			"type": "edge",
			"source": 4,
			"target": 7,
			"source_slot": "output.dog",
			"target_slot": "input"
		},
		{
			"type": "edge",
			"source": 5,
			"target": 8,
			"source_slot": "output",
			"target_slot": "input.option_default"
		},
		{
			"type": "edge",
			"source": 6,
			"target": 8,
			"source_slot": "output",
			"target_slot": "input.option_1"
		},
		{
			"type": "edge",
			"source": 7,
			"target": 8,
			"source_slot": "output",
			"target_slot": "input.option_2"
		},
		{
			"type": "edge",
			"source": 8,
			"target": 9,
			"source_slot": "output",
			"target_slot": "flow_in"
		},
		{
			"type": "edge",
			"source": 9,
			"target": 1,
			"source_slot": "flow_out",
			"target_slot": "flow_in"
		}
	]
}

### Fan-in merging (merge_flow)
Set strategy: "first" | "last" | "concat" | "all"
Each branch: source_slot=<key> → merge_flow, target_slot="input.branch_name" (dotted)
Result: merge_flow.output → downstream.<key>
Example: see route_flow example above.

### Transformation (transform_flow)
Execute custom script that assigns to `output`.
The input is available in the `input` variable and its type depends on the connected node.
Be aware of type compatibility when connecting nodes.
Be aware of double quotes and single quotes when composing the JSON.
Example:
{
  "type": "workflow",
  "nodes": [
    {
      "type": "start_flow"
    },
    {
      "type": "user_input_flow",
      "query": "Enter your name:"
    },
    {
      "type": "transform_flow",
      "lang": "python",
      "script": "output = f'Hello, {str(input).upper()}!'"
    },
    {
      "type": "preview_flow"
    },
    {
      "type": "end_flow"
    }
  ],
  "edges": [
    { "source": 0, "target": 1, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 1, "target": 2, "source_slot": "message", "target_slot": "input" },
    { "source": 2, "target": 3, "source_slot": "output", "target_slot": "flow_in" },
    { "source": 3, "target": 4, "source_slot": "flow_out", "target_slot": "flow_in" }
  ]
}

### Loops
loop_start_flow.condition (bool) controls iteration. Connect body nodes between
loop_start_flow and loop_end_flow. loop_start_flow.iteration outputs current count.
For lists: for_each_start_flow.items → body → for_each_end_flow; current item on .current output.
An edge with source=<loop_end_flow>, source_slot="flow_out" to target=<loop_start_flow>, target_slot="flow_in" and attribute loop=true creates a feedback loop for the next iteration,
for example: {"source": 3, "target": 0, "source_slot": "flow_out", "target_slot": "flow_in", "loop": true }.

### Event-driven workflows
Register a source: timer_source_flow or webhook_source_flow → registered_id output.
Listen: registered_id → event_listener_flow, target_slot="sources.<key>" (dotted MULTI_INPUT).
event_listener_flow.event carries the received event payload.

### Toolkits (toolkit_config)
A toolkit provides multiple related tools with shared state (e.g. a sandboxed filesystem).
**With agents**: wire toolkit_config.config → agent_config, target_slot="toolkits.<key>".
The active backend exposes the toolkit's public methods as tools and may also surface toolkit-specific guidance from its description.
**With tool_flow (standalone)**: wire toolkit_config.config → tool_flow.config, and set
tool_flow.method to the public method name (e.g. "read_file"). Multiple tool_flow nodes
wired to the same toolkit_config share the toolkit instance and its state.
Set the actual toolkit module path on toolkit_config.name itself. Do not put module paths in extra.name.

### Skills (skill_config)
A skill provides a reusable capability package loaded from SKILL.md files.
Wire skill_config.config → agent_config, target_slot="skills.<key>".
When the active backend supports native skills, the skill is attached natively. Other backends may adapt it through equivalent instruction layers.
Skills do NOT provide callable tools — use toolkit_config for that.
Set skill_config.name to a skill ID (e.g. "web-search", "git-assistant").

### Tool invocation (tool_flow)
tool_flow executes a standalone tool or a toolkit method within the workflow graph.
**Standalone tool**: wire tool_config.config → tool_flow.config. The tool function is called with args.
**Toolkit method**: wire toolkit_config.config → tool_flow.config, set tool_flow.method="<method_name>".
Example: toolkit_config(name="toolkits.file_toolkit") → tool_flow(method="read_file", args={"path": "data.txt"})
Multiple tool_flow nodes sharing the same toolkit_config use the same instance (shared state).
**IMPORTANT**: The toolkit_config `name` field must be the EXACT Python module path as listed in the
"Available Tools and Toolkits" section below. Do NOT guess or shorten module names — copy them verbatim
(e.g. "contrib.toolkits.mesh_toolkit", NOT "toolkits.mesh_toolkit").
**Dynamic args**: tool_flow.args is an INPUT slot (dict). For static args, set them inline in JSON.
For dynamic args (e.g. user input), use a transform_flow to build the args dict and wire its output
to tool_flow.args via an edge with target_slot="args":
  user_input_flow.message → transform_flow (script: output = {"path": input}) → tool_flow.args
Example (mesh processing with toolkit):
{
  "type": "workflow",
  "nodes": [
    { "type": "toolkit_config", "name": "contrib.toolkits.mesh_toolkit" },
    { "type": "start_flow" },
    { "type": "tool_flow", "method": "load_mesh", "args": { "path": "input.ply" } },
    { "type": "tool_flow", "method": "decimate", "args": { "target_percent": 0.5 } },
    { "type": "tool_flow", "method": "smooth", "args": { "iterations": 3 } },
    { "type": "tool_flow", "method": "save_mesh", "args": { "path": "output.ply" } },
    { "type": "end_flow" }
  ],
  "edges": [
    { "source": 0, "target": 2, "source_slot": "config", "target_slot": "config" },
    { "source": 0, "target": 3, "source_slot": "config", "target_slot": "config" },
    { "source": 0, "target": 4, "source_slot": "config", "target_slot": "config" },
    { "source": 0, "target": 5, "source_slot": "config", "target_slot": "config" },
    { "source": 1, "target": 2, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 2, "target": 3, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 3, "target": 4, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 4, "target": 5, "source_slot": "flow_out", "target_slot": "flow_in" },
    { "source": 5, "target": 6, "source_slot": "flow_out", "target_slot": "flow_in" }
  ]
}

## Available Tools and Toolkits
{tools_catalog}

## Rules
1. Always place start_flow at index 0. Always end with end_flow.
2. source_slot must be an OUTPUT or MULTI_OUTPUT field name shown in the catalog "out:" line.
3. target_slot must be an INPUT or MULTI_INPUT field name shown in the catalog "in:" line.
4. MULTI_OUTPUT: declare sub-keys in node JSON as {"field": {"key": null}}; use dotted source_slot.
5. MULTI_INPUT: use dotted target_slot only; never include sub-keys inline in node JSON.
6. transform_flow: set lang="python"; write Python that assigns to the `output` variable.
7. Config nodes: use source_slot matching their "out:" slot (e.g. "config" for model_config).
8. Omit node fields that keep their default values to keep JSON concise.
9. Return ONLY the JSON object, nothing else.
10. **PREFER toolkits over transform_flow**: When a toolkit provides a method that does what you need
    (e.g. mesh operations, file I/O, context sensing), use toolkit_config + tool_flow instead of
    writing inline Python in transform_flow. Toolkits handle errors, state, and edge cases properly.
    Only use transform_flow for simple data reshaping or glue logic that no toolkit covers.

## Available Node Types
{node_catalog}"""

	def _extract_json_from_response(text: str) -> dict:
		"""Extract JSON from LLM response, handling markdown code blocks."""
		text = text.strip()
		# Try direct JSON parse first
		try:
			return json.loads(text)
		except json.JSONDecodeError:
			pass
		# Try extracting from markdown code block
		match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
		if match:
			try:
				return json.loads(match.group(1).strip())
			except json.JSONDecodeError:
				pass
		# Try finding first { to last }
		start = text.find('{')
		end = text.rfind('}')
		if start != -1 and end != -1 and end > start:
			try:
				return json.loads(text[start:end + 1])
			except json.JSONDecodeError:
				pass
		raise ValueError("Could not extract valid JSON from LLM response")

	_generation_cache = {"config_hash": None, "backend": None, "agent_index": None}

	def _build_generation_agent(request: GenerateWorkflowRequest, system_prompt: str):
		"""Build an AI agent subgraph from generation request config.

		Constructs a Workflow graph with BackendConfig → ModelConfig → AgentOptionsConfig → AgentConfig
		(plus optional MemoryManager, SessionManager, Tools, Knowledge) and builds it via the active backend adapter.
		Results are cached and reused when the config hasn't changed.
		"""
		from schema import (
			ModelConfig, AgentOptionsConfig, AgentConfig,
			MemoryManagerConfig, SessionManagerConfig, ToolConfig, ToolkitConfig,
			KnowledgeManagerConfig, ContentDBConfig, IndexDBConfig,
			EmbeddingConfig, Edge, Workflow
		)

		# Config hash for cache invalidation
		config_hash = hash(json.dumps({
			"backend": request.backend, "model": request.model, "options": request.options,
			"memory": request.memory, "session": request.session, "tools": request.tools,
			"toolkits": request.toolkits, "knowledge": request.knowledge,
			"system_prompt": system_prompt,
		}, sort_keys=True, default=str))

		cache = _generation_cache
		if cache["config_hash"] == config_hash and cache["backend"] is not None:
			return cache["backend"], cache["agent_index"]

		# Build nodes and edges for the agent subgraph
		nodes = []
		edges = []
		supported_backends = list_supported_backends()
		requested_backend = normalize_backend_name((request.backend or {}).get("engine"))
		show_backend_config = len(supported_backends) > 1 or requested_backend != DEFAULT_BACKEND_NAME

		# 0: ModelConfig (always present)
		mcfg = request.model or {}
		nodes.append(ModelConfig(
			source  = mcfg.get("source", "ollama"),
			name    = mcfg.get("name", "mistral:latest"),
			version = mcfg.get("version", ""),
		))
		model_idx = 0

		# 1: AgentOptionsConfig (always present)
		ocfg = request.options or {}
		nodes.append(AgentOptionsConfig(
			name            = ocfg.get("name", "Workflow Generator"),
			description     = ocfg.get("description", None),
			instructions    = ocfg.get("instructions", None),
			prompt_override = ocfg.get("prompt_override", None) or system_prompt,
			markdown        = ocfg.get("markdown", False),
		))
		options_idx = 1

		next_idx = 2
		backend_idx = None
		if show_backend_config:
			from schema import BackendConfig
			nodes.insert(0, BackendConfig(name=requested_backend))
			model_idx += 1
			options_idx += 1
			next_idx += 1
			backend_idx = 0

		# Optional: MemoryManagerConfig
		memory_idx = None
		if request.memory:
			m = request.memory
			nodes.append(MemoryManagerConfig(
				query   = m.get("query", False),
				update  = m.get("update", False),
				managed = m.get("managed", False),
				prompt  = m.get("prompt", None),
			))
			memory_idx = next_idx
			edges.append(Edge(source=model_idx, target=memory_idx, source_slot="get", target_slot="model"))
			next_idx += 1

		# Optional: SessionManagerConfig
		session_idx = None
		if request.session:
			s = request.session
			nodes.append(SessionManagerConfig(
				query        = s.get("query", False),
				update       = s.get("update", False),
				history_size = s.get("history_size", 10),
				prompt       = s.get("prompt", None),
			))
			session_idx = next_idx
			next_idx += 1

		# Optional: ToolConfig[] (multiple)
		tool_indices = []
		if request.tools:
			for t in request.tools:
				nodes.append(ToolConfig(
					name = t.get("name", ""),
					args = t.get("args", None),
				))
				tool_indices.append(next_idx)
				next_idx += 1

		# Optional: ToolkitConfig[] (multiple)
		toolkit_indices = []
		if request.toolkits:
			for t in request.toolkits:
				nodes.append(ToolkitConfig(
					name = t.get("name", ""),
					args = t.get("args", None),
				))
				toolkit_indices.append(next_idx)
				next_idx += 1

		# Optional: KnowledgeManagerConfig (needs ContentDB + IndexDB + Embedding)
		knowledge_idx = None
		if request.knowledge:
			k = request.knowledge
			# EmbeddingConfig (uses same source as model)
			nodes.append(EmbeddingConfig(
				source = mcfg.get("source", "ollama"),
				name   = mcfg.get("name", "mistral:latest"),
			))
			embed_idx = next_idx
			next_idx += 1
			# ContentDBConfig
			cdb = k.get("content_db", {})
			nodes.append(ContentDBConfig(
				engine = cdb.get("engine", "sqlite"),
				url    = cdb.get("url", "storage/gen_content"),
			))
			cdb_idx = next_idx
			next_idx += 1
			# IndexDBConfig
			idb = k.get("index_db", {})
			nodes.append(IndexDBConfig(
				engine = idb.get("engine", "lancedb"),
				url    = idb.get("url", "storage/gen_index"),
			))
			idb_idx = next_idx
			next_idx += 1
			edges.append(Edge(source=embed_idx, target=idb_idx, source_slot="get", target_slot="embedding"))
			# KnowledgeManagerConfig
			nodes.append(KnowledgeManagerConfig(
				query       = k.get("query", True),
				description = k.get("description", None),
				max_results = k.get("max_results", 10),
				urls        = k.get("urls", None),
			))
			knowledge_idx = next_idx
			next_idx += 1
			edges.append(Edge(source=cdb_idx, target=knowledge_idx, source_slot="get", target_slot="content_db"))
			edges.append(Edge(source=idb_idx, target=knowledge_idx, source_slot="get", target_slot="index_db"))

		# AgentConfig (last node — connects to all above)
		# For MULTI_INPUT tools, use string keys matching dotted edge slot convention
		tool_keys = [str(i) for i in range(len(tool_indices))] if tool_indices else None
		nodes.append(AgentConfig(
			memory_mgr    = nodes[memory_idx]    if memory_idx    is not None else None,
			session_mgr   = nodes[session_idx]   if session_idx   is not None else None,
			tools         = tool_keys,
			knowledge_mgr = nodes[knowledge_idx] if knowledge_idx is not None else None,
		))
		agent_idx = next_idx

		# Core edges: backend (when exposed), model, options → agent
		if backend_idx is not None:
			edges.append(Edge(source=backend_idx, target=agent_idx, source_slot="get", target_slot="backend"))
		edges.append(Edge(source=model_idx,   target=agent_idx, source_slot="get", target_slot="model"))
		edges.append(Edge(source=options_idx,  target=agent_idx, source_slot="get", target_slot="options"))
		if memory_idx is not None:
			edges.append(Edge(source=memory_idx, target=agent_idx, source_slot="get", target_slot="memory_mgr"))
		if session_idx is not None:
			edges.append(Edge(source=session_idx, target=agent_idx, source_slot="get", target_slot="session_mgr"))
		# Tools use dotted slot names for MULTI_INPUT: tools.0, tools.1, ...
		for i, ti in enumerate(tool_indices):
			edges.append(Edge(source=ti, target=agent_idx, source_slot="get", target_slot=f"tools.{i}"))
		# Toolkits use dotted slot names for MULTI_INPUT: toolkits.0, toolkits.1, ...
		for i, ti in enumerate(toolkit_indices):
			edges.append(Edge(source=ti, target=agent_idx, source_slot="get", target_slot=f"toolkits.{i}"))
		if knowledge_idx is not None:
			edges.append(Edge(source=knowledge_idx, target=agent_idx, source_slot="get", target_slot="knowledge_mgr"))

		workflow = Workflow(nodes=nodes, edges=edges)
		workflow.link()
		backend  = build_backend(workflow, skill_mgr=skill_mgr)

		cache.update({"config_hash": config_hash, "backend": backend, "agent_index": agent_idx})
		return backend, agent_idx

	def _build_generation_prompt(tool_names: Optional[List[str]] = None,
	                             toolkit_names: Optional[List[str]] = None) -> str:
		"""Build the workflow-generation contract, optionally filtered to active tools/toolkits."""
		nonlocal schema_code
		node_catalog = _build_node_catalog(schema_code)
		normalized_tool_names = None if tool_names is None else list(tool_names)
		normalized_toolkit_names = None if toolkit_names is None else list(toolkit_names)
		toolkit_scope = ""
		if normalized_toolkit_names is not None:
			if normalized_toolkit_names:
				scoped_names = ", ".join(normalized_toolkit_names)
				toolkit_scope = (
					"\n## Toolkit Scope\n"
					f"- Only the following toolkits are enabled for this turn: {scoped_names}.\n"
					"- If one of those toolkits matches the user's domain, use it instead of unrelated nodes or generic transforms.\n"
					"- Do NOT invent or rely on toolkits outside that enabled set.\n"
				)
			else:
				toolkit_scope = (
					"\n## Toolkit Scope\n"
					"- No toolkits are enabled for this turn.\n"
					"- Do NOT invent toolkit usage unless the user explicitly asks to add one.\n"
				)
		if normalized_tool_names is None and normalized_toolkit_names is None:
			tools_catalog = _build_tools_catalog()
		else:
			tools_catalog = _build_tools_catalog(
				tool_names=normalized_tool_names or [],
				toolkit_names=normalized_toolkit_names or [],
			)
		return (
			_GENERATE_SYSTEM_PROMPT
			.replace("{node_catalog}", node_catalog)
			.replace("{tools_catalog}", tools_catalog)
			.replace("{toolkit_scope}", toolkit_scope)
		)

	class GenerationPromptRequest(BaseModel):
		tool_names:    Optional[List[str]] = None  # e.g. ["tools.my_fn"]
		toolkit_names: Optional[List[str]] = None  # e.g. ["contrib.toolkits.mesh_toolkit"]

	@app.post("/generation-prompt")
	async def get_generation_prompt(request: GenerationPromptRequest = GenerationPromptRequest()):
		"""Return the generation system prompt (node catalog + instructions) for chat-based /gen.
		When tool_names/toolkit_names are provided, only those are listed in the catalog."""
		return {
			"prompt": _build_generation_prompt(
				tool_names=request.tool_names,
				toolkit_names=request.toolkit_names,
			)
		}

	@app.post("/generate-workflow")
	async def generate_workflow(request: GenerateWorkflowRequest):
		nonlocal schema_code

		try:
			# Build node catalog and system prompt — only list the agent's own tools/toolkits
			tool_names    = [t.get("name") for t in (request.tools or []) if t.get("name")]    or None
			toolkit_names = [t.get("name") for t in (request.toolkits or []) if t.get("name")] or None
			node_catalog  = _build_node_catalog(schema_code)
			tools_catalog = _build_tools_catalog(tool_names=tool_names, toolkit_names=toolkit_names)
			system_prompt = _GENERATE_SYSTEM_PROMPT.replace("{node_catalog}", node_catalog).replace("{tools_catalog}", tools_catalog)

			# Build user message with history context
			user_message = ""
			if request.history:
				for msg in request.history:
					role = msg.get("role", "user")
					content = msg.get("content", "")
					user_message += f"[{role}]: {content}\n\n"
				user_message += f"[user]: {request.prompt}"
			else:
				user_message = request.prompt

			# Build agent from full subgraph config
			backend, agent_idx = _build_generation_agent(request, system_prompt)
			agent_handle = backend.handles[agent_idx]

			# Call the agent
			result = await backend.run_agent(agent_handle, user_message)
			response_text = result.get("content", "")
			if not isinstance(response_text, str):
				response_text = str(response_text)

			# Extract and validate JSON
			workflow = _extract_json_from_response(response_text)

			if "nodes" not in workflow or not isinstance(workflow["nodes"], list):
				raise ValueError("Generated workflow missing 'nodes' array")
			if "edges" not in workflow:
				workflow["edges"] = []

			node_count = len(workflow["nodes"])
			edge_count = len(workflow["edges"])

			return {
				"workflow": workflow,
				"raw_response": response_text,
				"message": f"Generated {node_count} nodes, {edge_count} edges"
			}

		except ValueError as e:
			raise HTTPException(status_code=422, detail=str(e))
		except ImportError as e:
			raise HTTPException(status_code=502, detail=f"Model provider not available: {e}")
		except Exception as e:
			_generation_cache["backend"] = None
			raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")


	# ── Docs / tutorials ──────────────────────────────────────────────

	_docs_dir = Path(__file__).resolve().parent.parent / "docs"

	@app.post("/docs")
	async def list_docs():
		"""Return the list of available documentation files."""
		if not _docs_dir.is_dir():
			return []
		items = []
		for md in sorted(_docs_dir.glob("*.md")):
			title = md.stem
			try:
				first_line = md.read_text(encoding="utf-8", errors="replace").split("\n", 1)[0]
				if first_line.startswith("# "):
					title = first_line[2:].strip()
			except Exception:
				pass
			has_workflow = (md.with_suffix(".json")).is_file()
			items.append({"filename": md.name, "title": title, "hasWorkflow": has_workflow})
		return items

	class DocRequest(BaseModel):
		filename: str

	@app.post("/docs/file")
	async def get_doc(req: DocRequest):
		"""Return the contents of a documentation file (.md or .json)."""
		filename = req.filename
		if ".." in filename or "/" in filename or "\\" in filename:
			raise HTTPException(status_code=400, detail="Invalid filename")
		path = _docs_dir / filename
		if not path.suffix in (".md", ".json") or not path.is_file():
			raise HTTPException(status_code=404, detail="File not found")
		content = path.read_text(encoding="utf-8", errors="replace")
		if path.suffix == ".json":
			return json.loads(content)
		return {"filename": filename, "content": content}

	# === Toolkit Management API ===

	_app_dir      = os.path.dirname(os.path.abspath(__file__))
	_project_root = os.path.dirname(_app_dir)
	_contrib_dir  = os.path.join(_project_root, "contrib", "toolkits")

	def _resolve_toolkit_module(name: str):
		"""Import a toolkit module by name, trying standard resolution paths.
		Returns (module, resolved_name) or raises ImportError."""
		module_name = name.replace("/", ".").replace("\\", ".")
		candidates = [module_name]
		if "." not in module_name:
			candidates += [f"toolkits.{module_name}", f"contrib.toolkits.{module_name}"]
		elif module_name.startswith("toolkits.") and not module_name.startswith("contrib."):
			candidates.append(f"contrib.{module_name}")
		for candidate in candidates:
			try:
				md = importlib.import_module(candidate)
				return md, candidate
			except (ImportError, ModuleNotFoundError):
				continue
		raise ImportError(f"Cannot resolve toolkit: {name}")

	def _find_toolkit_class(module):
		"""Find the class marked with __toolkit__ = True in a module."""
		for attr_name in dir(module):
			attr = getattr(module, attr_name)
			if isinstance(attr, type) and getattr(attr, '__toolkit__', False):
				return attr
		return None

	def _get_toolkit_modules(context=None):
		"""Options provider: list all importable toolkit module names."""
		modules = _discover_all_toolkit_modules()
		# Also include short names (without prefix) for convenience
		return modules

	register_options_provider("toolkit_modules", _get_toolkit_modules)

	def _get_skill_names(context=None):
		"""Options provider: list all available skill names."""
		if skill_mgr:
			return [s["name"] for s in skill_mgr.list()]
		return []

	register_options_provider("skill_names", _get_skill_names)

	def _titleize_extension_name(value: str) -> str:
		text = str(value or "").strip()
		if not text:
			return "Unnamed Extension"
		if "." in text:
			text = text.split(".")[-1]
		text = text.replace("-", " ").replace("_", " ").strip()
		text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
		return re.sub(r"\s+", " ", text).strip().title()

	def _toolkit_registry_entry(mod_name: str) -> Dict[str, Any]:
		builtin = mod_name.startswith("toolkits.")
		entry: Dict[str, Any] = {
			"id": f"toolkit:{mod_name}",
			"kind": "toolkit",
			"name": mod_name,
			"module_name": mod_name,
			"title": _titleize_extension_name(mod_name),
			"description": "",
			"author": "Numel" if builtin else "Community",
			"source": "builtin" if builtin else "shared",
			"trust": "core" if builtin else "shared",
			"featured": mod_name in {
				"toolkits.workspace_toolkit",
				"toolkits.file_toolkit",
				"toolkits.http_toolkit",
				"toolkits.search_toolkit",
				"toolkits.console_toolkit",
			},
			"tags": [],
			"version": "",
			"enabled": None,
			"setup_done": None,
			"setup_pending": False,
			"builtin": builtin,
			"removable": mod_name.startswith("contrib.toolkits."),
			"path": "",
			"platforms": ["local", "prod"],
			"actions": ["inspect", *([] if builtin else ["remove"])],
		}
		try:
			md, resolved = _resolve_toolkit_module(mod_name)
			tk_cls = _find_toolkit_class(md)
			entry["path"] = str(resolved)
			if tk_cls:
				entry["description"] = (tk_cls.__doc__ or "").strip().split('\n')[0]
				entry["class_name"] = tk_cls.__name__
				entry["title"] = _titleize_extension_name(tk_cls.__name__)
				entry["tags"] = [
					tag for tag in {
						"toolkit",
						entry["source"],
						_titleize_extension_name(mod_name).replace(" ", "-").lower(),
					}
					if tag
				]
		except Exception:
			entry["description"] = "(failed to load)"
		return entry

	def _skill_registry_entry(summary: Dict[str, Any]) -> Dict[str, Any]:
		name = str(summary.get("name", "") or "").strip()
		skill_obj = getattr(skill_mgr, "_skills", {}).get(name) if skill_mgr else None
		skill_path = str(getattr(skill_obj, "path", "") or "")
		builtin_dir = _runtime_settings.builtin_skills_dir.resolve()
		user_dir = _runtime_settings.user_skills_dir.resolve()
		builtin = False
		removable = False
		if skill_path:
			try:
				resolved_path = Path(skill_path).resolve()
				builtin = _path_within_root(resolved_path, builtin_dir)
				removable = _path_within_root(resolved_path, user_dir)
			except Exception:
				pass
		entry: Dict[str, Any] = {
			"id": f"skill:{name}",
			"kind": "skill",
			"name": name,
			"title": _titleize_extension_name(name),
			"description": str(summary.get("description", "") or ""),
			"author": str(summary.get("author", "") or ("Numel" if builtin else "Community")),
			"source": "builtin" if builtin else "shared",
			"trust": "core" if builtin else "shared",
			"featured": name in {"git-assistant", "web-search", "commit-helper"},
			"tags": list(summary.get("tags", []) or []),
			"version": str(summary.get("version", "") or ""),
			"enabled": bool(summary.get("enabled", False)),
			"setup_done": bool(summary.get("setup_done", False)),
			"builtin": builtin,
			"removable": removable,
			"requires": summary.get("requires", {}) or {},
			"examples": list(summary.get("examples", []) or []),
			"scripts": list(summary.get("scripts", []) or []),
			"references": list(summary.get("references", []) or []),
			"install": list(summary.get("install", []) or []),
			"primary_env": str(summary.get("primaryEnv", "") or summary.get("primary_env", "") or ""),
			"os": list(summary.get("os", []) or []),
			"path": skill_path,
			"platforms": list(summary.get("os", []) or ["local", "prod"]),
			"script_count": len(summary.get("scripts", []) or []),
			"reference_count": len(summary.get("references", []) or []),
			"install_count": len(summary.get("install", []) or []),
			"setup_pending": (
				not bool(summary.get("setup_done", False))
				and (
					len(summary.get("install", []) or []) > 0
					or bool(summary.get("requires", {}) or {})
				)
			),
			"actions": [
				"view",
				"setup",
				"disable" if bool(summary.get("enabled", False)) else "enable",
				*(["remove"] if removable else []),
			],
		}
		return entry

	def _extensions_registry_payload() -> Dict[str, Any]:
		entries: List[Dict[str, Any]] = []
		for mod_name in _discover_all_toolkit_modules():
			entries.append(_toolkit_registry_entry(mod_name))
		if skill_mgr:
			for summary in skill_mgr.list():
				entries.append(_skill_registry_entry(summary))
		entries.sort(
			key=lambda item: (
				0 if item.get("featured") else 1,
				0 if item.get("source") == "builtin" else 1,
				str(item.get("kind", "")),
				str(item.get("title", "")).lower(),
			)
		)
		return {
			"entries": entries,
			"counts": {
				"total": len(entries),
				"toolkits": sum(1 for item in entries if item.get("kind") == "toolkit"),
				"skills": sum(1 for item in entries if item.get("kind") == "skill"),
				"featured": sum(1 for item in entries if item.get("featured")),
				"shared": sum(1 for item in entries if item.get("source") == "shared"),
				"setup_pending": sum(1 for item in entries if item.get("setup_pending")),
				"enabled": sum(1 for item in entries if item.get("kind") == "skill" and item.get("enabled")),
			},
		}

	@app.post("/toolkits/list")
	async def toolkits_list():
		"""List all available toolkit modules with descriptions."""
		import inspect as _ins
		results = []
		for mod_name in _discover_all_toolkit_modules():
			entry = {
				"name": mod_name,
				"description": "",
				"builtin": mod_name.startswith("toolkits."),
				"removable": mod_name.startswith("contrib.toolkits."),
			}
			try:
				md, resolved = _resolve_toolkit_module(mod_name)
				tk_cls = _find_toolkit_class(md)
				if tk_cls:
					entry["description"] = (tk_cls.__doc__ or "").strip().split('\n')[0]
					entry["class_name"] = tk_cls.__name__
			except Exception:
				entry["description"] = "(failed to load)"
			results.append(entry)
		return results

	@app.post("/extensions/registry")
	async def extensions_registry():
		"""Unified extension registry for toolkits and skills with creator/source metadata."""
		return _extensions_registry_payload()

	@app.post("/toolkits/inspect")
	async def toolkits_inspect(request: dict):
		"""Introspect a toolkit's constructor parameters and methods."""
		import inspect as _ins
		name = request.get("name", "")
		if not name:
			raise HTTPException(status_code=400, detail="name is required")
		try:
			md, resolved = _resolve_toolkit_module(name)
		except ImportError as e:
			raise HTTPException(status_code=404, detail=str(e))
		tk_cls = _find_toolkit_class(md)
		if not tk_cls:
			raise HTTPException(status_code=404, detail=f"No toolkit class found in {name}")

		# Introspect __init__ parameters
		params = []
		try:
			sig = _ins.signature(tk_cls.__init__)
			for pname, param in sig.parameters.items():
				if pname == "self":
					continue
				ptype = "Any"
				if param.annotation is not _ins.Parameter.empty:
					ann = param.annotation
					ptype = getattr(ann, '__name__', str(ann))
					# Clean up typing prefixes
					for prefix in ("typing.", "<class '", "'>"):
						ptype = ptype.replace(prefix, "")
				required = param.default is _ins.Parameter.empty
				default = None if required else param.default
				params.append({
					"name": pname,
					"type": ptype,
					"default": default,
					"required": required,
				})
		except (ValueError, TypeError):
			pass

		# List public methods
		methods = []
		for mname in sorted(dir(tk_cls)):
			if mname.startswith('_'):
				continue
			method = getattr(tk_cls, mname, None)
			if not callable(method):
				continue
			msig = ""
			try:
				msig = str(_ins.signature(method))
			except (ValueError, TypeError):
				pass
			mdoc = (method.__doc__ or "").strip().split('\n')[0]
			methods.append({"name": mname, "signature": msig, "description": mdoc})

		return {
			"name": resolved,
			"class_name": tk_cls.__name__,
			"description": (tk_cls.__doc__ or "").strip(),
			"params": params,
			"methods": methods,
		}

	@app.post("/toolkits/upload")
	async def toolkits_upload(req: Request, file: UploadFile = File(...), overwrite: bool = False):
		"""Upload a .py file to contrib/toolkits/."""
		_require_admin(req)
		if not file.filename or not file.filename.endswith('.py'):
			raise HTTPException(status_code=400, detail="Only .py files are allowed")
		if file.filename.startswith('_'):
			raise HTTPException(status_code=400, detail="Filenames starting with _ are reserved")

		content = await file.read()
		if len(content) > 512 * 1024:
			raise HTTPException(status_code=400, detail="File too large (max 512KB)")

		# Validate it compiles
		try:
			compile(content, file.filename, 'exec')
		except SyntaxError as e:
			raise HTTPException(status_code=400, detail=f"Syntax error: {e}")

		os.makedirs(_contrib_dir, exist_ok=True)
		dest = os.path.join(_contrib_dir, file.filename)
		if os.path.exists(dest) and not overwrite:
			raise HTTPException(status_code=409, detail=f"{file.filename} already exists. Use overwrite=true to replace.")

		with open(dest, 'wb') as f:
			f.write(content)

		# Reload if already imported
		stem = file.filename[:-3]
		mod_name = f"contrib.toolkits.{stem}"
		import sys
		if mod_name in sys.modules:
			importlib.reload(sys.modules[mod_name])

		# Verify it has a toolkit class
		has_toolkit = False
		try:
			md = importlib.import_module(mod_name)
			has_toolkit = _find_toolkit_class(md) is not None
		except Exception:
			pass

		log_print(f"Toolkit uploaded: {file.filename} → {mod_name} (toolkit_class={has_toolkit})")
		return {
			"status": "ok",
			"module": mod_name,
			"filename": file.filename,
			"has_toolkit_class": has_toolkit,
		}

	@app.post("/toolkits/remove")
	async def toolkits_remove(req: Request, request: dict):
		"""Delete a user-created toolkit from contrib/toolkits/."""
		_require_admin(req)
		name = str(request.get("name", "")).strip()
		if not name:
			raise HTTPException(status_code=400, detail="name is required")

		module_name = name.replace("/", ".").replace("\\", ".").removesuffix(".py")
		short_name = module_name
		if module_name.startswith("contrib.toolkits."):
			short_name = module_name[len("contrib.toolkits."):]
		elif module_name.startswith("toolkits."):
			raise HTTPException(status_code=403, detail="Built-in toolkits cannot be removed")
		elif "." in module_name:
			raise HTTPException(status_code=400, detail="Only contrib toolkit modules can be removed")

		if not short_name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", short_name):
			raise HTTPException(status_code=400, detail="Invalid toolkit name")

		builtin_path = os.path.join(_app_dir, "toolkits", f"{short_name}.py")
		contrib_path = os.path.join(_contrib_dir, f"{short_name}.py")
		if not os.path.exists(contrib_path):
			if os.path.exists(builtin_path):
				raise HTTPException(status_code=403, detail="Built-in toolkits cannot be removed")
			raise HTTPException(status_code=404, detail=f"Contrib toolkit '{short_name}' not found")

		os.remove(contrib_path)

		pycache_dir = os.path.join(_contrib_dir, "__pycache__")
		if os.path.isdir(pycache_dir):
			prefix = f"{short_name}."
			for fname in os.listdir(pycache_dir):
				if fname.startswith(prefix) and fname.endswith(".pyc"):
					try:
						os.remove(os.path.join(pycache_dir, fname))
					except OSError:
						pass

		import sys
		mod_name = f"contrib.toolkits.{short_name}"
		if mod_name in sys.modules:
			del sys.modules[mod_name]
		importlib.invalidate_caches()

		log_print(f"Toolkit removed: {contrib_path}")
		return {
			"status": "ok",
			"module": mod_name,
			"filename": os.path.basename(contrib_path),
		}

	# Expose generation prompt builder for planner / assistant reuse.
	app.state.build_generation_prompt = _build_generation_prompt

	log_print("Workflow API endpoints registered")
