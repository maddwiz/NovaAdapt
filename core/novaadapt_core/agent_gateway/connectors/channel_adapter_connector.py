from __future__ import annotations

from collections import deque
from typing import Any, Iterator

from ...channels.base import ChannelAdapter
from .base import InboundMessage


class ChannelAdapterConnector:
    def __init__(
        self,
        adapter: ChannelAdapter,
        *,
        target_metadata_keys: list[str] | None = None,
        fallback_to_sender: bool = True,
    ) -> None:
        self.adapter = adapter
        self.name = str(getattr(adapter, "name", "unknown")).strip().lower() or "unknown"
        self.target_metadata_keys = [str(item).strip() for item in (target_metadata_keys or []) if str(item).strip()]
        self.fallback_to_sender = bool(fallback_to_sender)
        self._inbox: deque[InboundMessage] = deque()

    def push_inbound(self, payload: dict[str, Any], *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        body = payload if isinstance(payload, dict) else {}
        auth = self.adapter.verify_inbound(body, headers=headers if isinstance(headers, dict) else None)
        if not bool(auth.get("ok", False)):
            return {
                "ok": False,
                "channel": self.name,
                "error": str(auth.get("error") or "unauthorized inbound payload"),
                "status_code": int(auth.get("status_code") or 401),
            }
        normalized = self.adapter.normalize_inbound(body)
        metadata = dict(normalized.metadata or {})
        target = ""
        for key in self.target_metadata_keys:
            value = metadata.get(key)
            if value is not None and str(value).strip():
                target = str(value).strip()
                break
        if not target and self.fallback_to_sender:
            target = str(normalized.sender or "").strip()
        self._inbox.append(
            InboundMessage(
                connector=self.name,
                sender=normalized.sender,
                text=normalized.text,
                reply_to={"connector": self.name, "to": target},
                metadata=metadata,
                message_id=normalized.message_id,
            )
        )
        return {
            "ok": True,
            "channel": self.name,
            "message_id": normalized.message_id,
        }

    def listen(self) -> Iterator[InboundMessage]:
        while self._inbox:
            yield self._inbox.popleft()

    def send(self, reply_to: dict[str, Any], content: str, attachments: list[dict[str, Any]] | None = None) -> None:
        _ = attachments
        target = str((reply_to or {}).get("to") or "").strip()
        self.adapter.send_text(
            target,
            str(content or ""),
            metadata={"reply_to": dict(reply_to or {})},
        )

    def health(self) -> dict[str, Any]:
        payload = self.adapter.health()
        out = payload if isinstance(payload, dict) else {}
        result = dict(out)
        result.setdefault("channel", self.name)
        return result
