import unittest

from novaadapt_core.plugins.sib_bridge import SIBBridge


class _StubRegistry:
    def __init__(self):
        self.calls = []

    def health(self, plugin_name: str):
        self.calls.append({"method": "health", "plugin": plugin_name})
        return {"ok": True, "plugin": plugin_name}

    def call(self, plugin_name: str, *, route: str, payload=None, method: str = "POST"):
        self.calls.append(
            {
                "method": "call",
                "plugin": plugin_name,
                "route": route,
                "payload": payload or {},
                "http_method": method,
            }
        )
        return {"ok": True, "plugin": plugin_name, "route": route, "payload": payload or {}, "method": method}


class SIBBridgeTests(unittest.TestCase):
    def test_routes_are_mapped_to_plugin_calls(self):
        registry = _StubRegistry()
        bridge = SIBBridge(registry)

        self.assertTrue(bridge.health()["ok"])
        self.assertEqual(bridge.realm("player-1", "game_world")["route"], "/game/realm")
        self.assertEqual(
            bridge.companion_state("adapt-1", {"mode": "combat"})["route"],
            "/game/companion/state",
        )
        self.assertEqual(
            bridge.companion_speak("adapt-1", "On your left!")["route"],
            "/game/companion/speak",
        )
        self.assertEqual(bridge.phase_event("entropy_spike")["route"], "/game/phase_event")
        self.assertEqual(bridge.resonance_start("player-1")["route"], "/game/resonance/start")
        self.assertEqual(
            bridge.resonance_result("player-1", "adapt-1", True)["route"],
            "/game/resonance/result",
        )

        call_routes = [item["route"] for item in registry.calls if item["method"] == "call"]
        self.assertIn("/game/realm", call_routes)
        self.assertIn("/game/resonance/result", call_routes)


if __name__ == "__main__":
    unittest.main()
