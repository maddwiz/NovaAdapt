from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


_SUPPORTED_HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


@dataclass(frozen=True)
class PluginConfig:
    name: str
    base_url: str
    headers: dict[str, str]
    health_paths: tuple[str, ...]


class PluginRegistry:
    def __init__(self, plugins: dict[str, PluginConfig], timeout_seconds: int = 20, max_response_bytes: int = 2 << 20) -> None:
        self._plugins = plugins
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_response_bytes = max(1024, int(max_response_bytes))

    def list_plugins(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for name in sorted(self._plugins.keys()):
            cfg = self._plugins[name]
            items.append(
                {
                    "name": cfg.name,
                    "base_url": cfg.base_url,
                    "health_paths": list(cfg.health_paths),
                    "auth_headers": sorted(cfg.headers.keys()),
                }
            )
        return items

    def health(self, plugin_name: str) -> dict[str, Any]:
        cfg = self._get_plugin(plugin_name)
        for health_path in cfg.health_paths:
            result = self._request(cfg, method="GET", route=health_path, payload=None)
            if bool(result.get("ok", False)):
                return result
        last = self._request(
            cfg,
            method="GET",
            route=cfg.health_paths[-1] if cfg.health_paths else "/health",
            payload=None,
        )
        return last

    def call(
        self,
        plugin_name: str,
        *,
        route: str,
        payload: dict[str, Any] | None = None,
        method: str = "POST",
    ) -> dict[str, Any]:
        cfg = self._get_plugin(plugin_name)
        return self._request(cfg, method=method, route=route, payload=payload)

    def _get_plugin(self, plugin_name: str) -> PluginConfig:
        normalized = str(plugin_name or "").strip().lower()
        if not normalized:
            raise ValueError("'plugin' is required")
        cfg = self._plugins.get(normalized)
        if cfg is None:
            supported = ", ".join(sorted(self._plugins.keys()))
            raise ValueError(f"Unknown plugin '{plugin_name}'. Supported: {supported}")
        return cfg

    def _request(
        self,
        cfg: PluginConfig,
        *,
        method: str,
        route: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        normalized_method = str(method or "GET").strip().upper()
        if normalized_method not in _SUPPORTED_HTTP_METHODS:
            raise ValueError(f"Unsupported plugin HTTP method '{method}'")

        route = str(route or "").strip()
        if not route.startswith("/"):
            raise ValueError("Plugin route must start with '/'")

        url = f"{cfg.base_url.rstrip('/')}{route}"
        body: bytes | None = None
        headers = dict(cfg.headers)
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))

        req = request.Request(url=url, data=body, headers=headers, method=normalized_method)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                status = int(resp.status)
                raw = resp.read(self.max_response_bytes + 1)
                truncated = len(raw) > self.max_response_bytes
                if truncated:
                    raw = raw[: self.max_response_bytes]
                parsed_body = _parse_body(raw)
                output: dict[str, Any] = {
                    "ok": 200 <= status < 400,
                    "plugin": cfg.name,
                    "base_url": cfg.base_url,
                    "route": route,
                    "method": normalized_method,
                    "status_code": status,
                    "response": parsed_body,
                }
                if truncated:
                    output["response_truncated"] = True
                return output
        except error.HTTPError as exc:
            try:
                raw = exc.read(self.max_response_bytes + 1)
            finally:
                try:
                    exc.close()
                except Exception:
                    pass
            truncated = len(raw) > self.max_response_bytes
            if truncated:
                raw = raw[: self.max_response_bytes]
            parsed_body = _parse_body(raw)
            output = {
                "ok": False,
                "plugin": cfg.name,
                "base_url": cfg.base_url,
                "route": route,
                "method": normalized_method,
                "status_code": int(exc.code),
                "response": parsed_body,
                "error": f"HTTP {exc.code}",
            }
            if truncated:
                output["response_truncated"] = True
            return output
        except error.URLError as exc:
            reason = exc.reason
            close_fn = getattr(reason, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            return {
                "ok": False,
                "plugin": cfg.name,
                "base_url": cfg.base_url,
                "route": route,
                "method": normalized_method,
                "status_code": 0,
                "error": f"transport error: {exc.reason}",
            }


def build_plugin_registry() -> PluginRegistry:
    plugin_timeout = int(os.getenv("NOVAADAPT_PLUGIN_TIMEOUT_SECONDS", "20"))
    max_response_bytes = int(os.getenv("NOVAADAPT_PLUGIN_MAX_RESPONSE_BYTES", str(2 << 20)))

    novabridge_base = str(os.getenv("NOVAADAPT_NOVABRIDGE_URL", "http://127.0.0.1:30010/nova")).strip()
    novabridge_headers = _build_headers(
        {
            "X-API-Key": os.getenv("NOVABRIDGE_API_KEY"),
            "X-NovaBridge-Token": os.getenv("NOVABRIDGE_RUNTIME_TOKEN"),
            "X-NovaBridge-Role": os.getenv("NOVABRIDGE_ROLE"),
        }
    )

    nova4d_base = str(os.getenv("NOVAADAPT_NOVA4D_URL", novabridge_base)).strip()
    nova4d_headers = _build_headers(
        {
            "X-API-Key": os.getenv("NOVA4D_API_KEY") or os.getenv("NOVABRIDGE_API_KEY"),
            "X-NovaBridge-Token": os.getenv("NOVA4D_RUNTIME_TOKEN") or os.getenv("NOVABRIDGE_RUNTIME_TOKEN"),
            "X-NovaBridge-Role": os.getenv("NOVA4D_ROLE") or os.getenv("NOVABRIDGE_ROLE"),
        }
    )

    novablox_base = str(os.getenv("NOVAADAPT_NOVABLOX_URL", "http://127.0.0.1:30010/bridge")).strip()
    novablox_headers = _build_headers({"X-API-Key": os.getenv("NOVABLOX_API_KEY")})

    plugins = {
        "novabridge": PluginConfig(
            name="novabridge",
            base_url=novabridge_base,
            headers=novabridge_headers,
            health_paths=("/health", "/caps"),
        ),
        "nova4d": PluginConfig(
            name="nova4d",
            base_url=nova4d_base,
            headers=nova4d_headers,
            health_paths=("/health", "/caps"),
        ),
        "novablox": PluginConfig(
            name="novablox",
            base_url=novablox_base,
            headers=novablox_headers,
            health_paths=("/health", "/stats"),
        ),
    }
    return PluginRegistry(
        plugins=plugins,
        timeout_seconds=plugin_timeout,
        max_response_bytes=max_response_bytes,
    )


def _build_headers(values: dict[str, str | None]) -> dict[str, str]:
    output: dict[str, str] = {}
    for key, value in values.items():
        text = str(value or "").strip()
        if text:
            output[key] = text
    return output


def _parse_body(raw: bytes) -> Any:
    if not raw:
        return {}
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text
