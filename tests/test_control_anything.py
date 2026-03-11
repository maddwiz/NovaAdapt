import base64
import json
import tempfile
import threading
import unittest
from pathlib import Path

from novaadapt_core.directshell import ExecutionResult
from novaadapt_core.homeassistant_executor import HomeAssistantExecutionResult
from novaadapt_core.server import create_server
from novaadapt_core.service import NovaAdaptService
from novaadapt_shared.api_client import NovaAdaptAPIClient
from novaadapt_shared.model_router import RouterResult


_SAMPLE_SCREENSHOT_B64 = base64.b64encode(b"fake-png").decode("ascii")


class _VisionRouter:
    def list_models(self):
        class _Model:
            def __init__(self):
                self.name = "local-vision"
                self.model = "vision-1"
                self.provider = "openai-compatible"
                self.base_url = "http://localhost:11434/v1"

        return [_Model()]

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
            model_name=model_name or "local-vision",
            model_id="vision-1",
            content=json.dumps(
                {
                    "action": {"type": "click", "x": 44, "y": 55},
                    "confidence": 0.91,
                    "reason": "visible continue button",
                }
            ),
            strategy=strategy,
            votes={},
            errors={},
            attempted_models=[model_name or "local-vision"],
        )


class _RecordingDirectShell:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def execute_action(self, action, dry_run=True):
        self.calls.append({"action": dict(action), "dry_run": bool(dry_run)})
        if dry_run:
            return ExecutionResult(
                action=dict(action),
                status="preview",
                output=f"Preview only: {json.dumps(action, ensure_ascii=True)}",
            )
        return ExecutionResult(action=dict(action), status="ok", output="executed")


class _StubHomeAssistantExecutor:
    def status(self):
        return {
            "ok": True,
            "transport": "homeassistant-http",
            "base_url": "http://stub-homeassistant.local",
        }

    def execute_action(self, action, *, dry_run=True):
        return HomeAssistantExecutionResult(
            status="preview" if dry_run else "ok",
            output=("Preview " if dry_run else "Executed ") + str(action.get("type") or "ha_service"),
            action=dict(action),
            data={"dry_run": bool(dry_run), "entity_id": action.get("entity_id")},
        )


def _build_service(directshell=None) -> NovaAdaptService:
    runtime = directshell or _RecordingDirectShell()
    return NovaAdaptService(
        default_config=Path("unused.json"),
        router_loader=lambda _path: _VisionRouter(),
        directshell_factory=lambda: runtime,
        homeassistant_executor_factory=lambda: _StubHomeAssistantExecutor(),
    )


class ControlServiceTests(unittest.TestCase):
    def test_vision_execute_preview_normalizes_coordinates(self):
        directshell = _RecordingDirectShell()
        service = _build_service(directshell)

        out = service.vision_execute(
            {
                "goal": "click the continue button",
                "screenshot_base64": _SAMPLE_SCREENSHOT_B64,
                "execute": False,
            }
        )

        self.assertEqual(out["status"], "preview")
        self.assertEqual(out["action"]["type"], "click")
        self.assertEqual(out["action"]["target"], "44,55")
        self.assertAlmostEqual(out["vision"]["confidence"], 0.91, places=2)
        self.assertEqual(directshell.calls[0]["action"]["target"], "44,55")

    def test_mobile_action_blocks_sensitive_android_payment(self):
        service = _build_service()

        out = service.mobile_action(
            {
                "platform": "android",
                "execute": True,
                "action": {
                    "type": "open_app",
                    "target": "com.bank.mobile.transfer",
                },
            }
        )

        self.assertEqual(out["status"], "blocked")
        self.assertTrue(out["dangerous"])
        self.assertIn("Blocked potentially destructive or sensitive action", out["output"])

    def test_mobile_action_ios_uses_vision_grounding_preview(self):
        service = _build_service()

        out = service.mobile_action(
            {
                "platform": "ios",
                "goal": "tap the visible continue button",
                "screenshot_base64": _SAMPLE_SCREENSHOT_B64,
                "execute": False,
            }
        )

        self.assertEqual(out["status"], "preview")
        self.assertEqual(out["platform"], "ios")
        self.assertEqual(out["action"]["target"], "44,55")
        self.assertEqual(out["vision"]["model"], "local-vision")

    def test_homeassistant_status_and_preview(self):
        service = _build_service()

        mobile_status = service.mobile_status()
        self.assertTrue(mobile_status["ok"])
        self.assertIn("android", mobile_status)
        self.assertIn("ios", mobile_status)

        status = service.homeassistant_status()
        self.assertTrue(status["ok"])
        self.assertEqual(status["transport"], "homeassistant-http")

        out = service.homeassistant_action(
            {
                "action": {
                    "type": "ha_service",
                    "domain": "light",
                    "service": "turn_on",
                    "entity_id": "light.office",
                },
                "execute": False,
            }
        )

        self.assertEqual(out["status"], "preview")
        self.assertTrue(out["dangerous"])
        self.assertEqual(out["action"]["entity_id"], "light.office")


class ControlAPIClientTests(unittest.TestCase):
    def test_api_client_control_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = _build_service()
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
                client = NovaAdaptAPIClient(base_url=f"http://{host}:{port}")

                vision = client.vision_execute(
                    "click the continue button",
                    screenshot_base64=_SAMPLE_SCREENSHOT_B64,
                )
                self.assertEqual(vision["status"], "preview")
                self.assertEqual(vision["action"]["target"], "44,55")

                mobile_android = client.mobile_action(
                    "android",
                    {"type": "tap", "x": 12, "y": 34},
                )
                self.assertEqual(mobile_android["status"], "preview")
                self.assertEqual(mobile_android["platform"], "android")

                mobile_status = client.mobile_status()
                self.assertTrue(mobile_status["ok"])
                self.assertIn("android", mobile_status)

                mobile_ios = client.mobile_action(
                    "ios",
                    execute=False,
                    goal="tap continue",
                    screenshot_base64=_SAMPLE_SCREENSHOT_B64,
                )
                self.assertEqual(mobile_ios["status"], "preview")
                self.assertEqual(mobile_ios["action"]["target"], "44,55")

                ha_status = client.homeassistant_status()
                self.assertTrue(ha_status["ok"])

                ha_action = client.homeassistant_action(
                    {
                        "type": "ha_service",
                        "domain": "light",
                        "service": "turn_on",
                        "entity_id": "light.office",
                    }
                )
                self.assertEqual(ha_action["status"], "preview")
                self.assertTrue(ha_action["dangerous"])

                dashboard = client.dashboard_data()
                self.assertIn("control", dashboard)
                self.assertIn("browser", dashboard["control"])
                self.assertIn("mobile", dashboard["control"])
                self.assertIn("homeassistant", dashboard["control"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)
