# providers_impl/loader.py — Load and instantiate providers from config.
#
# Reads server_config.json and returns the three provider instances.
# Each provider key maps to an implementation class + constructor args.

from __future__ import annotations

import json
import os
from typing import Any, Dict, Tuple

from providers.auth      import AuthProvider
from providers.data      import DataProvider
from providers.execution import ExecutionProvider

# Registry of known implementations (import lazily to avoid hard deps)
_AUTH_PROVIDERS = {
    "local":    "providers_impl.local_auth.LocalAuthProvider",
    "django":   "providers_impl.django_auth.DjangoAuthProvider",
}

_DATA_PROVIDERS = {
    "local":    "providers_impl.local_data.LocalFSDataProvider",
    "gitea":    "providers_impl.gitea_data.GiteaDataProvider",
}

_EXEC_PROVIDERS = {
    "local":    "providers_impl.local_exec.LocalProcessExecProvider",
    "docker":   "providers_impl.docker_exec.DockerExecProvider",
}


def _import_class(dotted_path: str):
    """Import a class from a dotted path like 'package.module.ClassName'."""
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _instantiate(registry: dict, kind: str, config: dict):
    """Look up the implementation class and instantiate with config args."""
    impl_name = config.get("type", "local")

    if impl_name in registry:
        cls = _import_class(registry[impl_name])
    else:
        # Assume it's a fully qualified class path
        cls = _import_class(impl_name)

    # Pass all config keys except 'type' as constructor kwargs
    kwargs = {k: v for k, v in config.items() if k != "type"}
    try:
        return cls(**kwargs)
    except TypeError as e:
        raise TypeError(f"Failed to instantiate {kind} provider '{impl_name}': {e}") from e


def load_providers(
    config_path: str = None,
) -> Tuple[AuthProvider, DataProvider, ExecutionProvider]:
    """Load providers from a JSON config file.

    Config format (server_config.json):
    ```json
    {
        "auth": {
            "type": "local",
            "path": "users.json"
        },
        "data": {
            "type": "local",
            "root": "storage/repos"
        },
        "execution": {
            "type": "local",
            "api_url": "http://localhost:11360"
        }
    }
    ```

    Returns: (auth_provider, data_provider, execution_provider)
    """
    if config_path is None:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server_config.json")

    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)
    else:
        # Default: all local providers
        config = {
            "auth":      {"type": "local"},
            "data":      {"type": "local"},
            "execution": {"type": "local"},
        }

    auth = _instantiate(_AUTH_PROVIDERS, "auth", config.get("auth", {"type": "local"}))
    data = _instantiate(_DATA_PROVIDERS, "data", config.get("data", {"type": "local"}))
    exec_ = _instantiate(_EXEC_PROVIDERS, "execution", config.get("execution", {"type": "local"}))

    return auth, data, exec_
