from __future__ import annotations

import os
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class WhatsAppChannelAdapter(ChannelAdapter):
    name = "whatsapp"

    def __init__(self) -> None:
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_WHATSAPP_TOKEN", "")).strip()
        self.phone_number_id = str(os.getenv("NOVAADAPT_CHANNEL_WHATSAPP_PHONE_NUMBER_ID", "")).strip()
        self.graph_base_url = str(os.getenv("NOVAADAPT_CHANNEL_WHATSAPP_GRAPH_BASE_URL", "https://graph.facebook.com")).strip(
            "/"
        )
        default_enabled = bool(self.token and self.phone_number_id)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_WHATSAPP_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        configured = bool(self.token and self.phone_number_id)
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and configured),
            "enabled": bool(self.enabled()),
            "configured": configured,
            "phone_number_id_configured": bool(self.phone_number_id),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        sender = "whatsapp-user"
        text = ""
        message_id = ""
        metadata: dict[str, Any] = {}

        entries = payload.get("entry")
        if not isinstance(entries, list):
            entries = []
        message_payload: dict[str, Any] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            for change in list(entry.get("changes") or []):
                if not isinstance(change, dict):
                    continue
                value = change.get("value")
                if not isinstance(value, dict):
                    continue
                metadata_info = value.get("metadata")
                if isinstance(metadata_info, dict):
                    metadata["phone_number_id"] = str(metadata_info.get("phone_number_id") or "").strip()
                messages = value.get("messages")
                if isinstance(messages, list) and messages:
                    maybe = messages[0]
                    if isinstance(maybe, dict):
                        message_payload = maybe
                        break
            if message_payload:
                break

        if message_payload:
            sender = str(message_payload.get("from") or sender).strip() or sender
            message_id = str(message_payload.get("id") or "").strip()
            text_payload = message_payload.get("text")
            if isinstance(text_payload, dict):
                text = str(text_payload.get("body") or "").strip()
            else:
                text = str(message_payload.get("body") or "").strip()
            metadata["type"] = str(message_payload.get("type") or "").strip()
        else:
            sender = str(payload.get("from") or sender).strip() or sender
            text = str(payload.get("text") or payload.get("message") or "").strip()
            message_id = str(payload.get("id") or "").strip()

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
            return {"ok": False, "channel": self.name, "error": "whatsapp channel disabled"}
        if not self.token:
            return {"ok": False, "channel": self.name, "error": "whatsapp token not configured"}
        if not self.phone_number_id:
            return {"ok": False, "channel": self.name, "error": "whatsapp phone number id not configured"}
        recipient = str(to or "").strip()
        body = str(text or "").strip()
        if not recipient:
            raise ValueError("'to' is required (whatsapp phone number)")
        if not body:
            raise ValueError("'text' is required")
        endpoint = f"{self.graph_base_url}/v20.0/{self.phone_number_id}/messages"
        response = http_json_request(
            method="POST",
            url=endpoint,
            headers={"Authorization": f"Bearer {self.token}"},
            payload={
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "text",
                "text": {"body": body},
            },
            timeout_seconds=20.0,
        )
        provider = dict(response.get("response") or {})
        message_id = ""
        messages_payload = provider.get("messages")
        if isinstance(messages_payload, list) and messages_payload:
            first = messages_payload[0]
            if isinstance(first, dict):
                message_id = str(first.get("id") or "").strip()
        ok = bool(response.get("ok", False) and message_id)
        out = {
            "ok": ok,
            "channel": self.name,
            "to": recipient,
            "text": body,
            "message_id": message_id,
            "metadata": dict(metadata or {}),
            "provider_response": provider,
        }
        if not ok:
            out["error"] = str(response.get("error") or provider.get("error", {}).get("message") or "whatsapp send failed")
        return out

