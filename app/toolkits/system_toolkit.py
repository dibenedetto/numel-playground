# system_toolkit.py — System administration toolkit for the Numel assistant.
#
# Lets the agent query and manage users, quotas, execution history, and
# system stats.  All admin operations require the caller to have admin role.
#
# Usage: set ToolkitConfig name="system_toolkit",
#        args={"base_url": "http://localhost:11360"}

from typing import Any, Dict, List, Optional


class SystemToolkit:
	"""Toolkit for system administration: users, quotas, executions, stats.
	Args: base_url (server URL, default http://localhost:11360),
	      token (bearer token for admin auth — auto-injected if available)."""

	__toolkit__ = True

	def __init__(self, base_url: str = "http://localhost:11360", token: str = ""):
		self._base  = base_url.rstrip("/")
		self._token = token

	def _post(self, path: str, data: Any = None) -> dict:
		import httpx
		headers = {}
		if self._token:
			headers["Authorization"] = f"Bearer {self._token}"
		r = httpx.post(f"{self._base}{path}", json=data or {}, headers=headers, timeout=30)
		r.raise_for_status()
		return r.json()

	# ── System Stats ──────────────────────────────────────────────────

	def get_system_stats(self) -> str:
		"""Get system-wide statistics: total users, active users, total executions,
		active executions, and execution status breakdown."""
		try:
			data = self._post("/admin/stats")
			lines = [
				"System Statistics:",
				f"  Users: {data['active_users']} active / {data['total_users']} total",
				f"  Executions: {data['total_executions']} total, {data['active_executions']} running",
			]
			breakdown = data.get("execution_status_breakdown", {})
			if breakdown:
				parts = [f"{k}: {v}" for k, v in breakdown.items()]
				lines.append(f"  Status breakdown: {', '.join(parts)}")
			return "\n".join(lines)
		except Exception as e:
			return f"Error: {e}"

	# ── User Management ───────────────────────────────────────────────

	def list_users(self, active_only: bool = True, limit: int = 50, offset: int = 0) -> str:
		"""List registered users with their roles and quota summaries.
		Args: active_only (default True), limit (default 50), offset (default 0)."""
		try:
			data = self._post("/admin/users", {
				"active_only": active_only, "limit": limit, "offset": offset,
			})
			users = data.get("users", [])
			if not users:
				return "No users found."
			lines = [f"Users ({data.get('count', len(users))}):", ""]
			for u in users:
				q = u.get("quota", {})
				cpu_h = round(q.get("cpu_seconds_remaining", 0) / 3600, 1)
				storage_mb = round(q.get("storage_bytes_remaining", 0) / 1_048_576, 1)
				lines.append(
					f"  [{u['role']}] {u['username']} (id={u['id']}) "
					f"— CPU: {cpu_h}h, Storage: {storage_mb}MB, "
					f"Active: {u['active']}"
				)
			return "\n".join(lines)
		except Exception as e:
			return f"Error: {e}"

	def get_user(self, user_id: str) -> str:
		"""Get detailed info for a specific user including quota and permissions.
		Args: user_id (the user's ID string)."""
		try:
			data = self._post(f"/admin/users/{user_id}")
			u = data["user"]
			q = data.get("quota", {})
			perms = data.get("permissions", [])
			lines = [
				f"User: {u['username']}",
				f"  ID: {u['id']}",
				f"  Email: {u['email']}",
				f"  Role: {u['role']}",
				f"  Active: {u['active']}",
				f"  Quota:",
				f"    CPU remaining: {round(q.get('cpu_seconds_remaining', 0) / 3600, 1)}h",
				f"    Storage remaining: {round(q.get('storage_bytes_remaining', 0) / 1_048_576, 1)}MB",
				f"    Max concurrent runs: {q.get('max_concurrent_runs', 0)}",
				f"    GPU hours remaining: {q.get('gpu_hours_remaining', 0)}",
			]
			if perms:
				lines.append("  Permissions:")
				for p in perms:
					lines.append(f"    {p['resource']} → {p['access']}")
			else:
				lines.append("  Permissions: none")
			return "\n".join(lines)
		except Exception as e:
			return f"Error: {e}"

	def update_user(self, user_id: str, email: str = "", role: str = "",
					active: Optional[bool] = None) -> str:
		"""Update a user's profile. Only non-empty fields are changed.
		Args: user_id, email (optional), role (admin/user/viewer, optional),
		      active (True/False, optional)."""
		fields = {}
		if email:  fields["email"] = email
		if role:   fields["role"]  = role
		if active is not None: fields["active"] = active
		if not fields:
			return "No fields to update."
		try:
			data = self._post(f"/admin/users/{user_id}/update", fields)
			u = data["user"]
			return f"Updated user {u['username']}: role={u['role']}, active={u['active']}"
		except Exception as e:
			return f"Error: {e}"

	def delete_user(self, user_id: str) -> str:
		"""Deactivate a user account (soft-delete).
		Args: user_id (the user's ID string)."""
		try:
			self._post(f"/admin/users/{user_id}/delete")
			return f"User {user_id} deactivated."
		except Exception as e:
			return f"Error: {e}"

	# ── Quota Management ──────────────────────────────────────────────

	def update_quota(self, user_id: str, cpu_seconds_remaining: float = -1,
					 max_concurrent_runs: int = -1, storage_bytes_remaining: int = -1,
					 gpu_hours_remaining: float = -1, max_repos: int = -1) -> str:
		"""Update a user's resource quota. Only values >= 0 are applied.
		Args: user_id, cpu_seconds_remaining, max_concurrent_runs,
		      storage_bytes_remaining, gpu_hours_remaining, max_repos."""
		fields = {}
		if cpu_seconds_remaining >= 0:   fields["cpu_seconds_remaining"]   = cpu_seconds_remaining
		if max_concurrent_runs >= 0:     fields["max_concurrent_runs"]     = max_concurrent_runs
		if storage_bytes_remaining >= 0: fields["storage_bytes_remaining"] = storage_bytes_remaining
		if gpu_hours_remaining >= 0:     fields["gpu_hours_remaining"]     = gpu_hours_remaining
		if max_repos >= 0:               fields["max_repos"]              = max_repos
		if not fields:
			return "No quota fields to update (all values are -1 / unchanged)."
		try:
			data = self._post(f"/admin/users/{user_id}/quota", fields)
			q = data["quota"]
			return (
				f"Quota updated for {q['user_id']}:\n"
				f"  CPU: {round(q['cpu_seconds_remaining'] / 3600, 1)}h\n"
				f"  Storage: {round(q['storage_bytes_remaining'] / 1_048_576, 1)}MB\n"
				f"  Concurrent runs: {q['max_concurrent_runs']}\n"
				f"  GPU hours: {q['gpu_hours_remaining']}\n"
				f"  Max repos: {q['max_repos']}"
			)
		except Exception as e:
			return f"Error: {e}"

	# ── Permission Management ─────────────────────────────────────────

	def grant_permission(self, user_id: str, resource: str, access: str = "read") -> str:
		"""Grant a permission to a user on a resource.
		Args: user_id, resource (e.g. 'repo:user/data', 'workflow:my-flow'),
		      access (none/read/write/execute/owner, default 'read')."""
		try:
			data = self._post(f"/admin/users/{user_id}/permissions/grant",
							  {"resource": resource, "access": access})
			p = data["permission"]
			return f"Granted {p['access']} on {p['resource']} to user {p['user_id']}"
		except Exception as e:
			return f"Error: {e}"

	def revoke_permission(self, user_id: str, resource: str) -> str:
		"""Revoke a user's permission on a resource.
		Args: user_id, resource (e.g. 'repo:user/data')."""
		try:
			data = self._post(f"/admin/users/{user_id}/permissions/revoke",
							  {"resource": resource})
			return "Permission revoked." if data.get("ok") else "Permission not found."
		except Exception as e:
			return f"Error: {e}"

	# ── Execution History ─────────────────────────────────────────────

	def list_executions(self, workflow_name: str = "", limit: int = 20,
						offset: int = 0) -> str:
		"""List recent workflow executions with status and duration.
		Args: workflow_name (filter, optional), limit (default 20), offset (default 0)."""
		try:
			body = {"limit": limit, "offset": offset}
			if workflow_name:
				body["workflow_name"] = workflow_name
			data = self._post("/admin/executions", body)
			items  = data.get("executions", [])
			active = data.get("active_execution_ids", [])
			if not items and not active:
				return "No executions found."
			lines = []
			if active:
				lines.append(f"Active executions: {', '.join(active)}")
				lines.append("")
			if items:
				lines.append(f"Recent executions ({len(items)}):")
				for ex in items[:limit]:
					dur = ex.get("duration_ms")
					dur_str = f"{dur}ms" if dur else "—"
					err = f" ERROR: {ex['error']}" if ex.get("error") else ""
					lines.append(
						f"  [{ex.get('status', '?')}] {ex.get('workflow_name', '?')} "
						f"({ex.get('execution_id', '?')[:8]}...) "
						f"duration={dur_str} at {ex.get('timestamp', '?')}{err}"
					)
			return "\n".join(lines)
		except Exception as e:
			return f"Error: {e}"

	def cancel_execution(self, execution_id: str) -> str:
		"""Cancel a running workflow execution.
		Args: execution_id."""
		try:
			data = self._post(f"/admin/executions/{execution_id}/cancel")
			return "Execution cancelled." if data.get("ok") else f"Cancel failed: {data}"
		except Exception as e:
			return f"Error: {e}"
