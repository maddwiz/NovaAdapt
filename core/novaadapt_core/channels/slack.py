from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class SlackChannelAdapter(ChannelAdapter):
    name = "slack"

    def __init__(self) -> None:
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_SLACK_BOT_TOKEN", "")).strip()
        self.default_channel_id = str(os.getenv("NOVAADAPT_CHANNEL_SLACK_DEFAULT_CHANNEL_ID", "")).strip()
        self.signing_secret = str(os.getenv("NOVAADAPT_CHANNEL_SLACK_SIGNING_SECRET", "")).strip()
        self.require_signature = env_bool("NOVAADAPT_CHANNEL_SLACK_REQUIRE_SIGNATURE", False)
        self.signature_max_age_seconds = max(
            5,
            int(os.getenv("NOVAADAPT_CHANNEL_SLACK_SIGNATURE_MAX_AGE_SECONDS", "300") or "300"),
        )
        default_enabled = bool(self.token)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_SLACK_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and self.token),
            "enabled": bool(self.enabled()),
            "configured": bool(self.token),
            "default_channel_configured": bool(self.default_channel_id),
            "inbound_token_configured": bool(self._inbound_token()),
            "signing_secret_configured": bool(self.signing_secret),
            "require_signature": bool(self.require_signature),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        event = payload.get("event")
        if not isinstance(event, dict):
            event = payload
        sender = str(event.get("user") or payload.get("user") or "slack-user").strip() or "slack-user"
        text = str(event.get("text") or payload.get("text") or "").strip()
        message_id = str(event.get("client_msg_id") or event.get("ts") or payload.get("ts") or "").strip()
        metadata = {
            "channel_id": str(event.get("channel") or "").strip(),
            "thread_ts": str(event.get("thread_ts") or "").strip(),
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
                "error": "invalid Slack signature timestamp",
            }
        now = int(time.time())
        age = now - timestamp
        if age < -30:
            return {
                "ok": False,
                "status_code": 401,
                "error": "Slack signature timestamp is in the future",
            }
        if age > int(self.signature_max_age_seconds):
            return {
                "ok": False,
                "status_code": 401,
                "error": "Slack signature timestamp expired",
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

        if self.require_signature and not self.signing_secret:
            return {
                "ok": False,
                "status_code": 500,
                "error": "Slack signature required but NOVAADAPT_CHANNEL_SLACK_SIGNING_SECRET is not configured",
            }
        if not self.signing_secret:
            return {
                "ok": True,
                "required": bool(token_auth.get("required", False)),
                "methods": ["inbound_token"] if bool(token_auth.get("required", False)) else [],
            }

        normalized_headers = self._normalized_headers(headers)
        signature = normalized_headers.get("x-slack-signature", "").strip().lower()
        timestamp = normalized_headers.get("x-slack-request-timestamp", "").strip()
        if not signature or not timestamp:
            return {
                "ok": False,
                "status_code": 401,
                "error": "missing Slack signature headers",
            }
        ts_check = self._validate_signature_timestamp(timestamp)
        if not bool(ts_check.get("ok", False)):
            return ts_check
        body = self._signature_message_body(payload, raw_body)
        message = f"v0:{timestamp}:{body}".encode("utf-8")
        expected = "v0=" + hmac.new(
            self.signing_secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return {
                "ok": False,
                "status_code": 401,
                "error": "invalid Slack signature",
            }

        methods: list[str] = ["slack_signature"]
        if bool(token_auth.get("required", False)):
            methods.append("inbound_token")
        return {
            "ok": True,
            "required": True,
            "methods": methods,
        }

    def send_text(self, to: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled():
            return {"ok": False, "channel": self.name, "error": "slack channel disabled"}
        if not self.token:
            return {"ok": False, "channel": self.name, "error": "slack bot token not configured"}
        channel_id = str(to or "").strip() or self.default_channel_id
        body = str(text or "").strip()
        if not channel_id:
            raise ValueError("'to' is required (slack channel id)")
        if not body:
            raise ValueError("'text' is required")
        response = http_json_request(
            method="POST",
            url="https://slack.com/api/chat.postMessage",
            headers={"Authorization": f"Bearer {self.token}"},
            payload={"channel": channel_id, "text": body},
            timeout_seconds=15.0,
        )
        provider = dict(response.get("response") or {})
        ok = bool(response.get("ok", False) and provider.get("ok", False))
        message_payload = provider.get("message")
        message_id = ""
        if isinstance(message_payload, dict):
            message_id = str(message_payload.get("client_msg_id") or message_payload.get("ts") or "").strip()
        if not message_id:
            message_id = str(provider.get("ts") or "").strip()
        out = {
            "ok": ok,
            "channel": self.name,
            "to": channel_id,
            "text": body,
            "message_id": message_id,
            "metadata": dict(metadata or {}),
            "provider_response": provider,
        }
        if not ok:
            out["error"] = str(response.get("error") or provider.get("error") or "slack send failed")
        return out
