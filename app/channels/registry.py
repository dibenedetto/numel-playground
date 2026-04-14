# channels.registry — Channel adapter registry and lifecycle management
#
# Manages all active channel adapters, persists configuration,
# and provides a unified interface for the API layer.

import json
import os

from   typing   import Dict, List, Optional, Type
from   runtime_settings import get_runtime_settings
from   utils    import log_print

from   channels.base import ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


_CONFIG_PATH = str(get_runtime_settings().channels_config_path)


# =============================================================================
# REGISTRY
# =============================================================================

class ChannelRegistry:
	"""Manages channel adapters: registration, lifecycle, persistence."""

	# Class-level registry of adapter types
	_adapter_types: Dict[str, Type[ChannelAdapter]] = {}

	def __init__(self, message_handler: Optional[MessageHandler] = None,
				 config_path: str = _CONFIG_PATH):
		self._adapters       : Dict[str, ChannelAdapter] = {}  # id → adapter
		self._message_handler = message_handler
		self._config_path     = config_path

	# ── Adapter Type Registration ─────────────────────────────────

	@classmethod
	def register_type(cls, channel_type: str, adapter_class: Type[ChannelAdapter]):
		"""Register an adapter class for a channel type."""
		cls._adapter_types[channel_type] = adapter_class

	@classmethod
	def get_available_types(cls) -> List[dict]:
		"""List all registered channel adapter types."""
		return [
			{"type": t, "class": c.__name__, "doc": (c.__doc__ or "").strip().split("\n")[0]}
			for t, c in cls._adapter_types.items()
		]

	# ── Lifecycle ─────────────────────────────────────────────────

	async def add(self, config: ChannelConfig) -> ChannelAdapter:
		"""Create and register a channel adapter from config."""
		adapter_cls = self._adapter_types.get(config.channel_type)
		if not adapter_cls:
			raise ValueError(f"Unknown channel type: {config.channel_type}. "
							 f"Available: {list(self._adapter_types.keys())}")

		adapter = adapter_cls(config=config, message_handler=self._message_handler)
		self._adapters[config.id] = adapter
		self._save()
		log_print(f"Channel added: {config.channel_type}/{config.name} ({config.id})")
		return adapter

	async def upsert_config(self, config: ChannelConfig) -> ChannelAdapter:
		"""Create or update a channel configuration while preserving hidden connection settings."""
		adapter = self._adapters.get(config.id)
		if adapter is None:
			return await self.add(config)
		if adapter.type != config.channel_type:
			raise ValueError(
				f"Channel '{config.id}' already exists as type '{adapter.type}' and cannot change to '{config.channel_type}'"
			)
		if not config.token:
			config.token = adapter.config.token
		if not config.webhook_url:
			config.webhook_url = adapter.config.webhook_url
		if not config.api_endpoint:
			config.api_endpoint = adapter.config.api_endpoint
		if not config.extras:
			config.extras = dict(adapter.config.extras or {})
		if not config.created_by:
			config.created_by = adapter.config.created_by
		adapter.config = config
		self._save()
		log_print(f"Channel updated: {config.channel_type}/{config.name} ({config.id})")
		return adapter

	async def remove(self, channel_id: str) -> bool:
		"""Stop and remove a channel adapter."""
		adapter = self._adapters.get(channel_id)
		if not adapter:
			return False

		if adapter.status == ChannelStatus.RUNNING:
			await adapter.stop()

		del self._adapters[channel_id]
		self._save()
		log_print(f"Channel removed: {channel_id}")
		return True

	async def start(self, channel_id: str) -> bool:
		"""Start a specific channel adapter."""
		adapter = self._adapters.get(channel_id)
		if not adapter:
			return False
		if adapter.status in {ChannelStatus.RUNNING, ChannelStatus.STARTING}:
			return True

		try:
			adapter.status = ChannelStatus.STARTING
			await adapter.start()
			adapter.status = ChannelStatus.RUNNING
			log_print(f"Channel started: {adapter.type}/{adapter.config.name}")
			return True
		except Exception as e:
			adapter.status = ChannelStatus.ERROR
			adapter._error = str(e)
			log_print(f"Channel start failed: {adapter.type}/{adapter.config.name} — {e}")
			return False

	async def stop(self, channel_id: str) -> bool:
		"""Stop a specific channel adapter."""
		adapter = self._adapters.get(channel_id)
		if not adapter:
			return False
		if adapter.status in {ChannelStatus.STOPPED, ChannelStatus.STOPPING}:
			return True

		try:
			adapter.status = ChannelStatus.STOPPING
			await adapter.stop()
			adapter.status = ChannelStatus.STOPPED
			log_print(f"Channel stopped: {adapter.type}/{adapter.config.name}")
			return True
		except Exception as e:
			adapter._error = str(e)
			return False

	async def start_all(self):
		"""Start all auto-start channels."""
		for adapter in self._adapters.values():
			if adapter.config.auto_start and adapter.config.enabled:
				await self.start(adapter.config.id)

	async def stop_all(self):
		"""Stop all running channels."""
		for adapter in self._adapters.values():
			if adapter.status == ChannelStatus.RUNNING:
				await self.stop(adapter.config.id)

	# ── Query ─────────────────────────────────────────────────────

	def get(self, channel_id: str) -> Optional[ChannelAdapter]:
		return self._adapters.get(channel_id)

	def list(self) -> List[dict]:
		"""List all channels with status."""
		return [a.get_status() for a in self._adapters.values()]

	# ── Persistence ───────────────────────────────────────────────

	def _save(self):
		"""Save all channel configs to disk."""
		configs = [a.config.model_dump() for a in self._adapters.values()]
		os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
		with open(self._config_path, "w") as f:
			json.dump(configs, f, indent=2)

	def load(self):
		"""Load channel configs from disk and recreate adapters (but don't start them)."""
		if not os.path.exists(self._config_path):
			return

		try:
			import credentials as _creds
			configs = _creds.load_json(self._config_path)
		except Exception as e:
			log_print(f"Failed to load channel configs: {e}")
			return

		for raw in configs:
			config = ChannelConfig(**raw)
			adapter_cls = self._adapter_types.get(config.channel_type)
			if not adapter_cls:
				log_print(f"Skipping unknown channel type: {config.channel_type}")
				continue
			adapter = adapter_cls(config=config, message_handler=self._message_handler)
			self._adapters[config.id] = adapter
			log_print(f"Channel loaded: {config.channel_type}/{config.name} ({config.id})")
