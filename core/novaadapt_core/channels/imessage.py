from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any

from .base import ChannelAdapter, ChannelMessage, env_bool, now_unix_ms


class IMessageChannelAdapter(ChannelAdapter):
    name = "imessage"

    def __init__(self) -> None:
        self._platform = platform.system().strip().lower()
        default_enabled = self._platform == "darwin"
        self._enabled = env_bool("NOVAADAPT_CHANNEL_IMESSAGE_ENABLED", default_enabled)
        self._default_handle = str(os.getenv("NOVAADAPT_CHANNEL_IMESSAGE_DEFAULT_HANDLE", "")).strip()

    def enabled(self) -> bool:
        return bool(self._enabled)

    def health(self) -> dict[str, Any]:
        osascript_path = shutil.which("osascript")
        supported = self._platform == "darwin" and bool(osascript_path)
        return {
            "channel": self.name,
            "ok": bool(self.enabled() and supported),
            "enabled": bool(self.enabled()),
            "supported": supported,
            "platform": self._platform,
            "configured": bool(supported),
            "default_handle_configured": bool(self._default_handle),
        }

    def normalize_inbound(self, payload: dict[str, Any]) -> ChannelMessage:
        sender = (
            str(payload.get("sender") or "").strip()
            or str(payload.get("from") or "").strip()
            or str(payload.get("handle") or "").strip()
            or "imessage-user"
        )
        text = str(payload.get("text") or payload.get("message") or "").strip()
        message_id = (
            str(payload.get("message_id") or "").strip()
            or str(payload.get("id") or "").strip()
            or str(payload.get("guid") or "").strip()
        )
        metadata = {
            "chat_id": str(payload.get("chat_id") or "").strip(),
            "service": str(payload.get("service") or "iMessage").strip() or "iMessage",
            "handle": str(payload.get("handle") or sender).strip(),
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
            return {"ok": False, "channel": self.name, "error": "imessage channel disabled"}
        if self._platform != "darwin":
            return {"ok": False, "channel": self.name, "error": "imessage requires macOS"}
        recipient = str(to or "").strip() or self._default_handle
        body = str(text or "").strip()
        if not recipient:
            raise ValueError("'to' is required (imessage handle/email/phone)")
        if not body:
            raise ValueError("'text' is required")

        script = (
            "on run argv\n"
            "set targetBuddy to item 1 of argv\n"
            "set bodyText to item 2 of argv\n"
            "tell application \"Messages\"\n"
            "set targetService to 1st service whose service type = iMessage\n"
            "set targetBuddyRef to buddy targetBuddy of targetService\n"
            "send bodyText to targetBuddyRef\n"
            "end tell\n"
            "end run\n"
        )
        try:
            proc = subprocess.run(
                ["osascript", "-e", script, recipient, body],
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:
            return {"ok": False, "channel": self.name, "error": str(exc)}

        ok = int(proc.returncode) == 0
        result: dict[str, Any] = {
            "ok": ok,
            "channel": self.name,
            "to": recipient,
            "text": body,
            "message_id": f"imessage-{now_unix_ms()}",
            "metadata": dict(metadata or {}),
            "provider_response": {
                "returncode": int(proc.returncode),
                "stdout": str(proc.stdout or "").strip(),
                "stderr": str(proc.stderr or "").strip(),
            },
        }
        if not ok:
            result["error"] = (
                str(proc.stderr or "").strip()
                or str(proc.stdout or "").strip()
                or "imessage send failed"
            )
        return result
