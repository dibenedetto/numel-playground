from __future__ import annotations

import asyncio
import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from published_app_generation import (
	PublishedAppGenerationConfig,
	detect_workflow_inputs,
	generate_published_app_bundle,
)
from runtime_settings import get_runtime_settings
from schema import Workflow
from utils import log_print


_SETTINGS = get_runtime_settings()
_APPS_PATH = str(_SETTINGS.published_apps_path)
_APPS_DIR = str(_SETTINGS.published_apps_dir)


class PublishedApp(BaseModel):
	id: str = Field(default_factory=lambda: f"app_{uuid.uuid4().hex[:8]}")
	name: str = ""
	slug: str = ""
	owner_user_id: str = ""
	owner_username: str = ""
	description: str = ""
	workflow: Dict[str, Any] = Field(default_factory=dict)
	inputs: List[dict] = Field(default_factory=list)
	workflow_summary: Dict[str, Any] = Field(default_factory=dict)
	generation: Dict[str, Any] = Field(default_factory=dict)
	generated_summary: str = ""
	asset_dir: str = ""
	index_file: str = ""
	published: str = Field(default_factory=lambda: datetime.now().isoformat())
	updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
	enabled: bool = True
	run_count: int = 0
	error_count: int = 0
	last_run_at: Optional[str] = None
	last_error: Optional[str] = None

	@property
	def public_key(self) -> str:
		return f"{self.owner_username.lower()}/{self.slug.lower()}"


class PublishRequest(BaseModel):
	title: str
	workflow: Dict[str, Any]
	slug: str
	description: str = ""
	inputs: Optional[List[dict]] = None
	page_generation: Optional[Dict[str, Any]] = None


class RegenerateRequest(BaseModel):
	slug: str
	title: Optional[str] = None
	description: Optional[str] = None
	page_generation: Optional[Dict[str, Any]] = None


def _slugify(value: str, fallback: str = "app") -> str:
	slug = re.sub(r"[^a-z0-9-]+", "-", str(value or "").strip().lower()).strip("-")
	return slug or fallback


def _utcnow() -> str:
	return datetime.now().isoformat()


def _safe_json_text(payload: Dict[str, Any]) -> str:
	return json.dumps(payload, ensure_ascii=False, indent=2)


def _runtime_css() -> str:
	return """
:root {
  --numel-runtime-bg: rgba(15, 23, 42, 0.78);
  --numel-runtime-border: rgba(148, 163, 184, 0.22);
  --numel-runtime-text: #e5eef8;
  --numel-runtime-muted: #94a3b8;
  --numel-runtime-accent: #4f8bd6;
  --numel-runtime-danger: #f87171;
  --numel-runtime-success: #4ade80;
}
.numel-runtime-root {
  display: flex;
  flex-direction: column;
  gap: 16px;
  width: 100%;
}
.numel-runtime-card {
  background: var(--numel-runtime-bg);
  border: 1px solid var(--numel-runtime-border);
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.14);
  backdrop-filter: blur(8px);
}
.numel-runtime-card h3 {
  margin: 0 0 12px;
  font-size: 0.95rem;
  color: var(--numel-runtime-text);
}
.numel-runtime-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.numel-runtime-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.numel-runtime-field label {
  font-size: 0.83rem;
  color: var(--numel-runtime-muted);
}
.numel-runtime-field input,
.numel-runtime-field textarea,
.numel-runtime-field select {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(15, 23, 42, 0.72);
  color: var(--numel-runtime-text);
  font: inherit;
}
.numel-runtime-field textarea {
  min-height: 96px;
  resize: vertical;
}
.numel-runtime-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.numel-runtime-btn {
  border: 0;
  border-radius: 999px;
  padding: 10px 16px;
  cursor: pointer;
  font: inherit;
  font-weight: 600;
}
.numel-runtime-btn.primary {
  background: var(--numel-runtime-accent);
  color: #fff;
}
.numel-runtime-btn.secondary {
  background: transparent;
  border: 1px solid rgba(248, 113, 113, 0.5);
  color: #fecaca;
}
.numel-runtime-btn:disabled {
  opacity: 0.55;
  cursor: default;
}
.numel-runtime-status {
  font-size: 0.9rem;
  color: var(--numel-runtime-muted);
  min-height: 20px;
}
.numel-runtime-status.success { color: var(--numel-runtime-success); }
.numel-runtime-status.error { color: var(--numel-runtime-danger); }
.numel-runtime-result {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  white-space: pre-wrap;
  line-height: 1.5;
  color: var(--numel-runtime-text);
  background: rgba(15, 23, 42, 0.66);
  border-radius: 12px;
  padding: 14px;
  max-height: 360px;
  overflow: auto;
}
.numel-runtime-log {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 220px;
  overflow: auto;
}
.numel-runtime-log-entry {
  display: flex;
  gap: 10px;
  font-size: 0.83rem;
  color: var(--numel-runtime-muted);
}
.numel-runtime-log-entry strong {
  color: var(--numel-runtime-text);
}
.numel-runtime-modal {
  position: fixed;
  inset: 0;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.56);
  z-index: 1000;
}
.numel-runtime-modal.open {
  display: flex;
}
.numel-runtime-modal-card {
  width: min(420px, 100%);
  background: #0f172a;
  color: #e5eef8;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  padding: 20px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.35);
}
.numel-runtime-modal-card h4 {
  margin: 0 0 10px;
  font-size: 1rem;
}
.numel-runtime-modal-card p {
  margin: 0 0 14px;
  color: #cbd5e1;
  line-height: 1.5;
}
@media (max-width: 768px) {
  .numel-runtime-card {
    padding: 16px;
    border-radius: 14px;
  }
}
"""


