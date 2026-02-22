from __future__ import annotations

import json
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
) -> ThreadingHTTPServer:
    managed_jobs = job_manager or JobManager()
    handler_cls = _build_handler(
        service=service,
        api_token=api_token,
        job_manager=managed_jobs,
    )
    return NovaAdaptHTTPServer((host, port), handler_cls, managed_jobs)


def run_server(
    host: str,
    port: int,
    service: NovaAdaptService,
    api_token: str | None = None,
) -> None:
    server = create_server(host=host, port=port, service=service, api_token=api_token)
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
):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            try:
                if path == "/health":
                    self._send_json(200, {"ok": True, "service": "novaadapt"})
                    return

                if not self._check_auth(path):
                    return

                if path == "/models":
                    config = _single(query, "config")
                    out = service.models(config_path=_to_path(config))
                    self._send_json(200, out)
                    return

                if path == "/history":
                    limit = int(_single(query, "limit") or 20)
                    self._send_json(200, service.history(limit=limit))
                    return

                if path == "/jobs":
                    limit = int(_single(query, "limit") or 50)
                    self._send_json(200, job_manager.list(limit=limit))
                    return

                if path.startswith("/jobs/"):
                    job_id = path.removeprefix("/jobs/").strip()
                    if not job_id:
                        self._send_json(404, {"error": "Not found"})
                        return
                    item = job_manager.get(job_id)
                    if item is None:
                        self._send_json(404, {"error": "Job not found"})
                        return
                    self._send_json(200, item)
                    return

                self._send_json(404, {"error": "Not found"})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive server boundary
                self._send_json(500, {"error": str(exc)})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path

            if not self._check_auth(path):
                return

            try:
                payload = self._read_json_body()

                if path == "/run":
                    self._send_json(200, service.run(payload))
                    return

                if path == "/run_async":
                    job_id = job_manager.submit(service.run, payload)
                    self._send_json(202, {"job_id": job_id, "status": "queued"})
                    return

                if path == "/undo":
                    self._send_json(200, service.undo(payload))
                    return

                if path == "/check":
                    config = _to_path(payload.get("config"))
                    models = payload.get("models")
                    probe = str(payload.get("probe", "Reply with: OK"))
                    out = service.check(config_path=config, model_names=service._as_name_list(models), probe_prompt=probe)
                    self._send_json(200, out)
                    return

                self._send_json(404, {"error": "Not found"})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except json.JSONDecodeError:
                self._send_json(400, {"error": "Request body must be valid JSON"})
            except Exception as exc:  # pragma: no cover - defensive server boundary
                self._send_json(500, {"error": str(exc)})

        def _check_auth(self, path: str) -> bool:
            if path == "/health" or not api_token:
                return True
            auth_header = self.headers.get("Authorization", "")
            expected = f"Bearer {api_token}"
            if auth_header == expected:
                return True
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("WWW-Authenticate", "Bearer")
            payload = json.dumps({"error": "Unauthorized"}).encode("utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
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

        def _send_json(self, status_code: int, payload: object) -> None:
            encoded = json.dumps(payload).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

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
