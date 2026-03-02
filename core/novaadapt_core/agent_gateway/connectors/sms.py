from __future__ import annotations

from ...channels.sms import SmsChannelAdapter
from .channel_adapter_connector import ChannelAdapterConnector


class SmsConnector(ChannelAdapterConnector):
    def __init__(self, adapter: SmsChannelAdapter | None = None) -> None:
        super().__init__(
            adapter or SmsChannelAdapter(),
            target_metadata_keys=[],
            fallback_to_sender=True,
        )