def _runtime_js() -> str:
	return r"""
(function () {
  var cfg = window.__NUMEL_PUBLISHED_APP__ || {};
  var root = document.getElementById('numel-runtime-root');
  if (!root) return;

  var execId = null;
  var pollTimer = null;
  var pendingNodeId = null;

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function inputType(field) {
    if (!field) return 'text';
    if (field.type === 'number' || field.type === 'int' || field.type === 'float' || field.type === 'integer') return 'number';
    if (field.type === 'bool') return 'checkbox';
    if (field.type === 'textarea') return 'textarea';
    return 'text';
  }

  function renderField(field) {
    var type = inputType(field);
    var id = 'numel-input-' + field.name;
    var label = esc(field.label || field.name);
    var required = field.required === false ? '' : ' required';
    if (type === 'textarea') {
      return '<div class="numel-runtime-field"><label for="' + id + '">' + label + '</label><textarea id="' + id + '" name="' + esc(field.name) + '"' + required + '>' + esc(field.default || '') + '</textarea></div>';
    }
    if (type === 'checkbox') {
      return '<div class="numel-runtime-field"><label for="' + id + '">' + label + '</label><input type="checkbox" id="' + id + '" name="' + esc(field.name) + '"' + (field.default ? ' checked' : '') + '></div>';
    }
    return '<div class="numel-runtime-field"><label for="' + id + '">' + label + '</label><input type="' + type + '" id="' + id + '" name="' + esc(field.name) + '" value="' + esc(field.default || '') + '"' + required + '></div>';
  }

  root.innerHTML = [
    '<section class="numel-runtime-card">',
      '<h3>Run Workflow</h3>',
      '<form id="numelRuntimeForm" class="numel-runtime-form">',
        (cfg.inputs || []).map(renderField).join(''),
        '<div class="numel-runtime-actions">',
          '<button type="submit" id="numelRuntimeRunBtn" class="numel-runtime-btn primary">Run</button>',
          '<button type="button" id="numelRuntimeCancelBtn" class="numel-runtime-btn secondary" style="display:none">Cancel</button>',
        '</div>',
      '</form>',
      '<div id="numelRuntimeStatus" class="numel-runtime-status"></div>',
    '</section>',
    '<section class="numel-runtime-card">',
      '<h3>Results</h3>',
      '<div id="numelRuntimeResult" class="numel-runtime-result">No execution yet.</div>',
    '</section>',
    '<section class="numel-runtime-card">',
      '<h3>Activity</h3>',
      '<div id="numelRuntimeLog" class="numel-runtime-log"></div>',
    '</section>',
    '<div id="numelRuntimeModal" class="numel-runtime-modal">',
      '<div class="numel-runtime-modal-card">',
        '<h4>Workflow input needed</h4>',
        '<p id="numelRuntimeModalPrompt"></p>',
        '<textarea id="numelRuntimeModalInput" class="numel-runtime-field" style="min-height:96px;"></textarea>',
        '<div class="numel-runtime-actions" style="margin-top:14px;">',
          '<button type="button" id="numelRuntimeModalSubmit" class="numel-runtime-btn primary">Submit</button>',
        '</div>',
      '</div>',
    '</div>'
  ].join('');

  var form = document.getElementById('numelRuntimeForm');
  var runBtn = document.getElementById('numelRuntimeRunBtn');
  var cancelBtn = document.getElementById('numelRuntimeCancelBtn');
  var statusEl = document.getElementById('numelRuntimeStatus');
  var resultEl = document.getElementById('numelRuntimeResult');
  var logEl = document.getElementById('numelRuntimeLog');
  var modal = document.getElementById('numelRuntimeModal');
  var modalPrompt = document.getElementById('numelRuntimeModalPrompt');
  var modalInput = document.getElementById('numelRuntimeModalInput');
  var modalSubmit = document.getElementById('numelRuntimeModalSubmit');

  function setStatus(text, kind) {
    statusEl.textContent = text || '';
    statusEl.className = 'numel-runtime-status' + (kind ? ' ' + kind : '');
  }

  function addLog(label, text) {
    var row = document.createElement('div');
    row.className = 'numel-runtime-log-entry';
    row.innerHTML = '<strong>' + esc(label) + '</strong><span>' + esc(text) + '</span>';
    logEl.prepend(row);
  }

  function collectFormData() {
    var payload = {};
    (cfg.inputs || []).forEach(function (field) {
      var el = document.getElementById('numel-input-' + field.name);
      if (!el) return;
      if (inputType(field) === 'checkbox') {
        payload[field.name] = !!el.checked;
        return;
      }
      var raw = el.value;
      if (inputType(field) === 'number') {
        payload[field.name] = raw === '' ? null : Number(raw);
        return;
      }
      payload[field.name] = raw;
    });
    return payload;
  }

  function openModal(nodeId, promptText) {
    pendingNodeId = nodeId;
    modalPrompt.textContent = promptText || 'Provide the requested input.';
    modalInput.value = '';
    modal.classList.add('open');
    modalInput.focus();
  }

  function closeModal() {
    pendingNodeId = null;
    modal.classList.remove('open');
  }

  function renderResult(payload) {
    resultEl.textContent = JSON.stringify(payload || {}, null, 2);
  }

  function findPendingInput(state) {
    var outputs = (state && state.node_outputs) || {};
    var prompts = cfg.user_inputs || {};
    for (var nodeId in outputs) {
      if (!Object.prototype.hasOwnProperty.call(outputs, nodeId)) continue;
      var content = outputs[nodeId] && outputs[nodeId].content;
      if (content && content.awaiting_input) {
        return {
          nodeId: nodeId,
          prompt: prompts[nodeId] || 'Provide the requested input.'
        };
      }
    }
    return null;
  }

  async function pollState() {
    if (!execId) return;
    try {
      var resp = await fetch(cfg.executionUrl.replace('__EXECUTION_ID__', encodeURIComponent(execId)), { method: 'POST' });
      if (!resp.ok) throw new Error('Failed to fetch execution state');
      var body = await resp.json();
      var state = body.state || {};
      if (state.status) {
        var status = String(state.status).toLowerCase();
        if (status === 'running' || status === 'pending') setStatus('Workflow is running...', '');
        if (status === 'waiting') setStatus('Workflow is waiting for input.', '');
      }
      var pending = findPendingInput(state);
      if (pending && pending.nodeId !== pendingNodeId) {
        addLog('Input', pending.prompt);
        openModal(pending.nodeId, pending.prompt);
      }
      if (state.node_outputs) {
        renderResult(state.node_outputs);
      }
      if (state.status === 'completed' || state.status === 'failed' || state.status === 'cancelled') {
        window.clearInterval(pollTimer);
        pollTimer = null;
        cancelBtn.style.display = 'none';
        runBtn.disabled = false;
        if (state.status === 'completed') {
          setStatus('Workflow completed.', 'success');
          addLog('Done', 'Execution completed.');
        } else {
          setStatus(state.error || ('Workflow ' + state.status + '.'), 'error');
          addLog('Error', state.error || ('Execution ' + state.status + '.'));
        }
      }
    } catch (err) {
      window.clearInterval(pollTimer);
      pollTimer = null;
      runBtn.disabled = false;
      cancelBtn.style.display = 'none';
      setStatus(err.message || String(err), 'error');
      addLog('Error', err.message || String(err));
    }
  }

  form.addEventListener('submit', async function (event) {
    event.preventDefault();
    runBtn.disabled = true;
    cancelBtn.style.display = '';
    setStatus('Starting workflow...', '');
    addLog('Run', 'Workflow start requested.');
    try {
      var resp = await fetch(cfg.startUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(collectFormData())
      });
      var body = await resp.json();
      if (!resp.ok || body.error) throw new Error(body.error || 'Failed to start workflow');
      execId = body.execution_id;
      addLog('Started', execId);
      pollTimer = window.setInterval(pollState, 1000);
      pollState();
    } catch (err) {
      runBtn.disabled = false;
      cancelBtn.style.display = 'none';
      setStatus(err.message || String(err), 'error');
      addLog('Error', err.message || String(err));
    }
  });

  cancelBtn.addEventListener('click', async function () {
    if (!execId) return;
    try {
      await fetch(cfg.cancelUrl.replace('__EXECUTION_ID__', encodeURIComponent(execId)), { method: 'POST' });
      addLog('Cancel', 'Cancellation requested.');
      setStatus('Cancellation requested...', '');
    } catch (err) {
      setStatus(err.message || String(err), 'error');
    }
  });

  modalSubmit.addEventListener('click', async function () {
    if (!execId || !pendingNodeId) return;
    try {
      var resp = await fetch(cfg.inputUrl.replace('__EXECUTION_ID__', encodeURIComponent(execId)), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: pendingNodeId, input_data: modalInput.value })
      });
      if (!resp.ok) throw new Error('Failed to submit workflow input');
      addLog('Input', 'Provided workflow input.');
      closeModal();
      pollState();
    } catch (err) {
      setStatus(err.message || String(err), 'error');
    }
  });

  document.dispatchEvent(new CustomEvent('numel-published-app-ready', { detail: cfg }));
})();
"""


