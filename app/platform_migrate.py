"""Apply, inspect, or reset Numel platform schema migrations."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Mapping

from platform_loader import (
    load_platform_backend_config,
    resolve_platform_backend_config_path,
)
from platform_local.migrations import ensure_platform_schema, get_platform_schema_status
from platform_local.support import resolve_database_path


def _selected_backend_section(config: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    backend = str(config.get("backend", "local") or "local").strip().lower()
    section = config.get(backend, {})
    if not isinstance(section, Mapping):
        raise ValueError(f"Missing backend section for '{backend}'")
    return backend, section


def _database_url(config: Mapping[str, Any]) -> str:
    backend, section = _selected_backend_section(config)
    database = section.get("database", {})
    if not isinstance(database, Mapping):
        raise ValueError(f"Backend '{backend}' is missing a database section")
    url = str(database.get("url", "") or "").strip()
    if not url:
        raise ValueError(f"Backend '{backend}' does not define database.url")
    return url


def _resettable_paths(config: Mapping[str, Any]) -> list[Path]:
    _backend, section = _selected_backend_section(config)
    paths: list[Path] = []

    db_url = _database_url(config)
    db_path = resolve_database_path(db_url)
    if db_path is not None:
        paths.append(db_path)

    git_section = section.get("git", {})
    if isinstance(git_section, Mapping):
        repos_root = str(git_section.get("repos_root", "") or "").strip()
        if repos_root:
            paths.append(Path(repos_root).resolve())

    artifacts_section = section.get("artifacts", {})
    if isinstance(artifacts_section, Mapping):
        root_path = str(artifacts_section.get("root_path", "") or "").strip()
        if root_path:
            paths.append(Path(root_path).resolve())

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _delete_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_file():
        path.unlink()
        return
    shutil.rmtree(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply, inspect, or reset Numel platform schema migrations.")
    parser.add_argument("--config", help="Path to platform_backend.json (defaults to NUMEL_PLATFORM_CONFIG or app/platform_backend.json)")
    parser.add_argument("--check", action="store_true", help="Show migration status without applying migrations")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    parser.add_argument(
        "--reset-local-state",
        action="store_true",
        help="Delete the selected backend's local sqlite DB, git repos, and artifact root before continuing",
    )
    args = parser.parse_args(argv)

    config_path = resolve_platform_backend_config_path(args.config)
    config = load_platform_backend_config(config_path)
    db_url = _database_url(config)
    reset_paths = []

    if args.reset_local_state:
        reset_paths = [str(path) for path in _resettable_paths(config)]
        for path_str in reset_paths:
            _delete_path(Path(path_str))

    status = get_platform_schema_status(db_url) if args.check else ensure_platform_schema(db_url)

    payload = {
        "config_path": config_path,
        "backend": config.get("backend", "local"),
        "database_url": db_url,
        "current_version": status.current_version,
        "target_version": status.target_version,
        "applied_versions": status.applied_versions,
        "applied_now": status.applied_now,
        "reset_paths": reset_paths,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        mode = "status" if args.check else "apply"
        print(f"Platform migrations ({mode})")
        print(f"  Config: {payload['config_path']}")
        print(f"  Backend: {payload['backend']}")
        print(f"  Database: {payload['database_url']}")
        print(f"  Current version: {payload['current_version']}")
        print(f"  Target version: {payload['target_version']}")
        print(f"  Applied versions: {payload['applied_versions']}")
        if reset_paths:
            print(f"  Reset paths: {reset_paths}")
        if not args.check:
            print(f"  Applied now: {payload['applied_now']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
