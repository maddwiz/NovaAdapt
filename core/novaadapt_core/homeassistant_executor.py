from __future__ import annotations

import json
import os
import socket
import ssl
from dataclasses import dataclass
from typing import Any
from urllib import error, request
from urllib.parse import urlparse


@dataclass(frozen=True)
class HomeAssistantExecutionResult:
    status: str
    output: str
    action: dict[str, Any]
    data: dict[str, Any] | None = None


class DirectMQTTExecutor:
    def __init__(
        self,
        *,
        broker_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        client_id: str | None = None,
        timeout_seconds: int = 10,
        keepalive_seconds: int = 30,
    ) -> None:
        self.broker_url = str(broker_url or os.getenv("NOVAADAPT_MQTT_BROKER_URL", "")).strip()
        self.username = str(username or os.getenv("NOVAADAPT_MQTT_USERNAME", "")).strip() or None
        self.password = str(password or os.getenv("NOVAADAPT_MQTT_PASSWORD", "")).strip() or None
        raw_client_id = client_id or os.getenv("NOVAADAPT_MQTT_CLIENT_ID", "")
        self.client_id = str(raw_client_id).strip() or "novaadapt"
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.keepalive_seconds = max(5, int(keepalive_seconds))

    def available(self) -> bool:
        return bool(self.broker_url)

    def status(self) -> dict[str, Any]:
        if not self.available():
            return {
                "ok": False,
                "configured": False,
                "transport": "mqtt-direct",
                "error": "NOVAADAPT_MQTT_BROKER_URL is not configured",
            }
        try:
            target = self._target()
            conn = self._connect()
            try:
                self._disconnect(conn)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
            return {
                "ok": True,
                "configured": True,
                "transport": "mqtt-direct",
                "broker_url": self.broker_url,
                "host": target["host"],
                "port": target["port"],
                "tls": target["tls"],
                "client_id": self.client_id,
            }
        except Exception as exc:
            return {
                "ok": False,
                "configured": True,
                "transport": "mqtt-direct",
                "broker_url": self.broker_url,
                "error": str(exc),
            }

    def publish(self, *, topic: str, payload: str, qos: int = 0, retain: bool = False) -> dict[str, Any]:
        normalized_topic = str(topic or "").strip()
        if not normalized_topic:
            raise ValueError("mqtt topic is required")
        normalized_qos = int(qos or 0)
        if normalized_qos != 0:
            raise ValueError("direct MQTT transport currently supports qos=0 only")
        encoded_payload = str(payload or "").encode("utf-8")
        conn = self._connect()
        try:
            header = 0x30 | (0x01 if retain else 0x00)
            body = self._encode_string(normalized_topic) + encoded_payload
            conn.sendall(bytes([header]) + self._encode_remaining_length(len(body)) + body)
            self._disconnect(conn)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        return {
            "transport": "mqtt-direct",
            "topic": normalized_topic,
            "payload_size": len(encoded_payload),
            "qos": normalized_qos,
            "retain": bool(retain),
        }

    def _connect(self):
        target = self._target()
        conn = socket.create_connection((target["host"], target["port"]), timeout=self.timeout_seconds)
        if target["tls"]:
            context = ssl.create_default_context()
            conn = context.wrap_socket(conn, server_hostname=target["host"])
        conn.settimeout(self.timeout_seconds)
        flags = 0x02
        if self.username:
            flags |= 0x80
        if self.password:
            flags |= 0x40
        payload = self._encode_string(self.client_id)
        if self.username:
            payload += self._encode_string(self.username)
        if self.password:
            payload += self._encode_string(self.password)
        variable = self._encode_string("MQTT") + bytes([0x04, flags]) + int(self.keepalive_seconds).to_bytes(2, "big")
        packet_body = variable + payload
        conn.sendall(b"\x10" + self._encode_remaining_length(len(packet_body)) + packet_body)
        packet_type = self._read_exact(conn, 1)[0]
        remaining = self._decode_remaining_length(conn)
        response = self._read_exact(conn, remaining)
        if packet_type != 0x20 or len(response) != 2:
            raise RuntimeError("invalid MQTT CONNACK from broker")
        return_code = response[1]
        if return_code != 0:
            raise RuntimeError(f"MQTT broker rejected connection with code {return_code}")
        return conn

    def _disconnect(self, conn) -> None:
        conn.sendall(b"\xe0\x00")

    def _target(self) -> dict[str, Any]:
        parsed = urlparse(self.broker_url or "")
        if parsed.scheme not in {"mqtt", "mqtts"}:
            raise ValueError("MQTT broker URL must use mqtt:// or mqtts://")
        if not parsed.hostname:
            raise ValueError("MQTT broker URL is missing a host")
        port = parsed.port or (8883 if parsed.scheme == "mqtts" else 1883)
        return {
            "host": parsed.hostname,
            "port": int(port),
            "tls": parsed.scheme == "mqtts",
        }

    @staticmethod
    def _encode_string(value: str) -> bytes:
        raw = str(value).encode("utf-8")
        return len(raw).to_bytes(2, "big") + raw

    @staticmethod
    def _encode_remaining_length(value: int) -> bytes:
        encoded = bytearray()
        remaining = int(value)
        while True:
            digit = remaining % 128
            remaining //= 128
            if remaining > 0:
                digit |= 0x80
            encoded.append(digit)
            if remaining == 0:
                break
        return bytes(encoded)

    @staticmethod
    def _decode_remaining_length(conn) -> int:
        multiplier = 1
        value = 0
        while True:
            digit = DirectMQTTExecutor._read_exact(conn, 1)[0]
            value += (digit & 0x7F) * multiplier
            if (digit & 0x80) == 0:
                return value
            multiplier *= 128
            if multiplier > 128 * 128 * 128:
                raise RuntimeError("invalid MQTT remaining length")

    @staticmethod
    def _read_exact(conn, size: int) -> bytes:
        buffer = bytearray()
        while len(buffer) < size:
            chunk = conn.recv(size - len(buffer))
            if not chunk:
                raise RuntimeError("unexpected EOF from MQTT broker")
            buffer.extend(chunk)
        return bytes(buffer)


