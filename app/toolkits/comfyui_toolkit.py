# comfyui_toolkit.py — ComfyUI integration toolkit for Numel
# Usage: set ToolkitConfig name="comfyui_toolkit", args={"url": "http://localhost:8188"}
#
# Wraps the ComfyUI REST API so Numel workflows and agents can:
#   - Submit generation prompts and poll for results
#   - Upload images (for img2img, ControlNet, inpainting)
#   - Retrieve generated images
#   - Query available models, nodes, queue status
#   - Interrupt / clear the queue
#
# Requires a running ComfyUI instance (default http://localhost:8188).

import base64
import io
import json
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx


class ComfyUIToolkit:
	"""Toolkit for interacting with a ComfyUI server.
	Args: url (ComfyUI server URL, default http://localhost:8188),
	timeout (request timeout in seconds, default 120),
	poll_interval (seconds between status checks, default 1.0)."""

	__toolkit__ = True

	def __init__(
		self,
		url:           str   = "http://localhost:8188",
		timeout:       float = 120.0,
		poll_interval: float = 1.0,
	):
		self._url      = url.rstrip("/")
		self._timeout  = timeout
		self._poll     = poll_interval
		self._client   = httpx.Client(base_url=self._url, timeout=self._timeout)

	# ── Internal helpers ─────────────────────────────────────────

	def _get(self, path: str, **kwargs) -> Any:
		r = self._client.get(path, **kwargs)
		r.raise_for_status()
		return r.json()

	def _post(self, path: str, data: Any = None, **kwargs) -> Any:
		r = self._client.post(path, json=data, **kwargs)
		r.raise_for_status()
		try:
			return r.json()
		except Exception:
			return {"status": r.status_code}

	def _post_form(self, path: str, files: dict, data: dict = None) -> Any:
		r = self._client.post(path, files=files, data=data or {})
		r.raise_for_status()
		return r.json()

	# ── Generation ───────────────────────────────────────────────

	def generate(
		self,
		workflow:   Dict[str, Any],
		wait:       bool = True,
		front:      bool = False,
	) -> str:
		"""Submit a ComfyUI workflow (prompt format) for execution.
		Args:
			workflow: ComfyUI prompt dict (node_id → {class_type, inputs}).
			wait: If True, poll until completion and return results JSON. If False, return prompt_id immediately.
			front: If True, add to front of queue (priority).
		Returns: JSON string with prompt_id and (if wait=True) output images/data."""
		prompt_data = {
			"prompt":    workflow,
			"prompt_id": str(uuid.uuid4()),
		}
		if front:
			prompt_data["front"] = True

		result = self._post("/prompt", prompt_data)

		if "error" in result:
			return json.dumps({"error": result["error"], "node_errors": result.get("node_errors", {})})

		prompt_id = result.get("prompt_id", prompt_data["prompt_id"])

		if not wait:
			return json.dumps({"prompt_id": prompt_id, "queued": True})

		# Poll for completion
		return self._poll_until_done(prompt_id)

	def _poll_until_done(self, prompt_id: str) -> str:
		"""Poll /history/{prompt_id} until the job completes or times out."""
		deadline = time.time() + self._timeout
		while time.time() < deadline:
			try:
				history = self._get(f"/history/{prompt_id}")
				if prompt_id in history:
					entry = history[prompt_id]
					outputs = entry.get("outputs", {})
					status_info = entry.get("status", {})
					# Extract image URLs from outputs
					images = []
					for node_id, node_output in outputs.items():
						for img in node_output.get("images", []):
							filename  = img.get("filename", "")
							subfolder = img.get("subfolder", "")
							img_type  = img.get("type", "output")
							view_url  = f"{self._url}/view?filename={filename}&subfolder={subfolder}&type={img_type}"
							images.append({
								"node_id":   node_id,
								"filename":  filename,
								"subfolder": subfolder,
								"type":      img_type,
								"url":       view_url,
							})
					return json.dumps({
						"prompt_id": prompt_id,
						"status":    status_info.get("status_str", "completed"),
						"outputs":   outputs,
						"images":    images,
					})
			except Exception:
				pass  # history not ready yet
			time.sleep(self._poll)

		return json.dumps({"prompt_id": prompt_id, "error": "Timed out waiting for completion"})

	def generate_simple(
		self,
		prompt:          str,
		negative_prompt: str  = "",
		model:           str  = "",
		width:           int  = 512,
		height:          int  = 512,
		steps:           int  = 20,
		cfg:             float = 7.0,
		seed:            int  = -1,
		sampler:         str  = "euler",
		scheduler:       str  = "normal",
	) -> str:
		"""Generate an image with a simple text prompt (builds a standard txt2img workflow).
		Args:
			prompt: Positive text prompt.
			negative_prompt: Negative text prompt.
			model: Checkpoint filename (e.g., 'v1-5-pruned.safetensors'). If empty, uses first available.
			width/height: Image dimensions.
			steps: Sampling steps.
			cfg: Classifier-free guidance scale.
			seed: Random seed (-1 for random).
			sampler: Sampler name (euler, dpmpp_2m, etc.).
			scheduler: Scheduler name (normal, karras, etc.).
		Returns: JSON with prompt_id, status, images."""
		if seed < 0:
			import random
			seed = random.randint(0, 2**32 - 1)

		# Auto-detect model if not specified
		if not model:
			try:
				models = self._get("/models/checkpoints")
				if models:
					model = models[0]
			except Exception:
				return json.dumps({"error": "No model specified and could not auto-detect checkpoints"})

		# Build standard txt2img workflow in ComfyUI prompt format
		workflow = {
			"1": {
				"class_type": "CheckpointLoaderSimple",
				"inputs": {"ckpt_name": model}
			},
			"2": {
				"class_type": "CLIPTextEncode",
				"inputs": {"text": prompt, "clip": ["1", 1]}
			},
			"3": {
				"class_type": "CLIPTextEncode",
				"inputs": {"text": negative_prompt, "clip": ["1", 1]}
			},
			"4": {
				"class_type": "EmptyLatentImage",
				"inputs": {"width": width, "height": height, "batch_size": 1}
			},
			"5": {
				"class_type": "KSampler",
				"inputs": {
					"model":     ["1", 0],
					"positive":  ["2", 0],
					"negative":  ["3", 0],
					"latent_image": ["4", 0],
					"seed":      seed,
					"steps":     steps,
					"cfg":       cfg,
					"sampler_name": sampler,
					"scheduler": scheduler,
					"denoise":   1.0,
				}
			},
			"6": {
				"class_type": "VAEDecode",
				"inputs": {"samples": ["5", 0], "vae": ["1", 2]}
			},
			"7": {
				"class_type": "SaveImage",
				"inputs": {"images": ["6", 0], "filename_prefix": "numel_gen"}
			},
		}
		return self.generate(workflow, wait=True)

	# ── Image retrieval ──────────────────────────────────────────

	def get_image(self, filename: str, subfolder: str = "", img_type: str = "output") -> str:
		"""Retrieve a generated image as a base64-encoded data URL.
		Args:
			filename: Image filename from generation output.
			subfolder: Subfolder within the output directory.
			img_type: 'output', 'input', or 'temp'.
		Returns: base64 data URL string (data:image/png;base64,...)."""
		params = {"filename": filename, "type": img_type}
		if subfolder:
			params["subfolder"] = subfolder
		r = self._client.get("/view", params=params)
		r.raise_for_status()
		content_type = r.headers.get("content-type", "image/png")
		b64 = base64.b64encode(r.content).decode()
		return f"data:{content_type};base64,{b64}"

	def get_images_from_result(self, result_json: str) -> str:
		"""Extract all images from a generate() result as base64 data URLs.
		Args:
			result_json: JSON string returned by generate() or generate_simple().
		Returns: JSON array of {node_id, filename, data_url} objects."""
		result = json.loads(result_json)
		images = result.get("images", [])
		out = []
		for img in images:
			try:
				data_url = self.get_image(
					img["filename"],
					img.get("subfolder", ""),
					img.get("type", "output"),
				)
				out.append({
					"node_id":  img.get("node_id", ""),
					"filename": img["filename"],
					"data_url": data_url,
				})
			except Exception as e:
				out.append({"filename": img.get("filename", ""), "error": str(e)})
		return json.dumps(out)

	# ── Image upload ─────────────────────────────────────────────

	def upload_image(
		self,
		image_data: str,
		filename:   str  = "upload.png",
		img_type:   str  = "input",
		subfolder:  str  = "",
		overwrite:  bool = True,
	) -> str:
		"""Upload an image to ComfyUI (for img2img, ControlNet, inpainting masks).
		Args:
			image_data: Base64-encoded image data (with or without data URL prefix).
			filename: Target filename.
			img_type: 'input', 'temp', or 'output'.
			subfolder: Target subfolder.
			overwrite: Replace existing file with same name.
		Returns: JSON with uploaded filename, subfolder, type."""
		# Strip data URL prefix if present
		if "," in image_data and image_data.startswith("data:"):
			image_data = image_data.split(",", 1)[1]
		raw = base64.b64decode(image_data)

		files = {"image": (filename, io.BytesIO(raw), "image/png")}
		data  = {"type": img_type, "overwrite": "true" if overwrite else "false"}
		if subfolder:
			data["subfolder"] = subfolder

		return json.dumps(self._post_form("/upload/image", files=files, data=data))

	# ── Queue management ─────────────────────────────────────────

	def queue_status(self) -> str:
		"""Get current queue status (running and pending items).
		Returns: JSON with queue_running and queue_pending arrays."""
		return json.dumps(self._get("/queue"))

	def clear_queue(self) -> str:
		"""Clear all pending items from the queue.
		Returns: JSON status."""
		return json.dumps(self._post("/queue", {"clear": True}))

	def cancel_item(self, prompt_id: str) -> str:
		"""Remove a specific item from the queue.
		Args:
			prompt_id: The prompt ID to cancel.
		Returns: JSON status."""
		return json.dumps(self._post("/queue", {"delete": [prompt_id]}))

	def interrupt(self, prompt_id: str = "") -> str:
		"""Interrupt the currently running generation.
		Args:
			prompt_id: Optional — interrupt a specific prompt. If empty, interrupts any running prompt.
		Returns: JSON status."""
		data = {}
		if prompt_id:
			data["prompt_id"] = prompt_id
		return json.dumps(self._post("/interrupt", data))

	# ── History ──────────────────────────────────────────────────

	def history(self, prompt_id: str = "", max_items: int = 10) -> str:
		"""Get execution history.
		Args:
			prompt_id: If specified, get history for this prompt only.
			max_items: Maximum items to return (default 10).
		Returns: JSON history entries."""
		if prompt_id:
			return json.dumps(self._get(f"/history/{prompt_id}"))
		return json.dumps(self._get("/history", params={"max_items": max_items}))

	def clear_history(self) -> str:
		"""Clear all execution history.
		Returns: JSON status."""
		return json.dumps(self._post("/history", {"clear": True}))

	# ── Server info ──────────────────────────────────────────────

	def system_stats(self) -> str:
		"""Get ComfyUI system info (OS, RAM, GPU, VRAM, version).
		Returns: JSON with system and device information."""
		return json.dumps(self._get("/system_stats"))

	def list_models(self, folder: str = "checkpoints") -> str:
		"""List available models in a folder.
		Args:
			folder: Model folder name — 'checkpoints', 'loras', 'vae', 'controlnet', 'embeddings', etc.
		Returns: JSON array of filenames."""
		return json.dumps(self._get(f"/models/{folder}"))

	def list_model_folders(self) -> str:
		"""List all model folder names (checkpoints, loras, vae, etc.).
		Returns: JSON array of folder names."""
		return json.dumps(self._get("/models"))

	def list_nodes(self) -> str:
		"""List all available ComfyUI node types with their inputs/outputs.
		Returns: JSON mapping of node class names to their configuration.
		Note: This can be very large. Consider node_info() for a specific node."""
		info = self._get("/object_info")
		# Return just the names and categories for brevity
		summary = {}
		for name, details in info.items():
			summary[name] = {
				"category":    details.get("category", ""),
				"display_name": details.get("display_name", name),
				"description": details.get("description", ""),
				"output":      details.get("output", []),
			}
		return json.dumps(summary)

	def node_info(self, node_class: str) -> str:
		"""Get detailed info for a specific ComfyUI node type.
		Args:
			node_class: Node class name (e.g., 'KSampler', 'CheckpointLoaderSimple').
		Returns: JSON with inputs, outputs, category, description."""
		return json.dumps(self._get(f"/object_info/{node_class}"))

	# ── Memory management ────────────────────────────────────────

	def free_memory(self, unload_models: bool = True) -> str:
		"""Free GPU memory and optionally unload models.
		Args:
			unload_models: If True, also unload all loaded models from VRAM.
		Returns: JSON status."""
		return json.dumps(self._post("/free", {
			"unload_models": unload_models,
			"free_memory": True,
		}))
