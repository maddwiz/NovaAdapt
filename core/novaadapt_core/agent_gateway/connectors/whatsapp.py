from __future__ import annotations

from ...channels.whatsapp import WhatsAppChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class WhatsAppConnector(ChannelAdapterConnector):
    def __init__(self, adapter: WhatsAppChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or WhatsAppChannelAdapter(),
            target_metadata_keys=[],
            fallback_to_sender=True,
        )
