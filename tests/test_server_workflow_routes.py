from __future__ import annotations

from unittest import TestCase

from novaadapt_core.server_workflow_routes import (
    get_workflow_item,
    get_workflows_list,
    get_workflows_status,
    post_workflows_advance,
    post_workflows_resume,
    post_workflows_start,
)


class _StubHandler:
    def __init__(self) -> None:
        self.last_status = 0
        self.last_payload: dict[str, object] | None = None

    def _send_json(self, status: int, payload: dict[str, object]):
        self.last_status = int(status)
        self.last_payload = payload


class _StubService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def workflows_status(self, *, context: str = "api"):
        self.calls.append(("status", {"context": context}))
        return {"ok": True, "enabled": False}

    def workflows_list(self, *, limit: int = 50, status: str = "", context: str = "api"):
        self.calls.append(("list", {"limit": limit, "status": status, "context": context}))
        return {"ok": True, "count": 1, "workflows": [{"workflow_id": "wf-1"}]}

    def workflows_get(self, workflow_id: str, *, context: str = "api"):
        self.calls.append(("get", {"workflow_id": workflow_id, "context": context}))
        return {"ok": True, "workflow_id": workflow_id}

    def workflows_start(self, objective: str, *, steps=None, metadata=None, workflow_id: str = "", context: str = "api"):
        self.calls.append(
            (
                "start",
                {
                    "objective": objective,
                    "steps": steps,
                    "metadata": metadata,
                    "workflow_id": workflow_id,
                    "context": context,
                },
            )
        )
        return {"ok": True, "workflow_id": workflow_id or "wf-new"}

    def workflows_advance(self, workflow_id: str, *, result=None, error: str = "", context: str = "api"):
        self.calls.append(("advance", {"workflow_id": workflow_id, "result": result, "error": error, "context": context}))
        return {"ok": True, "workflow_id": workflow_id}

    def workflows_resume(self, workflow_id: str, *, context: str = "api"):
        self.calls.append(("resume", {"workflow_id": workflow_id, "context": context}))
        return {"ok": True, "workflow_id": workflow_id}


def _single(query: dict[str, list[str]], key: str):
    values = query.get(key) or []
    return values[0] if values else None


class WorkflowRouteTests(TestCase):
    def test_get_status_and_list(self):
        handler = _StubHandler()
        service = _StubService()
        self.assertEqual(get_workflows_status(handler, service, _single, {"context": ["api"]}), 200)
        self.assertEqual(get_workflows_list(handler, service, _single, {"limit": ["7"], "status": ["running"]}), 200)
        self.assertEqual(handler.last_status, 200)
        self.assertEqual(service.calls[1][1]["limit"], 7)

    def test_get_item_requires_workflow_id(self):
        handler = _StubHandler()
        service = _StubService()
        with self.assertRaisesRegex(ValueError, "'workflow_id' is required"):
            get_workflow_item(handler, service, _single, {})

    def test_post_routes(self):
        handler = _StubHandler()
        service = _StubService()
        self.assertEqual(
            post_workflows_start(
                handler,
                service,
                {"objective": "patrol", "steps": [{"name": "scan"}], "workflow_id": "wf-7"},
            ),
            200,
        )
        self.assertEqual(
            post_workflows_advance(
                handler,
                service,
                {"workflow_id": "wf-7", "result": {"ok": True}},
            ),
            200,
        )
        self.assertEqual(post_workflows_resume(handler, service, {"workflow_id": "wf-7"}), 200)


if __name__ == "__main__":
    import unittest

    unittest.main()
