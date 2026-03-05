from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib import request

from novaadapt_core.directshell import ExecutionResult
from novaadapt_core.novaprime.client import NovaPrimeClient
from novaadapt_core.server import create_server
from novaadapt_core.service import NovaAdaptService
from novaadapt_shared.model_router import RouterResult


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
NOVAPRIME_REPO = WORKSPACE_ROOT / "NovaPrime"


class _StubRouter:
    def list_models(self):
        class Model:
            def __init__(self):
                self.name = "local"
                self.model = "qwen"
                self.provider = "openai-compatible"
                self.base_url = "http://localhost:11434/v1"

        return [Model()]

    def health_check(self, model_names=None, probe_prompt="Reply with: OK"):
        _ = (model_names, probe_prompt)
        return [{"name": "local", "ok": True, "latency_ms": 1.0}]

    def chat(
        self,
        messages,
        model_name=None,
        strategy="single",
        candidate_models=None,
        fallback_models=None,
    ):
        _ = (messages, candidate_models, fallback_models)
        return RouterResult(
            model_name=model_name or "local",
            model_id="qwen",
            content='{"actions":[{"type":"click","target":"OK"}]}',
            strategy=strategy,
            votes={},
            errors={},
            attempted_models=[model_name or "local"],
        )


class _StubDirectShell:
    def execute_action(self, action, dry_run=True):
        return ExecutionResult(action=action, status="preview" if dry_run else "ok", output="simulated")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


def _get_json(url: str) -> dict:
    with request.urlopen(url, timeout=10) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return parsed


def _post_json(url: str, payload: dict) -> dict:
    raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        url,
        data=raw,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with request.urlopen(req, timeout=10) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return parsed


