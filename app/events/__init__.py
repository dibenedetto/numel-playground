# Event Trigger System
#
# External event sources that can trigger workflow execution or inject data into running workflows.

from .sources import (
	EventSource,
	EventSourceConfig,
	EventSourceEvent,
	TimerSource,
	TimerSourceConfig,
	FSWatchSource,
	FSWatchSourceConfig,
	WebhookSource,
	WebhookSourceConfig,
	BrowserSource,
	BrowserSourceConfig,
)

from .registry import (
	EventSourceRegistry,
	init_event_registry,
	get_event_registry,
	shutdown_event_registry,
)

__all__ = [
	# Base classes
	"EventSource",
	"EventSourceConfig",
	"EventSourceEvent",
	# Concrete sources
	"TimerSource",
	"TimerSourceConfig",
	"FSWatchSource",
	"FSWatchSourceConfig",
	"WebhookSource",
	"WebhookSourceConfig",
	"BrowserSource",
	"BrowserSourceConfig",
	# Registry
	"EventSourceRegistry",
	"init_event_registry",
	"get_event_registry",
	"shutdown_event_registry",
]
