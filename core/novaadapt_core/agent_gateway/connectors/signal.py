from __future__ import annotations

from ...channels.signal import SignalChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class SignalConnector(ChannelAdapterConnector):
    def __init__(self, adapter: SignalChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or SignalChannelAdapter(),
            target_metadata_keys=[],
            fallback_to_sender=True,
        )