def _post_json_with_status(url: str, payload: dict) -> tuple[int, dict]:
    raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    req = request.Request(
        url,
        data=raw,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            status = int(response.getcode())
    except request.HTTPError as exc:
        status = int(exc.code)
        try:
            body = exc.read().decode("utf-8")
        finally:
            try:
                exc.close()
            except Exception:
                pass
    parsed = json.loads(body or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return status, parsed


def _get_json_with_status(url: str) -> tuple[int, dict]:
    req = request.Request(url, method="GET", headers={"Accept": "application/json"})
    try:
        with request.urlopen(req, timeout=10) as response:
            body = response.read().decode("utf-8")
            status = int(response.getcode())
    except request.HTTPError as exc:
        status = int(exc.code)
        try:
            body = exc.read().decode("utf-8")
        finally:
            try:
                exc.close()
            except Exception:
                pass
    parsed = json.loads(body or "{}")
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Expected JSON object from {url}")
    return status, parsed


def _wait_health(url: str, *, timeout_sec: float = 20.0) -> None:
    deadline = time.time() + max(1.0, float(timeout_sec))
    last_error = ""
    while time.time() < deadline:
        try:
            payload = _get_json(url)
            if bool(payload.get("ok", False)):
                return
        except Exception as exc:  # pragma: no cover - retry path
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for health {url}: {last_error}")


@unittest.skipUnless(NOVAPRIME_REPO.exists(), "NovaPrime repo not available in workspace")
class NovaPrimeContractE2ETests(unittest.TestCase):
    def test_novaadapt_proxies_live_novaprime_sib_and_aetherion_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            np_state = tmpdir / "novaprime_state"
            np_state.mkdir(parents=True, exist_ok=True)

            np_port = _find_free_port()
            np_url = f"http://127.0.0.1:{np_port}"

            env = os.environ.copy()
            env.update(
                {
                    "NOVAPRIME_API_TOKEN": "",
                    "C3_MEMORY_BACKEND": "local",
                    "C3_MEMORY_FAILOVER_PATH": str(np_state / "memory_events.jsonl"),
                    "NOVAPRIME_IDENTITY_STORE_PATH": str(np_state / "identity_state.json"),
                    "NOVAPRIME_IMPRINTING_STORE_PATH": str(np_state / "imprinting_sessions.json"),
                    "NOVAPRIME_AETHERION_STATE_PATH": str(np_state / "aetherion_state.json"),
                    "NOVAPRIME_LEDGER_PATH": str(np_state / "ledger.sqlite3"),
                    "NOVAPRIME_PEERS_PATH": str(np_state / "peers.json"),
                    "NOVAPRIME_SWARM_STATE_PATH": str(np_state / "swarm_state.json"),
                    "NOVAPRIME_COMPUTE_JOBS_PATH": str(np_state / "compute_jobs.jsonl"),
                    "NOVAPRIME_COMPUTE_DISPUTES_PATH": str(np_state / "compute_disputes.jsonl"),
                    "NOVAPRIME_REPUTATION_CONSENSUS_PATH": str(np_state / "reputation_consensus.json"),
                    "NOVAPRIME_RECONCILE_SCHEDULER_PATH": str(np_state / "reconcile_scheduler_state.json"),
                    "NOVAPRIME_PARTITION_STATE_PATH": str(np_state / "partition_state.json"),
                    "NOVAPRIME_TRANSFER_QUEUE_PATH": str(np_state / "transfer_queue.jsonl"),
                }
            )

            proc = subprocess.Popen(
                ["python3", "-m", "core.entrypoints.api_server", "--host", "127.0.0.1", "--port", str(np_port)],
                cwd=str(NOVAPRIME_REPO),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            server = None
            thread = None
            try:
                _wait_health(f"{np_url}/api/v1/health", timeout_sec=25.0)

                # This live contract test validates advanced SIB/Aetherion routes.
                # When CI checks out an older NovaPrime main revision without these
                # routes, skip instead of failing the whole NovaAdapt pipeline.
                capability_probes: list[tuple[str, int]] = []
                probe_status, _ = _get_json_with_status(f"{np_url}/api/v1/mesh/aetherion/state?refresh=1")
                capability_probes.append(("mesh.aetherion_state", probe_status))
                probe_status, _ = _post_json_with_status(
                    f"{np_url}/api/v1/sib/imprinting/start",
                    {"player_profile": {"class": "sentinel"}},
                )
                capability_probes.append(("sib.imprinting_start", probe_status))
                probe_status, _ = _post_json_with_status(
                    f"{np_url}/api/v1/sib/phase/evaluate",
                    {"player_state": {"player_id": "probe-player"}},
                )
                capability_probes.append(("sib.phase_evaluate", probe_status))
                probe_status, _ = _post_json_with_status(
                    f"{np_url}/api/v1/sib/void/create",
                    {"player_id": "probe-player", "player_profile": {"class": "sentinel"}},
                )
                capability_probes.append(("sib.void_create", probe_status))
                probe_status, _ = _get_json_with_status(
                    f"{np_url}/api/v1/narrative/bond/history?adapt_id=probe-adapt&player_id=probe-player"
                )
                capability_probes.append(("narrative.bond_history", probe_status))

                missing = [name for name, status in capability_probes if int(status) == 404]
                if missing:
                    self.skipTest(
                        "NovaPrime checkout missing advanced live-contract routes: "
                        + ", ".join(sorted(missing))
                    )

                service = NovaAdaptService(
                    default_config=Path("unused.json"),
                    db_path=tmpdir / "actions.db",
                    plans_db_path=tmpdir / "plans.db",
                    router_loader=lambda _path: _StubRouter(),
                    directshell_factory=_StubDirectShell,
                    novaprime_client=NovaPrimeClient(
                        base_url=np_url,
                        timeout_seconds=5.0,
                        retry_after_seconds=1.0,
                    ),
                )
                server = create_server(
                    "127.0.0.1",
                    0,
                    service,
                    audit_db_path=str(tmpdir / "events.db"),
                )
                host, port = server.server_address
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()

                base = f"http://{host}:{port}"

                aetherion = _get_json(f"{base}/novaprime/mesh/aetherion/state?refresh=1")
                self.assertTrue(aetherion["ok"])
                self.assertTrue(("snapshot" in aetherion) or ("population" in aetherion))

                imprint_start = _post_json(
                    f"{base}/novaprime/sib/imprinting/start",
                    {"player_id": "player-e2e", "player_profile": {"class": "sentinel"}, "ttl_sec": 900},
                )
                self.assertTrue(imprint_start["ok"])
                self.assertIn("session", imprint_start)
                session_id = str(imprint_start["session"]["session_id"])
                self.assertTrue(session_id)

                imprint_session = _get_json(
                    f"{base}/novaprime/sib/imprinting/session?session_id={session_id}"
                )
                self.assertTrue(imprint_session["ok"])
                self.assertEqual(imprint_session["session"]["session_id"], session_id)

                not_found_status, not_found_session = _get_json_with_status(
                    f"{base}/novaprime/sib/imprinting/session?session_id=missing-session"
                )
                self.assertEqual(not_found_status, 200)
                self.assertFalse(not_found_session.get("ok", True))
                self.assertIn("session_not_found", str(not_found_session.get("error", "")))

                missing_player_status, missing_player = _post_json_with_status(
                    f"{base}/novaprime/sib/imprinting/start",
                    {"player_profile": {"class": "sentinel"}},
                )
                self.assertEqual(missing_player_status, 400)
                self.assertTrue(("ok" not in missing_player) or (not missing_player.get("ok", True)))
                self.assertIn("player_id", str(missing_player.get("error", "")).lower())

                imprint_resolve = _post_json(
                    f"{base}/novaprime/sib/imprinting/resolve",
                    {"session_id": session_id, "accepted": False, "adapt_id": "adapt-e2e"},
                )
                self.assertTrue(imprint_resolve["ok"])
                self.assertFalse(imprint_resolve.get("accepted", True))

                missing_session_status, missing_session_resolve = _post_json_with_status(
                    f"{base}/novaprime/sib/imprinting/resolve",
                    {"session_id": "missing-session", "accepted": True},
                )
                self.assertEqual(missing_session_status, 200)
                self.assertFalse(missing_session_resolve.get("ok", True))
                self.assertIn("session_not_found", str(missing_session_resolve.get("error", "")))

                invalid_phase_status, invalid_phase = _post_json_with_status(
                    f"{base}/novaprime/sib/phase/evaluate",
                    {"player_state": "bad-shape"},
                )
                self.assertEqual(invalid_phase_status, 200)
                self.assertIn("ok", invalid_phase)

                phase = _post_json(
                    f"{base}/novaprime/sib/phase/evaluate",
                    {
                        "player_state": {"player_id": "player-e2e", "emotional_intensity": 0.9, "uncertainty": 0.6},
                        "narrative_state": {"beat_intensity": 0.7},
                        "environment_state": {"anomaly_density": 0.4},
                        "adapt_id": "adapt-e2e",
                        "auto_presence_update": True,
                    },
                )
                self.assertTrue(phase["ok"])
                self.assertIn("triggered", phase)

                void_created = _post_json(
                    f"{base}/novaprime/sib/void/create",
                    {"player_id": "player-e2e", "player_profile": {"class": "warden"}, "seed": "alpha"},
                )
                self.assertTrue(void_created["ok"])
                self.assertIn("state", void_created)

                void_ticked = _post_json(
                    f"{base}/novaprime/sib/void/tick",
                    {"state": void_created["state"], "stimulus": {"attention": 0.7, "alignment": 0.8}, "tick": 2},
                )
                self.assertTrue(void_ticked["ok"])
                self.assertIn("state", void_ticked)

                invalid_void_status, invalid_void = _post_json_with_status(
                    f"{base}/novaprime/sib/void/tick",
                    {"state": "not-an-object"},
                )
                self.assertEqual(invalid_void_status, 200)
                self.assertIn("ok", invalid_void)

                bond_history = _get_json(
                    f"{base}/novaprime/narrative/bond/history?adapt_id=adapt-e2e&player_id=player-e2e&top_k=20"
                )
                self.assertTrue(bond_history["ok"])
                self.assertEqual(bond_history["adapt_id"], "adapt-e2e")
                self.assertEqual(bond_history["player_id"], "player-e2e")
                self.assertIn("summary", bond_history)

                invalid_history_status, invalid_history = _get_json_with_status(
                    f"{base}/novaprime/narrative/bond/history?adapt_id=&player_id=player-e2e"
                )
                self.assertEqual(invalid_history_status, 400)
                self.assertTrue(("ok" not in invalid_history) or (not invalid_history.get("ok", True)))
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    thread.join(timeout=5.0)

                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=8.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5.0)
                if proc.stdout is not None:
                    proc.stdout.close()
                if proc.stderr is not None:
                    proc.stderr.close()
