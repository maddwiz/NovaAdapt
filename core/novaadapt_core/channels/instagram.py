from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class InstagramChannelAdapter(ChannelAdapter):
    name = "instagram"

    def __init__(self) -> None:
        self.access_token = str(os.getenv("NOVAADAPT_CHANNEL_INSTAGRAM_ACCESS_TOKEN", "")).strip()
        self.account_id = str(os.getenv("NOVAADAPT_CHANNEL_INSTAGRAM_ACCOUNT_ID", "")).strip()
        self.graph_base_url = str(os.getenv("NOVAADAPT_CHANNEL_INSTAGRAM_GRAPH_BASE_URL", "https://graph.facebook.com")).strip(
            "/"
        )
        self.app_secret = str(os.getenv("NOVAADAPT_CHANNEL_INSTAGRAM_APP_SECRET", "")).strip()
        self.require_signature = env_bool("NOVAADAPT_CHANNEL_INSTAGRAM_REQUIRE_SIGNATURE", False)
        default_enabled = bool(self.access_token)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_INSTAGRAM_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        configured = bool(self.access_token)
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and configured),
            "enabled": bool(self.enabled()),
            "configured": configured,
            "account_id_configured": bool(self.account_id),
            "inbound_token_configured": bool(self._inbound_token()),
            "app_secret_configured": bool(self.app_secret),
            "require_signature": bool(self.require_signature),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        sender = "instagram-user"
        text = ""
        message_id = ""
        metadata: dict[str, Any] = {}

        entries = payload.get("entry")
        if not isinstance(entries, list):
            entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            account_id = str(entry.get("id") or "").strip()
            if account_id:
                metadata["account_id"] = account_id

            messaging_rows = entry.get("messaging")
            if isinstance(messaging_rows, list):
                for row in messaging_rows:
                    if not isinstance(row, dict):
                        continue
                    sender_payload = row.get("sender")
                    recipient_payload = row.get("recipient")
                    if isinstance(sender_payload, dict):
                        sender = str(sender_payload.get("id") or sender).strip() or sender
                    if isinstance(recipient_payload, dict):
                        metadata["recipient_id"] = str(recipient_payload.get("id") or "").strip()
                    message_payload = row.get("message")
                    if isinstance(message_payload, dict):
                        message_id = str(message_payload.get("mid") or "").strip()
                        text = str(message_payload.get("text") or "").strip()
                        if not text:
                            attachments = message_payload.get("attachments")
                            if isinstance(attachments, list) and attachments:
                                text = str(attachments[0].get("type") or "").strip()
                        metadata["event_type"] = "message"
                        break
                if text:
                    break

            changes = entry.get("changes")
            if isinstance(changes, list):
                for change in changes:
                    if not isinstance(change, dict):
                        continue
                    value = change.get("value")
                    if not isinstance(value, dict):
                        continue
                    if str(value.get("messaging_product") or "").strip().lower() != "instagram":
                        continue
                    messages = value.get("messages")
                    if not isinstance(messages, list) or not messages:
                        continue
                    first = messages[0]
                    if not isinstance(first, dict):
                        continue
                    sender = str(first.get("from") or sender).strip() or sender
                    message_id = str(first.get("id") or "").strip()
                    text_payload = first.get("text")
                    if isinstance(text_payload, dict):
                        text = str(text_payload.get("body") or "").strip()
                    else:
                        text = str(first.get("body") or "").strip()
                    metadata["event_type"] = "message"
                    metadata["messaging_product"] = "instagram"
                    break
                if text:
                    break

        if not text:
            sender = str(payload.get("sender") or sender).strip() or sender
            text = str(payload.get("text") or payload.get("message") or "").strip()
            message_id = str(payload.get("message_id") or payload.get("id") or "").strip()

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
                "error": "Instagram signature required but NOVAADAPT_CHANNEL_INSTAGRAM_APP_SECRET is not configured",
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
                "error": "missing Instagram signature header",
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
                "error": "invalid Instagram signature",
            }
        methods: list[str] = ["instagram_signature"]
        if bool(token_auth.get("required", False)):
            methods.append("inbound_token")
        return {
            "ok": True,
            "required": True,
            "methods": methods,
        }

    def send_text(self, to: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled():
            return {"ok": False, "channel": self.name, "error": "instagram channel disabled"}
        if not self.access_token:
            return {"ok": False, "channel": self.name, "error": "instagram access token not configured"}
        recipient = str(to or "").strip()
        body = str(text or "").strip()
        if not recipient:
            raise ValueError("'to' is required (instagram scoped user id)")
        if not body:
            raise ValueError("'text' is required")

        msg_metadata = metadata if isinstance(metadata, dict) else {}
        messaging_type = str(msg_metadata.get("messaging_type") or "RESPONSE").strip() or "RESPONSE"
        endpoint = f"{self.graph_base_url}/v20.0/me/messages?access_token={self.access_token}"
        response = http_json_request(
            method="POST",
            url=endpoint,
            payload={
                "messaging_type": messaging_type,
                "recipient": {"id": recipient},
                "message": {"text": body},
            },
            timeout_seconds=20.0,
        )
        provider = dict(response.get("response") or {})
        message_id = str(provider.get("message_id") or "").strip()
        ok = bool(response.get("ok", False) and message_id)
        out = {
            "ok": ok,
            "channel": self.name,
            "to": recipient,
            "text": body,
            "message_id": message_id,
            "metadata": dict(msg_metadata),
            "provider_response": provider,
        }
        if not ok:
            provider_error = provider.get("error")
            provider_error_text = (
                str(provider_error.get("message") or "").strip()
                if isinstance(provider_error, dict)
                else ""
            )
            out["error"] = str(response.get("error") or provider_error_text or "instagram send failed")
        return out
