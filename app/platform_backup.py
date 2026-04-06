"""Create or restore local-only Numel platform backups."""

from __future__ import annotations

import argparse
import json
import shutil
import time
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from platform_loader import load_platform_backend_config, resolve_platform_backend_config_path
from platform_local.support import resolve_database_path
from runtime_settings import get_runtime_settings


BACKUP_MANIFEST_VERSION = 1


@dataclass(frozen=True)
class BackupEntry:
	label: str
	path: Path
	archive_path: str
	kind: str

	def as_dict(self) -> dict[str, str]:
		return {
			"label": self.label,
			"path": str(self.path),
			"archive_path": self.archive_path,
			"kind": self.kind,
		}


def _entry_from_record(record: Mapping[str, Any]) -> BackupEntry:
	return BackupEntry(
		label=str(record["label"]),
		path=Path(str(record["path"])).resolve(),
		archive_path=str(record["archive_path"]),
		kind=str(record["kind"]),
	)


def _selected_local_section(config: Mapping[str, Any]) -> Mapping[str, Any]:
	backend = str(config.get("backend", "local") or "local").strip().lower()
	if backend != "local":
		raise ValueError(
			"platform_backup.py only supports the local/reference backend. "
			"Use the private production slice for production backup/restore."
		)
	section = config.get("local", {})
	if not isinstance(section, Mapping):
		raise ValueError("Missing local backend section")
	return section


def _database_url(config: Mapping[str, Any]) -> str:
	section = _selected_local_section(config)
	database = section.get("database", {})
	if not isinstance(database, Mapping):
		raise ValueError("Local backend is missing a database section")
	url = str(database.get("url", "") or "").strip()
	if not url:
		raise ValueError("Local backend does not define database.url")
	db_path = resolve_database_path(url)
	if db_path is None:
		raise ValueError("platform_backup.py only supports sqlite-backed local installs")
	return url


def _archive_part(value: str) -> str:
	return str(value).replace("\\", "/").strip("/")


def _runtime_entries() -> list[BackupEntry]:
	settings = get_runtime_settings()
	return [
		BackupEntry("workspaces", settings.workspace_storage_dir.resolve(), "data/runtime/workspaces", "dir"),
		BackupEntry("memory", settings.memory_storage_dir.resolve(), "data/runtime/memory", "dir"),
		BackupEntry("user_memory", settings.user_memory_dir.resolve(), "data/runtime/user_memory", "dir"),
		BackupEntry("gallery", settings.gallery_dir.resolve(), "data/runtime/gallery", "dir"),
		BackupEntry("skills", settings.user_skills_dir.resolve(), "data/runtime/skills", "dir"),
		BackupEntry("credentials_file", settings.process_credentials_path.resolve(), "data/runtime/credentials.json", "file"),
		BackupEntry("channel_users_file", settings.channel_users_path.resolve(), "data/runtime/channel_users.json", "file"),
		BackupEntry("channels_config_file", settings.channels_config_path.resolve(), "data/runtime/channels.json", "file"),
		BackupEntry("agent_tasks_file", settings.agent_tasks_path.resolve(), "data/runtime/agent_tasks.json", "file"),
		BackupEntry("published_apps_file", settings.published_apps_path.resolve(), "data/runtime/published_apps.json", "file"),
	]


def _unique_entries(entries: list[BackupEntry]) -> list[BackupEntry]:
	ordered = sorted(entries, key=lambda item: (len(item.path.parts), item.label))
	selected: list[BackupEntry] = []
	for entry in ordered:
		duplicate = False
		for kept in selected:
			if entry.path == kept.path:
				duplicate = True
				break
			if kept.kind == "dir":
				try:
					entry.path.relative_to(kept.path)
					duplicate = True
					break
				except ValueError:
					pass
		if not duplicate:
			selected.append(entry)
	return selected


