# context_toolkit

import json
import platform
import os
import time

from   datetime import datetime, timezone
from   typing   import Optional


class ContextToolkit:
	"""System Context Sensing Toolkit.

You have access to methods that gather contextual information about the user's
environment. Use sense() to get a full snapshot, or call individual methods for
specific signals. The toolkit is designed to be extended with new signals over time.

Available signals:
- sense: full context snapshot (combines all enabled signals)
- get_time_context: current time, day of week, time-of-day category
- get_system_context: OS, platform, hostname, uptime, cpu/memory usage
- get_process_context: notable running processes (browsers, editors, etc.)
- get_active_window: currently focused window title and application
- get_network_context: network interfaces, connectivity, public IP
- get_disk_context: disk usage per mount point
- get_idle_context: user idle time (seconds since last input)
- get_clipboard_context: current clipboard text content (truncated)

The context dict returned by sense() is suitable for feeding directly into
an agent's request so it can reason about the user's current situation."""

	__toolkit__ = True

	def __init__(self, signals: Optional[str] = None):
		"""Initialize context toolkit.

		Args:
			signals: Comma-separated list of enabled signals (default: all).
			         Available: time, system, process, window, network, disk, idle, clipboard
		"""
		all_signals = {"time", "system", "process", "window", "network", "disk", "idle", "clipboard"}
		if signals:
			self._signals = {s.strip() for s in signals.split(",")} & all_signals
		else:
			self._signals = all_signals
		self._last_context = None

	def sense(self) -> str:
		"""Gather a full context snapshot from all enabled signals.

		Returns:
			JSON string with all context data keyed by signal name.
		"""
		dispatch = {
			"time":      self.get_time_context,
			"system":    self.get_system_context,
			"process":   self.get_process_context,
			"window":    self.get_active_window,
			"network":   self.get_network_context,
			"disk":      self.get_disk_context,
			"idle":      self.get_idle_context,
			"clipboard": self.get_clipboard_context,
		}
		ctx = {}
		for signal in self._signals:
			fn = dispatch.get(signal)
			if fn:
				try:
					ctx[signal] = json.loads(fn())
				except Exception as e:
					ctx[signal] = {"error": str(e)}
		self._last_context = ctx
		return json.dumps(ctx, indent=2)

	def get_changes(self) -> str:
		"""Compare current context with the last snapshot and return only changed fields.

		Returns:
			JSON string with changed fields. Empty dict if no previous snapshot.
		"""
		prev = self._last_context
		current = json.loads(self.sense())
		if not prev:
			return json.dumps({"note": "first snapshot, no previous context to compare"})

		changes = {}
		for key in current:
			if key not in prev or current[key] != prev[key]:
				changes[key] = {"previous": prev.get(key), "current": current[key]}
		return json.dumps(changes, indent=2) if changes else json.dumps({"changed": False})

	# ── Time ──────────────────────────────────────────────────────────────

	def get_time_context(self) -> str:
		"""Get current time context: timestamp, day of week, time-of-day category.

		Returns:
			JSON string with time information.
		"""
		now = datetime.now()
		utc_now = datetime.now(timezone.utc)
		hour = now.hour

		if 5 <= hour < 12:
			period = "morning"
		elif 12 <= hour < 14:
			period = "midday"
		elif 14 <= hour < 17:
			period = "afternoon"
		elif 17 <= hour < 21:
			period = "evening"
		else:
			period = "night"

		return json.dumps({
			"local_time":   now.strftime("%Y-%m-%d %H:%M:%S"),
			"utc_time":     utc_now.strftime("%Y-%m-%d %H:%M:%S"),
			"timezone":     time.tzname[0],
			"day_of_week":  now.strftime("%A"),
			"hour":         hour,
			"period":       period,
			"is_weekend":   now.weekday() >= 5,
		})

	# ── System ────────────────────────────────────────────────────────────

	def get_system_context(self) -> str:
		"""Get system information: OS, platform, hostname, CPU and memory usage.

		Returns:
			JSON string with system information.
		"""
		info = {
			"os":        platform.system(),
			"os_ver":    platform.version(),
			"hostname":  platform.node(),
			"arch":      platform.machine(),
			"python":    platform.python_version(),
		}

		try:
			import psutil
			info["cpu_percent"]        = psutil.cpu_percent(interval=0.1)
			mem = psutil.virtual_memory()
			info["memory_total_gb"]    = round(mem.total / (1024 ** 3), 1)
			info["memory_used_gb"]     = round(mem.used / (1024 ** 3), 1)
			info["memory_percent"]     = mem.percent
			info["boot_time"]          = datetime.fromtimestamp(psutil.boot_time()).strftime("%Y-%m-%d %H:%M:%S")
		except ImportError:
			info["note"] = "psutil not installed — cpu/memory stats unavailable"

		return json.dumps(info)

	# ── Processes ─────────────────────────────────────────────────────────

	def get_process_context(self) -> str:
		"""Get notable running processes (browsers, editors, communication apps).

		Returns:
			JSON string with categorized process list.
		"""
		categories = {
			"browsers":      {"chrome", "firefox", "msedge", "safari", "brave", "opera", "vivaldi"},
			"editors":       {"code", "cursor", "vim", "nvim", "emacs", "sublime_text", "notepad++", "idea", "pycharm", "webstorm"},
			"communication": {"slack", "discord", "teams", "zoom", "telegram", "signal", "whatsapp"},
			"media":         {"spotify", "vlc", "obs", "audacity"},
			"terminals":     {"windowsterminal", "iterm2", "alacritty", "wezterm", "hyper", "powershell", "cmd"},
		}

		result = {cat: [] for cat in categories}

		try:
			import psutil
			seen = set()
			for proc in psutil.process_iter(["name"]):
				try:
					name = proc.info["name"]
					if not name:
						continue
					name_lower = name.lower().replace(".exe", "")
					if name_lower in seen:
						continue
					seen.add(name_lower)
					for cat, names in categories.items():
						if name_lower in names:
							result[cat].append(name_lower)
				except (psutil.NoSuchProcess, psutil.AccessDenied):
					continue
		except ImportError:
			return json.dumps({"note": "psutil not installed — process scanning unavailable"})

		result = {k: v for k, v in result.items() if v}
		return json.dumps(result)

	# ── Active Window ─────────────────────────────────────────────────────

	def get_active_window(self) -> str:
		"""Get the currently focused window title and application name.

		Returns:
			JSON string with window title and app name.
		"""
		info = {"title": None, "app": None}
		system = platform.system()

		try:
			if system == "Windows":
				import ctypes
				from ctypes import wintypes
				user32 = ctypes.windll.user32
				hwnd = user32.GetForegroundWindow()
				length = user32.GetWindowTextLengthW(hwnd)
				buf = ctypes.create_unicode_buffer(length + 1)
				user32.GetWindowTextW(hwnd, buf, length + 1)
				info["title"] = buf.value or None

				# Get process name from window handle
				pid = wintypes.DWORD()
				user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
				try:
					import psutil
					proc = psutil.Process(pid.value)
					info["app"] = proc.name().replace(".exe", "")
				except Exception:
					info["app"] = f"pid:{pid.value}"

			elif system == "Darwin":
				import subprocess
				result = subprocess.run(
					["osascript", "-e",
					 'tell application "System Events" to get {name, title of first window} of first application process whose frontmost is true'],
					capture_output=True, text=True, timeout=2
				)
				if result.returncode == 0:
					parts = result.stdout.strip().split(", ", 1)
					info["app"] = parts[0] if parts else None
					info["title"] = parts[1] if len(parts) > 1 else None

			elif system == "Linux":
				import subprocess
				result = subprocess.run(["xdotool", "getactivewindow", "getwindowname"],
					capture_output=True, text=True, timeout=2)
				if result.returncode == 0:
					info["title"] = result.stdout.strip()
				result2 = subprocess.run(["xdotool", "getactivewindow", "getwindowpid"],
					capture_output=True, text=True, timeout=2)
				if result2.returncode == 0:
					try:
						import psutil
						proc = psutil.Process(int(result2.stdout.strip()))
						info["app"] = proc.name()
					except Exception:
						pass
		except Exception as e:
			info["error"] = str(e)

		return json.dumps(info)

	# ── Network ───────────────────────────────────────────────────────────

	def get_network_context(self) -> str:
		"""Get network connectivity status, active interfaces, and public IP.

		Returns:
			JSON string with network information.
		"""
		info = {"connected": False, "interfaces": []}

		try:
			import psutil
			stats = psutil.net_if_stats()
			addrs = psutil.net_if_addrs()
			import socket

			for iface, st in stats.items():
				if not st.isup or iface.startswith(("lo", "Loopback")):
					continue
				iface_info = {"name": iface, "speed_mbps": st.speed}
				# Get IPv4 address
				if iface in addrs:
					for addr in addrs[iface]:
						if addr.family == socket.AF_INET:
							iface_info["ipv4"] = addr.address
							break
				info["interfaces"].append(iface_info)

			info["connected"] = len(info["interfaces"]) > 0
		except ImportError:
			# Fallback: basic connectivity check
			import socket
			try:
				socket.create_connection(("8.8.8.8", 53), timeout=2)
				info["connected"] = True
			except OSError:
				info["connected"] = False

		# Public IP (best-effort, non-blocking-ish)
		if info["connected"]:
			try:
				import urllib.request
				req = urllib.request.Request("https://api.ipify.org?format=json", method="GET")
				with urllib.request.urlopen(req, timeout=3) as resp:
					data = json.loads(resp.read().decode())
					info["public_ip"] = data.get("ip")
			except Exception:
				pass

		return json.dumps(info)

	# ── Disk ──────────────────────────────────────────────────────────────

	def get_disk_context(self) -> str:
		"""Get disk usage for all mounted partitions.

		Returns:
			JSON string with per-mount disk usage.
		"""
		disks = []
		try:
			import psutil
			for part in psutil.disk_partitions(all=False):
				try:
					usage = psutil.disk_usage(part.mountpoint)
					disks.append({
						"mount":       part.mountpoint,
						"fstype":      part.fstype,
						"total_gb":    round(usage.total / (1024 ** 3), 1),
						"used_gb":     round(usage.used / (1024 ** 3), 1),
						"free_gb":     round(usage.free / (1024 ** 3), 1),
						"percent":     usage.percent,
					})
				except PermissionError:
					continue
		except ImportError:
			# Fallback for current drive
			import shutil
			total, used, free = shutil.disk_usage(".")
			disks.append({
				"mount":    os.getcwd()[:3] if platform.system() == "Windows" else "/",
				"total_gb": round(total / (1024 ** 3), 1),
				"used_gb":  round(used / (1024 ** 3), 1),
				"free_gb":  round(free / (1024 ** 3), 1),
				"percent":  round(used / total * 100, 1),
			})
		return json.dumps(disks)

	# ── Idle Time ─────────────────────────────────────────────────────────

	def get_idle_context(self) -> str:
		"""Get user idle time in seconds (time since last keyboard/mouse input).

		Returns:
			JSON string with idle_seconds and idle_category (active/idle/away/deep_away).
		"""
		idle_ms = None
		system = platform.system()

		try:
			if system == "Windows":
				import ctypes

				class LASTINPUTINFO(ctypes.Structure):
					_fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]

				lii = LASTINPUTINFO()
				lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
				if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
					tick = ctypes.windll.kernel32.GetTickCount()
					idle_ms = tick - lii.dwTime

			elif system == "Darwin":
				import subprocess
				result = subprocess.run(
					["ioreg", "-c", "IOHIDSystem"],
					capture_output=True, text=True, timeout=2
				)
				if result.returncode == 0:
					for line in result.stdout.splitlines():
						if "HIDIdleTime" in line:
							# Value is in nanoseconds
							val = line.split("=")[-1].strip()
							idle_ms = int(val) // 1_000_000
							break

			elif system == "Linux":
				import subprocess
				result = subprocess.run(["xprintidle"], capture_output=True, text=True, timeout=2)
				if result.returncode == 0:
					idle_ms = int(result.stdout.strip())
		except Exception:
			pass

		if idle_ms is not None:
			idle_sec = idle_ms / 1000.0
		else:
			idle_sec = -1  # unknown

		if idle_sec < 0:
			category = "unknown"
		elif idle_sec < 60:
			category = "active"
		elif idle_sec < 300:
			category = "idle"
		elif idle_sec < 900:
			category = "away"
		else:
			category = "deep_away"

		return json.dumps({
			"idle_seconds": round(idle_sec, 1),
			"idle_category": category,
		})

	# ── Clipboard ─────────────────────────────────────────────────────────

	def get_clipboard_context(self) -> str:
		"""Get current clipboard text content (truncated to 500 chars).

		Returns:
			JSON string with clipboard text and length.
		"""
		text = None
		system = platform.system()
		max_len = 500

		try:
			if system == "Windows":
				import ctypes
				user32 = ctypes.windll.user32
				kernel32 = ctypes.windll.kernel32
				if user32.OpenClipboard(0):
					try:
						handle = user32.GetClipboardData(13)  # CF_UNICODETEXT
						if handle:
							kernel32.GlobalLock.restype = ctypes.c_wchar_p
							text = kernel32.GlobalLock(handle)
							kernel32.GlobalUnlock(handle)
					finally:
						user32.CloseClipboard()

			elif system == "Darwin":
				import subprocess
				result = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=2)
				if result.returncode == 0:
					text = result.stdout

			elif system == "Linux":
				import subprocess
				result = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
					capture_output=True, text=True, timeout=2)
				if result.returncode == 0:
					text = result.stdout
		except Exception as e:
			return json.dumps({"error": str(e)})

		if text is None:
			return json.dumps({"text": None, "length": 0})

		full_len = len(text)
		return json.dumps({
			"text":      text[:max_len],
			"length":    full_len,
			"truncated": full_len > max_len,
		})
