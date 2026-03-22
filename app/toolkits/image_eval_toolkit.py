# image_eval_toolkit.py — Image quality evaluation toolkit for Numel
# Usage: set ToolkitConfig name="image_eval_toolkit"
#
# Provides CLIP-based image-text similarity scoring and LAION aesthetic
# quality scoring.  Models are loaded lazily on first call and cached.
#
# Dependencies (install as needed):
#   pip install transformers torch Pillow
#   pip install simple-aesthetics-predictor   # optional, for aesthetic scoring

import base64
import io
import json
from typing import Optional

_clip_model    = None
_clip_processor = None
_clip_tokenizer = None
_aes_model     = None
_aes_processor = None


def _ensure_clip():
	"""Lazy-load CLIP model (openai/clip-vit-base-patch32)."""
	global _clip_model, _clip_processor, _clip_tokenizer
	if _clip_model is not None:
		return
	import torch
	from transformers import CLIPModel, CLIPProcessor, CLIPTokenizerFast
	model_name = "openai/clip-vit-base-patch32"
	_clip_model     = CLIPModel.from_pretrained(model_name)
	_clip_processor = CLIPProcessor.from_pretrained(model_name)
	_clip_tokenizer = CLIPTokenizerFast.from_pretrained(model_name)
	_clip_model.eval()


def _ensure_aesthetic():
	"""Lazy-load LAION aesthetic predictor (uses CLIP ViT-L/14 + MLP head)."""
	global _aes_model, _aes_processor
	if _aes_model is not None:
		return
	try:
		from aesthetics_predictor import AestheticsPredictorV2Linear
		from transformers import CLIPProcessor as _CP
		model_id = "shunk031/aesthetics-predictor-v2-sac-logos-ava1-l14-linearMSE"
		_aes_model     = AestheticsPredictorV2Linear.from_pretrained(model_id)
		_aes_processor = _CP.from_pretrained("openai/clip-vit-large-patch14")
		_aes_model.eval()
	except ImportError:
		# Fallback: use CLIP similarity to "a beautiful, high quality photograph"
		# as a proxy for aesthetic quality
		_ensure_clip()
		_aes_model = "clip_fallback"


def _load_image(image_data: str):
	"""Load a PIL Image from base64 data URL or raw base64 string."""
	from PIL import Image
	if image_data.startswith("data:"):
		image_data = image_data.split(",", 1)[1]
	raw = base64.b64decode(image_data)
	return Image.open(io.BytesIO(raw)).convert("RGB")


