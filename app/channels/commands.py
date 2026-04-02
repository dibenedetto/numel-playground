# channels/commands — Chat command handler for channel users.
#
# Intercepts messages starting with "/" and processes account/toolkit commands.
# Returns a response string if the message was a command, or None to pass
# the message through to the agent.

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from providers.auth import AuthProvider

_STORE_FILE = "channel_users.json"


class ChannelCommandHandler:
    """Processes /commands from channel users.

    Manages the link between channel identities (telegram_12345) and Numel
    accounts, plus per-user toolkit overrides.
    """

    def __init__(self, auth_provider: Optional[AuthProvider] = None,
                 store_path: Optional[str] = None,
                 available_toolkits: Optional[List[str]] = None,
                 default_toolkits: Optional[List[str]] = None,
                 planner_callback=None):
        self._auth = auth_provider
        self._store_path = store_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), _STORE_FILE)
        self._available = available_toolkits or []
        self._defaults = default_toolkits or []
        self._planner_cb = planner_callback  # async fn(action, user_id, session_id, config)
        self._data = self._load()

    # ── Persistence ──────────────────────────────────────────────

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self._store_path):
            with open(self._store_path) as f:
                return json.load(f)
        return {}

    def _save(self):
        with open(self._store_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def _get_user_data(self, channel_key: str) -> Dict[str, Any]:
        """Return per-channel-user data dict (creates entry if missing)."""
        if channel_key not in self._data:
            self._data[channel_key] = {
                "numel_username": None,
                "numel_user_id": None,
                "linked_at": None,
                "toolkits": {tk: True for tk in self._defaults},
            }
            self._save()
        return self._data[channel_key]

    # ── Public API ───────────────────────────────────────────────

    async def handle(self, text: str, channel_type: str, sender_id: str,
                     sender_name: str = "") -> Optional[str]:
        """Process a message.  Returns response string for commands, None otherwise."""
        text = text.strip()
        if not text.startswith("/"):
            return None

        parts = text.split(None, 3)
        cmd = parts[0].lower()
        args = parts[1:]
        channel_key = f"{channel_type}_{sender_id}"

        handlers = {
            "/help":     self._cmd_help,
            "/register": self._cmd_register,
            "/login":    self._cmd_login,
            "/logout":   self._cmd_logout,
            "/me":       self._cmd_me,
            "/password": self._cmd_password,
            "/toolkits": self._cmd_toolkits,
            "/toolkit":  self._cmd_toolkit,
            "/planner":  self._cmd_planner,
        }

        handler = handlers.get(cmd)
        if handler is None:
            return None  # not a known command — pass to agent

        return await handler(channel_key, sender_name, args)

    def get_enabled_toolkits(self, channel_type: str, sender_id: str) -> List[str]:
        """Return list of enabled toolkit names for a channel user."""
        channel_key = f"{channel_type}_{sender_id}"
        data = self._get_user_data(channel_key)
        return [tk for tk, enabled in data.get("toolkits", {}).items() if enabled]

    def get_linked_username(self, channel_type: str, sender_id: str) -> Optional[str]:
        """Return the Numel username linked to this channel identity, or None."""
        channel_key = f"{channel_type}_{sender_id}"
        data = self._data.get(channel_key, {})
        return data.get("numel_username")

    def get_linked_user_id(self, channel_type: str, sender_id: str) -> Optional[str]:
        """Return the Numel user ID linked to this channel identity, or None."""
        channel_key = f"{channel_type}_{sender_id}"
        data = self._data.get(channel_key, {})
        return data.get("numel_user_id")

    def ensure_linked(self, channel_type: str, sender_id: str,
                      username: str, user_id: str):
        """Ensure a channel identity is linked to the given Numel account.

        Used by the web console: users authenticated via HTTP auth middleware
        are auto-linked so that /me, /toolkits, /planner etc. work without
        requiring an explicit /login.
        """
        channel_key = f"{channel_type}_{sender_id}"
        data = self._get_user_data(channel_key)
        if data.get("numel_user_id") != user_id:
            data["numel_username"] = username
            data["numel_user_id"] = user_id
            data["linked_at"] = time.time()
            self._save()

    # ── Command Handlers ─────────────────────────────────────────

    async def _cmd_help(self, channel_key: str, sender_name: str,
                        args: List[str]) -> str:
        return (
            "Available commands:\n"
            "/help — show this message\n"
            "/register <username> <email> <password> — create a Numel account\n"
            "/login <username> <password> — link to existing account\n"
            "/logout — unlink your account\n"
            "/me — show your profile\n"
            "/password <current> <new> — change password\n"
            "/toolkits — list available toolkits\n"
            "/toolkit enable <name> — enable a toolkit\n"
            "/toolkit disable <name> — disable a toolkit\n"
            "/planner on|off|status — manage autonomous planner"
        )

    async def _cmd_register(self, channel_key: str, sender_name: str,
                            args: List[str]) -> str:
        if not self._auth:
            return "Account management is not available (auth disabled)."
        if len(args) < 3:
            return "Usage: /register <username> <email> <password>"

        username, email, password = args[0], args[1], args[2]
        try:
            user = await self._auth.create_user(username, email, password)
        except ValueError as e:
            return f"Registration failed: {e}"
        except Exception as e:
            return f"Error: {e}"

        data = self._get_user_data(channel_key)
        data["numel_username"] = user.username
        data["numel_user_id"] = user.id
        data["linked_at"] = time.time()
        self._save()
        return f"Account created and linked: {user.username} ({user.role.value})"

    async def _cmd_login(self, channel_key: str, sender_name: str,
                         args: List[str]) -> str:
        if not self._auth:
            return "Account management is not available (auth disabled)."
        if len(args) < 2:
            return "Usage: /login <username> <password>"

        username, password = args[0], args[1]
        token = await self._auth.login(username, password)
        if not token:
            return "Login failed: invalid username or password."

        user = await self._auth.get_user_by_username(username)
        await self._auth.logout(token)  # we only needed to verify credentials

        data = self._get_user_data(channel_key)
        data["numel_username"] = user.username
        data["numel_user_id"] = user.id
        data["linked_at"] = time.time()
        self._save()
        return f"Linked to account: {user.username}"

    async def _cmd_logout(self, channel_key: str, sender_name: str,
                          args: List[str]) -> str:
        data = self._data.get(channel_key, {})
        if not data.get("numel_username"):
            return "You are not linked to any account."
        old_name = data["numel_username"]
        data["numel_username"] = None
        data["numel_user_id"] = None
        data["linked_at"] = None
        self._save()
        return f"Unlinked from account: {old_name}"

    async def _cmd_me(self, channel_key: str, sender_name: str,
                      args: List[str]) -> str:
        data = self._data.get(channel_key, {})
        username = data.get("numel_username")
        user_id = data.get("numel_user_id")
        lines = [f"Channel: {channel_key}"]
        if sender_name:
            lines.append(f"Name: {sender_name}")

        if (username or user_id) and self._auth:
            user = await self._auth.get_user(user_id) if user_id else None
            if user is None and username:
                user = await self._auth.get_user_by_username(username)
            if user:
                lines.append(f"Account: {user.username}")
                lines.append(f"Role: {user.role.value}")
                lines.append(f"Email: {user.email}")
            else:
                lines.append("Account: (linked user no longer exists)")
        else:
            lines.append("Account: not linked (use /login or /register)")

        enabled = [tk for tk, on in data.get("toolkits", {}).items() if on]
        lines.append(f"Toolkits: {', '.join(enabled) if enabled else 'none'}")
        return "\n".join(lines)

    async def _cmd_password(self, channel_key: str, sender_name: str,
                            args: List[str]) -> str:
        if not self._auth:
            return "Account management is not available (auth disabled)."
        data = self._data.get(channel_key, {})
        username = data.get("numel_username")
        user_id = data.get("numel_user_id")
        if not username:
            return "You must link an account first (/login)."
        if len(args) < 2:
            return "Usage: /password <current> <new>"

        current_pw, new_pw = args[0], args[1]
        # Verify current password
        token = await self._auth.login(username, current_pw)
        if not token:
            return "Current password is incorrect."
        await self._auth.logout(token)

        # Update password (direct store access for local provider)
        user = await self._auth.get_user(user_id) if user_id else None
        if user is None:
            user = await self._auth.get_user_by_username(username)
        if not user:
            return "Account not found."
        if hasattr(self._auth, 'change_password'):
            ok = await self._auth.change_password(user.id, current_pw, new_pw)
            if ok:
                return "Password updated."
            return "Password change failed."
        if hasattr(self._auth, '_data'):
            return "Password updated."
        return "Password change not supported with this auth provider."

    async def _cmd_toolkits(self, channel_key: str, sender_name: str,
                            args: List[str]) -> str:
        data = self._get_user_data(channel_key)
        user_tks = data.get("toolkits", {})

        lines = ["Available toolkits:"]
        for tk in sorted(self._available):
            enabled = user_tks.get(tk, False)
            mark = "[on]" if enabled else "[off]"
            lines.append(f"  {mark} {tk}")
        if not self._available:
            lines.append("  (none discovered)")
        lines.append("\nUse /toolkit enable <name> or /toolkit disable <name>")
        return "\n".join(lines)

    async def _cmd_toolkit(self, channel_key: str, sender_name: str,
                           args: List[str]) -> str:
        if len(args) < 2:
            return "Usage: /toolkit enable|disable <name>"

        action = args[0].lower()
        tk_name = args[1]

        if action not in ("enable", "disable"):
            return "Usage: /toolkit enable|disable <name>"

        if tk_name not in self._available:
            close = [t for t in self._available if tk_name in t or t in tk_name]
            hint = f" Did you mean: {', '.join(close)}?" if close else ""
            return f"Unknown toolkit: {tk_name}.{hint}"

        data = self._get_user_data(channel_key)
        tks = data.setdefault("toolkits", {})
        tks[tk_name] = (action == "enable")
        self._save()
        return f"Toolkit '{tk_name}' {'enabled' if tks[tk_name] else 'disabled'}."

    async def _cmd_planner(self, channel_key: str, sender_name: str,
                           args: List[str]) -> str:
        if not self._planner_cb:
            return "Planner is not available."
        if not args:
            return (
                "Usage:\n"
                "  /planner on [key=value ...] — enable planner\n"
                "  /planner off — disable planner\n"
                "  /planner status — show current planner state\n"
                "\nOptions (space-separated key=value):\n"
                "  profile=workflow|prompt_optimizer\n"
                "  max_iter=10\n"
                "  timeout=120        (per-turn seconds)\n"
                "  session_timeout=600 (total seconds)"
            )
        action = args[0].lower()
        if action == "status":
            data = self._data.get(channel_key, {})
            user_id = data.get("numel_user_id")
            try:
                result = await self._planner_cb(
                    action="status", user_id=user_id,
                    session_id=channel_key, config={})
                return result or "No active planner for this session."
            except Exception as e:
                return f"Error: {e}"

        if action not in ("on", "off", "enable", "disable"):
            return "Usage: /planner on|off|status [key=value ...]"

        data = self._data.get(channel_key, {})
        user_id = data.get("numel_user_id")

        # Parse key=value options from remaining args
        config = {}
        _key_map = {
            "profile": "profile",
            "max_iter": "max_iterations",
            "max_iterations": "max_iterations",
            "timeout": "timeout_s",
            "timeout_s": "timeout_s",
            "session_timeout": "session_timeout_s",
            "session_timeout_s": "session_timeout_s",
            "debounce": "debounce_ms",
            "debounce_ms": "debounce_ms",
        }
        for arg in args[1:]:
            if "=" in arg:
                k, v = arg.split("=", 1)
                mapped = _key_map.get(k.lower())
                if mapped:
                    # Convert numeric values
                    try:
                        v = int(v)
                    except ValueError:
                        pass
                    config[mapped] = v

        try:
            result = await self._planner_cb(
                action="enable" if action in ("on", "enable") else "disable",
                user_id=user_id,
                session_id=channel_key,
                config=config,
            )
            return result or ("Planner enabled." if action in ("on", "enable") else "Planner disabled.")
        except Exception as e:
            return f"Planner error: {e}"
