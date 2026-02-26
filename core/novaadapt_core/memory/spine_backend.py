from __future__ import annotations

import json
import os
import time
from typing import Any, Protocol
from urllib import error, request


class MemoryBackend(Protocol):
    def status(self) -> dict[str, Any]:
        ...

    def recall(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        ...

    def augment(
        self,
        query: str,
        top_k: int = 5,
        *,
        min_score: float = 0.005,
        format_name: str = "xml",
    ) -> str:
        ...

    def ingest(
        self,
        text: str,
        *,
        source_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        ...


class NoopMemoryBackend:
    def __init__(self, reason: str = "memory backend disabled") -> None:
        self.reason = str(reason).strip() or "memory backend disabled"

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "enabled": False,
            "backend": "noop",
            "reason": self.reason,
        }

    def recall(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        _ = (query, top_k)
        return []

    def augment(
        self,
        query: str,
        top_k: int = 5,
        *,
        min_score: float = 0.005,
        format_name: str = "xml",
    ) -> str:
        _ = (query, top_k, min_score, format_name)
        return ""

    def ingest(
        self,
        text: str,
        *,
        source_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        _ = (text, source_id, metadata)
        return None


class NovaSpineHTTPMemoryBackend:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float = 2.0,
        retry_after_seconds: float = 30.0,
    ) -> None:
        raw_url = (
            base_url
            if base_url is not None
            else os.getenv("NOVAADAPT_SPINE_URL", "http://127.0.0.1:8420")
        )
        self.base_url = str(raw_url).rstrip("/")
        raw_token = token if token is not None else os.getenv("NOVAADAPT_SPINE_TOKEN", os.getenv("C3AE_API_TOKEN", ""))
        self.token = str(raw_token).strip() or None
        self.timeout_seconds = max(0.05, float(timeout_seconds))
        self.retry_after_seconds = max(1.0, float(retry_after_seconds))
        self.required = str(os.getenv("NOVAADAPT_MEMORY_REQUIRED", "0")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._available: bool | None = None
        self._last_error: str = ""
        self._next_probe_after = 0.0

    def status(self) -> dict[str, Any]:
        available = self._ensure_available()
        enabled = bool(available)
        ok = bool(available) if self.required else True
        payload: dict[str, Any] = {
            "ok": ok,
            "enabled": enabled,
            "backend": "novaspine-http",
            "base_url": self.base_url,
            "reachable": bool(available),
        }
        if self.required:
            payload["required"] = True
        if self.token:
            payload["token_configured"] = True
        if self._last_error:
            payload["error"] = self._last_error
        return payload

    def recall(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        if not str(query or "").strip():
            return []
        if not self._ensure_available():
            return []
        try:
            payload = self._request_json(
                "POST",
                "/api/v1/memory/recall",
                {
                    "query": str(query),
                    "top_k": max(1, int(top_k)),
                },
            )
        except Exception as exc:
            self._mark_unavailable(exc)
            return []
        memories = payload.get("memories")
        if not isinstance(memories, list):
            return []
        out: list[dict[str, Any]] = []
        for item in memories:
            if not isinstance(item, dict):
                continue
            out.append(
                {
                    "content": str(item.get("content", "")),
                    "score": float(item.get("score", 0.0) or 0.0),
                    "role": str(item.get("role", "")),
                    "session_id": str(item.get("session_id", "")),
                    "metadata": item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {},
                }
            )
        return out

    def augment(
        self,
        query: str,
        top_k: int = 5,
        *,
        min_score: float = 0.005,
        format_name: str = "xml",
    ) -> str:
        if not str(query or "").strip():
            return ""
        if not self._ensure_available():
            return ""
        try:
            payload = self._request_json(
                "POST",
                "/api/v1/memory/augment",
                {
                    "query": str(query),
                    "top_k": max(1, int(top_k)),
                    "min_score": max(0.0, float(min_score)),
                    "format": str(format_name or "xml"),
                    "roles": ["user", "assistant"],
                },
            )
        except Exception as exc:
            self._mark_unavailable(exc)
            return ""
        context = payload.get("context")
        return str(context or "")

    def ingest(
        self,
        text: str,
        *,
        source_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        body = str(text or "").strip()
        if not body:
            return None
        if not self._ensure_available():
            return None
        try:
            payload = self._request_json(
                "POST",
                "/api/v1/memory/ingest",
                {
                    "text": body,
                    "source_id": str(source_id or ""),
                    "metadata": metadata or {},
                },
            )
        except Exception as exc:
            self._mark_unavailable(exc)
            return None
        return payload

    def _ensure_available(self) -> bool:
        now = time.monotonic()
        if self._available is True:
            return True
        if self._available is False and now < self._next_probe_after:
            return False

        try:
            _ = self._request_json("GET", "/api/v1/health", None)
            self._available = True
            self._last_error = ""
            self._next_probe_after = 0.0
            return True
        except Exception as exc:
            self._mark_unavailable(exc)
            return False

    def _mark_unavailable(self, exc: Exception) -> None:
        self._available = False
        self._last_error = str(exc)
        self._next_probe_after = time.monotonic() + self.retry_after_seconds

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        headers = {"Accept": "application/json"}
        if payload is not None:
            raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        else:
            raw = None
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        req = request.Request(url=url, data=raw, method=method.upper(), headers=headers)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = ""
            code = int(exc.code)
            try:
                detail = exc.read().decode("utf-8", errors="ignore")
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
            raise RuntimeError(f"NovaSpine HTTP {code}: {detail}") from None
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
            raise RuntimeError(f"NovaSpine transport error: {reason}") from None

        if not body.strip():
            return {}
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("NovaSpine returned non-JSON payload") from exc
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}


def build_memory_backend() -> MemoryBackend:
    mode = str(os.getenv("NOVAADAPT_MEMORY_BACKEND", "novaspine-http")).strip().lower()
    if mode in {"", "off", "none", "noop", "disabled"}:
        return NoopMemoryBackend(reason="disabled by NOVAADAPT_MEMORY_BACKEND")
    if mode in {"novaspine-http", "spine-http", "auto"}:
        return NovaSpineHTTPMemoryBackend()
    return NoopMemoryBackend(reason=f"unsupported memory backend mode: {mode}")