def build_backup_plan(config_path: str | None = None) -> dict[str, Any]:
	resolved_config = resolve_platform_backend_config_path(config_path)
	config = load_platform_backend_config(resolved_config)
	section = _selected_local_section(config)
	db_url = _database_url(config)
	db_path = resolve_database_path(db_url)
	assert db_path is not None

	git_section = section.get("git", {})
	if not isinstance(git_section, Mapping):
		raise ValueError("Local backend is missing a git section")
	repos_root = str(git_section.get("repos_root", "") or "").strip()
	if not repos_root:
		raise ValueError("Local backend does not define git.repos_root")

	artifacts_section = section.get("artifacts", {})
	if not isinstance(artifacts_section, Mapping):
		raise ValueError("Local backend is missing an artifacts section")
	artifacts_root = str(artifacts_section.get("root_path", "") or "").strip()
	if not artifacts_root:
		raise ValueError("Local backend does not define artifacts.root_path")

	entries = _unique_entries(
		[
			BackupEntry("database", db_path.resolve(), "data/platform.db", "file"),
			BackupEntry("spaces", Path(repos_root).resolve(), "data/spaces", "dir"),
			BackupEntry("artifacts", Path(artifacts_root).resolve(), "data/artifacts", "dir"),
			*_runtime_entries(),
		]
	)
	included: list[dict[str, Any]] = []
	missing: list[dict[str, Any]] = []
	for entry in entries:
		record = entry.as_dict()
		record["exists"] = entry.path.exists()
		if entry.path.exists():
			included.append(record)
		else:
			missing.append(record)
	return {
		"config_path": resolved_config,
		"backend": "local",
		"database_url": db_url,
		"included": included,
		"missing": missing,
	}


def _write_empty_dir(zip_handle: zipfile.ZipFile, archive_path: str) -> None:
	info = zipfile.ZipInfo(_archive_part(archive_path).rstrip("/") + "/")
	info.date_time = time.localtime()[:6]
	info.compress_type = zipfile.ZIP_DEFLATED
	zip_handle.writestr(info, "")


def _write_entry(zip_handle: zipfile.ZipFile, entry: BackupEntry) -> None:
	if entry.kind == "file":
		zip_handle.write(entry.path, arcname=_archive_part(entry.archive_path))
		return
	_write_empty_dir(zip_handle, entry.archive_path)
	for child in sorted(entry.path.rglob("*")):
		if child.is_dir():
			continue
		relative = child.relative_to(entry.path)
		zip_handle.write(child, arcname=_archive_part(f"{entry.archive_path}/{relative.as_posix()}"))


def _default_backup_output() -> Path:
	settings = get_runtime_settings()
	backup_dir = settings.data_root / "backups"
	backup_dir.mkdir(parents=True, exist_ok=True)
	timestamp = time.strftime("%Y%m%d-%H%M%S")
	return (backup_dir / f"numel-local-backup-{timestamp}.zip").resolve()


def _temporary_work_dir(prefix: str) -> Path:
	settings = get_runtime_settings()
	temp_root = settings.data_root / "_tmp"
	temp_root.mkdir(parents=True, exist_ok=True)
	path = (temp_root / f"{prefix}{uuid.uuid4().hex[:8]}").resolve()
	path.mkdir(parents=True, exist_ok=False)
	return path


