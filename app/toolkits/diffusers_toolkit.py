# diffusers_toolkit.py — Native HuggingFace Diffusers image generation toolkit
# Usage: set ToolkitConfig name="diffusers_toolkit", args={"model": "stable-diffusion-v1-5/stable-diffusion-v1-5"}
#
# Generates images directly using HuggingFace diffusers — no external server needed.
# Models are loaded lazily on first call and cached in memory.
#
# Dependencies:
#   pip install diffusers transformers torch accelerate safetensors
#
# Supported model families:
#   - Stable Diffusion 1.5:  "stable-diffusion-v1-5/stable-diffusion-v1-5"
#   - Stable Diffusion 2.1:  "stabilityai/stable-diffusion-2-1"
#   - SDXL:                  "stabilityai/stable-diffusion-xl-base-1.0"
#   - SDXL Turbo:            "stabilityai/sdxl-turbo"
#   - Flux.1 Schnell:        "black-forest-labs/FLUX.1-schnell"
#   - Any diffusers-compatible model from HuggingFace Hub

import base64
import io
import json
import os
from typing import Optional


class DiffusersToolkit:
	"""Toolkit for generating images using HuggingFace Diffusers.
	Runs entirely in-process — no external server required.
	Args: model (HuggingFace model ID or local path),
	device ('cuda', 'cpu', or 'auto'), dtype ('float16', 'float32', 'bfloat16'),
	enable_attention_slicing (reduce VRAM at slight speed cost),
	output_dir (where to save generated images, default './output')."""

	__toolkit__ = True

	def __init__(
		self,
		model:                     str  = "stable-diffusion-v1-5/stable-diffusion-v1-5",
		device:                    str  = "auto",
		dtype:                     str  = "float16",
		enable_attention_slicing:  bool = True,
		output_dir:                str  = "./output",
	):
		self._model_id  = model
		self._device    = device
		self._dtype_str = dtype
		self._attn_slicing = enable_attention_slicing
		self._output_dir   = output_dir
		self._pipe         = None
		self._pipe_type    = None  # track which pipeline class was loaded

	def _ensure_pipe(self):
		"""Lazy-load the diffusion pipeline."""
		if self._pipe is not None:
			return

		import torch
		from diffusers import AutoPipelineForText2Image

		# Resolve device
		if self._device == "auto":
			device = "cuda" if torch.cuda.is_available() else "cpu"
		else:
			device = self._device

		# Resolve dtype
		dtype_map = {
			"float16":  torch.float16,
			"float32":  torch.float32,
			"bfloat16": torch.bfloat16,
		}
		dtype = dtype_map.get(self._dtype_str, torch.float16)
		# CPU doesn't support float16 well
		if device == "cpu":
			dtype = torch.float32

		self._pipe = AutoPipelineForText2Image.from_pretrained(
			self._model_id,
			torch_dtype=dtype,
		)
		self._pipe = self._pipe.to(device)

		if self._attn_slicing and device != "cpu":
			try:
				self._pipe.enable_attention_slicing()
			except Exception:
				pass

		# Create output directory
		os.makedirs(self._output_dir, exist_ok=True)

	def _image_to_base64(self, image) -> str:
		"""Convert PIL Image to base64 data URL."""
		buf = io.BytesIO()
		image.save(buf, format="PNG")
		b64 = base64.b64encode(buf.getvalue()).decode()
		return f"data:image/png;base64,{b64}"

	def _save_image(self, image, prefix: str = "numel") -> str:
		"""Save image to output directory, return the path."""
		import time
		filename = f"{prefix}_{int(time.time() * 1000)}.png"
		path = os.path.join(self._output_dir, filename)
		image.save(path)
		return path

	# ── Generation ───────────────────────────────────────────────

	def generate(
		self,
		prompt:          str,
		negative_prompt: str  = "",
		width:           int  = 512,
		height:          int  = 512,
		steps:           int  = 25,
		guidance_scale:  float = 7.5,
		seed:            int  = -1,
		num_images:      int  = 1,
	) -> str:
		"""Generate image(s) from a text prompt.
		Args:
			prompt: Text description of the desired image.
			negative_prompt: What to avoid in the image.
			width/height: Image dimensions (should be multiples of 8).
			steps: Number of inference steps (more = better quality, slower).
			guidance_scale: CFG scale — how closely to follow the prompt (7–12 typical).
			seed: Random seed (-1 for random).
			num_images: Number of images to generate (batch).
		Returns: JSON with images array [{path, data_url, seed}] and generation metadata."""
		self._ensure_pipe()
		import torch

		if seed < 0:
			import random
			seed = random.randint(0, 2**32 - 1)
		generator = torch.Generator(device=self._pipe.device).manual_seed(seed)

		kwargs = {
			"prompt":          prompt,
			"negative_prompt": negative_prompt if negative_prompt else None,
			"width":           width,
			"height":          height,
			"num_inference_steps": steps,
			"guidance_scale":  guidance_scale,
			"generator":       generator,
			"num_images_per_prompt": num_images,
		}
		# Remove None values
		kwargs = {k: v for k, v in kwargs.items() if v is not None}

		result = self._pipe(**kwargs)
		images = result.images

		outputs = []
		for i, img in enumerate(images):
			path     = self._save_image(img, "gen")
			data_url = self._image_to_base64(img)
			outputs.append({
				"index":    i,
				"path":     path,
				"data_url": data_url,
				"seed":     seed + i,
			})

		return json.dumps({
			"prompt":    prompt,
			"model":     self._model_id,
			"steps":     steps,
			"cfg":       guidance_scale,
			"seed":      seed,
			"width":     width,
			"height":    height,
			"images":    outputs,
		})

	def img2img(
		self,
		prompt:          str,
		image_data:      str,
		negative_prompt: str   = "",
		strength:        float = 0.75,
		steps:           int   = 25,
		guidance_scale:  float = 7.5,
		seed:            int   = -1,
	) -> str:
		"""Generate a new image based on a source image + text prompt (image-to-image).
		Args:
			prompt: Text description of desired modifications.
			image_data: Base64-encoded source image (with or without data URL prefix).
			negative_prompt: What to avoid.
			strength: How much to transform (0.0 = no change, 1.0 = full generation).
			steps: Inference steps.
			guidance_scale: CFG scale.
			seed: Random seed (-1 for random).
		Returns: JSON with generated image data."""
		import torch
		from PIL import Image
		from diffusers import AutoPipelineForImage2Image

		# Load source image
		if image_data.startswith("data:"):
			image_data = image_data.split(",", 1)[1]
		raw = base64.b64decode(image_data)
		source_image = Image.open(io.BytesIO(raw)).convert("RGB")

		# Load img2img pipeline (reuses model components)
		self._ensure_pipe()
		pipe = AutoPipelineForImage2Image.from_pipe(self._pipe)

		if seed < 0:
			import random
			seed = random.randint(0, 2**32 - 1)
		generator = torch.Generator(device=pipe.device).manual_seed(seed)

		kwargs = {
			"prompt":          prompt,
			"image":           source_image,
			"strength":        strength,
			"num_inference_steps": steps,
			"guidance_scale":  guidance_scale,
			"generator":       generator,
		}
		if negative_prompt:
			kwargs["negative_prompt"] = negative_prompt

		result = pipe(**kwargs)
		img = result.images[0]
		path     = self._save_image(img, "img2img")
		data_url = self._image_to_base64(img)

		return json.dumps({
			"prompt":   prompt,
			"strength": strength,
			"seed":     seed,
			"path":     path,
			"data_url": data_url,
		})

	# ── Utilities ────────────────────────────────────────────────

	def list_models(self) -> str:
		"""List recommended diffusion models available on HuggingFace.
		Returns: JSON array of {id, name, description, size} objects."""
		models = [
			{"id": "stable-diffusion-v1-5/stable-diffusion-v1-5",
			 "name": "SD 1.5", "description": "Classic Stable Diffusion — fast, widely supported", "vram": "4GB"},
			{"id": "stabilityai/stable-diffusion-2-1",
			 "name": "SD 2.1", "description": "Improved quality, 768px native resolution", "vram": "5GB"},
			{"id": "stabilityai/stable-diffusion-xl-base-1.0",
			 "name": "SDXL", "description": "High quality 1024px generation, dual text encoders", "vram": "7GB"},
			{"id": "stabilityai/sdxl-turbo",
			 "name": "SDXL Turbo", "description": "Fast 1-4 step generation via adversarial distillation", "vram": "7GB"},
			{"id": "black-forest-labs/FLUX.1-schnell",
			 "name": "FLUX.1 Schnell", "description": "Fast high-quality generation, 12B parameters", "vram": "12GB"},
			{"id": "black-forest-labs/FLUX.1-dev",
			 "name": "FLUX.1 Dev", "description": "Best quality FLUX model for local use", "vram": "24GB"},
		]
		return json.dumps(models)

	def model_info(self) -> str:
		"""Get info about the currently loaded model.
		Returns: JSON with model ID, device, dtype, and pipeline type."""
		return json.dumps({
			"model":    self._model_id,
			"device":   str(self._pipe.device) if self._pipe else self._device,
			"dtype":    self._dtype_str,
			"loaded":   self._pipe is not None,
			"output_dir": self._output_dir,
		})

	def change_model(self, model: str) -> str:
		"""Switch to a different model. Unloads the current model first.
		Args:
			model: HuggingFace model ID or local path.
		Returns: JSON confirmation."""
		self.unload()
		self._model_id = model
		return json.dumps({"model": model, "status": "Model set. Will load on next generation."})

	def unload(self) -> str:
		"""Unload the current model from memory to free GPU/RAM.
		Returns: JSON confirmation."""
		if self._pipe is not None:
			import gc
			del self._pipe
			self._pipe = None
			gc.collect()
			try:
				import torch
				if torch.cuda.is_available():
					torch.cuda.empty_cache()
			except Exception:
				pass
			return json.dumps({"status": "Model unloaded and memory freed"})
		return json.dumps({"status": "No model was loaded"})