class PublishedAppManager:
	def __init__(
		self,
		workspace_mgr,
		config_path: str = _APPS_PATH,
		assets_root: str = _APPS_DIR,
		backend_name: Optional[str] = None,
	):
		self._ws_mgr = workspace_mgr
		self._config_path = str(config_path)
		self._assets_root = Path(assets_root)
		self._backend_name = backend_name
		self._apps: Dict[str, PublishedApp] = {}
		self._public_index: Dict[str, str] = {}

	def initialize(self):
		self._assets_root.mkdir(parents=True, exist_ok=True)
		self._load()
		log_print(f"Published apps initialized ({len(self._apps)} apps)")

	def _make_key(self, owner_user_id: str, slug: str) -> str:
		return f"{owner_user_id}:{slug.lower()}"

	def _rebuild_public_index(self) -> None:
		self._public_index = {app.public_key: key for key, app in self._apps.items()}

	def _save(self):
		path = Path(self._config_path)
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(
			json.dumps({key: app.model_dump() for key, app in self._apps.items()}, indent=2),
			encoding="utf-8",
		)

	def _load(self):
		path = Path(self._config_path)
		if not path.exists():
			return
		try:
			raw = json.loads(path.read_text(encoding="utf-8"))
			for key, payload in raw.items():
				self._apps[key] = PublishedApp(**payload)
			self._rebuild_public_index()
		except Exception as exc:
			log_print(f"Failed to load published apps: {exc}")

	def list(self, owner_user_id: Optional[str] = None) -> List[dict]:
		items = []
		for app in self._apps.values():
			if owner_user_id and app.owner_user_id != owner_user_id:
				continue
			items.append(
				{
					"id": app.id,
					"name": app.name,
					"slug": app.slug,
					"owner_user_id": app.owner_user_id,
					"owner_username": app.owner_username,
					"description": app.description,
					"inputs": app.inputs,
					"published": app.published,
					"updated_at": app.updated_at,
					"enabled": app.enabled,
					"run_count": app.run_count,
					"error_count": app.error_count,
					"last_run_at": app.last_run_at,
					"last_error": app.last_error,
					"url": f"/apps/{app.owner_username}/{app.slug}",
					"generation": app.generation,
					"generated_summary": app.generated_summary,
				}
			)
		items.sort(key=lambda item: item["published"], reverse=True)
		return items

	def get(self, owner_username: str, slug: str) -> Optional[PublishedApp]:
		key = self._public_index.get(f"{owner_username.lower()}/{slug.lower()}")
		if not key:
			return None
		return self._apps.get(key)

	def get_asset_path(self, owner_username: str, slug: str, asset_path: str) -> Optional[Path]:
		app = self.get(owner_username, slug)
		if not app:
			return None
		candidate = (Path(app.asset_dir) / asset_path).resolve()
		root = Path(app.asset_dir).resolve()
		try:
			candidate.relative_to(root)
		except ValueError:
			return None
		if not candidate.exists() or not candidate.is_file():
			return None
		return candidate

	async def publish(
		self,
		*,
		owner_user_id: str,
		owner_username: str,
		name: str,
		workflow: Dict[str, Any],
		description: str = "",
		inputs: Optional[List[dict]] = None,
		slug: Optional[str] = None,
		generation_config: Optional[PublishedAppGenerationConfig] = None,
		page_generator: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
	) -> PublishedApp:
		final_slug = _slugify(slug or name or "app")
		final_inputs = list(inputs or detect_workflow_inputs(workflow))
		generator = page_generator or generate_published_app_bundle
		bundle = await generator(
			app_name=name,
			app_slug=final_slug,
			description=description,
			workflow=workflow,
			inputs=final_inputs,
			generation_config=generation_config,
			backend_name=self._backend_name,
		)

		key = self._make_key(owner_user_id, final_slug)
		existing = self._apps.get(key)
		asset_dir = self._assets_root / owner_user_id / final_slug
		if asset_dir.exists():
			shutil.rmtree(asset_dir, ignore_errors=True)
		asset_dir.mkdir(parents=True, exist_ok=True)

		app = PublishedApp(
			id=existing.id if existing else f"app_{uuid.uuid4().hex[:8]}",
			name=name,
			slug=final_slug,
			owner_user_id=owner_user_id,
			owner_username=owner_username,
			description=description,
			workflow=workflow,
			inputs=final_inputs,
			workflow_summary=dict(bundle.get("workflow_summary") or {}),
			generation=(generation_config or PublishedAppGenerationConfig()).to_dict(),
			generated_summary=str(bundle.get("summary", "") or "").strip(),
			asset_dir=str(asset_dir),
			index_file=str(asset_dir / "index.html"),
			published=existing.published if existing else _utcnow(),
			updated_at=_utcnow(),
			enabled=True,
			run_count=existing.run_count if existing else 0,
			error_count=existing.error_count if existing else 0,
			last_run_at=existing.last_run_at if existing else None,
			last_error=existing.last_error if existing else None,
		)

		self._write_assets(app, list(bundle.get("files") or []))
		self._apps[key] = app
		self._rebuild_public_index()
		self._save()
		log_print(f"Published app: {app.name} → /apps/{app.owner_username}/{app.slug}")
		return app

	async def regenerate(
		self,
		*,
		owner_user_id: str,
		owner_username: str,
		slug: str,
		title: Optional[str] = None,
		description: Optional[str] = None,
		generation_config: Optional[PublishedAppGenerationConfig] = None,
		page_generator: Optional[Callable[..., Awaitable[Dict[str, Any]]]] = None,
	) -> PublishedApp:
		key = self._make_key(owner_user_id, slug)
		current = self._apps.get(key)
		if current is None:
			raise KeyError(slug)
		return await self.publish(
			owner_user_id=owner_user_id,
			owner_username=owner_username,
			name=(title or current.name).strip() or current.name,
			workflow=dict(current.workflow),
			description=current.description if description is None else description,
			inputs=list(current.inputs),
			slug=current.slug,
			generation_config=generation_config or PublishedAppGenerationConfig(**(current.generation or {})),
			page_generator=page_generator,
		)

	def _write_assets(self, app: PublishedApp, generated_files: List[Dict[str, str]]) -> None:
		asset_dir = Path(app.asset_dir)
		files_by_path = {item["path"]: item["content"] for item in generated_files}
		index_html = self._prepare_index_html(app, files_by_path.get("index.html", ""))
		(asset_dir / "index.html").write_text(index_html, encoding="utf-8")
		(asset_dir / "styles.css").write_text(files_by_path.get("styles.css", ""), encoding="utf-8")
		(asset_dir / "app.js").write_text(files_by_path.get("app.js", ""), encoding="utf-8")
		(asset_dir / "runtime.css").write_text(_runtime_css(), encoding="utf-8")
		(asset_dir / "runtime.js").write_text(_runtime_js(), encoding="utf-8")
		(asset_dir / "workflow.json").write_text(_safe_json_text(app.workflow), encoding="utf-8")
		(asset_dir / "manifest.json").write_text(
			_safe_json_text(
				{
					"name": app.name,
					"slug": app.slug,
					"owner_user_id": app.owner_user_id,
					"owner_username": app.owner_username,
					"description": app.description,
					"workflow_summary": app.workflow_summary,
					"generation": app.generation,
				}
			),
			encoding="utf-8",
		)
		for path, content in files_by_path.items():
			if path in {"index.html", "styles.css", "app.js"}:
				continue
			target = (asset_dir / path).resolve()
			try:
				target.relative_to(asset_dir.resolve())
			except ValueError:
				continue
			target.parent.mkdir(parents=True, exist_ok=True)
			target.write_text(content, encoding="utf-8")

	def _prepare_index_html(self, app: PublishedApp, raw_html: str) -> str:
		asset_base = f"/apps/{app.owner_username}/{app.slug}/assets/"

		def _normalize_asset_ref(value: str) -> str:
			normalized = str(value or "").strip()
			normalized = re.sub(r"^(?:\./)+", "", normalized)
			if normalized.startswith("assets/"):
				normalized = normalized[len("assets/") :]
			return normalized

		def _rewrite_relative_asset_urls(html: str) -> str:
			def _replace(match: re.Match[str]) -> str:
				attr = match.group(1)
				quote = match.group(2)
				raw_value = match.group(3).strip()
				lower = raw_value.lower()
				if (
					not raw_value
					or raw_value.startswith(("/", "#"))
					or lower.startswith(("http://", "https://", "data:", "mailto:", "tel:", "javascript:"))
				):
					return match.group(0)
				return f'{attr}={quote}{asset_base}{_normalize_asset_ref(raw_value)}{quote}'

			return re.sub(r'(?i)\b(href|src)=([\"\'])([^\"\']+)\2', _replace, html)

		config = {
			"name": app.name,
			"slug": app.slug,
			"owner_username": app.owner_username,
			"description": app.description,
			"inputs": app.inputs,
			"user_inputs": self._user_input_prompts(app.workflow),
			"startUrl": f"/apps/{app.owner_username}/{app.slug}/start",
			"executionUrl": f"/apps/{app.owner_username}/{app.slug}/executions/__EXECUTION_ID__",
			"cancelUrl": f"/apps/{app.owner_username}/{app.slug}/executions/__EXECUTION_ID__/cancel",
			"inputUrl": f"/apps/{app.owner_username}/{app.slug}/executions/__EXECUTION_ID__/input",
		}
		html = raw_html.strip() or (
			f"<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
			f"<title>{app.name}</title></head><body><main><!-- NUMEL_APP_RUNTIME --></main></body></html>"
		)
		html = _rewrite_relative_asset_urls(html)
		if "<!-- NUMEL_APP_RUNTIME -->" not in html:
			html = html.replace("</body>", "<!-- NUMEL_APP_RUNTIME --></body>")
			if "<!-- NUMEL_APP_RUNTIME -->" not in html:
				html += "<!-- NUMEL_APP_RUNTIME -->"
		html = html.replace("<!-- NUMEL_APP_RUNTIME -->", '<div id="numel-runtime-root"></div>', 1)
		runtime_css_href = f"{asset_base}runtime.css"
		styles_css_href = f"{asset_base}styles.css"
		runtime_js_src = f"{asset_base}runtime.js"
		app_js_src = f"{asset_base}app.js"
		head_additions: list[str] = []
		if "rel=\"icon\"" not in html and "rel='icon'" not in html:
			head_additions.append('<link rel="icon" href="data:,">')
		if runtime_css_href not in html:
			head_additions.append(f'<link rel="stylesheet" href="{runtime_css_href}">')
		if styles_css_href not in html:
			head_additions.append(f'<link rel="stylesheet" href="{styles_css_href}">')
		if head_additions:
			if "</head>" in html:
				html = html.replace("</head>", "".join(head_additions) + "</head>")
			else:
				html = "".join(head_additions) + html
		config_block = (
			"<script>window.__NUMEL_PUBLISHED_APP__ = "
			+ json.dumps(config, ensure_ascii=False)
			+ ";</script>"
		)
		script_tags: list[str] = []
		if runtime_js_src not in html:
			script_tags.append(f'<script src="{runtime_js_src}"></script>')
		if app_js_src not in html:
			script_tags.append(f'<script src="{app_js_src}"></script>')
		config_block += "".join(script_tags)
		if "</body>" in html:
			html = html.replace("</body>", config_block + "</body>")
		else:
			html += config_block
		return html

	def _user_input_prompts(self, workflow: Dict[str, Any]) -> Dict[str, str]:
		prompts: Dict[str, str] = {}
		for index, node in enumerate(workflow.get("nodes", []) or []):
			if not isinstance(node, dict) or node.get("type") != "user_input_flow":
				continue
			prompts[str(index)] = str(node.get("query", "") or "Provide the requested input.")
		return prompts

	def unpublish(self, owner_user_id: str, slug: str) -> bool:
		key = self._make_key(owner_user_id, slug)
		app = self._apps.get(key)
		if not app:
			return False
		shutil.rmtree(app.asset_dir, ignore_errors=True)
		del self._apps[key]
		self._rebuild_public_index()
		self._save()
		return True

	async def start(self, owner_username: str, slug: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
		app = self.get(owner_username, slug)
		if not app or not app.enabled:
			return {"error": "App not found or disabled"}
		try:
			ws_obj = self._ws_mgr.get_default_workspace()
			mgr = ws_obj.manager
			engine = ws_obj.engine
			temp_name = f"_published_{slug}_{uuid.uuid4().hex[:6]}"
			wf_obj = Workflow.model_validate(app.workflow)
			await mgr.add(wf_obj, temp_name)
			impl = await mgr.impl(temp_name)
			if not impl:
				await mgr.remove(temp_name)
				return {"error": "Failed to build workflow"}
			execution_id = await engine.start_workflow(
				workflow=impl["workflow"],
				backend=impl["backend"],
				initial_data=input_data,
			)
			asyncio.create_task(self._cleanup_when_done(engine, mgr, execution_id, temp_name, app))
			return {"execution_id": execution_id}
		except Exception as exc:
			return {"error": str(exc)}

	async def _cleanup_when_done(self, engine, mgr, execution_id: str, temp_name: str, app: PublishedApp):
		results = None
		for _ in range(960):
			results = engine.get_execution_results(execution_id)
			if results and results.get("status") in ("completed", "failed", "cancelled"):
				break
			await asyncio.sleep(0.5)
		try:
			await mgr.remove(temp_name)
		except Exception:
			pass
		app.run_count += 1
		app.last_run_at = _utcnow()
		if results and results.get("status") == "failed":
			app.error_count += 1
			app.last_error = results.get("error") or "unknown error"
		self._save()

	async def run(self, owner_username: str, slug: str, input_data: Dict[str, Any]) -> Dict[str, Any]:
		app = self.get(owner_username, slug)
		if not app or not app.enabled:
			return {"error": "App not found or disabled"}
		try:
			ws_obj = self._ws_mgr.get_default_workspace()
			mgr = ws_obj.manager
			engine = ws_obj.engine
			temp_name = f"_published_{slug}_{uuid.uuid4().hex[:6]}"
			wf_obj = Workflow.model_validate(app.workflow)
			await mgr.add(wf_obj, temp_name)
			impl = await mgr.impl(temp_name)
			if not impl:
				return {"error": "Failed to build workflow"}
			execution_id = await engine.start_workflow(
				workflow=impl["workflow"],
				backend=impl["backend"],
				initial_data=input_data,
			)
			for _ in range(240):
				results = engine.get_execution_results(execution_id)
				if results and results.get("status") in ("completed", "failed"):
					break
				await asyncio.sleep(0.5)
			results = engine.get_execution_results(execution_id)
			await mgr.remove(temp_name)
			if not results:
				return {"error": "Execution timed out"}
			return {
				"status": results.get("status", "unknown"),
				"outputs": results.get("node_outputs", {}),
				"error": results.get("error"),
			}
		except Exception as exc:
			return {"error": str(exc)}

	def _default_engine(self):
		return self._ws_mgr.get_default_workspace().engine

	def get_execution_state(self, execution_id: str) -> Optional[Dict[str, Any]]:
		state = self._default_engine().get_execution_state(execution_id)
		if state is None:
			return None
		return state.model_dump() if hasattr(state, "model_dump") else dict(state)

	def get_execution_results(self, execution_id: str) -> Optional[Dict[str, Any]]:
		return self._default_engine().get_execution_results(execution_id)

	async def cancel_execution(self, execution_id: str):
		return await self._default_engine().cancel_execution(execution_id)

	async def provide_user_input(self, execution_id: str, node_id: str, user_input: Any):
		return await self._default_engine().provide_user_input(
			execution_id=execution_id,
			node_id=node_id,
			user_input=user_input,
		)


def setup_published_apps_api(app: FastAPI, app_mgr: PublishedAppManager, gallery_mgr=None):
	def _require_auth(req: Request):
		user = getattr(req.state, "user", None)
		if not user:
			raise HTTPException(status_code=401, detail="Not authenticated")
		return user

	@app.post("/apps/list")
	async def apps_list(req: Request):
		user = _require_auth(req)
		return app_mgr.list(owner_user_id=user.id)

	@app.post("/apps/publish")
	async def apps_publish(request: PublishRequest, req: Request):
		user = _require_auth(req)
		page_generation = PublishedAppGenerationConfig(**(request.page_generation or {}))
		page_generator = getattr(req.app.state, "published_app_page_generator", None)
		result = await app_mgr.publish(
			owner_user_id=user.id,
			owner_username=user.username,
			name=request.title.strip() or "Untitled",
			workflow=request.workflow,
			description=request.description,
			inputs=request.inputs,
			slug=request.slug,
			generation_config=page_generation,
			page_generator=page_generator,
		)
		return {
			"slug": result.slug,
			"owner_username": result.owner_username,
			"url": f"/apps/{result.owner_username}/{result.slug}",
		}

	@app.post("/apps/regenerate")
	async def apps_regenerate(request: RegenerateRequest, req: Request):
		user = _require_auth(req)
		page_generator = getattr(req.app.state, "published_app_page_generator", None)
		try:
			result = await app_mgr.regenerate(
				owner_user_id=user.id,
				owner_username=user.username,
				slug=request.slug,
				title=request.title,
				description=request.description,
				generation_config=PublishedAppGenerationConfig(**(request.page_generation or {})) if request.page_generation else None,
				page_generator=page_generator,
			)
		except KeyError:
			return JSONResponse(status_code=404, content={"error": f"Published app '{request.slug}' not found"})
		return {
			"slug": result.slug,
			"owner_username": result.owner_username,
			"url": f"/apps/{result.owner_username}/{result.slug}",
			"updated_at": result.updated_at,
		}

	@app.post("/apps/unpublish")
	async def apps_unpublish(request: dict, req: Request):
		user = _require_auth(req)
		return {"removed": app_mgr.unpublish(user.id, request.get("slug", ""))}

	@app.get("/apps/{owner_username}/{slug}")
	async def apps_page(owner_username: str, slug: str):
		published_app = app_mgr.get(owner_username, slug)
		if not published_app or not published_app.enabled:
			return HTMLResponse("<h1>App not found</h1>", status_code=404)
		index_path = Path(published_app.index_file)
		if not index_path.exists():
			return HTMLResponse("<h1>App files are missing</h1>", status_code=404)
		return HTMLResponse(index_path.read_text(encoding="utf-8"))

	@app.get("/apps/{owner_username}/{slug}/assets/{asset_path:path}")
	async def apps_asset(owner_username: str, slug: str, asset_path: str):
		path = app_mgr.get_asset_path(owner_username, slug, asset_path)
		if path is None:
			raise HTTPException(status_code=404, detail="Asset not found")
		return FileResponse(path)

	@app.post("/apps/{owner_username}/{slug}/start")
	async def apps_start(owner_username: str, slug: str, request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		return JSONResponse(await app_mgr.start(owner_username, slug, body))

	@app.post("/apps/{owner_username}/{slug}/executions/{execution_id}")
	async def apps_execution_state(owner_username: str, slug: str, execution_id: str):
		published_app = app_mgr.get(owner_username, slug)
		if not published_app or not published_app.enabled:
			return JSONResponse(status_code=404, content={"error": "App not found or disabled"})
		state = app_mgr.get_execution_state(execution_id)
		if state is None:
			return JSONResponse(status_code=404, content={"error": f"Execution '{execution_id}' not found"})
		return {"execution_id": execution_id, "state": state}

	@app.post("/apps/{owner_username}/{slug}/executions/{execution_id}/cancel")
	async def apps_execution_cancel(owner_username: str, slug: str, execution_id: str):
		published_app = app_mgr.get(owner_username, slug)
		if not published_app or not published_app.enabled:
			return JSONResponse(status_code=404, content={"error": "App not found or disabled"})
		state = await app_mgr.cancel_execution(execution_id)
		return {"execution_id": execution_id, "status": "cancelled", "state": state}

	class _PublishedAppInputRequest(BaseModel):
		node_id: str
		input_data: Any

	@app.post("/apps/{owner_username}/{slug}/executions/{execution_id}/input")
	async def apps_execution_input(owner_username: str, slug: str, execution_id: str, request: _PublishedAppInputRequest):
		published_app = app_mgr.get(owner_username, slug)
		if not published_app or not published_app.enabled:
			return JSONResponse(status_code=404, content={"error": "App not found or disabled"})
		await app_mgr.provide_user_input(execution_id, request.node_id, request.input_data)
		return {
			"execution_id": execution_id,
			"status": "input_received",
			"node_id": request.node_id,
			"input_data": request.input_data,
		}

	@app.post("/apps/{owner_username}/{slug}/run")
	async def apps_run(owner_username: str, slug: str, request: Request):
		try:
			body = await request.json()
		except Exception:
			body = {}
		return JSONResponse(await app_mgr.run(owner_username, slug, body))
"""
"""
