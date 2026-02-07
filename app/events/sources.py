# Event Sources
#
# Base classes and implementations for external event sources that can trigger workflows.

import asyncio
import os
import time
import uuid


from   abc                import ABC, abstractmethod
from   datetime           import datetime
from   enum               import Enum
from   pathlib            import Path
from   pydantic           import BaseModel, Field
from   typing             import Any, Callable, Dict, List, Literal, Optional, Set, Union
from   watchdog.observers import Observer
from   watchdog.events    import FileSystemEventHandler, FileSystemEvent


# =============================================================================
# EVENT SOURCE TYPES
# =============================================================================

class EventSourceType(str, Enum):
	TIMER    = "timer"
	FSWATCH  = "fswatch"
	WEBHOOK  = "webhook"
	BROWSER  = "browser"  # Webcam, microphone, etc.


class EventSourceStatus(str, Enum):
	STOPPED  = "stopped"
	STARTING = "starting"
	RUNNING  = "running"
	STOPPING = "stopping"
	ERROR    = "error"


# =============================================================================
# EVENT DATA MODELS
# =============================================================================

class EventSourceEvent(BaseModel):
	"""Event emitted by an event source"""
	event_id   : str                    = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
	source_id  : str                    # ID of the source that emitted this event
	source_type: EventSourceType        # Type of the source
	timestamp  : str                    = Field(default_factory=lambda: datetime.now().isoformat())
	data       : Dict[str, Any]         = Field(default_factory=dict)


class EventSourceConfig(BaseModel):
	"""Base configuration for event sources"""
	id          : str                   = Field(default_factory=lambda: f"src_{uuid.uuid4().hex[:8]}")
	name        : Optional[str]         = None
	source_type : EventSourceType
	enabled     : bool                  = True

	# Filtering/routing
	tags        : List[str]             = Field(default_factory=list)

	class Config:
		extra = "allow"  # Allow subclass-specific fields


class TimerSourceConfig(EventSourceConfig):
	"""Configuration for timer event source"""
	source_type : Literal[EventSourceType.TIMER] = EventSourceType.TIMER
	interval_ms : int                   = 1000
	max_triggers: int                   = -1     # -1 = infinite
	immediate   : bool                  = False  # Trigger immediately on start


class FSWatchSourceConfig(EventSourceConfig):
	"""Configuration for filesystem watcher event source"""
	source_type : Literal[EventSourceType.FSWATCH] = EventSourceType.FSWATCH
	path        : str                   # Path to watch
	recursive   : bool                  = True
	patterns    : List[str]             = Field(default_factory=lambda: ["*"])  # Glob patterns
	events      : List[str]             = Field(default_factory=lambda: ["created", "modified", "deleted", "moved"])
	debounce_ms : int                   = 100    # Debounce rapid events


class WebhookSourceConfig(EventSourceConfig):
	"""Configuration for webhook event source"""
	source_type : Literal[EventSourceType.WEBHOOK] = EventSourceType.WEBHOOK
	endpoint    : str                   # URL path (e.g., "/hook/my-webhook")
	methods     : List[str]             = Field(default_factory=lambda: ["POST"])
	secret      : Optional[str]         = None   # Optional secret for validation


class BrowserSourceConfig(EventSourceConfig):
	"""Configuration for browser-based event source (webcam, microphone)"""
	source_type  : Literal[EventSourceType.BROWSER] = EventSourceType.BROWSER
	device_type  : Literal["webcam", "microphone", "screen"] = "webcam"
	mode         : Literal["stream", "event"] = "event"  # stream=raw data, event=processed events
	interval_ms  : int                  = 1000   # Capture interval for stream mode
	# Device-specific options
	resolution   : Optional[str]        = None   # e.g., "640x480"
	audio_format : Optional[str]        = None   # e.g., "wav", "webm"


# Union type for all configs
AnySourceConfig = Union[TimerSourceConfig, FSWatchSourceConfig, WebhookSourceConfig, BrowserSourceConfig]


# =============================================================================
# BASE EVENT SOURCE CLASS
# =============================================================================

