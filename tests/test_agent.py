import tempfile
import unittest
from pathlib import Path

from novaadapt_core.agent import NovaAdaptAgent
from novaadapt_shared.model_router import RouterResult
from novaadapt_shared.undo_queue import UndoQueue


class _StubRouter:
    def __init__(self, content: str):
        self._content = content
        self.last_messages = None

    def chat(
        self,
        messages,
        model_name=None,
        strategy="single",
        candidate_models=None,
        fallback_models=None,
    ):
        self.last_messages = messages
        return RouterResult(
            model_name=model_name or "stub",
            model_id="stub-model",
            content=self._content,
            strategy=strategy,
            votes={},
        )


class _StubDirectShell:
    def __init__(self):
        self.calls = []

    def execute_action(self, action, dry_run=True):
        self.calls.append((action, dry_run))

        class Result:
            pass

        result = Result()
        result.action = action
        result.status = "preview" if dry_run else "ok"
        result.output = "simulated"
        return result


class _StubMemoryBackend:
    def __init__(self):
        self.augment_calls: list[dict[str, object]] = []
        self.ingest_calls: list[dict[str, object]] = []

    def status(self):
        return {"ok": True, "enabled": True, "backend": "stub"}

    def recall(self, query: str, top_k: int = 10):
        _ = (query, top_k)
        return []

    def augment(self, query: str, top_k: int = 5, *, min_score: float = 0.005, format_name: str = "xml"):
        self.augment_calls.append(
            {"query": query, "top_k": top_k, "min_score": min_score, "format_name": format_name}
        )
        return "<relevant-memories><user>Use dark mode</user></relevant-memories>"

    def ingest(self, text: str, *, source_id: str = "", metadata=None):
        self.ingest_calls.append({"text": text, "source_id": source_id, "metadata": metadata or {}})
        return {"count": 1}


class AgentSafetyTests(unittest.TestCase):
    def test_blocks_dangerous_action_without_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = UndoQueue(db_path=Path(tmp) / "actions.db")
            directshell = _StubDirectShell()
            router = _StubRouter('{"actions": [{"type": "delete", "target": "~/Desktop/file.txt"}]}')
            agent = NovaAdaptAgent(router=router, directshell=directshell, undo_queue=queue)

            out = agent.run_objective(
                objective="Delete local file",
                dry_run=False,
                allow_dangerous=False,
            )

            self.assertEqual(out["results"][0]["status"], "blocked")
            self.assertEqual(directshell.calls, [])
            self.assertEqual(queue.recent(limit=1)[0]["status"], "blocked")

    def test_allows_dangerous_action_with_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = UndoQueue(db_path=Path(tmp) / "actions.db")
            directshell = _StubDirectShell()
            router = _StubRouter('{"actions": [{"type": "delete", "target": "~/Desktop/file.txt"}]}')
            agent = NovaAdaptAgent(router=router, directshell=directshell, undo_queue=queue)

            out = agent.run_objective(
                objective="Delete local file",
                dry_run=False,
                allow_dangerous=True,
            )

            self.assertEqual(out["results"][0]["status"], "ok")
            self.assertEqual(len(directshell.calls), 1)

    def test_parsing_falls_back_for_invalid_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = UndoQueue(db_path=Path(tmp) / "actions.db")
            directshell = _StubDirectShell()
            router = _StubRouter("not-json")
            agent = NovaAdaptAgent(router=router, directshell=directshell, undo_queue=queue)

            out = agent.run_objective(objective="Any objective", dry_run=True)
            self.assertEqual(out["actions"][0]["type"], "note")

    def test_memory_context_is_injected_and_run_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = UndoQueue(db_path=Path(tmp) / "actions.db")
            directshell = _StubDirectShell()
            router = _StubRouter('{"actions": [{"type": "note", "target": "memo"}]}')
            memory = _StubMemoryBackend()
            agent = NovaAdaptAgent(
                router=router,
                directshell=directshell,
                undo_queue=queue,
                memory_backend=memory,
            )

            out = agent.run_objective(objective="Remember my ui preference", dry_run=True)
            self.assertEqual(out["actions"][0]["type"], "note")
            self.assertTrue(memory.augment_calls)
            self.assertTrue(memory.ingest_calls)
            self.assertIsNotNone(router.last_messages)
            memory_messages = [item for item in router.last_messages if "Relevant long-term memory context" in str(item.get("content", ""))]
            self.assertEqual(len(memory_messages), 1)

    def test_identity_profile_and_bond_context_are_injected(self):
        with tempfile.TemporaryDirectory() as tmp:
            queue = UndoQueue(db_path=Path(tmp) / "actions.db")
            directshell = _StubDirectShell()
            router = _StubRouter('{"actions": [{"type": "note", "target": "identity"}]}')
            agent = NovaAdaptAgent(router=router, directshell=directshell, undo_queue=queue)

            _ = agent.run_objective(
                objective="Plan next move",
                dry_run=True,
                identity_profile={"adapt_id": "adapt-123", "element": "light", "form_stage": "symbiosis"},
                bond_verified=True,
            )

            self.assertIsNotNone(router.last_messages)
            identity_messages = [
                item
                for item in router.last_messages
                if "Adapt identity profile context for planning" in str(item.get("content", ""))
            ]
            self.assertEqual(len(identity_messages), 1)
            bond_messages = [
                item
                for item in router.last_messages
                if "Soulbond verification status with active player" in str(item.get("content", ""))
            ]
            self.assertEqual(len(bond_messages), 1)


if __name__ == "__main__":
    unittest.main()
