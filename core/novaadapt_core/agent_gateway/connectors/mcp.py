from __future__ import annotations

from collections import deque
from typing import Any, Callable, Iterator

from .base import InboundMessage


class McpConnector:
    name = "mcp"

    def __init__(
        self,
        *,
        send_fn: Callable[[dict[str, Any], str, list[dict[str, Any]] | None], None] | None = None,
    ) -> None:
        self._send_fn = send_fn
        self._inbox: deque[InboundMessage] = deque()

    def push_inbound(self, payload: dict[str, Any]) -> None:
        row = payload if isinstance(payload, dict) else {}
        self._inbox.append(
            InboundMessage(
                connector=self.name,
                sender=str(row.get("sender", "mcp-client")),
                text=str(row.get("text", "")),
                reply_to=row.get("reply_to") if isinstance(row.get("reply_to"), dict) else {},
                metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
                message_id=str(row.get("message_id", "")),
            )
        )

    def listen(self) -> Iterator[InboundMessage]:
        while self._inbox:
            yield self._inbox.popleft()

    def send(self, reply_to: dict[str, Any], content: str, attachments: list[dict[str, Any]] | None = None) -> None:
        if callable(self._send_fn):
            self._send_fn(reply_to, str(content or ""), attachments)

    def health(self) -> dict[str, Any]:
        return {"ok": True, "channel": self.name, "enabled": True}
