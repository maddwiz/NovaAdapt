import json
import os
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock
from urllib import error
from urllib.parse import parse_qs, urlparse

from novaadapt_core.novaprime.client import NoopNovaPrimeClient, NovaPrimeClient, build_novaprime_client


class _NovaPrimeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/api/v1/health":
            self._send(200, {"ok": True, "service": "novaprime"})
            return
        if path == "/api/v1/mesh/credits/balance":
            node_id = (parse_qs(parsed.query).get("node_id") or [""])[0]
            self._send(200, {"ok": True, "node_id": node_id, "balance": 42.5})
            return
        if path == "/api/v1/mesh/reputation":
            node_id = (parse_qs(parsed.query).get("node_id") or [""])[0]
            self._send(200, {"ok": True, "node_id": node_id, "reputation": 0.87})
            return
        if path == "/api/v1/mesh/marketplace/listings":
            self._send(200, {"ok": True, "listings": [{"listing_id": "l1", "title": "Capsule"}]})
            return
        if path == "/api/v1/identity/profile":
            adapt_id = (parse_qs(parsed.query).get("adapt_id") or [""])[0]
            self._send(200, {"ok": True, "profile": {"adapt_id": adapt_id, "level": 2}})
            return
        if path == "/api/v1/identity/presence":
            adapt_id = (parse_qs(parsed.query).get("adapt_id") or [""])[0]
            self._send(200, {"ok": True, "presence": {"adapt_id": adapt_id, "realm": "aetherion", "activity": "idle"}})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        body = json.loads(raw) if raw else {}
        path = self.path
        if path == "/api/v1/reason/dual":
            self._send(200, {"ok": True, "final_text": f"processed:{body.get('task', '')}"})
            return
        if path == "/api/v1/reason/emotion":
            action = str(body.get("action", "get"))
            if action == "get":
                self._send(200, {"ok": True, "emotions": {"focus": 0.7}})
            else:
                self._send(200, {"ok": True, "emotions": body.get("chemicals", {})})
            return
        if path == "/api/v1/mesh/credits/credit":
            self._send(200, {"ok": True, "node_id": body.get("node_id"), "balance": 100.0})
            return
        if path == "/api/v1/mesh/credits/transfer":
            self._send(
                200,
                {
                    "ok": True,
                    "balances": {
                        str(body.get("from_node", "")): 5.0,
                        str(body.get("to_node", "")): 15.0,
                    },
                },
            )
            return
        if path == "/api/v1/mesh/marketplace/list":
            self._send(200, {"ok": True, "listing_id": "l-new"})
            return
        if path == "/api/v1/mesh/marketplace/buy":
            self._send(200, {"ok": True, "receipt": "r1"})
            return
        if path == "/api/v1/identity/bond":
            self._send(
                200,
                {
                    "ok": True,
                    "bond": {
                        "adapt_id": body.get("adapt_id"),
                        "player_id": body.get("player_id"),
                    },
                },
            )
            return
        if path == "/api/v1/identity/verify":
            self._send(200, {"ok": True, "verified": True})
            return
        if path == "/api/v1/identity/evolve":
            self._send(200, {"ok": True, "profile": {"adapt_id": body.get("adapt_id"), "level": 3}})
            return
        if path == "/api/v1/identity/presence/update":
            self._send(
                200,
                {
                    "ok": True,
                    "presence": {
                        "adapt_id": body.get("adapt_id"),
                        "realm": body.get("realm", "aetherion"),
                        "activity": body.get("activity", "idle"),
                    },
                },
            )
            return
        if path == "/api/v1/sib/resonance/score":
            self._send(200, {"ok": True, "chosen_element": "light", "resonance_strength": 0.9})
            return
        if path == "/api/v1/sib/resonance/bond":
            self._send(200, {"ok": True, "adapt_id": body.get("adapt_id") or "adapt-x"})
            return
        self._send(404, {"ok": False, "error": "not found"})

    def _send(self, status: int, payload):
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format, *args):
        return


@contextmanager
def _patched_env(name: str, value: str):
    old = os.environ.get(name)
    os.environ[name] = value
    try:
        yield
    finally:
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old


