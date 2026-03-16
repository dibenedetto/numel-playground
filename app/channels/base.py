# channels.base — Base channel adapter interface
#
# All channel adapters implement this interface.
# The adapter translates platform-specific messages to/from the console agent.

import asyncio
import uuid

from   abc      import ABC, abstractmethod
from   datetime import datetime
from   enum     import Enum
from   pydantic import BaseModel, Field
from   typing   import Any, Callable, Coroutine, Dict, List, Optional


# =============================================================================
# DATA MODELS
# =============================================================================

class ChannelStatus(str, Enum):
	STOPPED      = "stopped"
	STARTING     = "starting"
	RUNNING      = "running"
	STOPPING     = "stopping"
	ERROR        = "error"
	DISCONNECTED = "disconnected"


class ChannelMessage(BaseModel):
	"""Normalized message that flows between channels and the agent."""
	id           : str            = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
	channel_type : str            = ""           # "telegram", "whatsapp", "discord", "webhook"
	channel_id   : str            = ""           # Instance ID of the channel adapter
	sender_id    : str            = ""           # Platform-specific user ID
	sender_name  : str            = ""           # Display name
	content      : str            = ""           # Text content
	media_url    : Optional[str]  = None         # Attached media URL
	media_type   : Optional[str]  = None         # MIME type of media
	reply_to     : Optional[str]  = None         # Message ID being replied to
	metadata     : Dict[str, Any] = Field(default_factory=dict)
	timestamp    : str            = Field(default_factory=lambda: datetime.now().isoformat())


class ChannelConfig(BaseModel):
	"""Base configuration for a channel adapter."""
	id           : str            = Field(default_factory=lambda: f"ch_{uuid.uuid4().hex[:8]}")
	name         : str            = ""
	channel_type : str            = ""           # "telegram", "whatsapp", "discord", "webhook"
	enabled      : bool           = True
	auto_start   : bool           = False        # Start on server boot

	# Auth/connection
	token        : Optional[str]  = None         # Bot token / API key
	webhook_url  : Optional[str]  = None         # Incoming webhook URL
	api_endpoint : Optional[str]  = None         # Custom API endpoint

	# Behavior
	allowed_users: List[str]      = Field(default_factory=list)    # Empty = allow all
	session_id   : Optional[str]  = None         # Fixed session ID (shared memory)

	# Platform-specific extras
	extras       : Dict[str, Any] = Field(default_factory=dict)

	class Config:
		extra = "allow"


# =============================================================================
# ABSTRACT ADAPTER
# =============================================================================

# Callback signature: async def handler(msg: ChannelMessage) -> str
MessageHandler = Callable[[ChannelMessage], Coroutine[Any, Any, str]]


class ChannelAdapter(ABC):
	"""Base class for all channel adapters.

	Subclasses must implement:
	  - start()  — connect to the platform and begin listening
	  - stop()   — disconnect and clean up
	  - send()   — send a message back to a specific user/chat
	  - type property — return the channel type string
	"""

	def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
		self.config          = config
		self.status          = ChannelStatus.STOPPED
		self.message_handler = message_handler
		self._error          = None
		self._task           = None   # Background asyncio task

	@property
	@abstractmethod
	def type(self) -> str:
		"""Channel type identifier (e.g. 'telegram', 'discord')."""
		...

	@abstractmethod
	async def start(self):
		"""Connect to the platform and start listening for messages."""
		...

	@abstractmethod
	async def stop(self):
		"""Disconnect and clean up resources."""
		...

	@abstractmethod
	async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
		"""Send a message to a recipient. Returns True on success."""
		...

	async def on_message(self, msg: ChannelMessage) -> Optional[str]:
		"""Called when a message is received from the platform.
		Routes to the registered handler and returns the response."""
		if not self.message_handler:
			return None

		# Check allowed users
		if self.config.allowed_users and msg.sender_id not in self.config.allowed_users:
			return None

		try:
			return await self.message_handler(msg)
		except Exception as e:
			self._error = str(e)
			return f"Error processing message: {e}"

	def get_status(self) -> dict:
		"""Return current adapter status."""
		return {
			"id":           self.config.id,
			"name":         self.config.name,
			"channel_type": self.type,
			"status":       self.status.value,
			"error":        self._error,
			"enabled":      self.config.enabled,
		}
