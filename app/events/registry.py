# Event Source Registry
#
# Manages event sources with persistence and auto-start/stop based on subscriptions.

import asyncio
import json
import os


from   datetime import datetime
from   pathlib  import Path
from   pydantic import BaseModel
from   typing   import Any, Callable, Dict, List, Optional, Set, Union


from   .sources import (
	EventSource,
	EventSourceConfig,
	EventSourceEvent,
	EventSourceType,
	EventSourceStatus,
	TimerSourceConfig,
	FSWatchSourceConfig,
	WebhookSourceConfig,
	BrowserSourceConfig,
	AnySourceConfig,
	create_event_source,
)


# =============================================================================
# PERSISTENCE MODELS
# =============================================================================

class PersistedSourceConfig(BaseModel):
	"""Wrapper for persisted source configuration"""
	config     : Dict[str, Any]
	created_at : str
	updated_at : str


class RegistryPersistence(BaseModel):
	"""Root persistence model"""
	version : int = 1
	sources : Dict[str, PersistedSourceConfig] = {}


# =============================================================================
# SUBSCRIPTION MANAGEMENT
# =============================================================================

class SourceSubscription:
	"""
	Represents a subscription to an event source.
	Tracks the subscriber and manages auto-start/stop.
	"""

	def __init__(
		self,
		source_id: str,
		subscriber_id: str,
		callback: Callable[[EventSourceEvent], Any]
	):
		self.source_id = source_id
		self.subscriber_id = subscriber_id
		self.callback = callback
		self.created_at = datetime.now().isoformat()


# =============================================================================
# EVENT SOURCE REGISTRY
# =============================================================================

