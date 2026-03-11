from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


@dataclass(frozen=True)
class HomeAssistantExecutionResult:
    status: str
    output: str
    action: dict[str, Any]
    data: dict[str, Any] | None = None


class HomeAssistantExecutor:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        raw_base_url = base_url if base_url is not None else os.getenv("NOVAADAPT_HOMEASSISTANT_URL", "http://127.0.0.1:8123")
        self.base_url = str(raw_base_url).rstrip("/")
        raw_token = token if token is not None else os.getenv("NOVAADAPT_HOMEASSISTANT_TOKEN", "")
        self.token = str(raw_token).strip() or None
        self.timeout_seconds = max(1, int(timeout_seconds))

    def status(self) -> dict[str, Any]:
        try:
            payload = self._request_json("GET", "/api/", None)
            return {
                "ok": True,
                "transport": "homeassistant-http",
                "base_url": self.base_url,
                "response": payload,
            }
        except Exception as exc:
            return {
                "ok": False,
                "transport": "homeassistant-http",
                "base_url": self.base_url,
                "error": str(exc),
            }

    def discover(self, *, domain: str = "", entity_id_prefix: str = "", limit: int = 250) -> dict[str, Any]:
        payload = self._request_json("GET", "/api/states", None)
        if not isinstance(payload, list):
            payload = []
        normalized_domain = str(domain or "").strip().lower()
        normalized_prefix = str(entity_id_prefix or "").strip().lower()
        entities: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            entity_id = str(item.get("entity_id") or "").strip()
            if not entity_id:
                continue
            if normalized_domain and not entity_id.startswith(f"{normalized_domain}."):
                continue
            if normalized_prefix and not entity_id.lower().startswith(normalized_prefix):
                continue
            entities.append(
                {
                    "entity_id": entity_id,
                    "state": item.get("state"),
                    "attributes": item.get("attributes", {}) if isinstance(item.get("attributes"), dict) else {},
                }
            )
            if len(entities) >= max(1, int(limit)):
                break
        return {"ok": True, "count": len(entities), "entities": entities}

    def execute_action(self, action: dict[str, Any], *, dry_run: bool = True) -> HomeAssistantExecutionResult:
        action_type = str(action.get("type") or "").strip().lower()
        if action_type == "discover":
            result = self.discover(
                domain=str(action.get("domain") or ""),
                entity_id_prefix=str(action.get("entity_id_prefix") or action.get("target") or ""),
                limit=int(action.get("limit", 250) or 250),
            )
            return HomeAssistantExecutionResult(
                status="preview" if dry_run else "ok",
                output=f"discovered {result['count']} entities",
                action=action,
                data=result,
            )
        if action_type == "mqtt_publish":
            service_payload = {
                "topic": str(action.get("topic") or action.get("target") or "").strip(),
                "payload": str(action.get("payload") or action.get("value") or "").strip(),
                "qos": int(action.get("qos", 0) or 0),
                "retain": bool(action.get("retain", False)),
            }
            if not service_payload["topic"]:
                raise ValueError("mqtt_publish requires topic")
            if dry_run:
                return HomeAssistantExecutionResult(
                    status="preview",
                    output=f"Preview mqtt publish to {service_payload['topic']}",
                    action=action,
                    data=service_payload,
                )
            payload = self._request_json("POST", "/api/services/mqtt/publish", service_payload)
            return HomeAssistantExecutionResult(
                status="ok",
                output=f"published to {service_payload['topic']}",
                action=action,
                data={"response": payload},
            )
        if action_type != "ha_service":
            raise ValueError(f"unsupported Home Assistant action type '{action_type}'")

        domain = str(action.get("domain") or "").strip().lower()
        service = str(action.get("service") or "").strip().lower()
        entity_id = str(action.get("entity_id") or action.get("target") or "").strip()
        if not domain or not service:
            raise ValueError("ha_service requires domain and service")

        body: dict[str, Any] = {"entity_id": entity_id} if entity_id else {}
        extra = action.get("data")
        if isinstance(extra, dict):
            body.update(extra)
        for key in ("brightness", "temperature", "position", "speed", "message"):
            if action.get(key) is not None:
                body[key] = action.get(key)
        if dry_run:
            return HomeAssistantExecutionResult(
                status="preview",
                output=f"Preview Home Assistant service {domain}.{service}",
                action=action,
                data=body,
            )
        payload = self._request_json("POST", f"/api/services/{domain}/{service}", body)
        return HomeAssistantExecutionResult(
            status="ok",
            output=f"executed {domain}.{service}",
            action=action,
            data={"response": payload},
        )

    def _request_json(self, method: str, path: str, payload: dict[str, Any] | None) -> Any:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        raw: bytes | None = None
        if payload is not None:
            raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(url=f"{self.base_url}{path}", data=raw, headers=headers, method=method.upper())
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.HTTPError as exc:
            detail = ""
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
            raise RuntimeError(f"Home Assistant HTTP {int(exc.code)}: {detail}") from None
        except error.URLError as exc:
            reason = exc.reason
            close_fn = getattr(reason, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
            raise RuntimeError(f"Home Assistant transport error: {reason}") from None
        if not body.strip():
            return {}
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body.strip()
