from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class TelegramChannelAdapter(ChannelAdapter):
    name = "telegram"

    def __init__(self) -> None:
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_TELEGRAM_BOT_TOKEN", "")).strip()
        self.default_chat_id = str(os.getenv("NOVAADAPT_CHANNEL_TELEGRAM_DEFAULT_CHAT_ID", "")).strip()
        self.webhook_secret_token = str(os.getenv("NOVAADAPT_CHANNEL_TELEGRAM_WEBHOOK_SECRET_TOKEN", "")).strip()
        self.webhook_signing_secret = str(os.getenv("NOVAADAPT_CHANNEL_TELEGRAM_WEBHOOK_SIGNING_SECRET", "")).strip()
        self.require_signature = env_bool("NOVAADAPT_CHANNEL_TELEGRAM_REQUIRE_SIGNATURE", False)
        self.signature_max_age_seconds = max(
            5,
            int(os.getenv("NOVAADAPT_CHANNEL_TELEGRAM_SIGNATURE_MAX_AGE_SECONDS", "300") or "300"),
        )
        default_enabled = bool(self.token)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_TELEGRAM_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and self.token),
            "enabled": bool(self.enabled()),
            "configured": bool(self.token),
            "default_chat_id_configured": bool(self.default_chat_id),
            "inbound_token_configured": bool(self._inbound_token()),
            "webhook_secret_token_configured": bool(self.webhook_secret_token),
            "webhook_signing_secret_configured": bool(self.webhook_signing_secret),
            "require_signature": bool(self.require_signature),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        message = payload.get("message")
        if not isinstance(message, dict):
            message = payload.get("edited_message")
        if not isinstance(message, dict):
            message = payload
        from_payload = message.get("from")
        if not isinstance(from_payload, dict):
            from_payload = {}
        chat = message.get("chat")
        if not isinstance(chat, dict):
            chat = {}
        sender = (
            str(from_payload.get("username") or "").strip()
            or str(from_payload.get("id") or "").strip()
            or "telegram-user"
        )
        text = str(message.get("text") or message.get("caption") or "").strip()
        message_id = str(message.get("message_id") or payload.get("update_id") or "").strip()
        metadata = {
            "chat_id": str(chat.get("id") or "").strip(),
            "chat_type": str(chat.get("type") or "").strip(),
        }
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

    def _validate_signature_timestamp(self, timestamp_text: str) -> dict[str, Any]:
        try:
            timestamp = int(str(timestamp_text).strip())
        except Exception:
            return {
                "ok": False,
                "status_code": 401,
                "error": "invalid Telegram signature timestamp",
            }
        now = int(time.time())
        age = now - timestamp
        if age < -30:
            return {
                "ok": False,
                "status_code": 401,
                "error": "Telegram signature timestamp is in the future",
            }
        if age > int(self.signature_max_age_seconds):
            return {
                "ok": False,
                "status_code": 401,
                "error": "Telegram signature timestamp expired",
            }
        return {"ok": True, "timestamp": timestamp}

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

        signature_required = bool(self.require_signature)
        signature_active = bool(self.webhook_secret_token or self.webhook_signing_secret)
        if signature_required and not signature_active:
            return {
                "ok": False,
                "status_code": 500,
                "error": (
                    "Telegram signature required but no webhook secret/signing "
                    "secret is configured"
                ),
            }

        normalized_headers = self._normalized_headers(headers)
        methods: list[str] = []
        if bool(token_auth.get("required", False)):
            methods.append("inbound_token")

        if self.webhook_secret_token:
            provided_secret = normalized_headers.get("x-telegram-bot-api-secret-token", "").strip()
            if not provided_secret:
                return {
                    "ok": False,
                    "status_code": 401,
                    "error": "missing Telegram webhook secret token header",
                }
            if not hmac.compare_digest(provided_secret, self.webhook_secret_token):
                return {
                    "ok": False,
                    "status_code": 401,
                    "error": "invalid Telegram webhook secret token",
                }
            methods.append("telegram_secret_token")

        if self.webhook_signing_secret:
            signature = (
                normalized_headers.get("x-novaadapt-signature", "").strip().lower()
                or normalized_headers.get("x-signature", "").strip().lower()
            )
            timestamp = (
                normalized_headers.get("x-novaadapt-timestamp", "").strip()
                or normalized_headers.get("x-signature-timestamp", "").strip()
            )
            if not signature or not timestamp:
                return {
                    "ok": False,
                    "status_code": 401,
                    "error": "missing Telegram signature headers",
                }
            ts_check = self._validate_signature_timestamp(timestamp)
            if not bool(ts_check.get("ok", False)):
                return ts_check
            body = self._signature_message_body(payload, raw_body)
            message = f"{timestamp}.{body}".encode("utf-8")
            expected = hmac.new(
                self.webhook_signing_secret.encode("utf-8"),
                message,
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return {
                    "ok": False,
                    "status_code": 401,
                    "error": "invalid Telegram webhook signature",
                }
            methods.append("telegram_hmac")

        if signature_required and not methods and not bool(token_auth.get("required", False)):
            return {
                "ok": False,
                "status_code": 401,
                "error": "signature required but no Telegram signature headers were provided",
            }
        return {
            "ok": True,
            "required": bool(token_auth.get("required", False) or methods),
            "methods": methods,
        }

    def send_text(self, to: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled():
            return {"ok": False, "channel": self.name, "error": "telegram channel disabled"}
        if not self.token:
            return {"ok": False, "channel": self.name, "error": "telegram bot token not configured"}
        chat_id = str(to or "").strip() or self.default_chat_id
        body = str(text or "").strip()
        if not chat_id:
            raise ValueError("'to' is required (telegram chat_id)")
        if not body:
            raise ValueError("'text' is required")
        endpoint = f"https://api.telegram.org/bot{self.token}/sendMessage"
        response = http_json_request(
            method="POST",
            url=endpoint,
            payload={"chat_id": chat_id, "text": body},
            timeout_seconds=15.0,
        )
        provider = dict(response.get("response") or {})
        provider_ok = bool(provider.get("ok", False))
        message_payload = provider.get("result")
        message_id = ""
        if isinstance(message_payload, dict):
            message_id = str(message_payload.get("message_id") or "").strip()
        out = {
            "ok": bool(response.get("ok", False) and provider_ok),
            "channel": self.name,
            "to": chat_id,
            "text": body,
            "message_id": message_id,
            "metadata": dict(metadata or {}),
            "provider_response": provider,
        }
        if not out["ok"]:
            out["error"] = str(response.get("error") or provider.get("description") or "telegram send failed")
        return out