class NovaPrimeClientTests(unittest.TestCase):
    def test_noop_backend(self):
        client = NoopNovaPrimeClient()
        status = client.status()
        self.assertTrue(status["ok"])
        self.assertFalse(status["enabled"])
        self.assertEqual(client.marketplace_listings(), [])
        self.assertEqual(client.mesh_balance("node-1"), 0.0)
        self.assertEqual(client.mesh_reputation("node-1"), 0.0)
        self.assertFalse(client.identity_verify("adapt-1", "player-1"))

    def test_build_backend_disabled(self):
        with _patched_env("NOVAADAPT_NOVAPRIME_BACKEND", "off"):
            client = build_novaprime_client()
        self.assertIsInstance(client, NoopNovaPrimeClient)

    def test_http_backend_unavailable_is_optional_by_default(self):
        client = NovaPrimeClient(base_url="http://127.0.0.1:9", timeout_seconds=0.1, retry_after_seconds=1.0)
        status = client.status()
        self.assertTrue(status["ok"])
        self.assertFalse(status["enabled"])
        self.assertFalse(status["reachable"])

    def test_http_backend_unavailable_can_be_required(self):
        with _patched_env("NOVAADAPT_NOVAPRIME_REQUIRED", "1"):
            client = NovaPrimeClient(base_url="http://127.0.0.1:9", timeout_seconds=0.1, retry_after_seconds=1.0)
            status = client.status()
            self.assertFalse(status["ok"])
            self.assertFalse(status["enabled"])
            self.assertFalse(status["reachable"])
            self.assertTrue(status["required"])

    def test_http_backend_roundtrip(self):
        server = HTTPServer(("127.0.0.1", 0), _NovaPrimeHandler)
        host, port = server.server_address
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = NovaPrimeClient(
                base_url=f"http://{host}:{port}",
                timeout_seconds=1.0,
                retry_after_seconds=1.0,
            )
            status = client.status()
            self.assertTrue(status["ok"])
            self.assertTrue(status["enabled"])
            self.assertTrue(status["reachable"])

            reason = client.reason_dual("map route")
            self.assertTrue(reason["ok"])
            self.assertIn("processed", reason["final_text"])

            self.assertGreater(client.mesh_balance("node-1"), 0)
            self.assertGreater(client.mesh_reputation("node-1"), 0)
            listings = client.marketplace_listings()
            self.assertEqual(listings[0]["listing_id"], "l1")
            self.assertTrue(client.identity_verify("adapt-1", "player-1"))
            self.assertEqual(client.identity_profile("adapt-1")["adapt_id"], "adapt-1")

            presence = client.presence_get("adapt-1")
            self.assertEqual(presence["realm"], "aetherion")
            updated = client.presence_update("adapt-1", realm="game_world", activity="combat")
            self.assertEqual(updated["presence"]["realm"], "game_world")

            resonance = client.resonance_score({"class": "sentinel"})
            self.assertEqual(resonance["chosen_element"], "light")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_http_error_response_is_closed(self):
        class _ClosingHTTPError(error.HTTPError):
            def __init__(self):
                super().__init__(
                    url="http://127.0.0.1:8400/api/v1/health",
                    code=503,
                    msg="Service Unavailable",
                    hdrs=None,
                    fp=None,
                )
                self.closed = False

            def read(self):
                return b'{"error":"unavailable"}'

            def close(self):
                self.closed = True

        err = _ClosingHTTPError()
        client = NovaPrimeClient(base_url="http://127.0.0.1:8400", timeout_seconds=0.1)
        with mock.patch("novaadapt_core.novaprime.client.request.urlopen", side_effect=err):
            status = client.status()
        self.assertFalse(status["enabled"])
        self.assertTrue(err.closed)

    def test_url_error_reason_close_is_called(self):
        class _Reason:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

            def __str__(self):
                return "synthetic transport error"

        reason = _Reason()
        client = NovaPrimeClient(base_url="http://127.0.0.1:8400", timeout_seconds=0.1)
        with mock.patch("novaadapt_core.novaprime.client.request.urlopen", side_effect=error.URLError(reason)):
            status = client.status()
        self.assertFalse(status["enabled"])
        self.assertTrue(reason.closed)


if __name__ == "__main__":
    unittest.main()
