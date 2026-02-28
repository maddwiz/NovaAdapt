from __future__ import annotations

from collections import deque
from typing import Any, Callable, Iterator

from .base import InboundMessage


class CliConnector:
    name = "cli"

    def __init__(
        self,
        *,
        send_fn: Callable[[dict[str, Any], str, list[dict[str, Any]] | None], None] | None = None,
    ) -> None:
        self._send_fn = send_fn
        self._inbox: deque[InboundMessage] = deque()

    def push_inbound(self, sender: str, text: str, *, reply_to: dict[str, Any] | None = None) -> None:
        self._inbox.append(
            InboundMessage(
                connector=self.name,
                sender=str(sender or "cli-user"),
                text=str(text or ""),
                reply_to=reply_to if isinstance(reply_to, dict) else {},
                metadata={},
                message_id="",
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
