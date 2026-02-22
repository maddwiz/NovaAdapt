from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from typing import Any
from urllib import error, request


class APIClientError(RuntimeError):
    pass


@dataclass
class NovaAdaptAPIClient:
    base_url: str
    token: str | None = None
    timeout_seconds: int = 30

    def health(self, deep: bool = False) -> dict[str, Any]:
        suffix = "/health?deep=1" if deep else "/health"
        return self._get_json(suffix)

    def openapi(self) -> dict[str, Any]:
        return self._get_json("/openapi.json")

    def models(self) -> list[dict[str, Any]]:
        payload = self._get_json("/models")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /models")

    def check(self, models: list[str] | None = None, probe: str = "Reply with: OK") -> Any:
        body = {"models": models or [], "probe": probe}
        return self._post_json("/check", body)

    def run(self, objective: str, **kwargs: Any) -> dict[str, Any]:
        body = {"objective": objective, **kwargs}
        payload = self._post_json("/run", body)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /run")

    def run_async(self, objective: str, **kwargs: Any) -> dict[str, Any]:
        body = {"objective": objective, **kwargs}
        payload = self._post_json("/run_async", body)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /run_async")

    def jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._get_json(f"/jobs?limit={max(1, limit)}")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /jobs")

    def job(self, job_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/jobs/{job_id}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /jobs/{id}")

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        payload = self._get_json(f"/history?limit={max(1, limit)}")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /history")

    def undo(self, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json("/undo", kwargs)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /undo")

    def metrics_text(self) -> str:
        return self._request_text("GET", "/metrics")

    def _get_json(self, path: str) -> Any:
        return self._request_json("GET", path, None)

    def _post_json(self, path: str, body: dict[str, Any]) -> Any:
        return self._request_json("POST", path, body)

    def _request_json(self, method: str, path: str, body: dict[str, Any] | None) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        req = self._build_request(method=method, path=path, payload=payload)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="ignore")
            raise APIClientError(f"HTTP {exc.code}: {body_text}") from exc
        except error.URLError as exc:
            raise APIClientError(f"Request failed: {exc.reason}") from exc

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise APIClientError("Expected JSON response") from exc

    def _request_text(self, method: str, path: str) -> str:
        req = self._build_request(method=method, path=path, payload=None)
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return response.read().decode("utf-8")
        except error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="ignore")
            raise APIClientError(f"HTTP {exc.code}: {body_text}") from exc
        except error.URLError as exc:
            raise APIClientError(f"Request failed: {exc.reason}") from exc

    def _build_request(self, method: str, path: str, payload: bytes | None) -> request.Request:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": secrets.token_hex(12),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return request.Request(url=url, data=payload, headers=headers, method=method)
