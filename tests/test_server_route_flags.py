from __future__ import annotations

from unittest import TestCase

from novaadapt_core.server_adapt_routes import post_adapt_bond_verify
from novaadapt_core.server_channel_routes import post_channel_inbound
from novaadapt_core.server_run_memory_routes import post_swarm_run
from novaadapt_core.server_sib_routes import post_sib_resonance_result


class _StubHandler:
    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self._last_raw_body = ""
        self.last_status = 0
        self.last_payload: dict[str, object] | None = None

    def _respond_idempotent(self, *, operation, **_kwargs):
        status, payload = operation()
        self.last_status = int(status)
        self.last_payload = payload if isinstance(payload, dict) else None
        return int(status)

    def _send_json(self, status: int, payload: dict[str, object]):
        self.last_status = int(status)
        self.last_payload = payload


class _StubService:
    def __init__(self) -> None:
        self.channel_inbound_calls: list[dict[str, object]] = []
        self.adapt_bond_verify_calls: list[dict[str, object]] = []
        self.sib_resonance_result_calls: list[dict[str, object]] = []

    def run(self, payload):  # pragma: no cover - only used as callback reference
        return payload

    def channel_inbound(
        self,
        channel_name: str,
        normalized_payload: dict[str, object],
        *,
        adapt_id: str = "",
        auto_run: bool = False,
        execute: bool = False,
        request_headers: dict[str, str] | None = None,
        request_body_text: str | None = None,
    ):
        self.channel_inbound_calls.append(
            {
                "channel": channel_name,
                "payload": normalized_payload,
                "adapt_id": adapt_id,
                "auto_run": auto_run,
                "execute": execute,
                "headers": dict(request_headers or {}),
                "body": request_body_text,
            }
        )
        return {"ok": True, "status_code": 200}

    def adapt_bond_verify(self, adapt_id: str, player_id: str, *, refresh_profile: bool = True):
        self.adapt_bond_verify_calls.append(
            {
                "adapt_id": adapt_id,
                "player_id": player_id,
                "refresh_profile": refresh_profile,
            }
        )
        return {"ok": True}

    def sib_resonance_result(
        self,
        player_id: str,
        adapt_id: str,
        accepted: bool,
        player_profile=None,
        toggle_mode: str | None = None,
    ):
        self.sib_resonance_result_calls.append(
            {
                "player_id": player_id,
                "adapt_id": adapt_id,
                "accepted": accepted,
                "player_profile": player_profile,
                "toggle_mode": toggle_mode,
            }
        )
        return {"ok": True}


class _StubJobManager:
    def __init__(self) -> None:
        self.submitted: list[dict[str, object]] = []

    def submit(self, fn, payload):
        self.submitted.append({"fn": fn, "payload": dict(payload)})
        return f"job-{len(self.submitted)}"


class RouteFlagParsingTests(TestCase):
    def test_channel_inbound_string_false_flags_stay_false(self):
        handler = _StubHandler()
        service = _StubService()
        code = post_channel_inbound(
            handler,
            service,
            "/channels/webchat/inbound",
            {
                "payload": {"sender": "player-1", "text": "status"},
                "auto_run": "false",
                "execute": "false",
            },
        )
        self.assertEqual(code, 200)
        self.assertEqual(len(service.channel_inbound_calls), 1)
        call = service.channel_inbound_calls[0]
        self.assertFalse(call["auto_run"])
        self.assertFalse(call["execute"])

    def test_swarm_forwards_kernel_flags_and_parses_booleans(self):
        handler = _StubHandler()
        service = _StubService()
        job_manager = _StubJobManager()
        code = post_swarm_run(
            handler,
            service,
            job_manager,
            "/swarm/run",
            {
                "objectives": ["alpha"],
                "execute": "false",
                "allow_dangerous": "true",
                "use_kernel": "true",
                "kernel_required": "false",
            },
        )
        self.assertEqual(code, 202)
        self.assertEqual(len(job_manager.submitted), 1)
        submitted = job_manager.submitted[0]["payload"]
        self.assertFalse(submitted["execute"])
        self.assertTrue(submitted["allow_dangerous"])
        self.assertTrue(submitted["use_kernel"])
        self.assertFalse(submitted["kernel_required"])

    def test_adapt_bond_verify_string_false_refresh_profile(self):
        handler = _StubHandler()
        service = _StubService()
        code = post_adapt_bond_verify(
            handler,
            service,
            {
                "adapt_id": "adapt-1",
                "player_id": "player-1",
                "refresh_profile": "false",
            },
        )
        self.assertEqual(code, 200)
        self.assertEqual(len(service.adapt_bond_verify_calls), 1)
        self.assertFalse(service.adapt_bond_verify_calls[0]["refresh_profile"])

    def test_sib_resonance_result_string_false_accepted(self):
        handler = _StubHandler()
        service = _StubService()
        code = post_sib_resonance_result(
            handler,
            service,
            {
                "player_id": "player-1",
                "adapt_id": "adapt-1",
                "accepted": "false",
            },
        )
        self.assertEqual(code, 200)
        self.assertEqual(len(service.sib_resonance_result_calls), 1)
        self.assertFalse(service.sib_resonance_result_calls[0]["accepted"])
