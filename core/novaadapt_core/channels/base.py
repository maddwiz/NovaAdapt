from __future__ import annotations

import json
import os
import time
import hmac
from dataclasses import dataclass
from typing import Any
from urllib import error, request


def env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "")).strip().lower()
    if not raw:
        return bool(default)
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def now_unix_ms() -> int:
    return int(time.time() * 1000)


def http_json_request(
    *,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    body = None
    req_headers: dict[str, str] = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")
    req = request.Request(
        url=str(url),
        data=body,
        method=str(method or "GET").upper(),
        headers=req_headers,
    )
    try:
        with request.urlopen(req, timeout=max(0.2, float(timeout_seconds))) as resp:
            raw = resp.read().decode("utf-8")
            code = int(resp.status)
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(raw) if raw else {}
        except Exception:
            parsed = {"raw": raw}
        return {
            "ok": False,
            "status_code": int(exc.code),
            "error": str(parsed.get("error") or parsed.get("message") or raw or f"HTTP {exc.code}"),
            "response": parsed if isinstance(parsed, dict) else {"data": parsed},
        }
    except error.URLError as exc:
        return {"ok": False, "error": f"transport: {exc.reason}"}
    except Exception as exc:  # pragma: no cover - defensive boundary
        return {"ok": False, "error": str(exc)}

    parsed: dict[str, Any]
    if not raw.strip():
        parsed = {}
    else:
        try:
            loaded = json.loads(raw)
            if isinstance(loaded, dict):
                parsed = loaded
            else:
                parsed = {"data": loaded}
        except Exception:
            parsed = {"raw": raw}
    return {"ok": True, "status_code": code, "response": parsed}


@dataclass
class ChannelMessage:
    channel: str
    sender: str
    text: str
    message_id: str = ""
    received_at_ms: int = 0
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "sender": self.sender,
            "text": self.text,
            "message_id": self.message_id,
            "received_at_ms": int(self.received_at_ms or now_unix_ms()),
            "metadata": dict(self.metadata or {}),
        }


class ChannelAdapter:
    name: str = "unknown"

    def enabled(self) -> bool:
        return False

    def health(self) -> dict[str, Any]:
        return {
            "channel": self.name,
            "ok": bool(self.enabled()),
            "enabled": bool(self.enabled()),
            "inbound_auth_configured": bool(self._inbound_token()),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        raise NotImplementedError

    def send_text(self, to: str, text: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def verify_inbound(
        self,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        expected = self._inbound_token()
        if not expected:
            return {"ok": True, "required": False}

        provided = self._extract_inbound_token(payload, headers=headers)
        if provided and hmac.compare_digest(provided, expected):
            return {"ok": True, "required": True}

        return {
            "ok": False,
            "required": True,
            "error": "unauthorized inbound payload",
            "status_code": 401,
        }

    def _inbound_token(self) -> str:
        env_name = self.inbound_token_env_name()
        return str(os.getenv(env_name, "")).strip()

    def inbound_token_env_name(self) -> str:
        safe_name = str(self.name or "unknown").upper().replace("-", "_")
        return f"NOVAADAPT_CHANNEL_{safe_name}_INBOUND_TOKEN"

    def _extract_inbound_token(
        self,
        payload: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> str:
        direct = str(payload.get("auth_token") or "").strip()
        if direct:
            return direct
        normalized_headers: dict[str, str] = {}
        if isinstance(headers, dict):
            for key, value in headers.items():
                header_name = str(key or "").strip().lower()
                if not header_name:
                    continue
                normalized_headers[header_name] = str(value or "").strip()
        via_header = normalized_headers.get("x-novaadapt-channel-token", "").strip()
        if via_header:
            return via_header
        auth = normalized_headers.get("authorization", "").strip()
        if auth.lower().startswith("bearer "):
            return auth[7:].strip()
        return ""
