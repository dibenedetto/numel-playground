# channels — Multi-channel messaging adapters
#
# Each adapter bridges an external messaging platform (Telegram, WhatsApp,
# Discord, etc.) to the Numel console agent, allowing users to interact
# with the assistant from any connected channel.

from channels.base    import Attachment, ChannelAdapter, ChannelMessage, ChannelConfig, ChannelStatus
from channels.registry import ChannelRegistry
