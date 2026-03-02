from .base import ChannelAdapter, ChannelMessage
from .discord import DiscordChannelAdapter
from .googlechat import GoogleChatChannelAdapter
from .imessage import IMessageChannelAdapter
from .instagram import InstagramChannelAdapter
from .matrix import MatrixChannelAdapter
from .messenger import MessengerChannelAdapter
from .registry import ChannelRegistry, build_channel_registry
from .signal import SignalChannelAdapter
from .slack import SlackChannelAdapter
from .sms import SmsChannelAdapter
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
    "InstagramChannelAdapter",
    "MatrixChannelAdapter",
    "MessengerChannelAdapter",
    "SignalChannelAdapter",
    "SlackChannelAdapter",
    "SmsChannelAdapter",
    "TelegramChannelAdapter",
    "TeamsChannelAdapter",
    "WebChatChannelAdapter",
    "WhatsAppChannelAdapter",
    "build_channel_registry",
]
