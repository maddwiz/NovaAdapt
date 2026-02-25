import unittest

from novaadapt_core.mcp_server import NovaAdaptMCPServer


class _StubService:
    def run(self, payload):
        return {"status": "ok", "objective": payload.get("objective")}

    def models(self):
        return [{"name": "local"}]

    def check(self, model_names=None, probe_prompt="Reply with: OK"):
        return [{"name": "local", "ok": True, "probe": probe_prompt, "models": model_names}]

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


class MCPServerTests(unittest.TestCase):
    def test_initialize_and_tools(self):
        server = NovaAdaptMCPServer(service=_StubService())

        init = server.handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertIn("result", init)
        self.assertEqual(init["result"]["serverInfo"]["name"], "NovaAdapt MCP")

        tools = server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [item["name"] for item in tools["result"]["tools"]]
        self.assertIn("novaadapt_run", names)
        self.assertIn("novaadapt_models", names)
        self.assertIn("novaadapt_events", names)
        self.assertIn("novaadapt_plan_create", names)
        self.assertIn("novaadapt_plan_approve", names)
        self.assertIn("novaadapt_plan_undo", names)

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

    def test_unknown_method_returns_error(self):
        server = NovaAdaptMCPServer(service=_StubService())
        resp = server.handle_request({"jsonrpc": "2.0", "id": 5, "method": "unknown/method"})
        self.assertIn("error", resp)


if __name__ == "__main__":
    unittest.main()
