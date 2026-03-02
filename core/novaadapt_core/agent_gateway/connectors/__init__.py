from .base import Connector, InboundMessage
from .channel_adapter_connector import ChannelAdapterConnector
from .cli import CliConnector
from .discord import DiscordConnector
from .googlechat import GoogleChatConnector
from .halo import HaloConnector
from .http import HttpConnector
from .imessage import IMessageConnector
from .instagram import InstagramConnector
from .matrix import MatrixConnector
from .messenger import MessengerConnector
from .mcp import McpConnector
from .signal import SignalConnector
from .slack import SlackConnector
from .sms import SmsConnector
from .telegram import TelegramConnector
from .teams import TeamsConnector
from .webchat import WebChatConnector
from .whatsapp import WhatsAppConnector
from .xreal import XRealConnector

CONNECTOR_ALIASES: dict[str, str] = {
    "web_chat": "webchat",
    "i-message": "imessage",
    "i_message": "imessage",
    "apple_messages": "imessage",
    "whats_app": "whatsapp",
    "google_chat": "googlechat",
    "google-chat": "googlechat",
    "gchat": "googlechat",
    "ms_teams": "teams",
    "msteams": "teams",
    "microsoft_teams": "teams",
    "microsoft-teams": "teams",
    "facebook_messenger": "messenger",
    "facebook-messenger": "messenger",
    "fb_messenger": "messenger",
    "fb-messenger": "messenger",
    "meta_messenger": "messenger",
    "ig": "instagram",
    "insta": "instagram",
    "instagram_dm": "instagram",
    "instagram-dm": "instagram",
    "text": "sms",
    "text_message": "sms",
    "twilio": "sms",
    "twilio_sms": "sms",
    "twilio-sms": "sms",
    "xreal_x1": "xreal",
    "xreal-x1": "xreal",
    "x1": "xreal",
    "xreal_glasses": "xreal",
    "xreal-glasses": "xreal",
    "omi": "halo",
}


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
        MessengerConnector(),
        InstagramConnector(),
        SmsConnector(),
        TeamsConnector(),
        GoogleChatConnector(),
        MatrixConnector(),
        XRealConnector(),
        HaloConnector(),
    ]
    out: dict[str, Connector] = {}
    for item in rows:
        out[str(item.name).strip().lower()] = item
    for alias, canonical in CONNECTOR_ALIASES.items():
        alias_name = str(alias or "").strip().lower().replace(" ", "_")
        canonical_name = str(canonical or "").strip().lower().replace(" ", "_")
        target = out.get(canonical_name)
        if target is None or not alias_name or alias_name in out:
            continue
        out[alias_name] = target
    return out

__all__ = [
    "Connector",
    "InboundMessage",
    "ChannelAdapterConnector",
    "CONNECTOR_ALIASES",
    "build_gateway_connectors",
    "HttpConnector",
    "McpConnector",
    "CliConnector",
    "DiscordConnector",
    "TelegramConnector",
    "SlackConnector",
    "SignalConnector",
    "MessengerConnector",
    "InstagramConnector",
    "SmsConnector",
    "WhatsAppConnector",
    "IMessageConnector",
    "WebChatConnector",
    "TeamsConnector",
    "GoogleChatConnector",
    "MatrixConnector",
    "XRealConnector",
    "HaloConnector",
]