class ImageEvalToolkit:
	"""Toolkit for evaluating image quality and prompt alignment.
	Uses CLIP for text-image similarity and LAION aesthetic predictor for quality.
	Models are loaded lazily on first use."""

	__toolkit__ = True

	def __init__(self):
		pass

	def clip_score(self, image_data: str, prompt: str) -> str:
		"""Score how well an image matches a text prompt using CLIP.
		Args:
			image_data: Base64-encoded image (with or without data URL prefix).
			prompt: The text prompt to compare against.
		Returns: JSON with score (0.0–1.0), raw_similarity, and interpretation."""
		_ensure_clip()
		import torch

		image = _load_image(image_data)
		inputs = _clip_processor(
			text=[prompt],
			images=image,
			return_tensors="pt",
			padding=True,
			truncation=True,
		)
		with torch.no_grad():
			outputs = _clip_model(**inputs)
			# logits_per_image is cosine similarity * 100
			similarity = outputs.logits_per_image[0][0].item()

		# Normalize to 0–1 range (CLIP similarities typically range 15–35)
		score = max(0.0, min(1.0, (similarity - 15.0) / 20.0))

		if score >= 0.8:
			interpretation = "Excellent match — image closely matches the prompt"
		elif score >= 0.6:
			interpretation = "Good match — image generally matches the prompt"
		elif score >= 0.4:
			interpretation = "Fair match — image partially matches the prompt"
		elif score >= 0.2:
			interpretation = "Poor match — image weakly relates to the prompt"
		else:
			interpretation = "No match — image does not match the prompt"

		return json.dumps({
			"score": round(score, 4),
			"raw_similarity": round(similarity, 4),
			"interpretation": interpretation,
			"prompt": prompt,
		})

	def aesthetic_score(self, image_data: str) -> str:
		"""Score the aesthetic quality of an image (composition, lighting, appeal).
		Uses LAION aesthetic predictor V2 if available, falls back to CLIP-based proxy.
		Args:
			image_data: Base64-encoded image (with or without data URL prefix).
		Returns: JSON with score (0.0–1.0), raw_score (1–10 scale), and interpretation."""
		_ensure_aesthetic()
		import torch

		image = _load_image(image_data)

		if _aes_model == "clip_fallback":
			# Fallback: CLIP similarity with aesthetic reference prompts
			positive_prompts = [
				"a beautiful, high quality, well-composed photograph",
				"professional photography, masterpiece, detailed",
			]
			negative_prompts = [
				"ugly, blurry, low quality, distorted",
				"amateur, poorly composed, overexposed",
			]
			inputs_pos = _clip_processor(
				text=positive_prompts, images=image,
				return_tensors="pt", padding=True, truncation=True,
			)
			inputs_neg = _clip_processor(
				text=negative_prompts, images=image,
				return_tensors="pt", padding=True, truncation=True,
			)
			with torch.no_grad():
				pos_sim = _clip_model(**inputs_pos).logits_per_image[0].mean().item()
				neg_sim = _clip_model(**inputs_neg).logits_per_image[0].mean().item()
			# Score based on difference between positive and negative similarity
			diff = pos_sim - neg_sim
			raw_score = max(1.0, min(10.0, 5.0 + diff * 0.3))
			score = (raw_score - 1.0) / 9.0  # normalize to 0–1
		else:
			# Use LAION aesthetic predictor
			inputs = _aes_processor(images=image, return_tensors="pt")
			with torch.no_grad():
				raw_score = _aes_model(**inputs).logits[0].item()
			# LAION scores are typically 1–10
			raw_score = max(1.0, min(10.0, raw_score))
			score = (raw_score - 1.0) / 9.0  # normalize to 0–1

		if score >= 0.8:
			interpretation = "Excellent — highly aesthetic, professional quality"
		elif score >= 0.6:
			interpretation = "Good — visually appealing, above average quality"
		elif score >= 0.4:
			interpretation = "Average — acceptable quality, some room for improvement"
		elif score >= 0.2:
			interpretation = "Below average — noticeable quality issues"
		else:
			interpretation = "Poor — significant quality problems"

		return json.dumps({
			"score": round(score, 4),
			"raw_score": round(raw_score, 4),
			"interpretation": interpretation,
		})

	def evaluate(self, image_data: str, prompt: str = "") -> str:
		"""Full evaluation: CLIP alignment score + aesthetic quality score + combined score.
		Args:
			image_data: Base64-encoded image (with or without data URL prefix).
			prompt: Text prompt to compare against (optional — if empty, only aesthetic score is computed).
		Returns: JSON with clip_score, aesthetic_score, combined_score, and feedback."""
		results = {}

		# Aesthetic score (always computed)
		try:
			aes = json.loads(self.aesthetic_score(image_data))
			results["aesthetic"] = aes
		except Exception as e:
			results["aesthetic"] = {"score": 0.0, "error": str(e)}

		# CLIP score (only if prompt provided)
		if prompt.strip():
			try:
				clip = json.loads(self.clip_score(image_data, prompt))
				results["clip"] = clip
			except Exception as e:
				results["clip"] = {"score": 0.0, "error": str(e)}

		# Combined score
		aes_score  = results.get("aesthetic", {}).get("score", 0.0)
		clip_score = results.get("clip", {}).get("score", 0.0) if prompt.strip() else None

		if clip_score is not None:
			# Weighted: 60% prompt alignment, 40% aesthetic quality
			combined = clip_score * 0.6 + aes_score * 0.4
			feedback_parts = [
				f"Prompt alignment: {clip_score:.0%}",
				f"Aesthetic quality: {aes_score:.0%}",
			]
		else:
			combined = aes_score
			feedback_parts = [f"Aesthetic quality: {aes_score:.0%}"]

		results["combined_score"] = round(combined, 4)
		results["feedback"] = " | ".join(feedback_parts)

		return json.dumps(results)

	def compare(self, image_data_a: str, image_data_b: str, prompt: str = "") -> str:
		"""Compare two images and determine which is better.
		Args:
			image_data_a: First image (base64).
			image_data_b: Second image (base64).
			prompt: Optional text prompt for alignment scoring.
		Returns: JSON with scores for both images, winner, and reasoning."""
		eval_a = json.loads(self.evaluate(image_data_a, prompt))
		eval_b = json.loads(self.evaluate(image_data_b, prompt))

		score_a = eval_a["combined_score"]
		score_b = eval_b["combined_score"]

		if abs(score_a - score_b) < 0.05:
			winner = "tie"
			reasoning = f"Both images are similar quality (A={score_a:.2f}, B={score_b:.2f})"
		elif score_a > score_b:
			winner = "A"
			reasoning = f"Image A is better (A={score_a:.2f} vs B={score_b:.2f})"
		else:
			winner = "B"
			reasoning = f"Image B is better (B={score_b:.2f} vs A={score_a:.2f})"

		return json.dumps({
			"image_a": eval_a,
			"image_b": eval_b,
			"winner": winner,
			"reasoning": reasoning,
		})
