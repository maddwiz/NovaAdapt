import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from novaadapt_core.directshell import ExecutionResult
from novaadapt_core.server import create_server
from novaadapt_core.service import NovaAdaptService
from novaadapt_shared.api_client import NovaAdaptAPIClient
from novaadapt_shared.model_router import RouterResult


class _StubRouter:
    def list_models(self):
        class _Model:
            def __init__(self):
                self.name = "local-qwen"
                self.model = "qwen"
                self.provider = "openai-compatible"
                self.base_url = "http://127.0.0.1:11434/v1"

        return [_Model()]

    def chat(
        self,
        messages,
        model_name=None,
        strategy="single",
        candidate_models=None,
        fallback_models=None,
    ):
        _ = (messages, strategy, candidate_models, fallback_models)
        return RouterResult(
            model_name=model_name or "local-qwen",
            model_id="qwen",
            content=json.dumps({"actions": [{"type": "note", "target": "ops", "value": "reviewed"}]}),
            strategy=strategy,
            votes={},
            errors={},
            attempted_models=[model_name or "local-qwen"],
        )


class _StubDirectShell:
    def execute_action(self, action, dry_run=True):
        return ExecutionResult(
            action=dict(action),
            status="preview" if dry_run else "ok",
            output="preview" if dry_run else "executed",
        )


class _StubMemoryBackend:
    def __init__(self) -> None:
        self.ingested: list[dict[str, object]] = []
        self.events: list[str] = []

    def status(self):
        return {"ok": True, "enabled": True, "backend": "stub-memory"}

    def recall(self, query: str, top_k: int = 10):
        return [
            {
                "content": f"memory for {query}",
                "score": 0.9,
                "role": "assistant",
                "session_id": "session-1",
                "metadata": {"top_k": top_k},
            }
        ]

    def augment(self, query: str, top_k: int = 5, *, min_score: float = 0.005, format_name: str = "xml"):
        _ = (query, top_k, min_score, format_name)
        return ""

    def ingest(self, text: str, *, source_id: str = "", metadata: dict | None = None):
        payload = {"text": text, "source_id": source_id, "metadata": metadata or {}}
        self.ingested.append(payload)
        return {"ok": True}

    def track_event(self, event_type: str):
        self.events.append(str(event_type))
        return {"ok": True}

    def track_events_batch(self, event_types: list[str]):
        self.events.extend([str(item) for item in event_types])
        return {"ok": True}

    def consolidate(self, *, session_id: str = "", max_chunks: int = 32):
        _ = (session_id, max_chunks)
        return {"ok": True}

    def dream(self):
        return {"ok": True}


def _build_service(root: Path, memory_backend: _StubMemoryBackend | None = None) -> NovaAdaptService:
    return NovaAdaptService(
        default_config=root / "config.json",
        db_path=root / "state.sqlite3",
        plans_db_path=root / "plans.sqlite3",
        audit_db_path=root / "audit.sqlite3",
        router_loader=lambda _path: _StubRouter(),
        directshell_factory=_StubDirectShell,
        memory_backend=memory_backend or _StubMemoryBackend(),
    )


