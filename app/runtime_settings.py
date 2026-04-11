"""Runtime settings and mutable path layout for deployable Numel instances."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv


load_dotenv()


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent


def _path_from_env(name: str, default: Path | str, *, base_dir: Path = PROJECT_ROOT) -> Path:
    raw = os.getenv(name, "").strip()
    candidate = Path(raw) if raw else Path(default)
    if not candidate.is_absolute():
        candidate = (base_dir / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate


@dataclass(frozen=True)
class RuntimeSettings:
    project_root: Path
    app_dir: Path
    data_root: Path
    workspace_storage_dir: Path
    memory_storage_dir: Path
    user_memory_dir: Path
    process_credentials_path: Path
    console_agent_config_path: Path
    channel_users_path: Path
    channels_config_path: Path
    agent_tasks_path: Path
    published_apps_path: Path
    published_apps_dir: Path
    gallery_dir: Path
    builtin_gallery_dir: Path
    examples_dir: Path
    user_skills_dir: Path
    builtin_skills_dir: Path
    skills_state_path: Path
    web_dir: Path

    def ensure_directories(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        for directory in self.runtime_directories():
            directory.mkdir(parents=True, exist_ok=True)
        for file_path in self.runtime_files():
            file_path.parent.mkdir(parents=True, exist_ok=True)

    def runtime_directories(self) -> List[Path]:
        return [
            self.workspace_storage_dir,
            self.memory_storage_dir,
            self.user_memory_dir,
            self.gallery_dir,
            self.user_skills_dir,
            self.published_apps_dir,
        ]

    def runtime_files(self) -> List[Path]:
        return [
            self.process_credentials_path,
            self.channel_users_path,
            self.channels_config_path,
            self.agent_tasks_path,
            self.published_apps_path,
            self.skills_state_path,
        ]

    def public_dict(self) -> Dict[str, str]:
        data = asdict(self)
        return {key: str(value) for key, value in data.items()}


@lru_cache(maxsize=1)
def get_runtime_settings() -> RuntimeSettings:
    data_root = _path_from_env("NUMEL_DATA_ROOT", PROJECT_ROOT / "storage")
    return RuntimeSettings(
        project_root=PROJECT_ROOT,
        app_dir=APP_DIR,
        data_root=data_root,
        workspace_storage_dir=_path_from_env("NUMEL_WORKSPACES_DIR", data_root / "workspaces"),
        memory_storage_dir=_path_from_env("NUMEL_MEMORY_DIR", data_root / "memory"),
        user_memory_dir=_path_from_env("NUMEL_USER_MEMORY_DIR", data_root / "user_memory"),
        process_credentials_path=_path_from_env("NUMEL_CREDENTIALS_FILE", data_root / "credentials.json"),
        console_agent_config_path=_path_from_env("NUMEL_CONSOLE_AGENT_CONFIG", APP_DIR / "console_agent.json"),
        channel_users_path=_path_from_env("NUMEL_CHANNEL_USERS_FILE", data_root / "channel_users.json"),
        channels_config_path=_path_from_env("NUMEL_CHANNELS_CONFIG", data_root / "channels.json"),
        agent_tasks_path=_path_from_env("NUMEL_AGENT_TASKS_FILE", data_root / "agent_tasks.json"),
        published_apps_path=_path_from_env("NUMEL_PUBLISHED_APPS_FILE", data_root / "published_apps.json"),
        published_apps_dir=_path_from_env("NUMEL_PUBLISHED_APPS_DIR", data_root / "published_apps"),
        gallery_dir=_path_from_env("NUMEL_GALLERY_DIR", data_root / "gallery"),
        builtin_gallery_dir=(APP_DIR / "gallery").resolve(),
        examples_dir=(PROJECT_ROOT / "examples").resolve(),
        user_skills_dir=_path_from_env("NUMEL_SKILLS_DIR", data_root / "skills"),
        builtin_skills_dir=(APP_DIR / "skills").resolve(),
        skills_state_path=_path_from_env("NUMEL_SKILLS_STATE_FILE", data_root / "skills" / "_state.json"),
        web_dir=(PROJECT_ROOT / "web").resolve(),
    )
