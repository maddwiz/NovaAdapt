from __future__ import annotations

import ipaddress
import json
import logging
import secrets
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, parse_qsl, urlencode, urlparse

from .audit_store import AuditStore
from .idempotency_store import IdempotencyStore
from .jobs import JobManager
from .observability import start_span
from .server_routes import (
    build_get_dynamic_routes,
    build_get_private_routes,
    build_get_public_routes,
    build_post_dynamic_routes,
    build_post_exact_routes,
    is_idempotent_route,
)
from .service import NovaAdaptService
from .terminal import TerminalSessionManager
from . import server_terminal_browser as terminal_browser_routes
from . import server_plan_job_routes as plan_job_routes
from . import server_run_memory_routes as run_memory_routes
from . import server_admin_routes as admin_routes
from . import server_adapt_routes as adapt_routes
from . import server_memory_routes as memory_routes
from . import server_novaprime_routes as novaprime_routes
from . import server_sib_routes as sib_routes
from . import server_plugin_routes as plugin_routes
from . import server_idempotency_utils as idempotency_utils
from . import server_stream_utils as stream_utils

SENSITIVE_QUERY_KEYS = {
    "token",
    "access_token",
    "api_token",
    "api_key",
    "apikey",
    "authorization",
    "auth",
    "session_token",
}


class PayloadTooLargeError(ValueError):
    pass


IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