class HomeAssistantExecutor:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        token: str | None = None,
        direct_mqtt_executor: DirectMQTTExecutor | None = None,
        timeout_seconds: int = 15,
    ) -> None:
        raw_base_url = base_url if base_url is not None else os.getenv("NOVAADAPT_HOMEASSISTANT_URL", "http://127.0.0.1:8123")
        self.base_url = str(raw_base_url).rstrip("/")
        raw_token = token if token is not None else os.getenv("NOVAADAPT_HOMEASSISTANT_TOKEN", "")
        self.token = str(raw_token).strip() or None
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.direct_mqtt_executor = direct_mqtt_executor or DirectMQTTExecutor(timeout_seconds=self.timeout_seconds)

    def status(self) -> dict[str, Any]:
        mqtt_status = self.direct_mqtt_executor.status()
        try:
            payload = self._request_json("GET", "/api/", None)
            return {
                "ok": True,
                "transport": "homeassistant-http",
                "base_url": self.base_url,
                "response": payload,
                "mqtt_direct": mqtt_status,
            }
        except Exception as exc:
            return {
                "ok": False,
                "transport": "homeassistant-http",
                "base_url": self.base_url,
                "error": str(exc),
                "mqtt_direct": mqtt_status,
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
            transport = str(action.get("transport") or "").strip().lower()
            service_payload = {
                "topic": str(action.get("topic") or action.get("target") or "").strip(),
                "payload": str(action.get("payload") or action.get("value") or "").strip(),
                "qos": int(action.get("qos", 0) or 0),
                "retain": bool(action.get("retain", False)),
            }
            if not service_payload["topic"]:
                raise ValueError("mqtt_publish requires topic")
            use_direct = transport in {"mqtt", "mqtt-direct"} or (
                not self.token and self.direct_mqtt_executor.available()
            )
            if dry_run:
                return HomeAssistantExecutionResult(
                    status="preview",
                    output=f"Preview mqtt publish to {service_payload['topic']}",
                    action=action,
                    data={
                        **service_payload,
                        "transport": "mqtt-direct" if use_direct else "homeassistant-http",
                    },
                )
            if use_direct:
                result = self.direct_mqtt_executor.publish(
                    topic=service_payload["topic"],
                    payload=service_payload["payload"],
                    qos=service_payload["qos"],
                    retain=service_payload["retain"],
                )
                return HomeAssistantExecutionResult(
                    status="ok",
                    output=f"published to {service_payload['topic']}",
                    action=action,
                    data=result,
                )
            payload = self._request_json("POST", "/api/services/mqtt/publish", service_payload)
            return HomeAssistantExecutionResult(
                status="ok",
                output=f"published to {service_payload['topic']}",
                action=action,
                data={"transport": "homeassistant-http", "response": payload},
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
