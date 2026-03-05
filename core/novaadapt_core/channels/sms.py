from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib import error, parse, request

from .base import ChannelAdapter, ChannelMessage, env_bool, now_unix_ms


def _twilio_post(
    *,
    account_sid: str,
    auth_token: str,
    api_base_url: str,
    endpoint_path: str,
    payload: dict[str, Any],
    timeout_seconds: float = 20.0,
) -> dict[str, Any]:
    body = parse.urlencode(payload, doseq=True).encode("utf-8")
    auth_raw = f"{account_sid}:{auth_token}".encode("utf-8")
    auth_header = "Basic " + base64.b64encode(auth_raw).decode("ascii")
    req = request.Request(
        url=f"{api_base_url.rstrip('/')}{endpoint_path}",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": auth_header,
        },
    )
    try:
        with request.urlopen(req, timeout=max(0.2, float(timeout_seconds))) as resp:
            raw = resp.read().decode("utf-8")
            code = int(resp.status)
    except error.HTTPError as exc:
        raw = ""
        try:
            raw = exc.read().decode("utf-8", errors="ignore")
        finally:
            try:
                exc.close()
            except Exception:
                pass
            try:
                exc.fp = None
                exc.file = None
            except Exception:
                pass
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return {
            "ok": False,
            "status_code": int(exc.code),
            "error": str(parsed.get("message") or parsed.get("error") or raw or f"HTTP {exc.code}"),
            "response": parsed if isinstance(parsed, dict) else {"data": parsed},
        }
    except error.URLError as exc:
        reason = exc.reason
        close_fn = getattr(reason, "close", None)
        if callable(close_fn):
            try:
                close_fn()
            except Exception:
                pass
        try:
            setattr(reason, "fp", None)
            setattr(reason, "file", None)
        except Exception:
            pass
        return {"ok": False, "error": f"transport: {exc.reason}"}
    except Exception as exc:  # pragma: no cover - defensive boundary
        return {"ok": False, "error": str(exc)}

    if not raw.strip():
        parsed: dict[str, Any] = {}
    else:
        try:
            loaded = json.loads(raw)
            parsed = loaded if isinstance(loaded, dict) else {"data": loaded}
        except Exception:
            parsed = {"raw": raw}
    return {"ok": True, "status_code": code, "response": parsed}


