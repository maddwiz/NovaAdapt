from .base import Connector, InboundMessage
from .channel_adapter_connector import ChannelAdapterConnector
from .cli import CliConnector
from .discord import DiscordConnector
from .googlechat import GoogleChatConnector
from .halo import HaloConnector
from .http import HttpConnector
from .imessage import IMessageConnector
from .matrix import MatrixConnector
from .mcp import McpConnector
from .signal import SignalConnector
from .slack import SlackConnector
from .telegram import TelegramConnector
from .teams import TeamsConnector
from .webchat import WebChatConnector
from .whatsapp import WhatsAppConnector
from .xreal import XRealConnector


def build_gateway_connectors() -> dict[str, Connector]:
    rows: list[Connector] = [
        HttpConnector(),
        McpConnector(),
        CliConnector(),
        WebChatConnector(),
        IMessageConnector(),
        WhatsAppConnector(),
        TelegramConnector(),
        DiscordConnector(),
        SlackConnector(),
        SignalConnector(),
        TeamsConnector(),
        GoogleChatConnector(),
        MatrixConnector(),
        XRealConnector(),
        HaloConnector(),
    ]
    out: dict[str, Connector] = {}
    for item in rows:
        out[str(item.name).strip().lower()] = item
    return out

__all__ = [
    "Connector",
    "InboundMessage",
    "ChannelAdapterConnector",
    "build_gateway_connectors",
    "HttpConnector",
    "McpConnector",
    "CliConnector",
    "DiscordConnector",
    "TelegramConnector",
    "SlackConnector",
    "SignalConnector",
    "WhatsAppConnector",
    "IMessageConnector",
    "WebChatConnector",
    "TeamsConnector",
    "GoogleChatConnector",
    "MatrixConnector",
    "XRealConnector",
    "HaloConnector",
]
