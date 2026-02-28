from .base import ChannelAdapter, ChannelMessage
from .discord import DiscordChannelAdapter
from .googlechat import GoogleChatChannelAdapter
from .imessage import IMessageChannelAdapter
from .matrix import MatrixChannelAdapter
from .registry import ChannelRegistry, build_channel_registry
from .signal import SignalChannelAdapter
from .slack import SlackChannelAdapter
from .telegram import TelegramChannelAdapter
from .teams import TeamsChannelAdapter
from .webchat import WebChatChannelAdapter
from .whatsapp import WhatsAppChannelAdapter

__all__ = [
    "ChannelAdapter",
    "ChannelMessage",
    "ChannelRegistry",
    "DiscordChannelAdapter",
    "GoogleChatChannelAdapter",
    "IMessageChannelAdapter",
    "MatrixChannelAdapter",
    "SignalChannelAdapter",
    "SlackChannelAdapter",
    "TelegramChannelAdapter",
    "TeamsChannelAdapter",
    "WebChatChannelAdapter",
    "WhatsAppChannelAdapter",
    "build_channel_registry",
]