class AgentTemplateServiceTests(unittest.TestCase):
    def test_service_export_share_launch_import_and_gallery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.joinpath("agent_gallery.json").write_text(
                json.dumps(
                    [
                        {
                            "template_id": "gallery-one",
                            "name": "Gallery One",
                            "objective": "Inspect the queue",
                            "strategy": "single",
                            "tags": ["ops"],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            memory = _StubMemoryBackend()
            service = _build_service(root, memory)

            exported = service.agent_template_export(
                name="Ops Triage",
                objective="Inspect the queue and prepare a safe plan",
                strategy="vote",
                candidates=["local-qwen", "openai-gpt"],
                tags=["ops", "review"],
                include_memory=True,
            )
            self.assertTrue(exported["ok"])
            self.assertEqual(exported["name"], "Ops Triage")
            self.assertEqual(exported["strategy"], "vote")
            self.assertEqual(len(exported["memory_snapshot"]), 1)

            listed = service.agent_templates_list(limit=10)
            self.assertEqual(listed["count"], 1)

            template_id = exported["template_id"]
            detail = service.agent_template_get(template_id)
            self.assertTrue(detail["ok"])
            self.assertEqual(detail["template_id"], template_id)

            shared = service.agent_template_share(template_id, rotate=True, shared=True)
            self.assertTrue(shared["ok"])
            self.assertTrue(shared["share"]["share_token"])
            self.assertTrue(shared["share"]["share_path"].startswith("/agents/templates/shared/"))

            shared_fetch = service.agent_template_shared(shared["share"]["share_token"])
            self.assertTrue(shared_fetch["ok"])
            self.assertEqual(shared_fetch["template_id"], template_id)

            launched = service.agent_template_launch(template_id, mode="plan")
            self.assertTrue(launched["ok"])
            self.assertEqual(launched["mode"], "plan")
            self.assertEqual(launched["launch"]["status"], "pending")

            imported = service.agent_template_import(
                {
                    "manifest": {
                        "template_id": "imported-template",
                        "name": "Imported",
                        "objective": "Run imported objective",
                        "strategy": "single",
                        "tags": ["imported"],
                    }
                }
            )
            self.assertTrue(imported["ok"])
            self.assertEqual(imported["template_id"], "imported-template")

            gallery = service.agent_templates_gallery(tag="ops")
            self.assertEqual(gallery["count"], 1)
            self.assertEqual(gallery["templates"][0]["template_id"], "gallery-one")

            self.assertTrue(any("agent_template_export" in item["text"] for item in memory.ingested))
            self.assertTrue(any("agents.templates.agent_template_export" == item for item in memory.events))


class AgentTemplateAPIClientTests(unittest.TestCase):
    def test_api_client_routes_cover_export_share_and_public_fetch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.joinpath("agent_gallery.json").write_text(
                json.dumps(
                    [
                        {
                            "template_id": "gallery-public",
                            "name": "Gallery Public",
                            "objective": "Review the dashboard",
                            "tags": ["public"],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            service = _build_service(root, _StubMemoryBackend())
            server = create_server(
                "127.0.0.1",
                0,
                service,
                api_token="secret-token",
                audit_db_path=str(root / "events.db"),
            )
            host, port = server.server_address
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()

            try:
                client = NovaAdaptAPIClient(base_url=f"http://{host}:{port}", token="secret-token")
                public_client = NovaAdaptAPIClient(base_url=f"http://{host}:{port}")

                exported = client.agent_template_export(
                    name="Client Template",
                    objective="Prepare the safest plan",
                    include_memory=True,
                )
                self.assertTrue(exported["ok"])
                template_id = exported["template_id"]

                listed = client.agent_templates_list()
                self.assertEqual(listed["count"], 1)

                detail = client.agent_template_get(template_id)
                self.assertEqual(detail["template_id"], template_id)

                gallery = client.agent_templates_gallery(tag="public")
                self.assertEqual(gallery["count"], 1)

                shared = client.agent_template_share(template_id, rotate=True)
                self.assertTrue(shared["share"]["share_token"])

                shared_manifest = public_client.agent_template_shared(shared["share"]["share_token"])
                self.assertTrue(shared_manifest["ok"])
                self.assertEqual(shared_manifest["template_id"], template_id)

                with patch.dict(os.environ, {"NOVAADAPT_ENABLE_WORKFLOWS_API": "1"}, clear=False):
                    launched = client.agent_template_launch(template_id, mode="workflow", context="api")
                    self.assertTrue(launched["ok"])
                    self.assertEqual(launched["mode"], "workflow")

                imported = client.agent_template_import(
                    {
                        "template_id": "client-imported",
                        "name": "Client Imported",
                        "objective": "Imported objective",
                    }
                )
                self.assertTrue(imported["ok"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