def _build_handler(
    service: NovaAdaptService,
    api_token: str | None,
    job_manager: JobManager,
    log_requests: bool,
    logger: logging.Logger,
    limiter: _PerClientSlidingWindowRateLimiter | None,
    trusted_proxy_networks: list[IPNetwork],
    idempotency_store: IdempotencyStore | None,
    audit_store: AuditStore | None,
    terminal_manager: TerminalSessionManager,
    metrics: _RequestMetrics,
    max_request_body_bytes: int,
):
    class Handler(BaseHTTPRequestHandler):
        _request_id: str

        def do_GET(self) -> None:
            started = time.perf_counter()
            self._request_id = _normalize_request_id(self.headers.get("X-Request-ID"))
            status_code = 500
            metrics.inc("requests_total")
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            with start_span(
                "core.http.get",
                attributes={
                    "http.method": "GET",
                    "http.path": path,
                    "http.request_id": self._request_id,
                },
            ) as span:
                try:
                    status_code = self._dispatch_get(path, query)
                except ValueError as exc:
                    status_code = 400
                    metrics.inc("bad_request_total")
                    self._send_json(status_code, {"error": str(exc)})
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    status_code = 500
                    metrics.inc("server_errors_total")
                    self._send_json(status_code, {"error": str(exc)})
                finally:
                    if span is not None:
                        span.set_attribute("http.status_code", int(status_code))
                    self._log_request(status_code, started)

        def do_POST(self) -> None:
            started = time.perf_counter()
            self._request_id = _normalize_request_id(self.headers.get("X-Request-ID"))
            status_code = 500
            metrics.inc("requests_total")
            parsed = urlparse(self.path)
            path = parsed.path

            with start_span(
                "core.http.post",
                attributes={
                    "http.method": "POST",
                    "http.path": path,
                    "http.request_id": self._request_id,
                },
            ) as span:
                try:
                    status_code = self._dispatch_post(path)
                except PayloadTooLargeError as exc:
                    status_code = 413
                    metrics.inc("bad_request_total")
                    self._send_json(status_code, {"error": str(exc)})
                except ValueError as exc:
                    status_code = 400
                    metrics.inc("bad_request_total")
                    self._send_json(status_code, {"error": str(exc)})
                except Exception as exc:  # pragma: no cover - defensive server boundary
                    status_code = 500
                    metrics.inc("server_errors_total")
                    self._send_json(status_code, {"error": str(exc)})
                finally:
                    if span is not None:
                        span.set_attribute("http.status_code", int(status_code))
                    self._log_request(status_code, started)

        def _dispatch_get(self, path: str, query: dict[str, list[str]]) -> int:
            handler = build_get_public_routes(self).get(path)
            if handler is not None:
                return int(handler(query))

            if self._is_rate_limited(path):
                metrics.inc("rate_limited_total")
                self._send_json(429, {"error": "Rate limit exceeded"})
                return 429

            if not self._check_auth(path, query):
                return 401

            handler = build_get_private_routes(self).get(path)
            if handler is not None:
                return int(handler(query))

            for prefix, suffix, route_handler in build_get_dynamic_routes(self):
                if path.startswith(prefix) and (suffix == "" or path.endswith(suffix)):
                    return int(route_handler(path, query))

            self._send_json(404, {"error": "Not found"})
            return 404

        def _dispatch_post(self, path: str) -> int:
            if self._is_rate_limited(path):
                metrics.inc("rate_limited_total")
                self._send_json(429, {"error": "Rate limit exceeded"})
                return 429

            if not self._check_auth(path):
                return 401

            payload = self._read_json_body()

            handler = build_post_exact_routes(self).get(path)
            if handler is not None:
                return int(handler(payload))

            for prefix, suffix, route_handler in build_post_dynamic_routes(self):
                if path.startswith(prefix) and path.endswith(suffix):
                    return int(route_handler(path, payload))

            self._send_json(404, {"error": "Not found"})
            return 404

        def _get_health(self, query: dict[str, list[str]]) -> int:
            return admin_routes.get_health(
                self,
                service,
                audit_store,
                metrics,
                _single,
                _to_path,
                query,
            )

        def _get_dashboard(self, query: dict[str, list[str]]) -> int:
            return admin_routes.get_dashboard(self, query)

        def _get_dashboard_data(self, query: dict[str, list[str]]) -> int:
            return admin_routes.get_dashboard_data(
                self,
                service,
                job_manager,
                audit_store,
                metrics,
                _single,
                _to_path,
                query,
            )

        def _get_openapi(self, _query: dict[str, list[str]]) -> int:
            return admin_routes.get_openapi(self)

        def _get_metrics(self, query: dict[str, list[str]]) -> int:
            return admin_routes.get_metrics(self, query)

        def _get_events(self, query: dict[str, list[str]]) -> int:
            return admin_routes.get_events(self, audit_store, _single, query)

        def _get_events_stream(self, query: dict[str, list[str]]) -> int:
            return admin_routes.get_events_stream(self, _single, query)

        def _get_models(self, query: dict[str, list[str]]) -> int:
            config = _single(query, "config")
            self._send_json(200, service.models(config_path=_to_path(config)))
            return 200

        def _get_history(self, query: dict[str, list[str]]) -> int:
            limit = int(_single(query, "limit") or 20)
            self._send_json(200, service.history(limit=limit))
            return 200

        def _get_jobs(self, query: dict[str, list[str]]) -> int:
            return plan_job_routes.get_jobs(self, job_manager, _single, query)

        def _get_job_stream(self, path: str, query: dict[str, list[str]]) -> int:
            return plan_job_routes.get_job_stream(self, _single, path, query)

        def _get_job_item(self, path: str, _query: dict[str, list[str]]) -> int:
            return plan_job_routes.get_job_item(self, job_manager, path)

        def _get_plans(self, query: dict[str, list[str]]) -> int:
            return plan_job_routes.get_plans(self, service, _single, query)

        def _get_plugins(self, _query: dict[str, list[str]]) -> int:
            return plugin_routes.get_plugins(self, service)

        def _get_memory_status(self, _query: dict[str, list[str]]) -> int:
            return memory_routes.get_memory_status(self, service)

        def _get_novaprime_status(self, _query: dict[str, list[str]]) -> int:
            return novaprime_routes.get_novaprime_status(self, service)

        def _get_sib_status(self, _query: dict[str, list[str]]) -> int:
            return sib_routes.get_sib_status(self, service)

        def _get_adapt_toggle(self, query: dict[str, list[str]]) -> int:
            return adapt_routes.get_adapt_toggle(self, service, _single, query)

        def _get_adapt_bond(self, query: dict[str, list[str]]) -> int:
            return adapt_routes.get_adapt_bond(self, service, _single, query)

        def _get_browser_status(self, _query: dict[str, list[str]]) -> int:
            return terminal_browser_routes.get_browser_status(self, service)

        def _get_browser_pages(self, _query: dict[str, list[str]]) -> int:
            return terminal_browser_routes.get_browser_pages(self, service)

        def _get_plugin_health(self, path: str, _query: dict[str, list[str]]) -> int:
            return plugin_routes.get_plugin_health(self, service, path)

        def _get_terminal_sessions(self, _query: dict[str, list[str]]) -> int:
            return terminal_browser_routes.get_terminal_sessions(self, terminal_manager)

        def _get_terminal_session_item(self, path: str, _query: dict[str, list[str]]) -> int:
            return terminal_browser_routes.get_terminal_session_item(self, terminal_manager, path)

        def _get_terminal_output(self, path: str, query: dict[str, list[str]]) -> int:
            return terminal_browser_routes.get_terminal_output(self, terminal_manager, _single, path, query)

        def _get_plan_stream(self, path: str, query: dict[str, list[str]]) -> int:
            return plan_job_routes.get_plan_stream(self, _single, path, query)

        def _get_plan_item(self, path: str, _query: dict[str, list[str]]) -> int:
            return plan_job_routes.get_plan_item(self, service, path)

        def _post_cancel_job(self, path: str, payload: dict[str, object]) -> int:
            return plan_job_routes.post_cancel_job(self, path, payload)

        def _post_create_plan(self, path: str, payload: dict[str, object]) -> int:
            return self._respond_idempotent(
                path=path,
                payload=payload,
                operation=lambda: (201, service.create_plan(payload)),
                category="plans",
                action="create",
                entity_type="plan",
                entity_id_key="id",
            )

        def _post_plan_approve(self, path: str, payload: dict[str, object]) -> int:
            return plan_job_routes.post_plan_approve(self, service, path, payload)

        def _post_plan_approve_async(self, path: str, payload: dict[str, object]) -> int:
            return plan_job_routes.post_plan_approve_async(self, service, job_manager, path, payload)

        def _post_plan_retry_failed(self, path: str, payload: dict[str, object]) -> int:
            return plan_job_routes.post_plan_retry_failed(self, service, path, payload)

        def _post_plan_retry_failed_async(self, path: str, payload: dict[str, object]) -> int:
            return plan_job_routes.post_plan_retry_failed_async(self, service, job_manager, path, payload)

        def _post_plan_reject(self, path: str, payload: dict[str, object]) -> int:
            return plan_job_routes.post_plan_reject(self, service, path, payload)

        def _post_plan_undo(self, path: str, payload: dict[str, object]) -> int:
            return plan_job_routes.post_plan_undo(self, service, path, payload)

        def _post_run(self, path: str, payload: dict[str, object]) -> int:
            return run_memory_routes.post_run(self, service, path, payload)

        def _post_run_async(self, path: str, payload: dict[str, object]) -> int:
            return run_memory_routes.post_run_async(self, service, job_manager, path, payload)

        def _post_swarm_run(self, path: str, payload: dict[str, object]) -> int:
            return run_memory_routes.post_swarm_run(self, service, job_manager, path, payload)

        def _post_undo(self, path: str, payload: dict[str, object]) -> int:
            return run_memory_routes.post_undo(self, service, path, payload)

        def _post_check(self, payload: dict[str, object]) -> int:
            return run_memory_routes.post_check(self, service, _parse_name_list, _to_path, payload)

        def _post_plugin_call(self, path: str, payload: dict[str, object]) -> int:
            return plugin_routes.post_plugin_call(self, service, path, payload)

        def _post_feedback(self, path: str, payload: dict[str, object]) -> int:
            return run_memory_routes.post_feedback(self, service, path, payload)

        def _post_sib_realm(self, _path: str, payload: dict[str, object]) -> int:
            return sib_routes.post_sib_realm(self, service, payload)

        def _post_sib_companion_state(self, _path: str, payload: dict[str, object]) -> int:
            return sib_routes.post_sib_companion_state(self, service, payload)

        def _post_sib_companion_speak(self, _path: str, payload: dict[str, object]) -> int:
            return sib_routes.post_sib_companion_speak(self, service, payload)

        def _post_sib_phase_event(self, _path: str, payload: dict[str, object]) -> int:
            return sib_routes.post_sib_phase_event(self, service, payload)

        def _post_sib_resonance_start(self, _path: str, payload: dict[str, object]) -> int:
            return sib_routes.post_sib_resonance_start(self, service, payload)

        def _post_sib_resonance_result(self, _path: str, payload: dict[str, object]) -> int:
            return sib_routes.post_sib_resonance_result(self, service, payload)

        def _post_memory_recall(self, _path: str, payload: dict[str, object]) -> int:
            return memory_routes.post_memory_recall(self, service, payload)

        def _post_adapt_toggle(self, _path: str, payload: dict[str, object]) -> int:
            return adapt_routes.post_adapt_toggle(self, service, payload)

        def _post_memory_ingest(self, path: str, payload: dict[str, object]) -> int:
            return memory_routes.post_memory_ingest(self, service, path, payload)

        def _post_terminal_start(self, path: str, payload: dict[str, object]) -> int:
            return terminal_browser_routes.post_terminal_start(self, terminal_manager, path, payload)

        def _post_terminal_input(self, path: str, payload: dict[str, object]) -> int:
            return terminal_browser_routes.post_terminal_input(self, terminal_manager, path, payload)

        def _post_terminal_close(self, path: str, payload: dict[str, object]) -> int:
            return terminal_browser_routes.post_terminal_close(self, terminal_manager, path, payload)

        def _post_browser_action(self, path: str, payload: dict[str, object]) -> int:
            return terminal_browser_routes.post_browser_action(self, service, path, payload)

        def _post_browser_navigate(self, path: str, payload: dict[str, object]) -> int:
            return terminal_browser_routes.post_browser_navigate(self, service, path, payload)

        def _post_browser_click(self, path: str, payload: dict[str, object]) -> int:
            return self._post_browser_typed_action(path, payload, action_type="click_selector")

        def _post_browser_fill(self, path: str, payload: dict[str, object]) -> int:
            return self._post_browser_typed_action(path, payload, action_type="fill")

        def _post_browser_extract_text(self, path: str, payload: dict[str, object]) -> int:
            return self._post_browser_typed_action(path, payload, action_type="extract_text")

        def _post_browser_screenshot(self, path: str, payload: dict[str, object]) -> int:
            return self._post_browser_typed_action(path, payload, action_type="screenshot")

        def _post_browser_wait_for_selector(self, path: str, payload: dict[str, object]) -> int:
            return self._post_browser_typed_action(path, payload, action_type="wait_for_selector")

        def _post_browser_evaluate_js(self, path: str, payload: dict[str, object]) -> int:
            return self._post_browser_typed_action(path, payload, action_type="evaluate_js")

        def _post_browser_close(self, path: str, payload: dict[str, object]) -> int:
            return terminal_browser_routes.post_browser_close(self, service, path, payload)

        def _post_browser_typed_action(
            self,
            path: str,
            payload: dict[str, object],
            *,
            action_type: str,
        ) -> int:
            return terminal_browser_routes.post_browser_typed_action(
                self,
                service,
                path,
                payload,
                action_type=action_type,
            )

        def _respond_idempotent(
            self,
            *,
            path: str,
            payload: dict[str, object],
            operation,
            category: str,
            action: str,
            entity_type: str | None = None,
            entity_id: str | None = None,
            entity_id_key: str | None = None,
        ) -> int:
            return idempotency_utils.respond_idempotent(
                self,
                idempotency_store=idempotency_store,
                is_idempotent_route=is_idempotent_route,
                path=path,
                payload=payload,
                operation=operation,
                category=category,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                entity_id_key=entity_id_key,
            )


        def _is_rate_limited(self, path: str) -> bool:
            if limiter is None:
                return False
            if path in {"/health", "/metrics"}:
                return False
            return not limiter.allow(self._rate_limit_client_key())

        def _rate_limit_client_key(self) -> str:
            remote_ip = _parse_ip_token(self.client_address[0] if self.client_address else "")
            if remote_ip is not None and _ip_in_networks(remote_ip, trusted_proxy_networks):
                forwarded = _first_forwarded_ip(self.headers.get("X-Forwarded-For", ""))
                if forwarded is not None:
                    return str(forwarded)
            if remote_ip is not None:
                return str(remote_ip)
            remote_host = self.client_address[0] if self.client_address else ""
            remote_host = str(remote_host or "").strip()
            return remote_host or "unknown"

        def _check_auth(self, path: str, query: dict[str, list[str]] | None = None) -> bool:
            if path == "/health" or not api_token:
                return True
            if query is not None and path in {"/dashboard", "/dashboard/data"}:
                query_token = _single(query, "token")
                if query_token == api_token:
                    return True
            auth_header = self.headers.get("Authorization", "")
            expected = f"Bearer {api_token}"
            if auth_header == expected:
                return True
            metrics.inc("unauthorized_total")
            self._send_json(401, {"error": "Unauthorized"}, unauthorized=True)
            return False

        def _read_json_body(self) -> dict:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length > max_request_body_bytes:
                raise PayloadTooLargeError("Request body too large")
            if content_length <= 0:
                return {}

            raw = self.rfile.read(min(content_length, max_request_body_bytes + 1)).decode("utf-8")
            if len(raw.encode("utf-8")) > max_request_body_bytes:
                raise PayloadTooLargeError("Request body too large")
            if not raw.strip():
                return {}
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
            raise ValueError("Request JSON body must be an object")

        def _send_json(
            self,
            status_code: int,
            payload: object,
            unauthorized: bool = False,
            replayed: bool = False,
            idempotency_key: str | None = None,
        ) -> None:
            if isinstance(payload, dict):
                payload = dict(payload)
                payload.setdefault("request_id", self._request_id)
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Request-ID", self._request_id)
            if replayed:
                self.send_header("X-Idempotency-Replayed", "true")
            if idempotency_key:
                self.send_header("Idempotency-Key", idempotency_key)
            if unauthorized:
                self.send_header("WWW-Authenticate", "Bearer")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_metrics(self, status_code: int) -> None:
            encoded = metrics.render().encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("X-Request-ID", self._request_id)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_html(self, status_code: int, html: str) -> None:
            encoded = html.encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("X-Request-ID", self._request_id)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _cancel_job(self, job_id: str) -> tuple[int, object]:
            canceled = job_manager.cancel(job_id)
            if canceled is None:
                return 404, {"error": "Job not found"}
            return 200, canceled

        def _idempotency_key(self) -> str | None:
            return idempotency_utils.idempotency_key(self)

        def _execute_idempotent(
            self,
            path: str,
            payload: dict[str, object],
            operation,
        ) -> tuple[int, object, bool]:
            return idempotency_utils.execute_idempotent(
                self,
                idempotency_store=idempotency_store,
                is_idempotent_route=is_idempotent_route,
                path=path,
                payload=payload,
                operation=operation,
            )

        def _stream_job_events(self, job_id: str, timeout_seconds: float, interval_seconds: float) -> None:
            return stream_utils.stream_job_events(
                self,
                job_manager,
                job_id,
                timeout_seconds,
                interval_seconds,
            )

        def _stream_plan_events(self, plan_id: str, timeout_seconds: float, interval_seconds: float) -> None:
            return stream_utils.stream_plan_events(
                self,
                service,
                plan_id,
                timeout_seconds,
                interval_seconds,
            )

        def _stream_audit_events(self, timeout_seconds: float, interval_seconds: float, since_id: int) -> None:
            return stream_utils.stream_audit_events(
                self,
                audit_store,
                timeout_seconds,
                interval_seconds,
                since_id,
            )

        def _audit_event(
            self,
            *,
            category: str,
            action: str,
            status: str,
            entity_type: str | None = None,
            entity_id: str | None = None,
            payload: dict[str, object] | None = None,
        ) -> None:
            return stream_utils.audit_event(
                audit_store=audit_store,
                logger=logger,
                request_id=self._request_id,
                category=category,
                action=action,
                status=status,
                entity_type=entity_type,
                entity_id=entity_id,
                payload=payload,
            )

        def _write_sse_event(self, event: str, payload: dict[str, object]) -> bool:
            return stream_utils.write_sse_event(self, event, payload)

        def _log_request(self, status_code: int, started: float) -> None:
            if not log_requests:
                return
            duration_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "core request id=%s method=%s path=%s status=%s duration_ms=%.2f",
                self._request_id,
                self.command,
                _redact_path_for_logs(self.path),
                status_code,
                duration_ms,
            )

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