class EventSource(ABC):
	"""
	Abstract base class for event sources.

	Event sources run independently and emit events that can trigger workflows
	or inject data into running workflows.
	"""

	def __init__(self, config: EventSourceConfig):
		self.config = config
		self.status = EventSourceStatus.STOPPED
		self._subscribers: List[Callable[[EventSourceEvent], Any]] = []
		self._task: Optional[asyncio.Task] = None
		self._stop_event = asyncio.Event()
		self._error: Optional[str] = None
		self._stats = {
			"events_emitted": 0,
			"last_event_time": None,
			"started_at": None,
			"stopped_at": None,
		}

	@property
	def id(self) -> str:
		return self.config.id

	@property
	def source_type(self) -> EventSourceType:
		return self.config.source_type

	@property
	def is_running(self) -> bool:
		return self.status == EventSourceStatus.RUNNING

	def subscribe(self, callback: Callable[[EventSourceEvent], Any]):
		"""Subscribe to events from this source"""
		if callback not in self._subscribers:
			self._subscribers.append(callback)

	def unsubscribe(self, callback: Callable[[EventSourceEvent], Any]):
		"""Unsubscribe from events"""
		if callback in self._subscribers:
			self._subscribers.remove(callback)

	@property
	def subscriber_count(self) -> int:
		return len(self._subscribers)

	async def _emit(self, data: Dict[str, Any]):
		"""Emit an event to all subscribers"""
		event = EventSourceEvent(
			source_id=self.id,
			source_type=self.source_type,
			data=data
		)

		self._stats["events_emitted"] += 1
		self._stats["last_event_time"] = event.timestamp

		for callback in self._subscribers:
			try:
				result = callback(event)
				if asyncio.iscoroutine(result):
					await result
			except Exception as e:
				print(f"Error in event subscriber for {self.id}: {e}")

	async def start(self):
		"""Start the event source"""
		if self.status == EventSourceStatus.RUNNING:
			return

		self.status = EventSourceStatus.STARTING
		self._stop_event.clear()
		self._error = None

		try:
			await self._start_impl()
			self.status = EventSourceStatus.RUNNING
			self._stats["started_at"] = datetime.now().isoformat()
			self._task = asyncio.create_task(self._run_loop())
		except Exception as e:
			self.status = EventSourceStatus.ERROR
			self._error = str(e)
			raise

	async def stop(self):
		"""Stop the event source"""
		if self.status == EventSourceStatus.STOPPED:
			return

		self.status = EventSourceStatus.STOPPING
		self._stop_event.set()

		if self._task:
			self._task.cancel()
			try:
				await self._task
			except asyncio.CancelledError:
				pass
			self._task = None

		await self._stop_impl()
		self.status = EventSourceStatus.STOPPED
		self._stats["stopped_at"] = datetime.now().isoformat()

	def get_status(self) -> Dict[str, Any]:
		"""Get current status and stats"""
		return {
			"id": self.id,
			"source_type": self.source_type.value,
			"status": self.status.value,
			"error": self._error,
			"subscriber_count": self.subscriber_count,
			"config": self.config.model_dump(),
			"stats": self._stats.copy(),
		}

	@abstractmethod
	async def _start_impl(self):
		"""Implementation-specific start logic"""
		pass

	@abstractmethod
	async def _stop_impl(self):
		"""Implementation-specific stop logic"""
		pass

	@abstractmethod
	async def _run_loop(self):
		"""Main event loop for the source"""
		pass


# =============================================================================
# TIMER SOURCE
# =============================================================================

