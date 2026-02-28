from __future__ import annotations

from ...channels.googlechat import GoogleChatChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class GoogleChatConnector(ChannelAdapterConnector):
    def __init__(self, adapter: GoogleChatChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or GoogleChatChannelAdapter(),
            target_metadata_keys=["space_name", "thread_name"],
            fallback_to_sender=False,
        )