def _single(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _to_path(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str) and value.strip():
        from pathlib import Path

        return Path(value)
    return None


def _normalize_request_id(value: str | None) -> str:
    if value and value.strip():
        return value.strip()
    return secrets.token_hex(12)


def _parse_trusted_proxy_cidrs(values: list[str]) -> list[IPNetwork]:
    networks: list[IPNetwork] = []
    for raw in values:
        item = str(raw).strip()
        if not item:
            continue
        try:
            if "/" in item:
                network = ipaddress.ip_network(item, strict=False)
            else:
                ip = ipaddress.ip_address(item)
                suffix = 32 if isinstance(ip, ipaddress.IPv4Address) else 128
                network = ipaddress.ip_network(f"{ip}/{suffix}", strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid trusted proxy CIDR/IP: {item}") from exc
        networks.append(network)
    return networks


def _ip_in_networks(ip: IPAddress, networks: list[IPNetwork]) -> bool:
    return any(ip in network for network in networks)


def _first_forwarded_ip(value: str) -> IPAddress | None:
    for token in str(value).split(","):
        parsed = _parse_ip_token(token)
        if parsed is not None:
            return parsed
    return None


def _parse_ip_token(value: str) -> IPAddress | None:
    token = str(value or "").strip()
    if not token:
        return None
    if token.startswith("[") and "]" in token:
        token = token[1 : token.find("]")]
    elif token.count(":") == 1 and "." in token:
        host, port = token.rsplit(":", 1)
        if port.isdigit():
            token = host
    try:
        return ipaddress.ip_address(token)
    except ValueError:
        return None


def _redact_path_for_logs(raw_path: str) -> str:
    parsed = urlparse(raw_path)
    if not parsed.query:
        return parsed.path or raw_path
    redacted_pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        if key.lower() in SENSITIVE_QUERY_KEYS:
            redacted_pairs.append((key, "redacted"))
        else:
            redacted_pairs.append((key, value))
    redacted_query = urlencode(redacted_pairs, doseq=True)
    if not redacted_query:
        return parsed.path or raw_path
    return f"{parsed.path}?{redacted_query}"
