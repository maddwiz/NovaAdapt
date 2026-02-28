from __future__ import annotations

from ...channels.imessage import IMessageChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class IMessageConnector(ChannelAdapterConnector):
    def __init__(self, adapter: IMessageChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or IMessageChannelAdapter(),
            target_metadata_keys=["handle", "chat_id"],
            fallback_to_sender=True,
        )
