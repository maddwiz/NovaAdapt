from __future__ import annotations

from collections import deque
from typing import Any, Iterator

from ...channels.telegram import TelegramChannelAdapter
from .base import InboundMessage


class TelegramConnector:
    name = "telegram"

    def __init__(self, adapter: TelegramChannelAdapter | None = None) -> None:
        self.adapter = adapter or TelegramChannelAdapter()
        self._inbox: deque[InboundMessage] = deque()

    def push_inbound(self, payload: dict[str, Any]) -> None:
        normalized = self.adapter.normalize_inbound(payload if isinstance(payload, dict) else {})
        self._inbox.append(
            InboundMessage(
                connector=self.name,
                sender=normalized.sender,
                text=normalized.text,
                reply_to={
                    "connector": self.name,
                    "to": str(normalized.metadata.get("chat_id") or ""),
                },
                metadata=normalized.metadata,
                message_id=normalized.message_id,
            )
        )

    def listen(self) -> Iterator[InboundMessage]:
        while self._inbox:
            yield self._inbox.popleft()

    def send(self, reply_to: dict[str, Any], content: str, attachments: list[dict[str, Any]] | None = None) -> None:
        _ = attachments
        target = str((reply_to or {}).get("to") or "").strip()
        self.adapter.send_text(target, str(content or ""), metadata={"reply_to": dict(reply_to or {})})

    def health(self) -> dict[str, Any]:
        return self.adapter.health()
