from __future__ import annotations

from ...channels.teams import TeamsChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class TeamsConnector(ChannelAdapterConnector):
    def __init__(self, adapter: TeamsChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or TeamsChannelAdapter(),
            target_metadata_keys=["conversation_id"],
            fallback_to_sender=False,
        )
