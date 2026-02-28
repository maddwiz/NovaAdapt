from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class SignalChannelAdapter(ChannelAdapter):
    name = "signal"

    def __init__(self) -> None:
        self.base_url = str(os.getenv("NOVAADAPT_CHANNEL_SIGNAL_BASE_URL", "http://127.0.0.1:8080")).strip().rstrip("/")
        self.sender = str(os.getenv("NOVAADAPT_CHANNEL_SIGNAL_SENDER", "")).strip()
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_SIGNAL_TOKEN", "")).strip()
        self.webhook_signing_secret = str(os.getenv("NOVAADAPT_CHANNEL_SIGNAL_WEBHOOK_SIGNING_SECRET", "")).strip()
        self.require_signature = env_bool("NOVAADAPT_CHANNEL_SIGNAL_REQUIRE_SIGNATURE", False)
        self.signature_max_age_seconds = max(
            5,
            int(os.getenv("NOVAADAPT_CHANNEL_SIGNAL_SIGNATURE_MAX_AGE_SECONDS", "300") or "300"),
        )
        default_enabled = bool(self.base_url and self.sender)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_SIGNAL_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        configured = bool(self.base_url and self.sender)
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and configured),
            "enabled": bool(self.enabled()),
            "configured": configured,
            "base_url": self.base_url,
            "sender_configured": bool(self.sender),
            "token_configured": bool(self.token),
            "inbound_token_configured": bool(self._inbound_token()),
            "webhook_signing_secret_configured": bool(self.webhook_signing_secret),
            "require_signature": bool(self.require_signature),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        envelope = payload.get("envelope")
        if not isinstance(envelope, dict):
            envelope = payload
        data_message = envelope.get("dataMessage")
        if not isinstance(data_message, dict):
            data_message = {}
        sender = (
            str(envelope.get("sourceNumber") or "").strip()
            or str(payload.get("sender") or "").strip()
            or str(payload.get("from") or "").strip()
            or "signal-user"
        )
        text = (
            str(data_message.get("message") or "").strip()
            or str(payload.get("text") or "").strip()
            or str(payload.get("message") or "").strip()
        )
        message_id = (
            str(envelope.get("timestamp") or "").strip()
            or str(payload.get("message_id") or "").strip()
            or str(payload.get("id") or "").strip()
        )
        metadata = {
            "source_uuid": str(envelope.get("sourceUuid") or "").strip(),
            "source_device": str(envelope.get("sourceDevice") or "").strip(),
            "timestamp": str(envelope.get("timestamp") or "").strip(),
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
                "error": "invalid Signal signature timestamp",
            }
        now = int(time.time())
        age = now - timestamp
        if age < -30:
            return {
                "ok": False,
                "status_code": 401,
                "error": "Signal signature timestamp is in the future",
            }
        if age > int(self.signature_max_age_seconds):
            return {
                "ok": False,
                "status_code": 401,
                "error": "Signal signature timestamp expired",
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

        if self.require_signature and not self.webhook_signing_secret:
            return {
                "ok": False,
                "status_code": 500,
                "error": "Signal signature required but NOVAADAPT_CHANNEL_SIGNAL_WEBHOOK_SIGNING_SECRET is not configured",
            }
        if not self.webhook_signing_secret:
            methods = ["inbound_token"] if bool(token_auth.get("required", False)) else []
            return {
                "ok": True,
                "required": bool(token_auth.get("required", False)),
                "methods": methods,
            }

        normalized_headers = self._normalized_headers(headers)
        signature = (
            normalized_headers.get("x-signal-signature", "").strip().lower()
            or normalized_headers.get("x-novaadapt-signature", "").strip().lower()
            or normalized_headers.get("x-signature", "").strip().lower()
        )
        timestamp = (
            normalized_headers.get("x-signal-timestamp", "").strip()
            or normalized_headers.get("x-novaadapt-timestamp", "").strip()
            or normalized_headers.get("x-signature-timestamp", "").strip()
        )
        if not signature or not timestamp:
            return {
                "ok": False,
                "status_code": 401,
                "error": "missing Signal signature headers",
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
                "error": "invalid Signal webhook signature",
            }
        methods = ["signal_hmac"]
        if bool(token_auth.get("required", False)):
            methods.append("inbound_token")
        return {
            "ok": True,
            "required": True,
            "methods": methods,
        }

    def send_text(self, to: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled():
            return {"ok": False, "channel": self.name, "error": "signal channel disabled"}
        if not self.base_url:
            return {"ok": False, "channel": self.name, "error": "signal base url not configured"}
        if not self.sender:
            return {"ok": False, "channel": self.name, "error": "signal sender number not configured"}

        recipient = str(to or "").strip()
        body = str(text or "").strip()
        if not recipient:
            raise ValueError("'to' is required (signal phone number)")
        if not body:
            raise ValueError("'text' is required")

        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        response = http_json_request(
            method="POST",
            url=f"{self.base_url}/v2/send",
            headers=headers,
            payload={
                "message": body,
                "number": self.sender,
                "recipients": [recipient],
            },
            timeout_seconds=20.0,
        )
        provider = dict(response.get("response") or {})
        ok = bool(response.get("ok", False)) and not bool(provider.get("error"))
        timestamp = str(provider.get("timestamp") or "").strip()
        out = {
            "ok": ok,
            "channel": self.name,
            "to": recipient,
            "text": body,
            "message_id": timestamp or f"signal-{now_unix_ms()}",
            "metadata": dict(metadata or {}),
            "provider_response": provider,
        }
        if not ok:
            out["error"] = str(response.get("error") or provider.get("error") or "signal send failed")
        return out
