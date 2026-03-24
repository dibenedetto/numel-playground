# channels.web_adapter — Web console channel adapter
#
# Treats the browser-based assistant console as a channel, unifying the
# code path with Telegram, Discord, etc.  Unlike external adapters this
# one is "internal": messages arrive via the /console/chat HTTP endpoint,
# not from an external platform, and responses are returned inline.

from   typing   import Optional
from   utils    import log_print

from   channels.base import ChannelAdapter, ChannelConfig, ChannelMessage, ChannelStatus, MessageHandler


class WebChannelAdapter(ChannelAdapter):
    """Web console adapter — receives messages from the browser chat panel.

    This adapter doesn't connect to any external platform.  It exists so
    the web console is treated as just another channel, sharing the same
    command handler, agent pool, and memory-isolation code path.

    start()/stop() are no-ops; send() is unused (responses go inline via HTTP).
    """

    def __init__(self, config: ChannelConfig, message_handler: Optional[MessageHandler] = None):
        super().__init__(config, message_handler)

    @property
    def type(self) -> str:
        return "web"

    async def start(self):
        self.status = ChannelStatus.RUNNING
        log_print(f"Web channel active: {self.config.name} ({self.config.id})")

    async def stop(self):
        self.status = ChannelStatus.STOPPED

    async def send(self, recipient_id: str, text: str, **kwargs) -> bool:
        # Web console responses are returned inline via HTTP — no push needed.
        return True
