from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, http_json_request, now_unix_ms


class DiscordChannelAdapter(ChannelAdapter):
    name = "discord"

    def __init__(self) -> None:
        self.token = str(os.getenv("NOVAADAPT_CHANNEL_DISCORD_BOT_TOKEN", "")).strip()
        self.default_channel_id = str(os.getenv("NOVAADAPT_CHANNEL_DISCORD_DEFAULT_CHANNEL_ID", "")).strip()
        self._allowed_channel_ids = {
            item.strip()
            for item in str(os.getenv("NOVAADAPT_CHANNEL_DISCORD_ALLOWED_CHANNEL_IDS", "")).split(",")
            if item.strip()
        }
        self.discord_public_key = str(os.getenv("NOVAADAPT_CHANNEL_DISCORD_INTERACTIONS_PUBLIC_KEY", "")).strip()
        self.webhook_signing_secret = str(os.getenv("NOVAADAPT_CHANNEL_DISCORD_WEBHOOK_SIGNING_SECRET", "")).strip()
        self.require_signature = env_bool("NOVAADAPT_CHANNEL_DISCORD_REQUIRE_SIGNATURE", False)
        self.signature_max_age_seconds = max(
            5,
            int(os.getenv("NOVAADAPT_CHANNEL_DISCORD_SIGNATURE_MAX_AGE_SECONDS", "300") or "300"),
        )
        default_enabled = bool(self.token)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_DISCORD_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def _supports_discord_signature(self) -> bool:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey as _  # noqa: F401
        except Exception:
            return False
        return True

    def health(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and self.token),
            "enabled": bool(self.enabled()),
            "configured": bool(self.token),
            "default_channel_configured": bool(self.default_channel_id),
            "inbound_token_configured": bool(self._inbound_token()),
            "discord_public_key_configured": bool(self.discord_public_key),
            "webhook_signing_secret_configured": bool(self.webhook_signing_secret),
            "require_signature": bool(self.require_signature),
            "signature_verifier_available": bool(self._supports_discord_signature()),
            "allowed_channel_ids_count": len(self._allowed_channel_ids),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        data = payload.get("d")
        if not isinstance(data, dict):
            data = payload
        author = data.get("author")
        if not isinstance(author, dict):
            author = {}
        sender = (
            str(author.get("username") or "").strip()
            or str(author.get("id") or "").strip()
            or str(data.get("user_id") or "").strip()
            or "discord-user"
        )
        text = str(data.get("content") or "").strip()
        message_id = str(data.get("id") or payload.get("id") or "").strip()
        metadata = {
            "channel_id": str(data.get("channel_id") or "").strip(),
            "guild_id": str(data.get("guild_id") or "").strip(),
            "author_id": str(author.get("id") or "").strip(),
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
        # Fallback for non-HTTP callers that do not preserve raw body.
        import json

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    def _validate_signature_timestamp(self, timestamp_text: str) -> dict[str, Any]:
        try:
            timestamp = int(str(timestamp_text).strip())
        except Exception:
            return {
                "ok": False,
                "status_code": 401,
                "error": "invalid signature timestamp",
            }
        now = int(time.time())
        age = now - timestamp
        if age < -30:
            return {
                "ok": False,
                "status_code": 401,
                "error": "signature timestamp is in the future",
            }
        if age > int(self.signature_max_age_seconds):
            return {
                "ok": False,
                "status_code": 401,
                "error": "signature timestamp expired",
            }
        return {"ok": True, "timestamp": timestamp}

    def _verify_discord_ed25519(
        self,
        *,
        payload: dict[str, Any],
        headers: dict[str, str] | None,
        raw_body: str | None,
    ) -> dict[str, Any]:
        if not self.discord_public_key:
            return {"ok": True, "required": False}
        normalized_headers = self._normalized_headers(headers)
        signature = normalized_headers.get("x-signature-ed25519", "").strip().lower()
        timestamp = normalized_headers.get("x-signature-timestamp", "").strip()
        if not signature or not timestamp:
            return {
                "ok": False,
                "status_code": 401,
                "error": "missing Discord signature headers",
            }
        ts_check = self._validate_signature_timestamp(timestamp)
        if not bool(ts_check.get("ok")):
            return ts_check
        body = self._signature_message_body(payload, raw_body)
        try:
            signature_bytes = bytes.fromhex(signature)
            public_key_bytes = bytes.fromhex(self.discord_public_key)
        except Exception:
            return {
                "ok": False,
                "status_code": 500,
                "error": "invalid Discord signature/public key hex",
            }
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except Exception:
            return {
                "ok": False,
                "status_code": 500,
                "error": "discord signature verification unavailable (install cryptography)",
            }
        try:
            verifier = Ed25519PublicKey.from_public_bytes(public_key_bytes)
            verifier.verify(signature_bytes, timestamp.encode("utf-8") + body.encode("utf-8"))
        except Exception:
            return {
                "ok": False,
                "status_code": 401,
                "error": "invalid Discord signature",
            }
        return {"ok": True, "required": True, "method": "discord_ed25519"}

    def _verify_webhook_hmac(
        self,
        *,
        payload: dict[str, Any],
        headers: dict[str, str] | None,
        raw_body: str | None,
    ) -> dict[str, Any]:
        if not self.webhook_signing_secret:
            return {"ok": True, "required": False}
        normalized_headers = self._normalized_headers(headers)
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
                "error": "missing webhook signature headers",
            }
        ts_check = self._validate_signature_timestamp(timestamp)
        if not bool(ts_check.get("ok")):
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
                "error": "invalid webhook signature",
            }
        return {"ok": True, "required": True, "method": "webhook_hmac"}

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

        ed25519_auth = self._verify_discord_ed25519(payload=payload, headers=headers, raw_body=raw_body)
        if not bool(ed25519_auth.get("ok", False)):
            return ed25519_auth
        webhook_auth = self._verify_webhook_hmac(payload=payload, headers=headers, raw_body=raw_body)
        if not bool(webhook_auth.get("ok", False)):
            return webhook_auth

        signature_required = bool(self.require_signature)
        signature_active = bool(self.discord_public_key or self.webhook_signing_secret)
        if signature_required and not signature_active:
            return {
                "ok": False,
                "status_code": 500,
                "error": "signature required but no discord/webhook signing keys are configured",
            }

        required = bool(token_auth.get("required", False) or ed25519_auth.get("required", False) or webhook_auth.get("required", False))
        methods: list[str] = []
        if bool(token_auth.get("required", False)):
            methods.append("inbound_token")
        if bool(ed25519_auth.get("required", False)):
            methods.append("discord_ed25519")
        if bool(webhook_auth.get("required", False)):
            methods.append("webhook_hmac")
        if signature_required and not methods:
            return {
                "ok": False,
                "status_code": 401,
                "error": "signature required but no signature headers were provided",
            }
        return {
            "ok": True,
            "required": required or signature_required,
            "methods": methods,
        }

    def send_text(self, to: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled():
            return {"ok": False, "channel": self.name, "error": "discord channel disabled"}
        if not self.token:
            return {"ok": False, "channel": self.name, "error": "discord bot token not configured"}
        channel_id = str(to or "").strip() or self.default_channel_id
        body = str(text or "").strip()
        if not channel_id:
            raise ValueError("'to' is required (discord channel id)")
        if not body:
            raise ValueError("'text' is required")
        if len(body) > 2000:
            raise ValueError("'text' exceeds Discord message limit (2000 characters)")
        if self._allowed_channel_ids and channel_id not in self._allowed_channel_ids:
            return {
                "ok": False,
                "channel": self.name,
                "error": "discord channel is not in allowed channel list",
                "to": channel_id,
            }
        endpoint = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        response = http_json_request(
            method="POST",
            url=endpoint,
            headers={"Authorization": f"Bot {self.token}"},
            payload={
                "content": body,
                # Prevent accidental mass-mentions in automated agent output.
                "allowed_mentions": {"parse": []},
            },
            timeout_seconds=15.0,
        )
        provider = dict(response.get("response") or {})
        message_id = str(provider.get("id") or "").strip()
        ok = bool(response.get("ok", False) and message_id)
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
            out["error"] = str(response.get("error") or provider.get("message") or "discord send failed")
            retry_after = provider.get("retry_after")
            if retry_after is not None:
                out["retry_after_seconds"] = retry_after
        return out