def create_backup_archive(config_path: str | None = None, output_path: str | None = None) -> dict[str, Any]:
	plan = build_backup_plan(config_path)
	resolved_output = Path(output_path).resolve() if output_path else _default_backup_output()
	resolved_output.parent.mkdir(parents=True, exist_ok=True)
	entries = [_entry_from_record(item) for item in plan["included"]]
	manifest = {
		"manifest_version": BACKUP_MANIFEST_VERSION,
		"created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
		"backend": "local",
		"config_path": plan["config_path"],
		"database_url": plan["database_url"],
		"included": [entry.as_dict() for entry in entries],
		"missing": plan["missing"],
	}
	with zipfile.ZipFile(resolved_output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
		archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
		config_text = Path(plan["config_path"]).read_text(encoding="utf-8")
		archive.writestr("config/platform_backend.json", config_text)
		for entry in entries:
			_write_entry(archive, entry)
	result = dict(plan)
	result["output_path"] = str(resolved_output)
	result["manifest_version"] = BACKUP_MANIFEST_VERSION
	return result


def _delete_target(path: Path) -> None:
	if not path.exists():
		return
	if path.is_file():
		path.unlink()
		return
	shutil.rmtree(path)


def restore_backup_archive(
	archive_path: str,
	*,
	config_path: str | None = None,
	overwrite: bool = False,
) -> dict[str, Any]:
	archive_file = Path(archive_path).resolve()
	if not archive_file.exists():
		raise FileNotFoundError(f"Backup archive not found: {archive_file}")
	current_plan = build_backup_plan(config_path)
	entries = {item["label"]: _entry_from_record(item) for item in current_plan["included"] + current_plan["missing"]}
	with zipfile.ZipFile(archive_file, mode="r") as archive:
		manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
		if int(manifest.get("manifest_version", 0) or 0) != BACKUP_MANIFEST_VERSION:
			raise ValueError("Unsupported backup manifest version")
		if str(manifest.get("backend", "")).strip().lower() != "local":
			raise ValueError("Only local backup archives can be restored with platform_backup.py")
		manifest_entries = manifest.get("included", [])
		if not isinstance(manifest_entries, list):
			raise ValueError("Backup manifest is missing the included entries list")
		selected = []
		for item in manifest_entries:
			if not isinstance(item, Mapping):
				continue
			label = str(item.get("label", "") or "").strip()
			entry = entries.get(label)
			if entry is not None:
				selected.append(entry)
		existing = [entry.path for entry in selected if entry.path.exists()]
		if existing and not overwrite:
			raise FileExistsError(
				"Restore target already exists. Re-run with --overwrite to replace local data: "
				+ ", ".join(str(path) for path in existing[:5])
			)
		temp_root = _temporary_work_dir("numel-local-restore-")
		try:
			archive.extractall(temp_root)
			for entry in selected:
				source = temp_root / Path(_archive_part(entry.archive_path))
				if not source.exists():
					continue
				if overwrite:
					_delete_target(entry.path)
				entry.path.parent.mkdir(parents=True, exist_ok=True)
				if entry.kind == "file":
					shutil.copy2(source, entry.path)
				else:
					shutil.copytree(source, entry.path, dirs_exist_ok=False)
		finally:
			shutil.rmtree(temp_root, ignore_errors=True)
	return {
		"archive_path": str(archive_file),
		"backend": "local",
		"restored_labels": [entry.label for entry in selected],
		"config_path": current_plan["config_path"],
	}


def _print_human_summary(payload: Mapping[str, Any], *, command: str) -> None:
	print(f"Local platform backup ({command})")
	print(f"  Config: {payload.get('config_path', '')}")
	print(f"  Backend: {payload.get('backend', '')}")
	if payload.get("database_url"):
		print(f"  Database: {payload['database_url']}")
	if payload.get("output_path"):
		print(f"  Output: {payload['output_path']}")
	if payload.get("archive_path"):
		print(f"  Archive: {payload['archive_path']}")
	if "included" in payload:
		print(f"  Included entries: {len(payload.get('included', []))}")
		print(f"  Missing entries: {len(payload.get('missing', []))}")
	if payload.get("restored_labels"):
		print(f"  Restored: {payload['restored_labels']}")


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(
		description="Create or restore local-only Numel backups (sqlite + git spaces + local runtime files)."
	)
	subparsers = parser.add_subparsers(dest="command", required=True)

	plan_parser = subparsers.add_parser("plan", help="Show what a local backup would include")
	plan_parser.add_argument("--config", help="Path to platform_backend.json")
	plan_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")

	backup_parser = subparsers.add_parser("backup", help="Create a local backup archive")
	backup_parser.add_argument("--config", help="Path to platform_backend.json")
	backup_parser.add_argument("--output", help="Destination zip file path")
	backup_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")

	restore_parser = subparsers.add_parser("restore", help="Restore a local backup archive")
	restore_parser.add_argument("--config", help="Path to platform_backend.json")
	restore_parser.add_argument("--archive", required=True, help="Backup archive to restore")
	restore_parser.add_argument("--overwrite", action="store_true", help="Replace existing local data")
	restore_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")

	args = parser.parse_args(argv)

	try:
		if args.command == "plan":
			payload = build_backup_plan(args.config)
		elif args.command == "backup":
			payload = create_backup_archive(args.config, args.output)
		else:
			payload = restore_backup_archive(args.archive, config_path=args.config, overwrite=args.overwrite)
	except Exception as exc:
		if getattr(args, "json", False):
			print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
		else:
			print(f"Error: {exc}")
		return 1

	if getattr(args, "json", False):
		print(json.dumps(payload, indent=2))
	else:
		_print_human_summary(payload, command=args.command)
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
