# code_toolkit — Self-improving toolkit for the console agent
#
# Allows the agent to create, list, and reload Python toolkits at runtime.
# New toolkits are written to contrib/toolkits/ so they are user-generated
# and easy to review or delete.

import importlib
import os
import sys

from   inspect import getmembers, ismethod
from   pathlib import Path


# Resolve paths relative to the project root (parent of app/)
_APP_DIR      = os.path.dirname(os.path.abspath(__file__))            # app/toolkits/
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_APP_DIR))            # project root
_CONTRIB_DIR  = os.path.join(_PROJECT_ROOT, "contrib", "toolkits")    # contrib/toolkits/
_BUILTIN_DIR  = os.path.join(os.path.dirname(_APP_DIR), "toolkits")   # app/toolkits/


class CodeToolkit:
	"""Self-Improving Toolkit — create, inspect, and hot-reload Python toolkits.

Enables the assistant to extend its own capabilities by writing new Python
toolkit modules. New toolkits are saved to contrib/toolkits/ and can be
enabled via the toolkit picker in the UI.

Available operations:
- create_toolkit: write a new Python toolkit module
- list_toolkits: list all available toolkits with their tools
- read_toolkit: read the source code of an existing toolkit
- reload_toolkit: hot-reload a toolkit module after changes
- delete_toolkit: remove a contrib toolkit"""

	__toolkit__ = True

	def create_toolkit(self, name: str, code: str, overwrite: bool = False) -> str:
		"""Create a new Python toolkit module in contrib/toolkits/.

The code must define a class with __toolkit__ = True and at least one
public method (which becomes a tool). Methods must have docstrings.

Example code:
	class WeatherToolkit:
		\"\"\"Weather lookup tools.\"\"\"
		__toolkit__ = True

		def get_weather(self, city: str) -> str:
			\"\"\"Get current weather for a city.
			Args:
				city: City name.
			Returns:
				Weather description.
			\"\"\"
			return f"Weather in {city}: sunny, 22°C"

Args:
	name: Module name (without .py extension). Must be a valid Python identifier.
	code: Python source code for the toolkit.
	overwrite: If True, overwrite an existing toolkit with the same name.

Returns:
	Success or error message.
		"""
		# Validate name
		if not name.isidentifier():
			return f"Error: '{name}' is not a valid Python identifier."

		if name in ("console_toolkit", "file_toolkit", "code_toolkit"):
			return f"Error: cannot overwrite built-in toolkit '{name}'."

		filepath = os.path.join(_CONTRIB_DIR, f"{name}.py")

		if os.path.exists(filepath) and not overwrite:
			return (f"Error: toolkit '{name}' already exists at {filepath}. "
					"Set overwrite=True to replace it.")

		# Validate syntax
		try:
			compile(code, f"{name}.py", "exec")
		except SyntaxError as e:
			return f"Error: syntax error in toolkit code — {e}"

		# Validate it defines a toolkit class
		if "__toolkit__" not in code:
			return ("Error: code must define a class with __toolkit__ = True. "
					"This is how the system discovers the toolkit class.")

		# Write the file
		os.makedirs(_CONTRIB_DIR, exist_ok=True)
		with open(filepath, "w", encoding="utf-8") as f:
			f.write(code)

		# Try to import and validate
		try:
			mod_name = f"contrib.toolkits.{name}"
			if mod_name in sys.modules:
				del sys.modules[mod_name]
			mod = importlib.import_module(mod_name)

			# Find toolkit class
			toolkit_cls = None
			for attr_name in dir(mod):
				attr = getattr(mod, attr_name)
				if isinstance(attr, type) and getattr(attr, "__toolkit__", False):
					toolkit_cls = attr
					break

			if not toolkit_cls:
				os.remove(filepath)
				return "Error: code was written but no class with __toolkit__ = True was found. File removed."

			# Count public methods
			instance = toolkit_cls()
			tools = [m for m, _ in getmembers(instance, predicate=ismethod) if not m.startswith("_")]
			if not tools:
				os.remove(filepath)
				return "Error: toolkit class has no public methods (tools). File removed."

			return (f"Toolkit '{name}' created successfully at contrib/toolkits/{name}.py\n"
					f"Class: {toolkit_cls.__name__}\n"
					f"Tools: {', '.join(tools)}\n\n"
					f"To use it: ask the user to enable '{name}' in the toolkit picker, "
					f"or restart the agent with this toolkit included.")

		except Exception as e:
			# Remove the broken file
			if os.path.exists(filepath):
				os.remove(filepath)
			return f"Error: toolkit code failed to import — {e}. File removed."

	def list_toolkits(self) -> str:
		"""List all available toolkits with their tools and descriptions.

Scans both app/toolkits/ (built-in) and contrib/toolkits/ (user-created).

Returns:
	Formatted list of toolkits, their classes, and available tools.
		"""
		lines = []

		for label, search_dir, prefix in [
			("Built-in", _BUILTIN_DIR, "toolkits"),
			("User/Contrib", _CONTRIB_DIR, "contrib.toolkits"),
		]:
			if not os.path.isdir(search_dir):
				continue

			lines.append(f"\n{label} toolkits ({search_dir}):")
			found = False

			for fname in sorted(os.listdir(search_dir)):
				if fname.startswith("_") or not fname.endswith(".py"):
					continue
				mod_name = fname[:-3]
				full_mod = f"{prefix}.{mod_name}"
				found = True

				try:
					if full_mod in sys.modules:
						mod = sys.modules[full_mod]
					else:
						mod = importlib.import_module(full_mod)

					# Find toolkit class
					toolkit_cls = None
					for attr_name in dir(mod):
						attr = getattr(mod, attr_name)
						if isinstance(attr, type) and getattr(attr, "__toolkit__", False):
							toolkit_cls = attr
							break

					if toolkit_cls:
						doc = (toolkit_cls.__doc__ or "").strip().split("\n")[0]
						lines.append(f"  [{mod_name}] {toolkit_cls.__name__}: {doc}")

						# List tools
						try:
							instance = toolkit_cls() if mod_name not in ("console_toolkit",) else None
							if instance:
								for mname, method in getmembers(instance, predicate=ismethod):
									if mname.startswith("_"):
										continue
									mdoc = (method.__doc__ or "").strip().split("\n")[0]
									lines.append(f"    - {mname}: {mdoc}")
						except Exception:
							lines.append("    (could not inspect tools)")
					else:
						lines.append(f"  [{mod_name}] (no __toolkit__ class found)")

				except Exception as e:
					lines.append(f"  [{mod_name}] (failed to load: {e})")

			if not found:
				lines.append("  (none)")

		return "\n".join(lines) if lines else "No toolkits found."

	def read_toolkit(self, name: str) -> str:
		"""Read the source code of an existing toolkit.

Args:
	name: Toolkit module name (without .py).

Returns:
	The full source code of the toolkit, or an error message.
		"""
		# Check contrib first, then builtin
		for search_dir in [_CONTRIB_DIR, _BUILTIN_DIR]:
			filepath = os.path.join(search_dir, f"{name}.py")
			if os.path.exists(filepath):
				with open(filepath, "r", encoding="utf-8") as f:
					return f"# Source: {filepath}\n\n{f.read()}"

		return f"Error: toolkit '{name}' not found."

	def reload_toolkit(self, name: str) -> str:
		"""Hot-reload a toolkit module so code changes take effect immediately.

Args:
	name: Toolkit module name (without .py).

Returns:
	Success or error message.
		"""
		# Try both module paths
		for mod_path in [f"contrib.toolkits.{name}", f"toolkits.{name}"]:
			if mod_path in sys.modules:
				try:
					mod = importlib.reload(sys.modules[mod_path])
					# Verify toolkit class still exists
					for attr_name in dir(mod):
						attr = getattr(mod, attr_name)
						if isinstance(attr, type) and getattr(attr, "__toolkit__", False):
							return f"Toolkit '{name}' reloaded successfully (module: {mod_path})."
					return f"Warning: '{name}' reloaded but no __toolkit__ class found."
				except Exception as e:
					return f"Error reloading '{name}': {e}"

		# Not loaded yet, try to import
		for mod_path in [f"contrib.toolkits.{name}", f"toolkits.{name}"]:
			try:
				importlib.import_module(mod_path)
				return f"Toolkit '{name}' loaded for the first time (module: {mod_path})."
			except (ImportError, ModuleNotFoundError):
				continue

		return f"Error: toolkit '{name}' not found in any search path."

	def delete_toolkit(self, name: str) -> str:
		"""Delete a user-created toolkit from contrib/toolkits/.

Only contrib toolkits can be deleted. Built-in toolkits are protected.

Args:
	name: Toolkit module name (without .py).

Returns:
	Success or error message.
		"""
		# Prevent deleting built-in toolkits
		builtin_path = os.path.join(_BUILTIN_DIR, f"{name}.py")
		if os.path.exists(builtin_path):
			return f"Error: '{name}' is a built-in toolkit and cannot be deleted."

		filepath = os.path.join(_CONTRIB_DIR, f"{name}.py")
		if not os.path.exists(filepath):
			return f"Error: contrib toolkit '{name}' not found."

		os.remove(filepath)

		# Remove from sys.modules if loaded
		mod_path = f"contrib.toolkits.{name}"
		if mod_path in sys.modules:
			del sys.modules[mod_path]

		return f"Toolkit '{name}' deleted from contrib/toolkits/."
