from __future__ import annotations

from ...channels.slack import SlackChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class SlackConnector(ChannelAdapterConnector):
    def __init__(self, adapter: SlackChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or SlackChannelAdapter(),
            target_metadata_keys=["channel_id"],
            fallback_to_sender=False,
        )