class TimerSource(EventSource):
	"""
	Timer event source - emits events at regular intervals.
	"""

	def __init__(self, config: TimerSourceConfig):
		super().__init__(config)
		self._count = 0
		self._elapsed_ms = 0

	@property
	def timer_config(self) -> TimerSourceConfig:
		return self.config  # type: ignore

	async def _start_impl(self):
		self._count = 0
		self._elapsed_ms = 0

	async def _stop_impl(self):
		pass

	async def _run_loop(self):
		config = self.timer_config

		# Immediate trigger if configured
		if config.immediate:
			await self._emit({
				"count": self._count,
				"elapsed_ms": self._elapsed_ms,
			})
			self._count += 1

		while not self._stop_event.is_set():
			try:
				# Wait for interval
				await asyncio.wait_for(
					self._stop_event.wait(),
					timeout=config.interval_ms / 1000.0
				)
				# If we get here, stop was requested
				break
			except asyncio.TimeoutError:
				# Timeout = interval elapsed, emit event
				self._elapsed_ms += config.interval_ms

				await self._emit({
					"count": self._count,
					"elapsed_ms": self._elapsed_ms,
				})

				self._count += 1

				# Check max triggers
				if config.max_triggers > 0 and self._count >= config.max_triggers:
					break


# =============================================================================
# FILESYSTEM WATCHER SOURCE
# =============================================================================

class FSWatchSource(EventSource):
	"""
	Filesystem watcher event source - emits events on file changes.
	"""

	def __init__(self, config: FSWatchSourceConfig):
		super().__init__(config)
		self._observer: Optional[Observer] = None
		self._event_queue: asyncio.Queue = asyncio.Queue()
		self._last_events: Dict[str, float] = {}  # For debouncing

	@property
	def fswatch_config(self) -> FSWatchSourceConfig:
		return self.config  # type: ignore

	async def _start_impl(self):
		config = self.fswatch_config

		# Validate path exists
		path = Path(config.path)
		if not path.exists():
			raise ValueError(f"Watch path does not exist: {config.path}")

		# Create observer with handler
		self._observer = Observer()
		handler = _FSEventHandler(self._event_queue, config)

		self._observer.schedule(
			handler,
			str(path),
			recursive=config.recursive
		)
		self._observer.start()

	async def _stop_impl(self):
		if self._observer:
			self._observer.stop()
			self._observer.join(timeout=5.0)
			self._observer = None

	async def _run_loop(self):
		config = self.fswatch_config
		debounce_sec = config.debounce_ms / 1000.0

		while not self._stop_event.is_set():
			try:
				# Get event from queue with timeout
				event_data = await asyncio.wait_for(
					self._event_queue.get(),
					timeout=0.5
				)

				# Debounce: skip if same path was processed recently
				event_key = f"{event_data['event_type']}:{event_data['path']}"
				now = time.time()

				if event_key in self._last_events:
					if now - self._last_events[event_key] < debounce_sec:
						continue

				self._last_events[event_key] = now

				# Emit the event
				await self._emit(event_data)

			except asyncio.TimeoutError:
				continue
			except asyncio.CancelledError:
				break


class _FSEventHandler(FileSystemEventHandler):
	"""Internal handler for watchdog events"""

	def __init__(self, queue: asyncio.Queue, config: FSWatchSourceConfig):
		super().__init__()
		self._queue = queue
		self._config = config
		self._loop: Optional[asyncio.AbstractEventLoop] = None

	def _should_handle(self, event: FileSystemEvent) -> bool:
		"""Check if event matches our filters"""
		# Check event type
		event_type = event.event_type  # created, modified, deleted, moved
		if event_type not in self._config.events:
			return False

		# Check patterns (simple glob matching)
		if self._config.patterns and self._config.patterns != ["*"]:
			filename = os.path.basename(event.src_path)
			matched = False
			for pattern in self._config.patterns:
				if pattern == "*":
					matched = True
					break
				# Simple wildcard matching
				if pattern.startswith("*."):
					ext = pattern[1:]  # e.g., ".txt"
					if filename.endswith(ext):
						matched = True
						break
				elif pattern == filename:
					matched = True
					break
			if not matched:
				return False

		return True

	def _queue_event(self, event: FileSystemEvent):
		"""Queue event for async processing"""
		if not self._should_handle(event):
			return

		event_data = {
			"event_type": event.event_type,
			"path": event.src_path,
			"is_directory": event.is_directory,
		}

		if hasattr(event, 'dest_path'):
			event_data["dest_path"] = event.dest_path

		# Get or create event loop
		try:
			if self._loop is None or self._loop.is_closed():
				self._loop = asyncio.get_event_loop()
			self._loop.call_soon_threadsafe(self._queue.put_nowait, event_data)
		except RuntimeError:
			pass  # No event loop, skip

	def on_created(self, event):
		self._queue_event(event)

	def on_modified(self, event):
		self._queue_event(event)

	def on_deleted(self, event):
		self._queue_event(event)

	def on_moved(self, event):
		self._queue_event(event)


