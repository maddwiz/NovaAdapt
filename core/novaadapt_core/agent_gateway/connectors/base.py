from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol


@dataclass
class InboundMessage:
    connector: str
    sender: str
    text: str
    reply_to: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    message_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "connector": self.connector,
            "sender": self.sender,
            "text": self.text,
            "reply_to": dict(self.reply_to),
            "metadata": dict(self.metadata),
            "message_id": self.message_id,
        }


class Connector(Protocol):
    name: str

    def listen(self) -> Iterator[InboundMessage]:
        ...

    def send(self, reply_to: dict[str, Any], content: str, attachments: list[dict[str, Any]] | None = None) -> None:
        ...

    def health(self) -> dict[str, Any]:
        ...
