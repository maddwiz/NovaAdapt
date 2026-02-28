from __future__ import annotations

from ...channels.matrix import MatrixChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class MatrixConnector(ChannelAdapterConnector):
    def __init__(self, adapter: MatrixChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or MatrixChannelAdapter(),
            target_metadata_keys=["room_id"],
            fallback_to_sender=False,
        )