# =============================================================================
# WEBHOOK SOURCE
# =============================================================================

class WebhookSource(EventSource):
	"""
	Webhook event source - receives events via HTTP.

	Note: The actual HTTP endpoint is managed by the API layer.
	This source just manages the subscription and event routing.
	"""

	def __init__(self, config: WebhookSourceConfig):
		super().__init__(config)
		self._pending_events: asyncio.Queue = asyncio.Queue()

	@property
	def webhook_config(self) -> WebhookSourceConfig:
		return self.config  # type: ignore

	async def _start_impl(self):
		pass  # Endpoint registration handled by API layer

	async def _stop_impl(self):
		pass

	async def _run_loop(self):
		"""Process incoming webhook events"""
		while not self._stop_event.is_set():
			try:
				event_data = await asyncio.wait_for(
					self._pending_events.get(),
					timeout=0.5
				)
				await self._emit(event_data)
			except asyncio.TimeoutError:
				continue
			except asyncio.CancelledError:
				break

	async def receive_webhook(self, data: Dict[str, Any], headers: Dict[str, str] = None):
		"""Called by API layer when webhook is received"""
		if not self.is_running:
			return

		event_data = {
			"payload": data,
			"headers": headers or {},
			"received_at": datetime.now().isoformat(),
		}

		await self._pending_events.put(event_data)


# =============================================================================
# BROWSER SOURCE
# =============================================================================

class BrowserSource(EventSource):
	"""
	Browser-based event source - receives events from frontend (webcam, microphone, etc.)

	The frontend captures media and sends frames/events via WebSocket.
	This source manages the subscription and event routing.
	"""

	def __init__(self, config: BrowserSourceConfig):
		super().__init__(config)
		self._pending_events: asyncio.Queue = asyncio.Queue()
		self._connected_clients: Set[str] = set()

	@property
	def browser_config(self) -> BrowserSourceConfig:
		return self.config  # type: ignore

	async def _start_impl(self):
		pass  # WebSocket handling managed by API layer

	async def _stop_impl(self):
		self._connected_clients.clear()

	async def _run_loop(self):
		"""Process incoming browser events"""
		while not self._stop_event.is_set():
			try:
				event_data = await asyncio.wait_for(
					self._pending_events.get(),
					timeout=0.5
				)
				await self._emit(event_data)
			except asyncio.TimeoutError:
				continue
			except asyncio.CancelledError:
				break

	def add_client(self, client_id: str):
		"""Track connected browser client"""
		self._connected_clients.add(client_id)

	def remove_client(self, client_id: str):
		"""Remove browser client"""
		self._connected_clients.discard(client_id)

	@property
	def client_count(self) -> int:
		return len(self._connected_clients)

	async def receive_event(self, data: Dict[str, Any], client_id: str = None):
		"""Called when browser sends an event"""
		if not self.is_running:
			return

		event_data = {
			"device_type": self.browser_config.device_type,
			"mode": self.browser_config.mode,
			"client_id": client_id,
			"received_at": datetime.now().isoformat(),
			**data
		}

		await self._pending_events.put(event_data)


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_event_source(config: AnySourceConfig) -> EventSource:
	"""Factory function to create event source from config"""
	source_map = {
		EventSourceType.TIMER: TimerSource,
		EventSourceType.FSWATCH: FSWatchSource,
		EventSourceType.WEBHOOK: WebhookSource,
		EventSourceType.BROWSER: BrowserSource,
	}

	source_class = source_map.get(config.source_type)
	if not source_class:
		raise ValueError(f"Unknown source type: {config.source_type}")

	return source_class(config)
