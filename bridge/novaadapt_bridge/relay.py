from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error, request
from urllib.parse import urlparse

FORWARDED_PATHS = {
    "/models",
    "/history",
    "/run",
    "/run_async",
    "/undo",
    "/check",
    "/jobs",
}


def create_server(
    host: str,
    port: int,
    core_base_url: str,
    bridge_token: str | None = None,
    core_token: str | None = None,
    timeout_seconds: int = 30,
) -> ThreadingHTTPServer:
    handler = _build_handler(
        core_base_url=core_base_url.rstrip("/"),
        bridge_token=bridge_token,
        core_token=core_token,
        timeout_seconds=timeout_seconds,
    )
    return ThreadingHTTPServer((host, port), handler)


def run_server(
    host: str,
    port: int,
    core_base_url: str,
    bridge_token: str | None = None,
    core_token: str | None = None,
    timeout_seconds: int = 30,
) -> None:
    server = create_server(
        host=host,
        port=port,
        core_base_url=core_base_url,
        bridge_token=bridge_token,
        core_token=core_token,
        timeout_seconds=timeout_seconds,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_handler(
    core_base_url: str,
    bridge_token: str | None,
    core_token: str | None,
    timeout_seconds: int,
):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/health":
                self._send_json(200, {"ok": True, "service": "novaadapt-bridge"})
                return

            if not self._check_auth():
                return

            if path == "/jobs" or path.startswith("/jobs/") or path in {"/models", "/history"}:
                out = self._forward("GET", self.path)
                self._send_json(out["status"], out["payload"])
                return

            self._send_json(404, {"error": "Not found"})

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if not self._check_auth():
                return

            if path not in {"/run", "/run_async", "/undo", "/check"}:
                self._send_json(404, {"error": "Not found"})
                return

            payload = self._read_json_body()
            out = self._forward("POST", self.path, payload)
            self._send_json(out["status"], out["payload"])

        def _forward(self, method: str, path_with_query: str, payload: dict | None = None) -> dict:
            parsed = urlparse(path_with_query)
            if parsed.path not in FORWARDED_PATHS and not parsed.path.startswith("/jobs/"):
                return {"status": 404, "payload": {"error": "Unsupported path"}}

            url = f"{core_base_url}{path_with_query}"
            headers = {"Content-Type": "application/json"}
            if core_token:
                headers["Authorization"] = f"Bearer {core_token}"

            body = None
            if method == "POST":
                body = json.dumps(payload or {}).encode("utf-8")

            req = request.Request(url=url, data=body, headers=headers, method=method)
            try:
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    raw = response.read().decode("utf-8")
                    status = int(response.status)
            except error.HTTPError as exc:
                raw = exc.read().decode("utf-8", errors="ignore")
                status = int(exc.code)
            except error.URLError as exc:
                return {
                    "status": 502,
                    "payload": {"error": f"Core API unreachable: {exc.reason}"},
                }

            try:
                return {"status": status, "payload": json.loads(raw)}
            except json.JSONDecodeError:
                return {"status": status, "payload": {"raw": raw}}

        def _check_auth(self) -> bool:
            if not bridge_token:
                return True
            auth_header = self.headers.get("Authorization", "")
            if auth_header == f"Bearer {bridge_token}":
                return True
            payload = json.dumps({"error": "Unauthorized"}).encode("utf-8")
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("WWW-Authenticate", "Bearer")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return False

        def _read_json_body(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                return {}
            raw = self.rfile.read(length).decode("utf-8")
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="novaadapt-bridge", description="NovaAdapt secure bridge relay")
    parser.add_argument("--host", default=os.getenv("NOVAADAPT_BRIDGE_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("NOVAADAPT_BRIDGE_PORT", "9797")))
    parser.add_argument(
        "--core-url",
        default=os.getenv("NOVAADAPT_CORE_URL", "http://127.0.0.1:8787"),
    )
    parser.add_argument(
        "--bridge-token",
        default=os.getenv("NOVAADAPT_BRIDGE_TOKEN"),
        help="Bearer token required for bridge clients",
    )
    parser.add_argument(
        "--core-token",
        default=os.getenv("NOVAADAPT_CORE_TOKEN"),
        help="Bearer token used by bridge when calling core API",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=int(os.getenv("NOVAADAPT_BRIDGE_TIMEOUT", "30")),
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    run_server(
        host=args.host,
        port=args.port,
        core_base_url=args.core_url,
        bridge_token=args.bridge_token,
        core_token=args.core_token,
        timeout_seconds=max(1, int(args.timeout)),
    )


if __name__ == "__main__":
    main()
