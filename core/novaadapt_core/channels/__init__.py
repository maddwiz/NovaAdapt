from .base import ChannelAdapter, ChannelMessage
from .discord import DiscordChannelAdapter
from .imessage import IMessageChannelAdapter
from .registry import ChannelRegistry, build_channel_registry
from .signal import SignalChannelAdapter
from .slack import SlackChannelAdapter
from .telegram import TelegramChannelAdapter
from .webchat import WebChatChannelAdapter
from .whatsapp import WhatsAppChannelAdapter

__all__ = [
    "ChannelAdapter",
    "ChannelMessage",
    "ChannelRegistry",
    "DiscordChannelAdapter",
    "IMessageChannelAdapter",
    "SignalChannelAdapter",
    "SlackChannelAdapter",
    "TelegramChannelAdapter",
    "WebChatChannelAdapter",
    "WhatsAppChannelAdapter",
    "build_channel_registry",
]
