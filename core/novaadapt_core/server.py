from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .service import NovaAdaptService


def create_server(host: str, port: int, service: NovaAdaptService) -> ThreadingHTTPServer:
    handler_cls = _build_handler(service)
    return ThreadingHTTPServer((host, port), handler_cls)


def run_server(host: str, port: int, service: NovaAdaptService) -> None:
    server = create_server(host=host, port=port, service=service)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_handler(service: NovaAdaptService):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            try:
                if path == "/health":
                    self._send_json(200, {"ok": True, "service": "novaadapt"})
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

                self._send_json(404, {"error": "Not found"})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover - defensive server boundary
                self._send_json(500, {"error": str(exc)})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            payload = self._read_json_body()

            try:
                if path == "/run":
                    self._send_json(200, service.run(payload))
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
            except Exception as exc:  # pragma: no cover - defensive server boundary
                self._send_json(500, {"error": str(exc)})

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
