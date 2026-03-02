from __future__ import annotations

from ...channels.messenger import MessengerChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class MessengerConnector(ChannelAdapterConnector):
    def __init__(self, adapter: MessengerChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or MessengerChannelAdapter(),
            target_metadata_keys=[],
            fallback_to_sender=True,
        )
