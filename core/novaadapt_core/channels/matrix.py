from __future__ import annotations

import os
import uuid
from typing import Any
from urllib.parse import quote

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class MatrixChannelAdapter(ChannelAdapter):
    name = "matrix"

    def __init__(self) -> None:
        self.homeserver = str(os.getenv("NOVAADAPT_CHANNEL_MATRIX_HOMESERVER", "https://matrix.org")).strip().rstrip("/")
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_MATRIX_ACCESS_TOKEN", "")).strip()
        self.default_room_id = str(os.getenv("NOVAADAPT_CHANNEL_MATRIX_DEFAULT_ROOM_ID", "")).strip()
        default_enabled = bool(self.token)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_MATRIX_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        configured = bool(self.homeserver and self.token)
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and configured),
            "enabled": bool(self.enabled()),
            "configured": configured,
            "homeserver": self.homeserver,
            "token_configured": bool(self.token),
            "default_room_configured": bool(self.default_room_id),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        sender = (
            str(payload.get("sender") or "").strip()
            or str(payload.get("from") or "").strip()
            or "matrix-user"
        )
        content = payload.get("content")
        if not isinstance(content, dict):
            content = {}
        text = (
            str(content.get("body") or "").strip()
            or str(payload.get("text") or "").strip()
            or str(payload.get("message") or "").strip()
        )
        message_id = (
            str(payload.get("event_id") or "").strip()
            or str(payload.get("id") or "").strip()
            or str(payload.get("message_id") or "").strip()
        )
        metadata = {
            "room_id": str(payload.get("room_id") or "").strip(),
            "event_type": str(payload.get("type") or "").strip(),
            "msgtype": str(content.get("msgtype") or "").strip(),
        }
        return ChannelMessage(
            channel=self.name,
            sender=sender,
            text=text,
            message_id=message_id,
            received_at_ms=now_unix_ms(),
            metadata=metadata,
        )

    def send_text(self, to: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled():
            return {"ok": False, "channel": self.name, "error": "matrix channel disabled"}
        if not self.token:
            return {"ok": False, "channel": self.name, "error": "matrix access token not configured"}
        room_id = str(to or "").strip() or self.default_room_id
        body = str(text or "").strip()
        if not room_id:
            raise ValueError("'to' is required (matrix room id)")
        if not body:
            raise ValueError("'text' is required")

        txn_id = uuid.uuid4().hex
        endpoint = (
            f"{self.homeserver}/_matrix/client/v3/rooms/"
            f"{quote(room_id, safe='')}/send/m.room.message/{quote(txn_id, safe='')}"
        )
        response = http_json_request(
            method="PUT",
            url=endpoint,
            headers={"Authorization": f"Bearer {self.token}"},
            payload={"msgtype": "m.text", "body": body},
            timeout_seconds=20.0,
        )
        provider = dict(response.get("response") or {})
        event_id = str(provider.get("event_id") or "").strip()
        ok = bool(response.get("ok", False) and event_id)
        out = {
            "ok": ok,
            "channel": self.name,
            "to": room_id,
            "text": body,
            "message_id": event_id or f"matrix-{now_unix_ms()}",
            "metadata": dict(metadata or {}),
            "provider_response": provider,
        }
        if not ok:
            out["error"] = str(response.get("error") or provider.get("error") or "matrix send failed")
        return out
