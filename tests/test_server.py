import io
import json
import logging
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

from novaadapt_core.browser_executor import BrowserExecutionResult
from novaadapt_core.directshell import ExecutionResult
from novaadapt_core.server import (
    _PerClientSlidingWindowRateLimiter,
    _parse_trusted_proxy_cidrs,
    create_server,
)
from novaadapt_core.service import NovaAdaptService
from novaadapt_shared.model_router import RouterResult


class _StubRouter:
    def list_models(self):
        class Model:
            def __init__(self, name, model, provider, base_url):
                self.name = name
                self.model = model
                self.provider = provider
                self.base_url = base_url

        return [Model("local", "qwen", "openai-compatible", "http://localhost:11434/v1")]

    def health_check(self, model_names=None, probe_prompt="Reply with: OK"):
        return [{"name": "local", "ok": True, "latency_ms": 1.0}]

    def chat(
        self,
        messages,
        model_name=None,
        strategy="single",
        candidate_models=None,
        fallback_models=None,
    ):
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


class _SlowRouter(_StubRouter):
    def chat(
        self,
        messages,
        model_name=None,
        strategy="single",
        candidate_models=None,
        fallback_models=None,
    ):
        return RouterResult(
            model_name=model_name or "local",
            model_id="qwen",
            content=(
                '{"actions":['
                '{"type":"click","target":"10,10"},'
                '{"type":"click","target":"20,20"},'
                '{"type":"click","target":"30,30"},'
                '{"type":"click","target":"40,40"},'
                '{"type":"click","target":"50,50"}'
                ']}'
            ),
            strategy=strategy,
            votes={},
            errors={},
            attempted_models=[model_name or "local"],
        )


class _SlowDirectShell:
    def execute_action(self, action, dry_run=True):
        if dry_run:
            return ExecutionResult(action=action, status="preview", output="simulated")
        time.sleep(0.05)
        return ExecutionResult(action=action, status="ok", output="slow-ok")


class _FlakyDirectShell:
    attempts = 0

    def execute_action(self, action, dry_run=True):
        if dry_run:
            return ExecutionResult(action=action, status="preview", output="simulated")
        _FlakyDirectShell.attempts += 1
        if _FlakyDirectShell.attempts == 1:
            return ExecutionResult(action=action, status="failed", output="transient failure")
        return ExecutionResult(action=action, status="ok", output="recovered")


class _StubBrowserExecutor:
    def __init__(self):
        self.closed = False

    def probe(self):
        return {"ok": True, "transport": "browser", "capabilities": ["navigate", "click_selector"]}

    def execute_action(self, action):
        if action.get("type") == "list_pages":
            return BrowserExecutionResult(
                status="ok",
                output="listed browser pages",
                data={
                    "count": 1,
                    "current_page_id": "page-1",
                    "pages": [{"page_id": "page-1", "url": "https://example.com", "current": True}],
                },
            )
        return BrowserExecutionResult(status="ok", output="browser simulated", data={"action": action})

    def close(self):
        self.closed = True
        return BrowserExecutionResult(status="ok", output="browser session closed")


