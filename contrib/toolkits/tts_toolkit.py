# tts_toolkit — Text-to-Speech toolkit
#
# Provides TTS capabilities to the agent using edge-tts (Microsoft Edge voices).
# Can generate audio files from text, list available voices, etc.

import asyncio
import base64
import os
import tempfile


_CACHE_DIR = os.path.join(tempfile.gettempdir(), "numel_tts_cache")


class TTSToolkit:
	"""Text-to-Speech Toolkit — generate spoken audio from text using edge-tts.

Provides high-quality TTS with 300+ voices in 40+ languages.
Generated audio can be played in the browser or saved to file.

Available operations:
- speak: convert text to speech audio (returns base64 audio)
- list_voices: list available TTS voices with language/gender
- save_speech: generate and save speech to a file"""

	__toolkit__ = True

	def __init__(self, voice: str = "en-US-AriaNeural"):
		self._voice = voice

	def speak(self, text: str, voice: str = None) -> str:
		"""Convert text to speech and return base64-encoded MP3 audio.

		Args:
			text: The text to speak.
			voice: Voice name (e.g. 'en-US-AriaNeural'). Defaults to configured voice.

		Returns:
			A data URL (data:audio/mp3;base64,...) that can be played in the browser,
			or an error message if edge-tts is not available.
		"""
		try:
			import edge_tts
		except ImportError:
			return ("Error: edge-tts is required. Install with: pip install edge-tts\n"
					"Alternatively, the frontend can use the browser's built-in SpeechSynthesis API.")

		voice = voice or self._voice
		os.makedirs(_CACHE_DIR, exist_ok=True)
		outfile = os.path.join(_CACHE_DIR, f"tts_{hash(text + voice) & 0xFFFFFFFF:08x}.mp3")

		# Run the async edge-tts in a sync context
		async def _generate():
			comm = edge_tts.Communicate(text, voice)
			await comm.save(outfile)

		try:
			# Try to use existing event loop, or create new one
			try:
				loop = asyncio.get_running_loop()
				# We're in an async context — run in thread
				import concurrent.futures
				with concurrent.futures.ThreadPoolExecutor() as pool:
					loop.run_in_executor(pool, lambda: asyncio.run(_generate()))
					# Fallback: just run synchronously
					asyncio.run(_generate())
			except RuntimeError:
				asyncio.run(_generate())
		except Exception as e:
			return f"Error generating speech: {e}"

		try:
			with open(outfile, "rb") as f:
				audio_bytes = f.read()
			b64 = base64.b64encode(audio_bytes).decode()
			return f"data:audio/mp3;base64,{b64}"
		except Exception as e:
			return f"Error reading audio: {e}"

	def list_voices(self, language: str = None) -> str:
		"""List available TTS voices, optionally filtered by language.

		Args:
			language: Language code prefix to filter (e.g. 'en', 'es', 'ja'). None for all.

		Returns:
			Formatted list of available voices.
		"""
		try:
			import edge_tts
		except ImportError:
			return ("Error: edge-tts is required. Install with: pip install edge-tts\n"
					"Some popular voices:\n"
					"  en-US-AriaNeural (female), en-US-GuyNeural (male)\n"
					"  en-GB-SoniaNeural (female), en-GB-RyanNeural (male)\n"
					"  es-ES-ElviraNeural (female), fr-FR-DeniseNeural (female)\n"
					"  de-DE-KatjaNeural (female), ja-JP-NanamiNeural (female)")

		try:
			voices = asyncio.run(edge_tts.list_voices())
		except Exception as e:
			return f"Error listing voices: {e}"

		if language:
			voices = [v for v in voices if v.get("Locale", "").startswith(language)]

		lines = [f"Available voices ({len(voices)}):"]
		for v in voices[:50]:
			name   = v.get("ShortName", "?")
			gender = v.get("Gender", "?")
			locale = v.get("Locale", "?")
			lines.append(f"  {name} ({gender}, {locale})")

		if len(voices) > 50:
			lines.append(f"  ... and {len(voices) - 50} more")

		return "\n".join(lines)

	def save_speech(self, text: str, filepath: str, voice: str = None) -> str:
		"""Generate speech and save to an MP3 file.

		Args:
			text: The text to speak.
			filepath: Output file path (should end in .mp3).
			voice: Voice name. Defaults to configured voice.

		Returns:
			Success message with file path, or error.
		"""
		try:
			import edge_tts
		except ImportError:
			return "Error: edge-tts is required. Install with: pip install edge-tts"

		voice = voice or self._voice

		async def _generate():
			comm = edge_tts.Communicate(text, voice)
			await comm.save(filepath)

		try:
			asyncio.run(_generate())
			size = os.path.getsize(filepath)
			return f"Speech saved to {filepath} ({size} bytes)"
		except Exception as e:
			return f"Error: {e}"
