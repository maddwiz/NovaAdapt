from __future__ import annotations

from ...channels.instagram import InstagramChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class InstagramConnector(ChannelAdapterConnector):
    def __init__(self, adapter: InstagramChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or InstagramChannelAdapter(),
            target_metadata_keys=[],
            fallback_to_sender=True,
        )
