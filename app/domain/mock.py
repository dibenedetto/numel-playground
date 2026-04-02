"""Bridge objects describing how today's local implementation maps to the
abstract platform domain.

This is intentionally descriptive rather than fully normative: current Numel
still splits responsibility across auth providers, data providers,
workspace/runtime state, and a global credential store. The goal is to make
that split explicit while keeping a single object in app.state that future
concrete implementations can replace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class MockPlatformLayer:
    name: str
    abstract_role: str
    concrete_impl: str
    status: str
    notes: str = ""


@dataclass
class MockPlatformStack:
    abstraction_version: str = "0.1"
    auth_provider: Any = None
    data_provider: Any = None
    execution_provider: Any = None
    workspace_manager: Any = None
    secrets_backend: Any = None
    layers: Dict[str, MockPlatformLayer] = field(default_factory=dict)

    def describe(self) -> Dict[str, Dict[str, str]]:
        """Return a serializable summary of the current mockup coverage."""
        return {
            key: {
                "abstract_role": layer.abstract_role,
                "concrete_impl": layer.concrete_impl,
                "status": layer.status,
                "notes": layer.notes,
            }
            for key, layer in self.layers.items()
        }


def build_mock_platform_stack(
    auth_provider: Any,
    data_provider: Any,
    execution_provider: Any,
    workspace_manager: Any,
    secrets_backend: Any = None,
) -> MockPlatformStack:
    """Describe the current implementation using the new platform vocabulary."""
    auth_name = auth_provider.__class__.__name__ if auth_provider is not None else "None"
    data_name = data_provider.__class__.__name__ if data_provider is not None else "None"
    exec_name = execution_provider.__class__.__name__ if execution_provider is not None else "None"
    ws_name = workspace_manager.__class__.__name__ if workspace_manager is not None else "None"
    secrets_name = getattr(secrets_backend, "__name__", secrets_backend.__class__.__name__) if secrets_backend is not None else "None"

    layers = {
        "identity": MockPlatformLayer(
            name="identity",
            abstract_role="users, auth, profiles, quotas, coarse permissions",
            concrete_impl=auth_name,
            status="implemented",
            notes="AuthProvider already covers login, user CRUD, quotas, and generic permissions.",
        ),
        "spaces": MockPlatformLayer(
            name="spaces",
            abstract_role="user-owned repo-like spaces with visibility, refs, and history",
            concrete_impl=f"{data_name} + {ws_name}",
            status="partial",
            notes="Versioned repo concerns and live workspace/runtime concerns are still split across two systems.",
        ),
        "resources": MockPlatformLayer(
            name="resources",
            abstract_role="workflows, skills, toolkits, files, and future assets inside a space tree",
            concrete_impl=f"{data_name} + app-specific managers",
            status="partial",
            notes="Assets exist today but are not yet unified under one typed space asset model.",
        ),
        "runtime": MockPlatformLayer(
            name="runtime",
            abstract_role="isolated executions scoped to user, space, ref, runtime profile, and secrets",
            concrete_impl=f"{exec_name} + {ws_name}",
            status="partial",
            notes="Execution provider exists, but most current requests still flow through live WorkspaceManager and WorkflowEngine objects.",
        ),
        "secrets": MockPlatformLayer(
            name="secrets",
            abstract_role="per-user or per-space credentials resolved only for that user's runtime",
            concrete_impl=secrets_name,
            status="mock",
            notes="The current credentials module is still a shared server store, not a true user-scoped secrets backend.",
        ),
        "friends": MockPlatformLayer(
            name="friends",
            abstract_role="friend graph used by protected visibility and future collaboration rules",
            concrete_impl="not implemented",
            status="planned",
            notes="Friendship is part of the target platform model but does not yet exist in the current implementation.",
        ),
    }

    return MockPlatformStack(
        auth_provider=auth_provider,
        data_provider=data_provider,
        execution_provider=execution_provider,
        workspace_manager=workspace_manager,
        secrets_backend=secrets_backend,
        layers=layers,
    )
