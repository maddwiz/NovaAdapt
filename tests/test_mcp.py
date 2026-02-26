import unittest

from novaadapt_core.mcp_server import NovaAdaptMCPServer


class _StubService:
    def run(self, payload):
        return {"status": "ok", "objective": payload.get("objective")}

    def models(self):
        return [{"name": "local"}]

    def check(self, model_names=None, probe_prompt="Reply with: OK"):
        return [{"name": "local", "ok": True, "probe": probe_prompt, "models": model_names}]

    def plugins(self):
        return [{"name": "novabridge"}, {"name": "novablox"}]

    def plugin_health(self, plugin_name):
        return {"plugin": plugin_name, "ok": True}

    def plugin_call(self, plugin_name, payload):
        return {"plugin": plugin_name, "route": payload.get("route"), "ok": True}

    def history(self, limit=20):
        return [{"id": 1, "limit": limit}]

    def events(self, limit=100, category=None, entity_type=None, entity_id=None, since_id=None):
        return [
            {
                "id": 10,
                "category": category or "run",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "since_id": since_id,
                "limit": limit,
            }
        ]

    def events_wait(
        self,
        timeout_seconds=30.0,
        interval_seconds=0.25,
        limit=100,
        category=None,
        entity_type=None,
        entity_id=None,
        since_id=None,
    ):
        return [
            {
                "id": 11,
                "category": category or "run",
                "timeout_seconds": timeout_seconds,
                "interval_seconds": interval_seconds,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "since_id": since_id,
                "limit": limit,
            }
        ]

    def create_plan(self, payload):
        return {"id": "plan-1", "objective": payload.get("objective"), "status": "pending"}

    def list_plans(self, limit=50):
        return [{"id": "plan-1", "status": "pending", "limit": limit}]

    def get_plan(self, plan_id):
        if plan_id != "plan-1":
            return None
        return {"id": "plan-1", "status": "pending"}

    def approve_plan(self, plan_id, payload):
        return {"id": plan_id, "status": "executed", "execute": payload.get("execute", True)}

    def reject_plan(self, plan_id, reason=None):
        return {"id": plan_id, "status": "rejected", "reason": reason}

    def undo_plan(self, plan_id, payload):
        return {"plan_id": plan_id, "executed": payload.get("execute", False), "results": [{"id": 1, "ok": True}]}

    def record_feedback(self, payload):
        return {"ok": True, "id": "feedback-1", "rating": payload.get("rating")}

    def memory_status(self):
        return {"ok": True, "enabled": True, "backend": "novaspine-http"}

    def novaprime_status(self):
        return {"ok": True, "enabled": True, "backend": "novaprime-http"}

    def sib_status(self):
        return {"ok": True, "plugin": "sib_bridge"}

    def sib_realm(self, player_id: str, realm: str):
        return {"ok": True, "player_id": player_id, "realm": realm}

    def sib_companion_state(self, adapt_id: str, state: dict):
        return {"ok": True, "adapt_id": adapt_id, "state": state}

    def sib_companion_speak(self, adapt_id: str, text: str, channel: str = "in_game"):
        return {"ok": True, "adapt_id": adapt_id, "text": text, "channel": channel}

    def sib_phase_event(self, event_type: str, payload=None):
        return {"ok": True, "event_type": event_type, "payload": payload or {}}

    def sib_resonance_start(self, player_id: str, player_profile=None):
        return {"ok": True, "player_id": player_id, "player_profile": player_profile or {}}

    def sib_resonance_result(self, player_id: str, adapt_id: str, accepted: bool):
        return {"ok": True, "player_id": player_id, "adapt_id": adapt_id, "accepted": bool(accepted)}

    def adapt_toggle_get(self, adapt_id: str):
        return {"adapt_id": adapt_id, "mode": "ask_only"}

    def adapt_toggle_set(self, adapt_id: str, mode: str, *, source: str = "mcp"):
        return {"adapt_id": adapt_id, "mode": mode, "source": source}

    def adapt_bond_get(self, adapt_id: str):
        return {"adapt_id": adapt_id, "player_id": "player-1", "verified": True}

    def memory_recall(self, query, top_k=10):
        return {"query": query, "top_k": top_k, "count": 1, "memories": [{"content": "remembered"}]}

    def memory_ingest(self, text, source_id="", metadata=None):
        return {"ok": True, "source_id": source_id, "metadata": metadata or {}, "result": {"ingested": text}}

    def browser_status(self):
        return {"ok": True, "transport": "browser", "capabilities": ["navigate", "click_selector"]}

    def browser_pages(self):
        return {
            "status": "ok",
            "count": 1,
            "current_page_id": "page-1",
            "pages": [{"page_id": "page-1", "url": "https://example.com", "current": True}],
        }

    def browser_action(self, payload):
        action = payload.get("action") if isinstance(payload.get("action"), dict) else payload
        return {"status": "ok", "output": "browser action", "action": action}

    def browser_close(self):
        return {"status": "ok", "output": "browser session closed"}


