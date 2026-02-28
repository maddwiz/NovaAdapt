from __future__ import annotations

from ...channels.webchat import WebChatChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class WebChatConnector(ChannelAdapterConnector):
    def __init__(self, adapter: WebChatChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or WebChatChannelAdapter(),
            target_metadata_keys=["room_id", "session_id"],
            fallback_to_sender=True,
        )