class EventSourceRegistry:
	"""
	Central registry for event sources.

	Features:
	- Manages event source lifecycle
	- Persists configurations to JSON file
	- Auto-starts sources when first subscriber subscribes
	- Auto-stops sources when last subscriber unsubscribes
	- Provides event routing to subscribers
	"""

	def __init__(self, persistence_path: Optional[str] = None):
		self._sources: Dict[str, EventSource] = {}
		self._subscriptions: Dict[str, List[SourceSubscription]] = {}  # source_id -> subscriptions
		self._persistence_path = persistence_path or self._default_persistence_path()
		self._lock = asyncio.Lock()

	def _default_persistence_path(self) -> str:
		"""Get default persistence file path"""
		# Store in app directory
		app_dir = Path(__file__).parent.parent
		return str(app_dir / "event_sources.json")

	# =========================================================================
	# PERSISTENCE
	# =========================================================================

	def _load_persistence(self) -> RegistryPersistence:
		"""Load persisted configurations"""
		if not os.path.exists(self._persistence_path):
			return RegistryPersistence()

		try:
			with open(self._persistence_path, "r") as f:
				data = json.load(f)
				return RegistryPersistence(**data)
		except Exception as e:
			print(f"Error loading event sources persistence: {e}")
			return RegistryPersistence()

	def _save_persistence(self, persistence: RegistryPersistence):
		"""Save configurations to disk"""
		try:
			# Ensure directory exists
			os.makedirs(os.path.dirname(self._persistence_path), exist_ok=True)

			with open(self._persistence_path, "w") as f:
				json.dump(persistence.model_dump(), f, indent=2)
		except Exception as e:
			print(f"Error saving event sources persistence: {e}")

	def _persist_source(self, config: EventSourceConfig):
		"""Persist a source configuration"""
		persistence = self._load_persistence()
		now = datetime.now().isoformat()

		if config.id in persistence.sources:
			persistence.sources[config.id].config = config.model_dump()
			persistence.sources[config.id].updated_at = now
		else:
			persistence.sources[config.id] = PersistedSourceConfig(
				config=config.model_dump(),
				created_at=now,
				updated_at=now,
			)

		self._save_persistence(persistence)

	def _unpersist_source(self, source_id: str):
		"""Remove a source from persistence"""
		persistence = self._load_persistence()
		if source_id in persistence.sources:
			del persistence.sources[source_id]
			self._save_persistence(persistence)

	def _config_from_dict(self, data: Dict[str, Any]) -> AnySourceConfig:
		"""Convert dict to appropriate config type"""
		source_type = data.get("source_type")

		config_map = {
			EventSourceType.TIMER.value: TimerSourceConfig,
			EventSourceType.FSWATCH.value: FSWatchSourceConfig,
			EventSourceType.WEBHOOK.value: WebhookSourceConfig,
			EventSourceType.BROWSER.value: BrowserSourceConfig,
			# Also handle enum directly
			EventSourceType.TIMER: TimerSourceConfig,
			EventSourceType.FSWATCH: FSWatchSourceConfig,
			EventSourceType.WEBHOOK: WebhookSourceConfig,
			EventSourceType.BROWSER: BrowserSourceConfig,
		}

		config_class = config_map.get(source_type)
		if not config_class:
			raise ValueError(f"Unknown source type: {source_type}")

		return config_class(**data)

	# =========================================================================
	# SOURCE MANAGEMENT
	# =========================================================================

	async def register(self, config: AnySourceConfig) -> EventSource:
		"""
		Register a new event source.
		Creates the source but doesn't start it until subscribed.
		"""
		async with self._lock:
			if config.id in self._sources:
				raise ValueError(f"Source already exists: {config.id}")

			# Create source instance
			source = create_event_source(config)
			self._sources[config.id] = source
			self._subscriptions[config.id] = []

			# Persist configuration
			self._persist_source(config)

			return source

	async def unregister(self, source_id: str):
		"""
		Unregister and remove an event source.
		Stops the source if running.
		"""
		async with self._lock:
			source = self._sources.get(source_id)
			if not source:
				raise ValueError(f"Source not found: {source_id}")

			# Stop if running
			if source.is_running:
				await source.stop()

			# Remove subscriptions
			del self._subscriptions[source_id]
			del self._sources[source_id]

			# Remove from persistence
			self._unpersist_source(source_id)

	async def update(self, source_id: str, config: AnySourceConfig) -> EventSource:
		"""
		Update a source's configuration.
		Restarts the source if it was running.
		"""
		async with self._lock:
			old_source = self._sources.get(source_id)
			if not old_source:
				raise ValueError(f"Source not found: {source_id}")

			was_running = old_source.is_running
			subscriptions = self._subscriptions.get(source_id, [])

			# Stop old source
			if was_running:
				await old_source.stop()

			# Create new source with updated config
			config.id = source_id  # Preserve ID
			new_source = create_event_source(config)
			self._sources[source_id] = new_source

			# Re-attach subscriptions
			for sub in subscriptions:
				new_source.subscribe(sub.callback)

			# Restart if was running
			if was_running:
				await new_source.start()

			# Update persistence
			self._persist_source(config)

			return new_source

	def get(self, source_id: str) -> Optional[EventSource]:
		"""Get a source by ID"""
		return self._sources.get(source_id)

	def get_all(self) -> List[EventSource]:
		"""Get all registered sources"""
		return list(self._sources.values())

	def get_by_type(self, source_type: EventSourceType) -> List[EventSource]:
		"""Get all sources of a specific type"""
		return [s for s in self._sources.values() if s.source_type == source_type]

	def get_by_tag(self, tag: str) -> List[EventSource]:
		"""Get all sources with a specific tag"""
		return [s for s in self._sources.values() if tag in s.config.tags]

	# =========================================================================
	# SUBSCRIPTION MANAGEMENT (Auto-start/stop)
	# =========================================================================

	async def subscribe(
		self,
		source_id: str,
		subscriber_id: str,
		callback: Callable[[EventSourceEvent], Any]
	) -> SourceSubscription:
		"""
		Subscribe to a source's events.
		Auto-starts the source if this is the first subscriber.
		"""
		async with self._lock:
			source = self._sources.get(source_id)
			if not source:
				raise ValueError(f"Source not found: {source_id}")

			# Check if already subscribed
			for sub in self._subscriptions[source_id]:
				if sub.subscriber_id == subscriber_id:
					raise ValueError(f"Already subscribed: {subscriber_id}")

			# Create subscription
			subscription = SourceSubscription(source_id, subscriber_id, callback)
			self._subscriptions[source_id].append(subscription)

			# Attach callback to source
			source.subscribe(callback)

			# Auto-start if first subscriber and source is enabled
			if source.subscriber_count == 1 and source.config.enabled:
				await source.start()

			return subscription

	async def unsubscribe(self, source_id: str, subscriber_id: str):
		"""
		Unsubscribe from a source's events.
		Auto-stops the source if this is the last subscriber.
		"""
		async with self._lock:
			source = self._sources.get(source_id)
			if not source:
				return

			# Find and remove subscription
			subscriptions = self._subscriptions.get(source_id, [])
			for sub in subscriptions[:]:
				if sub.subscriber_id == subscriber_id:
					source.unsubscribe(sub.callback)
					subscriptions.remove(sub)
					break

			# Auto-stop if no more subscribers.
			# Browser sources are kept alive between workflow runs so the browser
			# overlay can keep capturing without interruption.
			if source.subscriber_count == 0 and source.is_running:
				if not isinstance(source.config, BrowserSourceConfig):
					await source.stop()

	async def unsubscribe_all(self, subscriber_id: str):
		"""Unsubscribe a subscriber from all sources"""
		for source_id in list(self._subscriptions.keys()):
			await self.unsubscribe(source_id, subscriber_id)

	# =========================================================================
	# LIFECYCLE
	# =========================================================================

	async def load_persisted_sources(self):
		"""Load and register all persisted sources on startup"""
		persistence = self._load_persistence()

		for source_id, persisted in persistence.sources.items():
			try:
				config = self._config_from_dict(persisted.config)
				config.id = source_id  # Ensure ID matches

				source = create_event_source(config)
				self._sources[source_id] = source
				self._subscriptions[source_id] = []

			except Exception as e:
				print(f"Error loading persisted source {source_id}: {e}")

	async def shutdown(self):
		"""Stop all running sources on shutdown"""
		async with self._lock:
			for source in self._sources.values():
				if source.is_running:
					try:
						await source.stop()
					except Exception as e:
						print(f"Error stopping source {source.id}: {e}")

	# =========================================================================
	# STATUS / INFO
	# =========================================================================

	def get_status(self) -> Dict[str, Any]:
		"""Get registry status and all source statuses"""
		return {
			"source_count": len(self._sources),
			"running_count": sum(1 for s in self._sources.values() if s.is_running),
			"sources": {sid: s.get_status() for sid, s in self._sources.items()},
		}

	def list_sources(self) -> List[Dict[str, Any]]:
		"""List all sources with their status"""
		return [s.get_status() for s in self._sources.values()]


# =============================================================================
# GLOBAL REGISTRY INSTANCE
# =============================================================================

_global_registry: Optional[EventSourceRegistry] = None


def get_event_registry() -> EventSourceRegistry:
	"""Get or create global event source registry"""
	global _global_registry
	if _global_registry is None:
		_global_registry = EventSourceRegistry()
	return _global_registry


async def init_event_registry() -> EventSourceRegistry:
	"""Initialize registry and load persisted sources"""
	registry = get_event_registry()
	await registry.load_persisted_sources()
	return registry


async def shutdown_event_registry():
	"""Shutdown registry on application exit"""
	global _global_registry
	if _global_registry:
		await _global_registry.shutdown()
		_global_registry = None
