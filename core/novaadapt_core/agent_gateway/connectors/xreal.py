from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Iterator

from .base import InboundMessage


class XRealConnector:
    name = "xreal"

    def __init__(
        self,
        *,
        send_fn: Callable[[dict[str, Any], str, list[dict[str, Any]] | None], None] | None = None,
    ) -> None:
        self._send_fn = send_fn
        self._inbox: deque[InboundMessage] = deque()

    def push_intent(
        self,
        *,
        sender: str,
        transcript: str,
        confidence: float = 0.9,
        source: str = "xreal",
        device_model: str = "xreal-x1",
        display_mode: str = "ar_overlay",
        firmware_version: str = "",
        hand_tracking: bool = False,
    ) -> None:
        metadata = {
            "source": str(source or "xreal"),
            "confidence": max(0.0, min(1.0, float(confidence))),
            "intent_type": "wearable_voice",
            "wearable_family": "xreal",
            "device_model": str(device_model or "xreal-x1"),
            "display_mode": str(display_mode or "ar_overlay"),
            "firmware_version": str(firmware_version or ""),
            "hand_tracking": bool(hand_tracking),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        }
        self._inbox.append(
            InboundMessage(
                connector=self.name,
                sender=str(sender or "xreal-user"),
                text=str(transcript or ""),
                reply_to={"connector": self.name, "to": str(sender or "xreal-user")},
                metadata=metadata,
                message_id="",
            )
        )

    def listen(self) -> Iterator[InboundMessage]:
        while self._inbox:
            yield self._inbox.popleft()

    def send(self, reply_to: dict[str, Any], content: str, attachments: list[dict[str, Any]] | None = None) -> None:
        if callable(self._send_fn):
            self._send_fn(reply_to if isinstance(reply_to, dict) else {}, str(content or ""), attachments)

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "channel": self.name,
            "enabled": True,
            "wearable_family": "xreal",
            "device_model": "xreal-x1",
        }
