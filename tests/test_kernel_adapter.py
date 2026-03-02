from __future__ import annotations

from types import SimpleNamespace
from unittest import TestCase, mock

from novaadapt_core.novaprime.kernel_adapter import run_with_kernel


class _StubAgentJob:
    @classmethod
    def from_dict(cls, payload):
        return payload


class _StubIdentityContext:
    def __init__(self, **kwargs):
        self.kwargs = dict(kwargs)


class _StubDecision:
    def __init__(self, *, allowed: bool = True, dangerous: bool = False, reason: str = "") -> None:
        self.allowed = bool(allowed)
        self.dangerous = bool(dangerous)
        self.reason = str(reason or "")


class _StubPolicy:
    def evaluate(self, _action, allow_dangerous: bool = False):
        _ = allow_dangerous
        return _StubDecision()


class _StubDirectShell:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def execute_action(self, action, dry_run: bool = True):
        self.calls.append({"action": dict(action or {}), "dry_run": bool(dry_run)})
        return SimpleNamespace(status="ok", output="ok", action=dict(action or {}))


class _StubUndoQueue:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def record(self, *, action, status: str, undo_action=None):
        self.rows.append(
            {
                "action": dict(action or {}),
                "status": str(status),
                "undo_action": dict(undo_action) if isinstance(undo_action, dict) else None,
            }
        )
        return len(self.rows)


class _StubMemoryBackend:
    def ingest(self, _text, source_id: str = "", metadata=None):
        _ = (source_id, metadata)
        return {}


class _StubAgent:
    def __init__(self, *, directshell: _StubDirectShell) -> None:
        self.policy = _StubPolicy()
        self.directshell = directshell
        self.undo_queue = _StubUndoQueue()
        self.memory_backend = _StubMemoryBackend()
        self.persist_calls = 0

    def _persist_run_memory(self, **_kwargs) -> None:
        self.persist_calls += 1


class KernelAdapterTests(TestCase):
    def test_run_with_kernel_does_not_execute_actions_when_kernel_reports_failure(self):
        directshell = _StubDirectShell()
        agent = _StubAgent(directshell=directshell)
        kernel_result = SimpleNamespace(
            ok=False,
            error="kernel planner failed",
            output_text='{"actions":[{"type":"run_shell","target":"echo","value":"unsafe"}]}',
            job_id="job-1",
            session_id="session-1",
            artifacts=[],
        )
        with mock.patch(
            "novaadapt_core.novaprime.kernel_adapter._resolve_kernel_symbols",
            return_value=(
                lambda *_args, **_kwargs: kernel_result,
                lambda profile_name: profile_name,
                _StubAgentJob,
                _StubIdentityContext,
            ),
        ):
            out = run_with_kernel(
                payload={},
                objective="test objective",
                strategy="single",
                model_name="model-a",
                router=object(),
                agent=agent,
                execute=True,
                record_history=True,
                allow_dangerous=True,
                max_actions=5,
                adapt_id="adapt-1",
                player_id="player-1",
                identity_profile={},
            )

        self.assertFalse(out["ok"])
        self.assertEqual(out["result"]["actions"], [])
        self.assertEqual(out["result"]["results"], [])
        self.assertEqual(out["result"]["action_log_ids"], [])
        self.assertEqual(directshell.calls, [])

    def test_run_with_kernel_executes_actions_when_kernel_reports_success(self):
        directshell = _StubDirectShell()
        agent = _StubAgent(directshell=directshell)
        kernel_result = SimpleNamespace(
            ok=True,
            error="",
            output_text='{"actions":[{"type":"note","target":"kernel_output","value":"ok"}]}',
            job_id="job-2",
            session_id="session-2",
            artifacts=[],
        )
        with mock.patch(
            "novaadapt_core.novaprime.kernel_adapter._resolve_kernel_symbols",
            return_value=(
                lambda *_args, **_kwargs: kernel_result,
                lambda profile_name: profile_name,
                _StubAgentJob,
                _StubIdentityContext,
            ),
        ):
            out = run_with_kernel(
                payload={},
                objective="test objective",
                strategy="single",
                model_name="model-a",
                router=object(),
                agent=agent,
                execute=False,
                record_history=True,
                allow_dangerous=False,
                max_actions=5,
                adapt_id="adapt-1",
                player_id="player-1",
                identity_profile={},
            )

        self.assertTrue(out["ok"])
        self.assertEqual(len(out["result"]["actions"]), 1)
        self.assertEqual(len(directshell.calls), 1)
        self.assertTrue(directshell.calls[0]["dry_run"])
