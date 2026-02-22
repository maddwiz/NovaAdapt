import tempfile
import unittest
from pathlib import Path

from novaadapt_core.agent import NovaAdaptAgent
from novaadapt_shared.model_router import RouterResult
from novaadapt_shared.undo_queue import UndoQueue


class _StubRouter:
    def __init__(self, content: str):
        self._content = content

    def chat(
        self,
        messages,
        model_name=None,
        strategy="single",
        candidate_models=None,
        fallback_models=None,
    ):
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


if __name__ == "__main__":
    unittest.main()
