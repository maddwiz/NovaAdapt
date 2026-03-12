import unittest
from pathlib import Path

from novaadapt_core.mobile_executor import IOSAppiumExecutor, UnifiedMobileExecutor
from novaadapt_core.service import NovaAdaptService


class _FakeIOSAppiumExecutor(IOSAppiumExecutor):
    def __init__(self):
        super().__init__(base_url="http://appium.local", session_id="ios-session-1")
        self.requests: list[tuple[str, str, object]] = []

    def _request_json(self, method: str, path: str, payload):
        self.requests.append((method, path, payload))
        if path == "/status":
            return {"value": {"ready": True}}
        if path.endswith("/element"):
            return {"value": {"element-6066-11e4-a52e-4f735466cecf": "element-1"}}
        if path.endswith("/element/active"):
            return {"value": {"element-6066-11e4-a52e-4f735466cecf": "active-1"}}
        return {"value": {}}


class _UnusedDirectShell:
    def execute_action(self, action, dry_run=True):
        raise AssertionError(f"directshell should not be used here: {action} dry_run={dry_run}")


class MobileExecutorTests(unittest.TestCase):
    def test_ios_appium_status_reports_reachable(self):
        executor = _FakeIOSAppiumExecutor()
        status = executor.status()
        self.assertTrue(status["ok"])
        self.assertTrue(status["reachable"])
        self.assertEqual(status["transport"], "appium")

    def test_ios_appium_tap_uses_w3c_touch_actions(self):
        executor = _FakeIOSAppiumExecutor()
        result = executor.execute_action({"type": "tap", "x": 12, "y": 34}, dry_run=False)
        self.assertEqual(result.status, "ok")
        method, path, payload = executor.requests[-1]
        self.assertEqual((method, path), ("POST", "/session/ios-session-1/actions"))
        self.assertEqual(payload["actions"][0]["parameters"]["pointerType"], "touch")
        self.assertEqual(payload["actions"][0]["actions"][0]["x"], 12)
        self.assertEqual(payload["actions"][0]["actions"][0]["y"], 34)

    def test_ios_appium_type_uses_element_value(self):
        executor = _FakeIOSAppiumExecutor()
        result = executor.execute_action(
            {"type": "type", "selector": "Login Field", "value": "nova"},
            dry_run=False,
        )
        self.assertEqual(result.status, "ok")
        method, path, payload = executor.requests[-1]
        self.assertEqual((method, path), ("POST", "/session/ios-session-1/element/element-1/value"))
        self.assertEqual(payload["text"], "nova")

    def test_service_mobile_action_prefers_appium_when_requested(self):
        appium = _FakeIOSAppiumExecutor()
        mobile = UnifiedMobileExecutor(android_executor=None, ios_executor=None, ios_appium_executor=appium)
        service = NovaAdaptService(
            default_config=Path("unused.json"),
            router_loader=lambda _path: None,
            directshell_factory=_UnusedDirectShell,
            mobile_executor_factory=lambda: mobile,
        )

        out = service.mobile_action(
            {
                "platform": "ios",
                "prefer_appium": True,
                "execute": True,
                "action": {"type": "open_url", "target": "https://example.com"},
            }
        )

        self.assertEqual(out["status"], "ok")
        self.assertEqual(out["transport"], "appium")
        self.assertEqual(appium.requests[-1][1], "/session/ios-session-1/url")


if __name__ == "__main__":
    unittest.main()