class SmsChannelAdapter(ChannelAdapter):
    name = "sms"

    def __init__(self) -> None:
        self.provider = str(os.getenv("NOVAADAPT_CHANNEL_SMS_PROVIDER", "twilio")).strip().lower() or "twilio"
        self.account_sid = str(os.getenv("NOVAADAPT_CHANNEL_SMS_ACCOUNT_SID", "")).strip()
        self.auth_token = str(os.getenv("NOVAADAPT_CHANNEL_SMS_AUTH_TOKEN", "")).strip()
        self.sender = str(os.getenv("NOVAADAPT_CHANNEL_SMS_FROM", "")).strip()
        self.api_base_url = str(os.getenv("NOVAADAPT_CHANNEL_SMS_API_BASE_URL", "https://api.twilio.com/2010-04-01")).strip()
        self.webhook_signing_secret = str(os.getenv("NOVAADAPT_CHANNEL_SMS_WEBHOOK_SIGNING_SECRET", "")).strip()
        self.require_signature = env_bool("NOVAADAPT_CHANNEL_SMS_REQUIRE_SIGNATURE", False)
        self.signature_max_age_seconds = max(
            5,
            int(os.getenv("NOVAADAPT_CHANNEL_SMS_SIGNATURE_MAX_AGE_SECONDS", "300") or "300"),
        )
        default_enabled = bool(self.account_sid and self.auth_token and self.sender)
        self._enabled = env_bool("NOVAADAPT_CHANNEL_SMS_ENABLED", default_enabled)

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        configured = bool(self.account_sid and self.auth_token and self.sender)
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and configured),
            "enabled": bool(self.enabled()),
            "configured": configured,
            "provider": self.provider,
            "account_sid_configured": bool(self.account_sid),
            "auth_token_configured": bool(self.auth_token),
            "sender_configured": bool(self.sender),
            "inbound_token_configured": bool(self._inbound_token()),
            "webhook_signing_secret_configured": bool(self.webhook_signing_secret),
            "require_signature": bool(self.require_signature),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        sms_payload = payload.get("sms")
        if not isinstance(sms_payload, dict):
            sms_payload = payload
        sender = (
            str(sms_payload.get("From") or "").strip()
            or str(sms_payload.get("from") or "").strip()
            or str(sms_payload.get("sender") or "").strip()
            or "sms-user"
        )
        text = (
            str(sms_payload.get("Body") or "").strip()
            or str(sms_payload.get("body") or "").strip()
            or str(sms_payload.get("text") or "").strip()
            or str(payload.get("text") or "").strip()
        )
        message_id = (
            str(sms_payload.get("MessageSid") or "").strip()
            or str(sms_payload.get("message_sid") or "").strip()
            or str(sms_payload.get("id") or "").strip()
        )
        metadata = {
            "to": str(sms_payload.get("To") or sms_payload.get("to") or "").strip(),
            "sms_status": str(sms_payload.get("SmsStatus") or sms_payload.get("sms_status") or "").strip(),
            "account_sid": str(sms_payload.get("AccountSid") or "").strip(),
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
                "error": "invalid SMS signature timestamp",
            }
        now = int(time.time())
        age = now - timestamp
        if age < -30:
            return {
                "ok": False,
                "status_code": 401,
                "error": "SMS signature timestamp is in the future",
            }
        if age > int(self.signature_max_age_seconds):
            return {
                "ok": False,
                "status_code": 401,
                "error": "SMS signature timestamp expired",
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
                "error": "SMS signature required but NOVAADAPT_CHANNEL_SMS_WEBHOOK_SIGNING_SECRET is not configured",
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
            normalized_headers.get("x-sms-signature", "").strip().lower()
            or normalized_headers.get("x-novaadapt-signature", "").strip().lower()
            or normalized_headers.get("x-signature", "").strip().lower()
        )
        timestamp = (
            normalized_headers.get("x-sms-timestamp", "").strip()
            or normalized_headers.get("x-novaadapt-timestamp", "").strip()
            or normalized_headers.get("x-signature-timestamp", "").strip()
        )
        if not signature or not timestamp:
            return {
                "ok": False,
                "status_code": 401,
                "error": "missing SMS signature headers",
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
                "error": "invalid SMS webhook signature",
            }
        methods = ["sms_hmac"]
        if bool(token_auth.get("required", False)):
            methods.append("inbound_token")
        return {
            "ok": True,
            "required": True,
            "methods": methods,
        }

    def send_text(self, to: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled():
            return {"ok": False, "channel": self.name, "error": "sms channel disabled"}
        if self.provider != "twilio":
            return {"ok": False, "channel": self.name, "error": f"unsupported sms provider: {self.provider}"}
        if not self.account_sid:
            return {"ok": False, "channel": self.name, "error": "sms account sid not configured"}
        if not self.auth_token:
            return {"ok": False, "channel": self.name, "error": "sms auth token not configured"}
        if not self.sender:
            return {"ok": False, "channel": self.name, "error": "sms sender number not configured"}

        recipient = str(to or "").strip()
        body = str(text or "").strip()
        if not recipient:
            raise ValueError("'to' is required (sms destination number)")
        if not body:
            raise ValueError("'text' is required")

        response = _twilio_post(
            account_sid=self.account_sid,
            auth_token=self.auth_token,
            api_base_url=self.api_base_url,
            endpoint_path=f"/Accounts/{self.account_sid}/Messages.json",
            payload={
                "To": recipient,
                "From": self.sender,
                "Body": body,
            },
            timeout_seconds=20.0,
        )
        provider = dict(response.get("response") or {})
        sid = str(provider.get("sid") or "").strip()
        ok = bool(response.get("ok", False) and sid)
        out = {
            "ok": ok,
            "channel": self.name,
            "to": recipient,
            "text": body,
            "message_id": sid or f"sms-{now_unix_ms()}",
            "metadata": dict(metadata or {}),
            "provider_response": provider,
        }
        if not ok:
            out["error"] = str(response.get("error") or provider.get("message") or "sms send failed")
        return out
