from __future__ import annotations

import json
import logging
import secrets
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .jobs import JobManager
from .service import NovaAdaptService


class NovaAdaptHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls, job_manager: JobManager):
        super().__init__(server_address, handler_cls)
        self.job_manager = job_manager

    def server_close(self) -> None:
        self.job_manager.shutdown(wait=True)
        super().server_close()


def create_server(
    host: str,
    port: int,
    service: NovaAdaptService,
    api_token: str | None = None,
    job_manager: JobManager | None = None,
    log_requests: bool = False,
    logger: logging.Logger | None = None,
) -> ThreadingHTTPServer:
    managed_jobs = job_manager or JobManager()
    handler_cls = _build_handler(
        service=service,
        api_token=api_token,
        job_manager=managed_jobs,
        log_requests=log_requests,
        logger=logger or logging.getLogger("novaadapt.api"),
    )
    return NovaAdaptHTTPServer((host, port), handler_cls, managed_jobs)


def run_server(
    host: str,
    port: int,
    service: NovaAdaptService,
    api_token: str | None = None,
    log_requests: bool = False,
    logger: logging.Logger | None = None,
) -> None:
    server = create_server(
        host=host,
        port=port,
        service=service,
        api_token=api_token,
        log_requests=log_requests,
        logger=logger,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_handler(
    service: NovaAdaptService,
    api_token: str | None,
    job_manager: JobManager,
    log_requests: bool,
    logger: logging.Logger,
):
    class Handler(BaseHTTPRequestHandler):
        _request_id: str

        def do_GET(self) -> None:
            started = time.perf_counter()
            self._request_id = _normalize_request_id(self.headers.get("X-Request-ID"))
            status_code = 500
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            try:
                if path == "/health":
                    status_code = 200
                    self._send_json(status_code, {"ok": True, "service": "novaadapt"})
                    return

                if not self._check_auth(path):
                    status_code = 401
                    return

                if path == "/models":
                    config = _single(query, "config")
                    out = service.models(config_path=_to_path(config))
                    status_code = 200
                    self._send_json(status_code, out)
                    return

                if path == "/history":
                    limit = int(_single(query, "limit") or 20)
                    status_code = 200
                    self._send_json(status_code, service.history(limit=limit))
                    return

                if path == "/jobs":
                    limit = int(_single(query, "limit") or 50)
                    status_code = 200
                    self._send_json(status_code, job_manager.list(limit=limit))
                    return

                if path.startswith("/jobs/"):
                    job_id = path.removeprefix("/jobs/").strip()
                    if not job_id:
                        status_code = 404
                        self._send_json(status_code, {"error": "Not found"})
                        return
                    item = job_manager.get(job_id)
                    if item is None:
                        status_code = 404
                        self._send_json(status_code, {"error": "Job not found"})
                        return
                    status_code = 200
                    self._send_json(status_code, item)
                    return

                status_code = 404
                self._send_json(status_code, {"error": "Not found"})
            except ValueError as exc:
                status_code = 400
                self._send_json(status_code, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive server boundary
                status_code = 500
                self._send_json(status_code, {"error": str(exc)})
            finally:
                self._log_request(status_code, started)

        def do_POST(self) -> None:
            started = time.perf_counter()
            self._request_id = _normalize_request_id(self.headers.get("X-Request-ID"))
            status_code = 500
            parsed = urlparse(self.path)
            path = parsed.path

            if not self._check_auth(path):
                status_code = 401
                self._log_request(status_code, started)
                return

            try:
                payload = self._read_json_body()

                if path == "/run":
                    status_code = 200
                    self._send_json(status_code, service.run(payload))
                    return

                if path == "/run_async":
                    job_id = job_manager.submit(service.run, payload)
                    status_code = 202
                    self._send_json(status_code, {"job_id": job_id, "status": "queued"})
                    return

                if path == "/undo":
                    status_code = 200
                    self._send_json(status_code, service.undo(payload))
                    return

                if path == "/check":
                    config = _to_path(payload.get("config"))
                    models = payload.get("models")
                    probe = str(payload.get("probe", "Reply with: OK"))
                    out = service.check(config_path=config, model_names=service._as_name_list(models), probe_prompt=probe)
                    status_code = 200
                    self._send_json(status_code, out)
                    return

                status_code = 404
                self._send_json(status_code, {"error": "Not found"})
            except ValueError as exc:
                status_code = 400
                self._send_json(status_code, {"error": str(exc)})
            except json.JSONDecodeError:
                status_code = 400
                self._send_json(status_code, {"error": "Request body must be valid JSON"})
            except Exception as exc:  # pragma: no cover - defensive server boundary
                status_code = 500
                self._send_json(status_code, {"error": str(exc)})
            finally:
                self._log_request(status_code, started)

        def _check_auth(self, path: str) -> bool:
            if path == "/health" or not api_token:
                return True
            auth_header = self.headers.get("Authorization", "")
            expected = f"Bearer {api_token}"
            if auth_header == expected:
                return True
            self._send_json(401, {"error": "Unauthorized"}, unauthorized=True)
            return False

        def _read_json_body(self) -> dict:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                return {}
            raw = self.rfile.read(content_length).decode("utf-8")
            if not raw.strip():
                return {}
            value = json.loads(raw)
            if isinstance(value, dict):
                return value
            raise ValueError("Request JSON body must be an object")

        def _send_json(self, status_code: int, payload: object, unauthorized: bool = False) -> None:
            if isinstance(payload, dict):
                payload = dict(payload)
                payload.setdefault("request_id", self._request_id)
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Request-ID", self._request_id)
            if unauthorized:
                self.send_header("WWW-Authenticate", "Bearer")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _log_request(self, status_code: int, started: float) -> None:
            if not log_requests:
                return
            duration_ms = (time.perf_counter() - started) * 1000.0
            logger.info(
                "core request id=%s method=%s path=%s status=%s duration_ms=%.2f",
                self._request_id,
                self.command,
                self.path,
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