class MCPServerTests(unittest.TestCase):
    def test_initialize_and_tools(self):
        server = NovaAdaptMCPServer(service=_StubService())

        init = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertIn("result", init)
        self.assertEqual(init["result"]["serverInfo"]["name"], "NovaAdapt MCP")

        tools = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [item["name"] for item in tools["result"]["tools"]]
        self.assertIn("novaadapt_run", names)
        self.assertIn("novaadapt_swarm_run", names)
        self.assertIn("novaadapt_models", names)
        self.assertIn("novaadapt_plugins", names)
        self.assertIn("novaadapt_plugin_health", names)
        self.assertIn("novaadapt_plugin_call", names)
        self.assertIn("novaadapt_events", names)
        self.assertIn("novaadapt_events_wait", names)
        self.assertIn("novaadapt_plan_create", names)
        self.assertIn("novaadapt_plan_approve", names)
        self.assertIn("novaadapt_plan_undo", names)
        self.assertIn("novaadapt_feedback", names)
        self.assertIn("novaadapt_memory_status", names)
        self.assertIn("novaadapt_novaprime_status", names)
        self.assertIn("novaadapt_sib_status", names)
        self.assertIn("novaadapt_sib_realm", names)
        self.assertIn("novaadapt_sib_companion_state", names)
        self.assertIn("novaadapt_sib_companion_speak", names)
        self.assertIn("novaadapt_sib_phase_event", names)
        self.assertIn("novaadapt_sib_resonance_start", names)
        self.assertIn("novaadapt_sib_resonance_result", names)
        self.assertIn("novaadapt_adapt_toggle_get", names)
        self.assertIn("novaadapt_adapt_toggle_set", names)
        self.assertIn("novaadapt_adapt_bond_get", names)
        self.assertIn("novaadapt_memory_recall", names)
        self.assertIn("novaadapt_memory_ingest", names)
        self.assertIn("novaadapt_browser_status", names)
        self.assertIn("novaadapt_browser_pages", names)
        self.assertIn("novaadapt_browser_action", names)
        self.assertIn("novaadapt_browser_navigate", names)
        self.assertIn("novaadapt_browser_click", names)
        self.assertIn("novaadapt_browser_fill", names)
        self.assertIn("novaadapt_browser_extract_text", names)
        self.assertIn("novaadapt_browser_screenshot", names)
        self.assertIn("novaadapt_browser_wait_for_selector", names)
        self.assertIn("novaadapt_browser_evaluate_js", names)
        self.assertIn("novaadapt_browser_close", names)

    def test_tools_call(self):
        server = NovaAdaptMCPServer(service=_StubService())

        run_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_run",
                    "arguments": {"objective": "demo"},
                },
            }
        )
        payload = run_resp["result"]["content"][0]["json"]
        self.assertEqual(payload["objective"], "demo")

        swarm_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_swarm_run",
                    "arguments": {"objectives": ["demo-a", "demo-b"]},
                },
            }
        )
        swarm_payload = swarm_resp["result"]["content"][0]["json"]
        self.assertEqual(swarm_payload["submitted_jobs"], 2)

        history_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_history",
                    "arguments": {"limit": 7},
                },
            }
        )
        history_payload = history_resp["result"]["content"][0]["json"]
        self.assertEqual(history_payload[0]["limit"], 7)

        plugins_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 401,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_plugins",
                    "arguments": {},
                },
            }
        )
        plugins_payload = plugins_resp["result"]["content"][0]["json"]
        self.assertEqual(plugins_payload[0]["name"], "novabridge")

        plugin_health_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 402,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_plugin_health",
                    "arguments": {"plugin": "novabridge"},
                },
            }
        )
        plugin_health_payload = plugin_health_resp["result"]["content"][0]["json"]
        self.assertTrue(plugin_health_payload["ok"])

        plugin_call_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 403,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_plugin_call",
                    "arguments": {"plugin": "novablox", "route": "/health", "method": "GET"},
                },
            }
        )
        plugin_call_payload = plugin_call_resp["result"]["content"][0]["json"]
        self.assertEqual(plugin_call_payload["plugin"], "novablox")

        events_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_events",
                    "arguments": {"limit": 5, "category": "plans", "since_id": 9},
                },
            }
        )
        events_payload = events_resp["result"]["content"][0]["json"]
        self.assertEqual(events_payload[0]["category"], "plans")
        self.assertEqual(events_payload[0]["since_id"], 9)

        events_wait_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 42,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_events_wait",
                    "arguments": {"timeout_seconds": 2.0, "interval_seconds": 0.1, "entity_type": "plan"},
                },
            }
        )
        events_wait_payload = events_wait_resp["result"]["content"][0]["json"]
        self.assertEqual(events_wait_payload[0]["entity_type"], "plan")
        self.assertEqual(events_wait_payload[0]["timeout_seconds"], 2.0)

        plan_create_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_plan_create",
                    "arguments": {"objective": "build dashboard"},
                },
            }
        )
        plan_create_payload = plan_create_resp["result"]["content"][0]["json"]
        self.assertEqual(plan_create_payload["status"], "pending")

        plan_approve_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_plan_approve",
                    "arguments": {"id": "plan-1", "execute": True},
                },
            }
        )
        plan_approve_payload = plan_approve_resp["result"]["content"][0]["json"]
        self.assertEqual(plan_approve_payload["status"], "executed")

        plan_reject_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_plan_reject",
                    "arguments": {"id": "plan-1", "reason": "unsafe"},
                },
            }
        )
        plan_reject_payload = plan_reject_resp["result"]["content"][0]["json"]
        self.assertEqual(plan_reject_payload["status"], "rejected")

        plan_undo_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_plan_undo",
                    "arguments": {"id": "plan-1", "mark_only": True},
                },
            }
        )
        plan_undo_payload = plan_undo_resp["result"]["content"][0]["json"]
        self.assertEqual(plan_undo_payload["plan_id"], "plan-1")

        feedback_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_feedback",
                    "arguments": {"rating": 9, "objective": "demo", "notes": "solid"},
                },
            }
        )
        feedback_payload = feedback_resp["result"]["content"][0]["json"]
        self.assertEqual(feedback_payload["rating"], 9)

        memory_status_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 91,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_memory_status",
                    "arguments": {},
                },
            }
        )
        memory_status_payload = memory_status_resp["result"]["content"][0]["json"]
        self.assertTrue(memory_status_payload["ok"])

        novaprime_status_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 911,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_novaprime_status",
                    "arguments": {},
                },
            }
        )
        novaprime_status_payload = novaprime_status_resp["result"]["content"][0]["json"]
        self.assertTrue(novaprime_status_payload["ok"])

        sib_status_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9111,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_sib_status",
                    "arguments": {},
                },
            }
        )
        sib_status_payload = sib_status_resp["result"]["content"][0]["json"]
        self.assertTrue(sib_status_payload["ok"])

        sib_realm_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9112,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_sib_realm",
                    "arguments": {"player_id": "player-1", "realm": "game_world"},
                },
            }
        )
        sib_realm_payload = sib_realm_resp["result"]["content"][0]["json"]
        self.assertEqual(sib_realm_payload["realm"], "game_world")

        sib_state_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9113,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_sib_companion_state",
                    "arguments": {"adapt_id": "adapt-1", "state": {"mode": "combat"}},
                },
            }
        )
        sib_state_payload = sib_state_resp["result"]["content"][0]["json"]
        self.assertEqual(sib_state_payload["adapt_id"], "adapt-1")

        sib_speak_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9114,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_sib_companion_speak",
                    "arguments": {"adapt_id": "adapt-1", "text": "On your six", "channel": "in_game"},
                },
            }
        )
        sib_speak_payload = sib_speak_resp["result"]["content"][0]["json"]
        self.assertEqual(sib_speak_payload["text"], "On your six")

        sib_phase_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9115,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_sib_phase_event",
                    "arguments": {"event_type": "entropy_spike", "payload": {"severity": "high"}},
                },
            }
        )
        sib_phase_payload = sib_phase_resp["result"]["content"][0]["json"]
        self.assertEqual(sib_phase_payload["event_type"], "entropy_spike")

        sib_start_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9116,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_sib_resonance_start",
                    "arguments": {"player_id": "player-1", "player_profile": {"class": "sentinel"}},
                },
            }
        )
        sib_start_payload = sib_start_resp["result"]["content"][0]["json"]
        self.assertEqual(sib_start_payload["player_id"], "player-1")

        sib_result_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9117,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_sib_resonance_result",
                    "arguments": {"player_id": "player-1", "adapt_id": "adapt-1", "accepted": True},
                },
            }
        )
        sib_result_payload = sib_result_resp["result"]["content"][0]["json"]
        self.assertTrue(sib_result_payload["accepted"])

        adapt_toggle_get_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 912,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_adapt_toggle_get",
                    "arguments": {"adapt_id": "adapt-1"},
                },
            }
        )
        adapt_toggle_get_payload = adapt_toggle_get_resp["result"]["content"][0]["json"]
        self.assertEqual(adapt_toggle_get_payload["mode"], "ask_only")

        adapt_toggle_set_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 913,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_adapt_toggle_set",
                    "arguments": {"adapt_id": "adapt-1", "mode": "in_game_only"},
                },
            }
        )
        adapt_toggle_set_payload = adapt_toggle_set_resp["result"]["content"][0]["json"]
        self.assertEqual(adapt_toggle_set_payload["mode"], "in_game_only")

        adapt_bond_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 914,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_adapt_bond_get",
                    "arguments": {"adapt_id": "adapt-1"},
                },
            }
        )
        adapt_bond_payload = adapt_bond_resp["result"]["content"][0]["json"]
        self.assertEqual(adapt_bond_payload["adapt_id"], "adapt-1")
        self.assertTrue(adapt_bond_payload["cached"]["verified"])

        memory_recall_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 92,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_memory_recall",
                    "arguments": {"query": "excel report", "top_k": 4},
                },
            }
        )
        memory_recall_payload = memory_recall_resp["result"]["content"][0]["json"]
        self.assertEqual(memory_recall_payload["query"], "excel report")
        self.assertEqual(memory_recall_payload["top_k"], 4)

        memory_ingest_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 93,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_memory_ingest",
                    "arguments": {"text": "remember this", "source_id": "mcp-test"},
                },
            }
        )
        memory_ingest_payload = memory_ingest_resp["result"]["content"][0]["json"]
        self.assertEqual(memory_ingest_payload["source_id"], "mcp-test")

        browser_status_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 94,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_status",
                    "arguments": {},
                },
            }
        )
        browser_status_payload = browser_status_resp["result"]["content"][0]["json"]
        self.assertTrue(browser_status_payload["ok"])

        browser_pages_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 941,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_pages",
                    "arguments": {},
                },
            }
        )
        browser_pages_payload = browser_pages_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_pages_payload["count"], 1)
        self.assertEqual(browser_pages_payload["current_page_id"], "page-1")

        browser_action_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 95,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_action",
                    "arguments": {"action": {"type": "navigate", "target": "https://example.com"}},
                },
            }
        )
        browser_action_payload = browser_action_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_action_payload["action"]["type"], "navigate")

        browser_nav_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 96,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_navigate",
                    "arguments": {"url": "https://example.com"},
                },
            }
        )
        browser_nav_payload = browser_nav_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_nav_payload["action"]["type"], "navigate")

        browser_click_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 97,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_click",
                    "arguments": {"selector": "#submit"},
                },
            }
        )
        browser_click_payload = browser_click_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_click_payload["action"]["type"], "click_selector")

        browser_fill_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 98,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_fill",
                    "arguments": {"selector": "#name", "value": "NovaAdapt"},
                },
            }
        )
        browser_fill_payload = browser_fill_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_fill_payload["action"]["type"], "fill")

        browser_extract_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 99,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_extract_text",
                    "arguments": {"selector": "h1"},
                },
            }
        )
        browser_extract_payload = browser_extract_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_extract_payload["action"]["type"], "extract_text")

        browser_shot_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 100,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_screenshot",
                    "arguments": {"path": "demo.png"},
                },
            }
        )
        browser_shot_payload = browser_shot_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_shot_payload["action"]["type"], "screenshot")

        browser_wait_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 101,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_wait_for_selector",
                    "arguments": {"selector": "#app"},
                },
            }
        )
        browser_wait_payload = browser_wait_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_wait_payload["action"]["type"], "wait_for_selector")

        browser_eval_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 102,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_evaluate_js",
                    "arguments": {"script": "() => 42"},
                },
            }
        )
        browser_eval_payload = browser_eval_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_eval_payload["action"]["type"], "evaluate_js")

        browser_close_resp = server.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 103,
                "method": "tools/call",
                "params": {
                    "name": "novaadapt_browser_close",
                    "arguments": {},
                },
            }
        )
        browser_close_payload = browser_close_resp["result"]["content"][0]["json"]
        self.assertEqual(browser_close_payload["status"], "ok")

    def test_unknown_method_returns_error(self):
        server = NovaAdaptMCPServer(service=_StubService())
        resp = server.handle_request({"jsonrpc": "2.0", "id": 5, "method": "unknown/method"})
        self.assertIn("error", resp)


if __name__ == "__main__":
    unittest.main()
