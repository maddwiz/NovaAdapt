from __future__ import annotations

import json
import secrets
import time
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
    max_retries: int = 1
    retry_backoff_seconds: float = 0.25

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

    def run(self, objective: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        body = {"objective": objective, **kwargs}
        payload = self._post_json("/run", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /run")

    def run_async(self, objective: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        body = {"objective": objective, **kwargs}
        payload = self._post_json("/run_async", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /run_async")

    def create_plan(self, objective: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        body = {"objective": objective, **kwargs}
        payload = self._post_json("/plans", body, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans")

    def plans(self, limit: int = 50) -> list[dict[str, Any]]:
        payload = self._get_json(f"/plans?limit={max(1, limit)}")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /plans")

    def plan(self, plan_id: str) -> dict[str, Any]:
        payload = self._get_json(f"/plans/{plan_id}")
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}")

    def approve_plan(self, plan_id: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/approve",
            kwargs,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}/approve")

    def approve_plan_async(self, plan_id: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/approve_async",
            kwargs,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}/approve_async")

    def reject_plan(
        self,
        plan_id: str,
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/reject",
            {"reason": reason} if reason is not None else {},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}/reject")

    def undo_plan(self, plan_id: str, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json(
            f"/plans/{plan_id}/undo",
            kwargs,
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /plans/{id}/undo")

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

    def job_stream(
        self,
        job_id: str,
        timeout_seconds: int = 30,
        interval_seconds: float = 0.25,
    ) -> list[dict[str, Any]]:
        timeout = max(1, int(timeout_seconds))
        interval = min(5.0, max(0.05, float(interval_seconds)))
        text = self._request_text(
            "GET",
            f"/jobs/{job_id}/stream?timeout={timeout}&interval={interval}",
        )

        events: list[dict[str, Any]] = []
        current_event = "message"
        for line in text.splitlines():
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip() or "message"
                continue
            if line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {"raw": raw}
                events.append({"event": current_event, "data": data})
                current_event = "message"
        return events

    def plan_stream(
        self,
        plan_id: str,
        timeout_seconds: int = 30,
        interval_seconds: float = 0.25,
    ) -> list[dict[str, Any]]:
        timeout = max(1, int(timeout_seconds))
        interval = min(5.0, max(0.05, float(interval_seconds)))
        text = self._request_text(
            "GET",
            f"/plans/{plan_id}/stream?timeout={timeout}&interval={interval}",
        )

        events: list[dict[str, Any]] = []
        current_event = "message"
        for line in text.splitlines():
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip() or "message"
                continue
            if line.startswith("data:"):
                raw = line.split(":", 1)[1].strip()
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = {"raw": raw}
                events.append({"event": current_event, "data": data})
                current_event = "message"
        return events

    def cancel_job(self, job_id: str, idempotency_key: str | None = None) -> dict[str, Any]:
        payload = self._post_json(
            f"/jobs/{job_id}/cancel",
            {},
            idempotency_key=idempotency_key,
        )
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /jobs/{id}/cancel")

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        payload = self._get_json(f"/history?limit={max(1, limit)}")
        if isinstance(payload, list):
            return payload
        raise APIClientError("Expected list payload from /history")

    def undo(self, idempotency_key: str | None = None, **kwargs: Any) -> dict[str, Any]:
        payload = self._post_json("/undo", kwargs, idempotency_key=idempotency_key)
        if isinstance(payload, dict):
            return payload
        raise APIClientError("Expected object payload from /undo")

    def metrics_text(self) -> str:
        return self._request_text("GET", "/metrics")

    def _get_json(self, path: str) -> Any:
        return self._request_json("GET", path, None)

    def _post_json(
        self,
        path: str,
        body: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> Any:
        return self._request_json("POST", path, body, idempotency_key=idempotency_key)

    def _request_json(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None,
        idempotency_key: str | None = None,
    ) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        raw = self._perform_request_with_retries(
            method=method,
            path=path,
            payload=payload,
            idempotency_key=idempotency_key,
        )

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise APIClientError("Expected JSON response") from exc

    def _request_text(self, method: str, path: str) -> str:
        return self._perform_request_with_retries(method=method, path=path, payload=None)

    def _perform_request_with_retries(
        self,
        method: str,
        path: str,
        payload: bytes | None,
        idempotency_key: str | None = None,
    ) -> str:
        attempts = max(0, int(self.max_retries)) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            req = self._build_request(
                method=method,
                path=path,
                payload=payload,
                idempotency_key=idempotency_key,
            )
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as response:
                    return response.read().decode("utf-8")
            except error.HTTPError as exc:
                body_text = exc.read().decode("utf-8", errors="ignore")
                last_error = APIClientError(f"HTTP {exc.code}: {body_text}")
                if not self._should_retry_http(exc.code) or attempt >= attempts - 1:
                    raise last_error from exc
            except error.URLError as exc:
                last_error = APIClientError(f"Request failed: {exc.reason}")
                if attempt >= attempts - 1:
                    raise last_error from exc

            if attempt < attempts - 1:
                backoff = max(0.0, float(self.retry_backoff_seconds)) * (2**attempt)
                if backoff:
                    time.sleep(backoff)

        raise APIClientError(str(last_error) if last_error else "Request failed")

    def _build_request(
        self,
        method: str,
        path: str,
        payload: bytes | None,
        idempotency_key: str | None = None,
    ) -> request.Request:
        url = f"{self.base_url.rstrip('/')}{path}"
        headers = {
            "Content-Type": "application/json",
            "X-Request-ID": secrets.token_hex(12),
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return request.Request(url=url, data=payload, headers=headers, method=method)

    @staticmethod
    def _should_retry_http(status_code: int) -> bool:
        return status_code in {408, 425, 429, 500, 502, 503, 504}
