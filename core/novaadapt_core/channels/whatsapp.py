from __future__ import annotations

import hashlib
import hmac
import json
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
        self.app_secret = str(os.getenv("NOVAADAPT_CHANNEL_WHATSAPP_APP_SECRET", "")).strip()
        self.require_signature = env_bool("NOVAADAPT_CHANNEL_WHATSAPP_REQUIRE_SIGNATURE", False)
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
            "inbound_token_configured": bool(self._inbound_token()),
            "app_secret_configured": bool(self.app_secret),
            "require_signature": bool(self.require_signature),
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

    def _normalized_headers(self, headers: dict[str, str] | None) -> dict[str, str]:
        out: dict[str, str] = {}
        if not isinstance(headers, dict):
            return out
        for key, value in headers.items():
            name = str(key or "").strip().lower()
            if not name:
                continue
            out[name] = str(value or "").strip()
        return out

    def _signature_message_body(self, payload: dict[str, Any], raw_body: str | None) -> str:
        raw = str(raw_body or "")
        if raw:
            return raw
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    def verify_inbound(
        self,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
        raw_body: str | None = None,
    ) -> dict[str, Any]:
        token_auth = super().verify_inbound(payload, headers=headers)
        if not bool(token_auth.get("ok", False)):
            return token_auth

        if self.require_signature and not self.app_secret:
            return {
                "ok": False,
                "status_code": 500,
                "error": "WhatsApp signature required but NOVAADAPT_CHANNEL_WHATSAPP_APP_SECRET is not configured",
            }
        if not self.app_secret:
            return {
                "ok": True,
                "required": bool(token_auth.get("required", False)),
                "methods": ["inbound_token"] if bool(token_auth.get("required", False)) else [],
            }

        normalized_headers = self._normalized_headers(headers)
        signature = normalized_headers.get("x-hub-signature-256", "").strip().lower()
        if signature.startswith("sha256="):
            signature = signature.split("=", 1)[1].strip().lower()
        if not signature:
            return {
                "ok": False,
                "status_code": 401,
                "error": "missing WhatsApp signature header",
            }
        body = self._signature_message_body(payload, raw_body)
        expected = hmac.new(
            self.app_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return {
                "ok": False,
                "status_code": 401,
                "error": "invalid WhatsApp signature",
            }
        methods: list[str] = ["whatsapp_signature"]
        if bool(token_auth.get("required", False)):
            methods.append("inbound_token")
        return {
            "ok": True,
            "required": True,
            "methods": methods,
        }

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