class ServerTests(unittest.TestCase):
    def test_http_endpoints(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
                browser_executor_factory=_StubBrowserExecutor,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                health, health_headers = _get_json_with_headers(f"http://{host}:{port}/health")
                self.assertTrue(health["ok"])
                self.assertIn("request_id", health)
                self.assertTrue(health_headers.get("X-Request-ID"))

                deep_health, _ = _get_json_with_headers(f"http://{host}:{port}/health?deep=1")
                self.assertTrue(deep_health["ok"])
                self.assertIn("checks", deep_health)
                self.assertTrue(deep_health["checks"]["models"]["ok"])
                self.assertTrue(deep_health["checks"]["audit_store"]["ok"])
                self.assertIn("memory", deep_health["checks"])
                self.assertIn("ok", deep_health["checks"]["memory"])
                self.assertIn("novaprime", deep_health["checks"])
                self.assertIn("ok", deep_health["checks"]["novaprime"])
                self.assertIn("metrics", deep_health)

                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/health?deep=1&execution=1")
                self.assertEqual(err.exception.code, 503)
                try:
                    execution_health = json.loads(err.exception.read().decode("utf-8"))
                finally:
                    err.exception.close()
                self.assertFalse(execution_health["ok"])
                self.assertIn("directshell", execution_health["checks"])
                self.assertFalse(execution_health["checks"]["directshell"]["ok"])

                dashboard_html = _get_text(f"http://{host}:{port}/dashboard")
                self.assertIn("NovaAdapt Core Dashboard", dashboard_html)
                self.assertIn("Approve Async", dashboard_html)
                self.assertIn("cancel-job", dashboard_html)

                dashboard_data, _ = _get_json_with_headers(f"http://{host}:{port}/dashboard/data")
                self.assertTrue(dashboard_data["health"]["ok"])
                self.assertIn("metrics", dashboard_data)
                self.assertIn("jobs", dashboard_data)
                self.assertIn("plans", dashboard_data)
                self.assertIn("events", dashboard_data)

                openapi, _ = _get_json_with_headers(f"http://{host}:{port}/openapi.json")
                self.assertEqual(openapi["openapi"], "3.1.0")
                self.assertIn("/run", openapi["paths"])
                self.assertIn("/jobs/{id}/cancel", openapi["paths"])
                self.assertIn("/jobs/{id}/stream", openapi["paths"])
                self.assertIn("/swarm/run", openapi["paths"])
                self.assertIn("/plans/{id}/stream", openapi["paths"])
                self.assertIn("/plans/{id}/approve", openapi["paths"])
                self.assertIn("/plans/{id}/approve_async", openapi["paths"])
                self.assertIn("/plans/{id}/retry_failed", openapi["paths"])
                self.assertIn("/plans/{id}/retry_failed_async", openapi["paths"])
                self.assertIn("/plans/{id}/undo", openapi["paths"])
                self.assertIn("/dashboard/data", openapi["paths"])
                self.assertIn("/events", openapi["paths"])
                self.assertIn("/events/stream", openapi["paths"])
                self.assertIn("/plugins", openapi["paths"])
                self.assertIn("/plugins/{name}/health", openapi["paths"])
                self.assertIn("/plugins/{name}/call", openapi["paths"])
                self.assertIn("/channels", openapi["paths"])
                self.assertIn("/channels/{name}/health", openapi["paths"])
                self.assertIn("/channels/{name}/send", openapi["paths"])
                self.assertIn("/channels/{name}/inbound", openapi["paths"])
                self.assertIn("/feedback", openapi["paths"])
                self.assertIn("/memory/status", openapi["paths"])
                self.assertIn("/novaprime/status", openapi["paths"])
                self.assertIn("/novaprime/reason/dual", openapi["paths"])
                self.assertIn("/novaprime/reason/emotion", openapi["paths"])
                self.assertIn("/novaprime/mesh/balance", openapi["paths"])
                self.assertIn("/novaprime/mesh/reputation", openapi["paths"])
                self.assertIn("/novaprime/marketplace/listings", openapi["paths"])
                self.assertIn("/novaprime/identity/profile", openapi["paths"])
                self.assertIn("/novaprime/presence", openapi["paths"])
                self.assertIn("/novaprime/mesh/credit", openapi["paths"])
                self.assertIn("/novaprime/mesh/transfer", openapi["paths"])
                self.assertIn("/novaprime/marketplace/list", openapi["paths"])
                self.assertIn("/novaprime/marketplace/buy", openapi["paths"])
                self.assertIn("/novaprime/identity/bond", openapi["paths"])
                self.assertIn("/novaprime/identity/verify", openapi["paths"])
                self.assertIn("/novaprime/identity/evolve", openapi["paths"])
                self.assertIn("/novaprime/presence/update", openapi["paths"])
                self.assertIn("/novaprime/resonance/score", openapi["paths"])
                self.assertIn("/novaprime/resonance/bond", openapi["paths"])
                self.assertIn("/sib/status", openapi["paths"])
                self.assertIn("/sib/realm", openapi["paths"])
                self.assertIn("/sib/companion/state", openapi["paths"])
                self.assertIn("/sib/companion/speak", openapi["paths"])
                self.assertIn("/sib/phase-event", openapi["paths"])
                self.assertIn("/sib/resonance/start", openapi["paths"])
                self.assertIn("/sib/resonance/result", openapi["paths"])
                self.assertIn("/adapt/toggle", openapi["paths"])
                self.assertIn("/adapt/bond", openapi["paths"])
                self.assertIn("/adapt/bond/verify", openapi["paths"])
                self.assertIn("/adapt/persona", openapi["paths"])
                self.assertIn("/memory/recall", openapi["paths"])
                self.assertIn("/memory/ingest", openapi["paths"])
                self.assertIn("/browser/status", openapi["paths"])
                self.assertIn("/browser/pages", openapi["paths"])
                self.assertIn("/browser/action", openapi["paths"])
                self.assertIn("/browser/navigate", openapi["paths"])
                self.assertIn("/browser/click", openapi["paths"])
                self.assertIn("/browser/fill", openapi["paths"])
                self.assertIn("/browser/extract_text", openapi["paths"])
                self.assertIn("/browser/screenshot", openapi["paths"])
                self.assertIn("/browser/wait_for_selector", openapi["paths"])
                self.assertIn("/browser/evaluate_js", openapi["paths"])
                self.assertIn("/browser/close", openapi["paths"])
                self.assertIn("/terminal/sessions", openapi["paths"])
                self.assertIn("/terminal/sessions/{id}/output", openapi["paths"])
                self.assertIn("/terminal/sessions/{id}/input", openapi["paths"])
                self.assertIn("/terminal/sessions/{id}/close", openapi["paths"])

                models, _ = _get_json_with_headers(f"http://{host}:{port}/models")
                self.assertEqual(models[0]["name"], "local")

                plugins, _ = _get_json_with_headers(f"http://{host}:{port}/plugins")
                self.assertGreaterEqual(len(plugins), 1)
                self.assertEqual(plugins[0]["name"], "nova4d")

                plugin_health, _ = _get_json_with_headers(f"http://{host}:{port}/plugins/novabridge/health")
                self.assertEqual(plugin_health["plugin"], "novabridge")

                channels, _ = _get_json_with_headers(f"http://{host}:{port}/channels")
                self.assertGreaterEqual(len(channels), 1)
                self.assertTrue(any(item.get("channel") == "webchat" for item in channels))

                webchat_health, _ = _get_json_with_headers(f"http://{host}:{port}/channels/webchat/health")
                self.assertTrue(webchat_health["ok"])
                self.assertEqual(webchat_health["channel"], "webchat")

                channel_send, _ = _post_json_with_headers(
                    f"http://{host}:{port}/channels/webchat/send",
                    {"to": "room-1", "text": "hello from api"},
                )
                self.assertTrue(channel_send["ok"])
                self.assertEqual(channel_send["channel"], "webchat")

                channel_inbound, _ = _post_json_with_headers(
                    f"http://{host}:{port}/channels/webchat/inbound",
                    {
                        "payload": {"sender": "player-1", "text": "status report", "room_id": "room-1"},
                        "adapt_id": "adapt-1",
                    },
                )
                self.assertTrue(channel_inbound["ok"])
                self.assertEqual(channel_inbound["channel"], "webchat")
                self.assertTrue(channel_inbound["memory"]["ok"])

                previous_channel_token = os.environ.get("NOVAADAPT_CHANNEL_WEBCHAT_INBOUND_TOKEN")
                os.environ["NOVAADAPT_CHANNEL_WEBCHAT_INBOUND_TOKEN"] = "server-secret"
                try:
                    with self.assertRaises(error.HTTPError) as err:
                        _post_json(
                            f"http://{host}:{port}/channels/webchat/inbound",
                            {"payload": {"sender": "player-1", "text": "blocked"}},
                        )
                    self.assertEqual(err.exception.code, 401)
                    err.exception.close()

                    authed_inbound, _ = _post_json_with_headers(
                        f"http://{host}:{port}/channels/webchat/inbound",
                        {
                            "payload": {"sender": "player-1", "text": "allowed"},
                            "auth_token": "server-secret",
                        },
                    )
                    self.assertTrue(authed_inbound["ok"])
                finally:
                    if previous_channel_token is None:
                        os.environ.pop("NOVAADAPT_CHANNEL_WEBCHAT_INBOUND_TOKEN", None)
                    else:
                        os.environ["NOVAADAPT_CHANNEL_WEBCHAT_INBOUND_TOKEN"] = previous_channel_token

                run, _ = _post_json_with_headers(
                    f"http://{host}:{port}/run",
                    {"objective": "click ok"},
                )
                self.assertEqual(run["results"][0]["status"], "preview")
                self.assertIn("request_id", run)

                run_mesh_probe, _ = _post_json_with_headers(
                    f"http://{host}:{port}/run",
                    {
                        "objective": "probe mesh",
                        "mesh_node_id": "node-1",
                        "mesh_probe": True,
                        "mesh_probe_marketplace": True,
                    },
                )
                self.assertEqual(run_mesh_probe["results"][0]["status"], "preview")
                self.assertIn("novaprime", run_mesh_probe)
                self.assertIn("mesh", run_mesh_probe["novaprime"])
                self.assertEqual(run_mesh_probe["novaprime"]["mesh"]["node_id"], "node-1")
                self.assertIn("reputation", run_mesh_probe["novaprime"]["mesh"])

                swarm, _ = _post_json_with_headers(
                    f"http://{host}:{port}/swarm/run",
                    {"objectives": ["click ok", "click ok again"], "execute": False, "max_agents": 2},
                )
                self.assertEqual(swarm["status"], "queued")
                self.assertEqual(swarm["kind"], "swarm")
                self.assertEqual(swarm["submitted_jobs"], 2)

                plugin_call, _ = _post_json_with_headers(
                    f"http://{host}:{port}/plugins/novabridge/call",
                    {"route": "/health", "method": "GET"},
                )
                self.assertEqual(plugin_call["plugin"], "novabridge")
                self.assertIn("ok", plugin_call)

                feedback, _ = _post_json_with_headers(
                    f"http://{host}:{port}/feedback",
                    {"rating": 8, "objective": "smoke", "notes": "good"},
                )
                self.assertTrue(feedback["ok"])
                self.assertEqual(feedback["rating"], 8)

                memory_status, _ = _get_json_with_headers(f"http://{host}:{port}/memory/status")
                self.assertIn("ok", memory_status)
                self.assertIn("backend", memory_status)

                novaprime_status, _ = _get_json_with_headers(f"http://{host}:{port}/novaprime/status")
                self.assertIn("ok", novaprime_status)
                self.assertIn("backend", novaprime_status)

                novaprime_emotion_get, _ = _get_json_with_headers(
                    f"http://{host}:{port}/novaprime/reason/emotion"
                )
                self.assertIn("ok", novaprime_emotion_get)

                novaprime_reason, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/reason/dual",
                    {"task": "Map eastern patrol routes"},
                )
                self.assertIn("ok", novaprime_reason)

                novaprime_emotion_set, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/reason/emotion",
                    {"chemicals": {"focus": 0.8, "calm": 0.7}},
                )
                self.assertIn("ok", novaprime_emotion_set)

                novaprime_mesh_balance, _ = _get_json_with_headers(
                    f"http://{host}:{port}/novaprime/mesh/balance?node_id=node-1"
                )
                self.assertTrue(novaprime_mesh_balance["ok"])
                self.assertEqual(novaprime_mesh_balance["node_id"], "node-1")

                novaprime_mesh_reputation, _ = _get_json_with_headers(
                    f"http://{host}:{port}/novaprime/mesh/reputation?node_id=node-1"
                )
                self.assertTrue(novaprime_mesh_reputation["ok"])
                self.assertEqual(novaprime_mesh_reputation["node_id"], "node-1")

                novaprime_marketplace_listings, _ = _get_json_with_headers(
                    f"http://{host}:{port}/novaprime/marketplace/listings"
                )
                self.assertTrue(novaprime_marketplace_listings["ok"])
                self.assertIn("listings", novaprime_marketplace_listings)

                novaprime_profile, _ = _get_json_with_headers(
                    f"http://{host}:{port}/novaprime/identity/profile?adapt_id=adapt-1"
                )
                self.assertTrue(novaprime_profile["ok"])
                self.assertEqual(novaprime_profile["adapt_id"], "adapt-1")

                novaprime_presence, _ = _get_json_with_headers(
                    f"http://{host}:{port}/novaprime/presence?adapt_id=adapt-1"
                )
                self.assertTrue(novaprime_presence["ok"])
                self.assertEqual(novaprime_presence["adapt_id"], "adapt-1")

                novaprime_bond, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/identity/bond",
                    {"adapt_id": "adapt-1", "player_id": "player-1", "element": "light", "subclass": "light"},
                )
                self.assertIn("ok", novaprime_bond)

                novaprime_mesh_credit, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/mesh/credit",
                    {"node_id": "node-1", "amount": 10},
                )
                self.assertIn("ok", novaprime_mesh_credit)

                novaprime_mesh_transfer, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/mesh/transfer",
                    {"from_node": "node-1", "to_node": "node-2", "amount": 5},
                )
                self.assertIn("ok", novaprime_mesh_transfer)

                novaprime_marketplace_list, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/marketplace/list",
                    {"capsule_id": "capsule-1", "seller": "node-1", "price": 25, "title": "Storm Slash"},
                )
                self.assertIn("ok", novaprime_marketplace_list)

                novaprime_marketplace_buy, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/marketplace/buy",
                    {"listing_id": "listing-1", "buyer": "node-2"},
                )
                self.assertIn("ok", novaprime_marketplace_buy)

                novaprime_verify, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/identity/verify",
                    {"adapt_id": "adapt-1", "player_id": "player-1"},
                )
                self.assertTrue(novaprime_verify["ok"])
                self.assertIn("verified", novaprime_verify)

                novaprime_evolve, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/identity/evolve",
                    {"adapt_id": "adapt-1", "xp_gain": 150, "new_skill": "storm_slash"},
                )
                self.assertIn("ok", novaprime_evolve)

                novaprime_presence_update, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/presence/update",
                    {"adapt_id": "adapt-1", "realm": "game_world", "activity": "patrol"},
                )
                self.assertIn("ok", novaprime_presence_update)

                novaprime_resonance_score, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/resonance/score",
                    {"player_profile": {"class": "sentinel"}},
                )
                self.assertIn("ok", novaprime_resonance_score)

                novaprime_resonance_bond, _ = _post_json_with_headers(
                    f"http://{host}:{port}/novaprime/resonance/bond",
                    {"player_id": "player-1", "player_profile": {"class": "sentinel"}, "adapt_id": "adapt-1"},
                )
                self.assertIn("ok", novaprime_resonance_bond)

                sib_status, _ = _get_json_with_headers(f"http://{host}:{port}/sib/status")
                self.assertEqual(sib_status["plugin"], "sib_bridge")

                sib_realm, _ = _post_json_with_headers(
                    f"http://{host}:{port}/sib/realm",
                    {"player_id": "player-1", "realm": "game_world"},
                )
                self.assertEqual(sib_realm["plugin"], "sib_bridge")

                sib_state, _ = _post_json_with_headers(
                    f"http://{host}:{port}/sib/companion/state",
                    {"adapt_id": "adapt-1", "state": {"mode": "combat"}},
                )
                self.assertEqual(sib_state["plugin"], "sib_bridge")

                sib_speak, _ = _post_json_with_headers(
                    f"http://{host}:{port}/sib/companion/speak",
                    {"adapt_id": "adapt-1", "text": "On your left", "channel": "in_game"},
                )
                self.assertEqual(sib_speak["plugin"], "sib_bridge")

                sib_phase, _ = _post_json_with_headers(
                    f"http://{host}:{port}/sib/phase-event",
                    {"event_type": "entropy_spike", "payload": {"severity": "high"}},
                )
                self.assertEqual(sib_phase["plugin"], "sib_bridge")

                sib_start, _ = _post_json_with_headers(
                    f"http://{host}:{port}/sib/resonance/start",
                    {"player_id": "player-1", "player_profile": {"class": "sentinel"}},
                )
                self.assertEqual(sib_start["plugin"], "sib_bridge")
                self.assertIn("novaprime_resonance", sib_start)

                sib_result, _ = _post_json_with_headers(
                    f"http://{host}:{port}/sib/resonance/result",
                    {
                        "player_id": "player-1",
                        "adapt_id": "adapt-1",
                        "accepted": True,
                        "player_profile": {"class": "sentinel"},
                        "toggle_mode": "in_game_only",
                    },
                )
                self.assertEqual(sib_result["plugin"], "sib_bridge")
                self.assertIn("novaprime_bond", sib_result)
                self.assertEqual(sib_result["adapt_toggle"]["mode"], "in_game_only")
                self.assertIn("novaprime_presence", sib_result)
                self.assertIn("adapt_persona", sib_result)
                if bool(sib_result["novaprime_bond"].get("ok", False)):
                    self.assertIn("adapt_bond_cache", sib_result)

                adapt_toggle_set, _ = _post_json_with_headers(
                    f"http://{host}:{port}/adapt/toggle",
                    {"adapt_id": "adapt-1", "mode": "ask_only"},
                )
                self.assertEqual(adapt_toggle_set["mode"], "ask_only")
                adapt_toggle_get, _ = _get_json_with_headers(f"http://{host}:{port}/adapt/toggle?adapt_id=adapt-1")
                self.assertEqual(adapt_toggle_get["mode"], "ask_only")
                adapt_bond, _ = _get_json_with_headers(f"http://{host}:{port}/adapt/bond?adapt_id=adapt-1")
                self.assertIn("found", adapt_bond)
                adapt_bond_verify, _ = _post_json_with_headers(
                    f"http://{host}:{port}/adapt/bond/verify",
                    {"adapt_id": "adapt-1", "player_id": "player-1"},
                )
                self.assertEqual(adapt_bond_verify["adapt_id"], "adapt-1")
                self.assertEqual(adapt_bond_verify["player_id"], "player-1")
                self.assertIn("verified", adapt_bond_verify)
                adapt_persona, _ = _get_json_with_headers(
                    f"http://{host}:{port}/adapt/persona?adapt_id=adapt-1&player_id=player-1"
                )
                self.assertTrue(adapt_persona["ok"])
                self.assertEqual(adapt_persona["adapt_id"], "adapt-1")
                self.assertIn("persona", adapt_persona)

                memory_recall, _ = _post_json_with_headers(
                    f"http://{host}:{port}/memory/recall",
                    {"query": "click ok", "top_k": 5},
                )
                self.assertEqual(memory_recall["query"], "click ok")
                self.assertIn("memories", memory_recall)

                memory_ingest, _ = _post_json_with_headers(
                    f"http://{host}:{port}/memory/ingest",
                    {"text": "operator preference: use dark mode", "source_id": "test-source"},
                )
                self.assertTrue(memory_ingest["ok"])
                self.assertEqual(memory_ingest["source_id"], "test-source")

                browser_status, _ = _get_json_with_headers(f"http://{host}:{port}/browser/status")
                self.assertIn("ok", browser_status)
                self.assertEqual(browser_status["transport"], "browser")

                browser_pages, _ = _get_json_with_headers(f"http://{host}:{port}/browser/pages")
                self.assertEqual(browser_pages["count"], 1)
                self.assertEqual(browser_pages["current_page_id"], "page-1")

                browser_action, _ = _post_json_with_headers(
                    f"http://{host}:{port}/browser/action",
                    {"type": "navigate", "target": "https://example.com"},
                )
                self.assertEqual(browser_action["status"], "ok")

                browser_nav, _ = _post_json_with_headers(
                    f"http://{host}:{port}/browser/navigate",
                    {"url": "https://example.com"},
                )
                self.assertEqual(browser_nav["status"], "ok")

                started_terminal, _ = _post_json_with_headers(
                    f"http://{host}:{port}/terminal/sessions",
                    {"max_chunks": 500},
                )
                terminal_id = started_terminal["id"]
                self.assertTrue(started_terminal["open"])

                terminal_sessions, _ = _get_json_with_headers(f"http://{host}:{port}/terminal/sessions")
                self.assertTrue(any(item["id"] == terminal_id for item in terminal_sessions))

                terminal_item, _ = _get_json_with_headers(f"http://{host}:{port}/terminal/sessions/{terminal_id}")
                self.assertEqual(terminal_item["id"], terminal_id)

                terminal_output, _ = _get_json_with_headers(
                    f"http://{host}:{port}/terminal/sessions/{terminal_id}/output?since_seq=0&limit=100"
                )
                self.assertIn("chunks", terminal_output)

                terminal_input, _ = _post_json_with_headers(
                    f"http://{host}:{port}/terminal/sessions/{terminal_id}/input",
                    {"input": "echo done\n"},
                )
                self.assertTrue(terminal_input["accepted"])

                closed_terminal, _ = _post_json_with_headers(
                    f"http://{host}:{port}/terminal/sessions/{terminal_id}/close",
                    {},
                )
                self.assertTrue(closed_terminal["closed"])

                events, _ = _get_json_with_headers(f"http://{host}:{port}/events?limit=10")
                self.assertGreaterEqual(len(events), 1)
                self.assertTrue(any(item.get("category") == "run" for item in events))

                history, _ = _get_json_with_headers(f"http://{host}:{port}/history?limit=5")
                self.assertGreaterEqual(len(history), 1)

                created_plan, _ = _post_json_with_headers(
                    f"http://{host}:{port}/plans",
                    {"objective": "click ok"},
                )
                self.assertEqual(created_plan["status"], "pending")
                plan_id = created_plan["id"]

                plan_list, _ = _get_json_with_headers(f"http://{host}:{port}/plans?limit=5")
                self.assertGreaterEqual(len(plan_list), 1)

                plan_item, _ = _get_json_with_headers(f"http://{host}:{port}/plans/{plan_id}")
                self.assertEqual(plan_item["id"], plan_id)

                approved_plan, _ = _post_json_with_headers(
                    f"http://{host}:{port}/plans/{plan_id}/approve",
                    {"execute": True},
                )
                self.assertEqual(approved_plan["status"], "executed")
                self.assertEqual(len(approved_plan.get("execution_results") or []), 1)

                with self.assertRaises(error.HTTPError) as err:
                    _post_json(
                        f"http://{host}:{port}/plans/{plan_id}/retry_failed",
                        {"allow_dangerous": True},
                    )
                self.assertEqual(err.exception.code, 400)
                err.exception.close()

                plan_stream = _get_text(
                    f"http://{host}:{port}/plans/{plan_id}/stream?timeout=2&interval=0.05"
                )
                self.assertIn("event: plan", plan_stream)
                self.assertIn("event: end", plan_stream)

                events_stream = _get_text(f"http://{host}:{port}/events/stream?timeout=1&interval=0.05&since_id=0")
                self.assertIn("event: audit", events_stream)

                undo_plan, _ = _post_json_with_headers(
                    f"http://{host}:{port}/plans/{plan_id}/undo",
                    {"mark_only": True},
                )
                self.assertEqual(undo_plan["plan_id"], plan_id)
                self.assertTrue(all(item.get("ok") for item in undo_plan["results"]))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_server_close_closes_browser_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            browser = _StubBrowserExecutor()
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
                browser_executor_factory=lambda: browser,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                browser_status, _ = _get_json_with_headers(f"http://{host}:{port}/browser/status")
                self.assertTrue(browser_status["ok"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertTrue(browser.closed)

    def test_token_auth_and_async_jobs(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            jobs_db = Path(tmp) / "jobs.db"
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(jobs_db),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/models")
                self.assertEqual(err.exception.code, 401)
                err.exception.close()

                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/plugins")
                self.assertEqual(err.exception.code, 401)
                err.exception.close()

                models = _get_json(f"http://{host}:{port}/models", token="secret")
                self.assertEqual(models[0]["name"], "local")

                plugins = _get_json(f"http://{host}:{port}/plugins", token="secret")
                self.assertGreaterEqual(len(plugins), 1)

                dashboard_html = _get_text(f"http://{host}:{port}/dashboard", token="secret")
                self.assertIn("NovaAdapt Core Dashboard", dashboard_html)
                self.assertIn("Approve Async", dashboard_html)

                dashboard_with_query = _get_text(f"http://{host}:{port}/dashboard?token=secret")
                self.assertIn("NovaAdapt Core Dashboard", dashboard_with_query)

                dashboard_data = _get_json(f"http://{host}:{port}/dashboard/data?token=secret")
                self.assertTrue(dashboard_data["health"]["ok"])
                self.assertIn("metrics", dashboard_data)
                self.assertIn("events", dashboard_data)

                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/events")
                self.assertEqual(err.exception.code, 401)
                err.exception.close()

                queued = _post_json(
                    f"http://{host}:{port}/run_async",
                    {"objective": "click ok"},
                    token="secret",
                )
                self.assertEqual(queued["status"], "queued")
                job_id = queued["job_id"]

                stream = _get_text(
                    f"http://{host}:{port}/jobs/{job_id}/stream?timeout=2&interval=0.05",
                    token="secret",
                )
                self.assertIn("event: job", stream)
                self.assertIn(job_id, stream)

                cancel = _post_json(
                    f"http://{host}:{port}/jobs/{job_id}/cancel",
                    {},
                    token="secret",
                )
                self.assertEqual(cancel["id"], job_id)

                # Poll briefly for completion.
                terminal = None
                for _ in range(30):
                    terminal = _get_json(f"http://{host}:{port}/jobs/{job_id}", token="secret")
                    if terminal["status"] in {"succeeded", "failed"}:
                        break
                    time.sleep(0.02)

                self.assertIsNotNone(terminal)
                self.assertIn(terminal["status"], {"succeeded", "running", "queued", "canceled"})

                created_plan = _post_json(
                    f"http://{host}:{port}/plans",
                    {"objective": "click ok"},
                    token="secret",
                )
                self.assertEqual(created_plan["status"], "pending")

                queued_plan = _post_json(
                    f"http://{host}:{port}/plans/{created_plan['id']}/approve_async",
                    {"execute": True},
                    token="secret",
                )
                self.assertEqual(queued_plan["status"], "queued")
                self.assertEqual(queued_plan["kind"], "plan_approval")
                approval_job_id = queued_plan["job_id"]

                terminal_plan_job = None
                for _ in range(30):
                    terminal_plan_job = _get_json(f"http://{host}:{port}/jobs/{approval_job_id}", token="secret")
                    if terminal_plan_job["status"] in {"succeeded", "failed", "canceled"}:
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(terminal_plan_job)
                self.assertIn(terminal_plan_job["status"], {"succeeded", "running", "queued", "canceled"})

                created_plan_2 = _post_json(
                    f"http://{host}:{port}/plans",
                    {"objective": "click ok again"},
                    token="secret",
                )
                rejected_plan = _post_json(
                    f"http://{host}:{port}/plans/{created_plan_2['id']}/reject",
                    {"reason": "manual deny"},
                    token="secret",
                )
                self.assertEqual(rejected_plan["status"], "rejected")

                events = _get_json(f"http://{host}:{port}/events?limit=20", token="secret")
                self.assertGreaterEqual(len(events), 1)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            # Verify job history is retained across server restart.
            server2 = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(jobs_db),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host2, port2 = server2.server_address
            thread2 = threading.Thread(target=server2.serve_forever, daemon=True)
            thread2.start()
            try:
                jobs_list = _get_json(f"http://{host2}:{port2}/jobs?limit=10", token="secret")
                self.assertGreaterEqual(len(jobs_list), 1)
            finally:
                server2.shutdown()
                server2.server_close()
                thread2.join(timeout=2)

    def test_cancel_running_plan_approval_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _SlowRouter(),
                directshell_factory=_SlowDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(Path(tmp) / "jobs.db"),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                created_plan = _post_json(
                    f"http://{host}:{port}/plans",
                    {"objective": "slow multi click"},
                    token="secret",
                )
                plan_id = created_plan["id"]

                queued_plan = _post_json(
                    f"http://{host}:{port}/plans/{plan_id}/approve_async",
                    {"execute": True, "allow_dangerous": True},
                    token="secret",
                )
                job_id = queued_plan["job_id"]

                saw_running = False
                for _ in range(100):
                    item = _get_json(f"http://{host}:{port}/jobs/{job_id}", token="secret")
                    if item["status"] == "running":
                        saw_running = True
                        break
                    if item["status"] in {"failed", "succeeded", "canceled"}:
                        break
                    time.sleep(0.01)
                self.assertTrue(saw_running)

                cancel_payload = _post_json(
                    f"http://{host}:{port}/jobs/{job_id}/cancel",
                    {},
                    token="secret",
                )
                self.assertEqual(cancel_payload["id"], job_id)

                terminal = None
                for _ in range(200):
                    terminal = _get_json(f"http://{host}:{port}/jobs/{job_id}", token="secret")
                    if terminal["status"] in {"succeeded", "failed", "canceled"}:
                        break
                    time.sleep(0.01)
                self.assertIsNotNone(terminal)
                self.assertEqual(terminal["status"], "canceled")

                canceled_plan = _get_json(f"http://{host}:{port}/plans/{plan_id}", token="secret")
                self.assertEqual(canceled_plan["status"], "failed")
                self.assertIn("canceled", str(canceled_plan.get("execution_error", "")).lower())
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_retry_failed_async_route_queues_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            _FlakyDirectShell.attempts = 0
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_FlakyDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(Path(tmp) / "jobs.db"),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                created_plan = _post_json(
                    f"http://{host}:{port}/plans",
                    {"objective": "click ok"},
                    token="secret",
                )
                plan_id = created_plan["id"]

                failed_plan = _post_json(
                    f"http://{host}:{port}/plans/{plan_id}/approve",
                    {"execute": True},
                    token="secret",
                )
                self.assertEqual(failed_plan["status"], "failed")

                queued_retry = _post_json(
                    f"http://{host}:{port}/plans/{plan_id}/retry_failed_async",
                    {"allow_dangerous": True, "action_retry_attempts": 2, "action_retry_backoff_seconds": 0.0},
                    token="secret",
                )
                self.assertEqual(queued_retry["status"], "queued")
                self.assertEqual(queued_retry["kind"], "plan_retry_failed")
                retry_job_id = queued_retry["job_id"]

                terminal_retry_job = None
                for _ in range(40):
                    terminal_retry_job = _get_json(f"http://{host}:{port}/jobs/{retry_job_id}", token="secret")
                    if terminal_retry_job["status"] in {"succeeded", "failed", "canceled"}:
                        break
                    time.sleep(0.02)
                self.assertIsNotNone(terminal_retry_job)
                self.assertEqual(terminal_retry_job["status"], "succeeded")

                retried_plan = _get_json(f"http://{host}:{port}/plans/{plan_id}", token="secret")
                self.assertEqual(retried_plan["status"], "executed")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_request_id_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                body, headers = _get_json_with_headers(
                    f"http://{host}:{port}/models",
                    token="secret",
                    request_id="rid-123",
                )
                self.assertEqual(body[0]["name"], "local")
                self.assertEqual(headers.get("X-Request-ID"), "rid-123")

                run, headers = _post_json_with_headers(
                    f"http://{host}:{port}/run",
                    {"objective": "click ok"},
                    token="secret",
                    request_id="rid-xyz",
                )
                self.assertEqual(run["request_id"], "rid-xyz")
                self.assertEqual(headers.get("X-Request-ID"), "rid-xyz")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_request_logs_redact_query_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            stream = io.StringIO()
            logger = logging.getLogger("novaadapt.tests.server.log_redaction")
            logger.setLevel(logging.INFO)
            logger.handlers = []
            logger.propagate = False
            handler = logging.StreamHandler(stream)
            logger.addHandler(handler)

            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                log_requests=True,
                logger=logger,
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                html = _get_text(f"http://{host}:{port}/dashboard?token=secret")
                self.assertIn("NovaAdapt Core Dashboard", html)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
                logger.removeHandler(handler)
                handler.close()

            output = stream.getvalue()
            self.assertIn("/dashboard?token=redacted", output)
            self.assertNotIn("token=secret", output)

    def test_metrics_endpoint_and_auth(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                with self.assertRaises(error.HTTPError) as err:
                    _get_text(f"http://{host}:{port}/metrics")
                self.assertEqual(err.exception.code, 401)
                err.exception.close()

                _ = _get_json(f"http://{host}:{port}/models", token="secret")
                metrics = _get_text(f"http://{host}:{port}/metrics", token="secret")
                self.assertIn("novaadapt_core_requests_total", metrics)
                self.assertIn("novaadapt_core_unauthorized_total", metrics)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_rate_limit_and_max_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                rate_limit_rps=1,
                rate_limit_burst=1,
                max_request_body_bytes=128,
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                _ = _get_json(f"http://{host}:{port}/models", token="secret")
                with self.assertRaises(error.HTTPError) as err:
                    _get_json(f"http://{host}:{port}/models", token="secret")
                self.assertEqual(err.exception.code, 429)
                err.exception.close()

                time.sleep(1.05)
                with self.assertRaises(error.HTTPError) as err:
                    _post_json(
                        f"http://{host}:{port}/run",
                        {"objective": "x" * 1024},
                        token="secret",
                    )
                self.assertEqual(err.exception.code, 413)
                err.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_per_client_rate_limiter_keys_are_isolated(self):
        limiter = _PerClientSlidingWindowRateLimiter(burst=1, window_seconds=1.0, idle_ttl_seconds=60.0)
        self.assertTrue(limiter.allow("client-a"))
        self.assertFalse(limiter.allow("client-a"))
        self.assertTrue(limiter.allow("client-b"))

    def test_parse_trusted_proxy_cidrs(self):
        networks = _parse_trusted_proxy_cidrs(["127.0.0.1/32", "10.0.0.1"])
        self.assertEqual(len(networks), 2)
        with self.assertRaises(ValueError):
            _parse_trusted_proxy_cidrs(["invalid-cidr"])

    def test_rate_limit_ignores_forwarded_for_without_trusted_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                rate_limit_rps=1,
                rate_limit_burst=1,
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                _ = _get_json(
                    f"http://{host}:{port}/models",
                    token="secret",
                    extra_headers={"X-Forwarded-For": "198.51.100.20"},
                )
                with self.assertRaises(error.HTTPError) as err:
                    _get_json(
                        f"http://{host}:{port}/models",
                        token="secret",
                        extra_headers={"X-Forwarded-For": "198.51.100.21"},
                    )
                self.assertEqual(err.exception.code, 429)
                err.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_rate_limit_uses_forwarded_for_with_trusted_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                rate_limit_rps=1,
                rate_limit_burst=1,
                trusted_proxy_cidrs=["127.0.0.1/32"],
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                _ = _get_json(
                    f"http://{host}:{port}/models",
                    token="secret",
                    extra_headers={"X-Forwarded-For": "198.51.100.20"},
                )
                _ = _get_json(
                    f"http://{host}:{port}/models",
                    token="secret",
                    extra_headers={"X-Forwarded-For": "198.51.100.21"},
                )
                with self.assertRaises(error.HTTPError) as err:
                    _get_json(
                        f"http://{host}:{port}/models",
                        token="secret",
                        extra_headers={"X-Forwarded-For": "198.51.100.21"},
                    )
                self.assertEqual(err.exception.code, 429)
                err.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_idempotency_replay_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(Path(tmp) / "jobs.db"),
                idempotency_db_path=str(Path(tmp) / "idempotency.db"),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                first, _ = _post_json_with_headers(
                    f"http://{host}:{port}/run_async",
                    {"objective": "click ok"},
                    token="secret",
                    idempotency_key="idem-1",
                )
                second, headers = _post_json_with_headers(
                    f"http://{host}:{port}/run_async",
                    {"objective": "click ok"},
                    token="secret",
                    idempotency_key="idem-1",
                )
                self.assertEqual(first["job_id"], second["job_id"])
                self.assertEqual(headers.get("X-Idempotency-Replayed"), "true")
                self.assertEqual(headers.get("Idempotency-Key"), "idem-1")

                with self.assertRaises(error.HTTPError) as err:
                    _post_json(
                        f"http://{host}:{port}/run_async",
                        {"objective": "different"},
                        token="secret",
                        idempotency_key="idem-1",
                    )
                self.assertEqual(err.exception.code, 409)
                err.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_retry_failed_async_idempotency_replay_and_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            _FlakyDirectShell.attempts = 0
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_FlakyDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret",
                jobs_db_path=str(Path(tmp) / "jobs.db"),
                idempotency_db_path=str(Path(tmp) / "idempotency.db"),
                audit_db_path=str(Path(tmp) / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                created_plan = _post_json(
                    f"http://{host}:{port}/plans",
                    {"objective": "click ok"},
                    token="secret",
                )
                plan_id = created_plan["id"]

                failed_plan = _post_json(
                    f"http://{host}:{port}/plans/{plan_id}/approve",
                    {"execute": True},
                    token="secret",
                )
                self.assertEqual(failed_plan["status"], "failed")

                first, _ = _post_json_with_headers(
                    f"http://{host}:{port}/plans/{plan_id}/retry_failed_async",
                    {"allow_dangerous": True, "action_retry_attempts": 2, "action_retry_backoff_seconds": 0.0},
                    token="secret",
                    idempotency_key="idem-retry-1",
                )
                second, headers = _post_json_with_headers(
                    f"http://{host}:{port}/plans/{plan_id}/retry_failed_async",
                    {"allow_dangerous": True, "action_retry_attempts": 2, "action_retry_backoff_seconds": 0.0},
                    token="secret",
                    idempotency_key="idem-retry-1",
                )
                self.assertEqual(first["job_id"], second["job_id"])
                self.assertEqual(headers.get("X-Idempotency-Replayed"), "true")
                self.assertEqual(headers.get("Idempotency-Key"), "idem-retry-1")

                with self.assertRaises(error.HTTPError) as err:
                    _post_json(
                        f"http://{host}:{port}/plans/{plan_id}/retry_failed_async",
                        {"allow_dangerous": False, "action_retry_attempts": 0, "action_retry_backoff_seconds": 0.0},
                        token="secret",
                        idempotency_key="idem-retry-1",
                    )
                self.assertEqual(err.exception.code, 409)
                err.exception.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_audit_retention_prunes_expired_events_on_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            events_db = Path(tmp) / "events.db"
            service = NovaAdaptService(
                default_config=Path("unused.json"),
                db_path=Path(tmp) / "actions.db",
                plans_db_path=Path(tmp) / "plans.db",
                router_loader=lambda _path: _StubRouter(),
                directshell_factory=_StubDirectShell,
            )
            server = create_server(
                "127.0.0.1",
                0,
                service,
                audit_db_path=str(events_db),
                audit_retention_seconds=1,
                audit_cleanup_interval_seconds=0,
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                _post_json(f"http://{host}:{port}/run", {"objective": "first run"})
                first_events = _get_json(f"http://{host}:{port}/events?limit=10")
                self.assertGreaterEqual(len(first_events), 1)
                stale_event_id = int(first_events[0]["id"])

                old_timestamp = datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat()
                with closing(sqlite3.connect(events_db)) as conn:
                    conn.execute(
                        "UPDATE audit_events SET created_at = ? WHERE id = ?",
                        (old_timestamp, stale_event_id),
                    )
                    conn.commit()

                _post_json(f"http://{host}:{port}/run", {"objective": "second run"})
                second_events = _get_json(f"http://{host}:{port}/events?limit=10")
                ids = {int(item["id"]) for item in second_events}
                self.assertNotIn(stale_event_id, ids)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


def _get_json(url: str, token: str | None = None, extra_headers: dict[str, str] | None = None):
    return _get_json_with_headers(url=url, token=token, extra_headers=extra_headers)[0]


def _post_json(
    url: str,
    payload: dict,
    token: str | None = None,
    idempotency_key: str | None = None,
    extra_headers: dict[str, str] | None = None,
):
    return _post_json_with_headers(
        url=url,
        payload=payload,
        token=token,
        idempotency_key=idempotency_key,
        extra_headers=extra_headers,
    )[0]


def _get_text(url: str, token: str | None = None, extra_headers: dict[str, str] | None = None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.setdefault("Connection", "close")
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(url=url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=5) as response:
            return response.read().decode("utf-8")
    except error.HTTPError as exc:
        _reraise_http_error_with_buffer(exc)


def _get_json_with_headers(
    url: str,
    token: str | None = None,
    request_id: str | None = None,
    extra_headers: dict[str, str] | None = None,
):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    headers.setdefault("Connection", "close")
    if request_id:
        headers["X-Request-ID"] = request_id
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(url=url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body, dict(response.headers)
    except error.HTTPError as exc:
        _reraise_http_error_with_buffer(exc)


def _post_json_with_headers(
    url: str,
    payload: dict,
    token: str | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
    extra_headers: dict[str, str] | None = None,
):
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Connection": "close"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if request_id:
        headers["X-Request-ID"] = request_id
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    if extra_headers:
        headers.update(extra_headers)
    req = request.Request(
        url=url,
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            body = json.loads(response.read().decode("utf-8"))
            return body, dict(response.headers)
    except error.HTTPError as exc:
        _reraise_http_error_with_buffer(exc)


def _reraise_http_error_with_buffer(exc: error.HTTPError) -> None:
    raw = b""
    url = ""
    code = 500
    msg = "HTTP Error"
    hdrs = None
    try:
        url = exc.geturl() or ""
        code = int(exc.code)
        msg = str(exc.msg)
        hdrs = exc.headers
        raw = exc.read()
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
    buffer = io.BytesIO(raw)
    buffered = error.HTTPError(url=url, code=code, msg=msg, hdrs=hdrs, fp=buffer)
    buffered.file = buffer
    buffered.read = lambda amt=None, _raw=raw: _raw if amt is None else _raw[: max(0, int(amt))]
    raise buffered from None


if __name__ == "__main__":
    unittest.main()
