# file_toolkit

import stat


from   datetime import datetime
from   pathlib  import Path


class FileToolkit:
	"""Filesystem Toolkit for safe file operations within a sandboxed root directory.

You have access to a shared filesystem workspace rooted at a configurable directory.
All paths are relative to this root and cannot escape it (path traversal is blocked).

Available operations:
- list_directory: browse directory contents with type/size indicators
- read_file: read text or binary file contents
- write_file: create or overwrite files (parent dirs created automatically)
- file_info: get file metadata (size, timestamps, permissions)
- search_files: recursive glob search for files matching a pattern

All operations are sandboxed to the root directory for safety."""

	__toolkit__ = True

	def __init__(self, root: str = "."):
		self._root = str(Path(root).resolve())

	def _safe_resolve(self, path: str) -> Path:
		root_abs = Path(self._root)
		target = (root_abs / path).resolve()
		try:
			target.relative_to(root_abs)
		except ValueError:
			raise ValueError(f"Path traversal blocked: '{path}' escapes root '{self._root}'")
		return target

	def list_directory(self, path: str = ".") -> str:
		"""List the contents of a directory with type indicators and file sizes.

		Args:
			path: Directory path relative to root. Defaults to root itself.

		Returns:
			Formatted directory listing.
		"""
		target = self._safe_resolve(path)
		if not target.exists():
			raise FileNotFoundError(f"Directory not found: {path}")
		if not target.is_dir():
			raise NotADirectoryError(f"Not a directory: {path}")
		entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
		lines = []
		for entry in entries:
			if entry.is_dir():
				lines.append(f"[DIR]  {entry.name}/")
			else:
				size = entry.stat().st_size
				lines.append(f"[FILE] {entry.name}  ({_fmt_size(size)})")
		if not lines:
			return "(empty directory)"
		return "\n".join(lines)

	def read_file(self, path: str) -> str:
		"""Read and return the contents of a file.

		Args:
			path: File path relative to root.

		Returns:
			The full contents of the file.
		"""
		target = self._safe_resolve(path)
		if not target.exists():
			raise FileNotFoundError(f"File not found: {path}")
		if _is_text_file(target):
			return target.read_text(encoding="utf-8")
		with open(target, mode="rb") as file:
			raw = file.read()
		return raw

	def write_file(self, path: str, content: str) -> str:
		"""Write content to a file, creating parent directories if needed.

		Args:
			path: File path relative to root.
			content: The content to write.

		Returns:
			Confirmation message with the number of bytes written.
		"""
		target = self._safe_resolve(path)
		self._safe_resolve(str(target.parent.relative_to(Path(self._root))))
		target.parent.mkdir(parents=True, exist_ok=True)
		if _is_text_file(target):
			n = target.write_text(str(content), encoding="utf-8")
		else:
			with open(target, mode="wb") as file:
				n = file.write(content)
		return f"Wrote {n} bytes to {path}"

	def file_info(self, path: str) -> str:
		"""Return metadata about a file or directory: size, timestamps, type, permissions.

		Args:
			path: File or directory path relative to root.

		Returns:
			Formatted metadata string.
		"""
		target = self._safe_resolve(path)
		if not target.exists():
			raise FileNotFoundError(f"Path not found: {path}")
		st = target.stat()
		kind = "directory" if target.is_dir() else "file"
		perms = stat.filemode(st.st_mode)
		created = datetime.fromtimestamp(st.st_ctime).isoformat(sep=" ", timespec="seconds")
		modified = datetime.fromtimestamp(st.st_mtime).isoformat(sep=" ", timespec="seconds")
		lines = [
			f"Path: {path}",
			f"Type: {kind}",
			f"Size: {_fmt_size(st.st_size)}",
			f"Created: {created}",
			f"Modified: {modified}",
			f"Permissions: {perms}",
		]
		return "\n".join(lines)

	def search_files(self, pattern: str = "*", path: str = ".") -> str:
		"""Recursively search for files matching a glob pattern.

		Args:
			pattern: Glob pattern to match (e.g. '*.py', '**/*.txt'). Defaults to '*'.
			path: Starting directory relative to root. Defaults to root itself.

		Returns:
			Newline-separated list of matching file paths relative to root.
		"""
		target = self._safe_resolve(path)
		if not target.exists():
			raise FileNotFoundError(f"Directory not found: {path}")
		root_abs = Path(self._root)
		matches = []
		for p in target.rglob(pattern):
			try:
				rel = p.relative_to(root_abs)
				matches.append(str(rel))
			except ValueError:
				continue
		matches.sort()
		if not matches:
			return "(no matches)"
		return "\n".join(matches)

	def open_preview(self, path: str) -> str:
		"""Open a file in an inline preview within the chat. Supports text, images, audio, video, and 3D models.

		Supported formats:
		- Text: .txt, .md, .log, .csv, .json, .xml, .py, .js, .html, .css, .yaml, .yml, .toml, .ini, .cfg
		- Images: .png, .jpg, .jpeg, .gif, .bmp, .webp, .svg
		- Audio: .mp3, .wav, .ogg, .flac, .aac, .m4a
		- Video: .mp4, .webm, .mov, .avi, .mkv
		- 3D Models: .glb, .gltf, .obj, .fbx, .stl

		Args:
			path: File path relative to root.

		Returns:
			A preview marker that the chat UI renders as an inline media viewer.
		"""
		target = self._safe_resolve(path)
		if not target.exists():
			raise FileNotFoundError(f"File not found: {path}")
		ext = target.suffix.lower()
		preview_type = _detect_preview_type(ext)
		abs_path = str(target).replace("\\", "/")
		return f"<<preview:{preview_type}:{abs_path}>>"


_PREVIEW_TYPE_MAP = {
	".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".bmp": "image", ".webp": "image", ".svg": "image",
	".mp3": "audio", ".wav": "audio", ".ogg": "audio", ".flac": "audio", ".aac": "audio", ".m4a": "audio",
	".mp4": "video", ".webm": "video", ".mov": "video", ".avi": "video", ".mkv": "video",
	".glb": "model3d", ".gltf": "model3d", ".obj": "model3d", ".fbx": "model3d", ".stl": "model3d",
	".txt": "text", ".md": "text", ".log": "text", ".csv": "text", ".json": "text", ".xml": "text",
	".py": "text", ".js": "text", ".html": "text", ".css": "text", ".yaml": "text", ".yml": "text",
	".toml": "text", ".ini": "text", ".cfg": "text", ".sh": "text", ".bat": "text",
}


def _detect_preview_type(ext: str) -> str:
	return _PREVIEW_TYPE_MAP.get(ext, "file")


def _fmt_size(size: int) -> str:
	for unit in ("B", "KB", "MB", "GB"):
		if size < 1024:
			return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
		size /= 1024
	return f"{size:.1f} TB"


def _is_text_file(path: Path) -> bool:
	"""Heuristic check if a file is likely text based on extension."""
	return path.suffix.lower() in {".txt", ".md", ".log", ".csv", ".json", ".xml"}
