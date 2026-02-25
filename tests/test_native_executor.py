import unittest

from novaadapt_core.native_executor import NativeDesktopExecutor


class NativeExecutorTests(unittest.TestCase):
    def test_note_action(self):
        executor = NativeDesktopExecutor(platform_name="darwin")
        result = executor.execute_action({"type": "note", "target": "test", "value": "ok"})
        self.assertEqual(result.status, "ok")
        self.assertIn("note:test", result.output)

    def test_wait_action(self):
        executor = NativeDesktopExecutor(platform_name="darwin")
        result = executor.execute_action({"type": "wait", "value": "0.001s"})
        self.assertEqual(result.status, "ok")
        self.assertIn("waited", result.output)

    def test_click_requires_coordinates(self):
        executor = NativeDesktopExecutor(platform_name="darwin")
        result = executor.execute_action({"type": "click", "target": "OK"})
        self.assertEqual(result.status, "failed")
        self.assertIn("coordinates", result.output)

    def test_probe_unsupported_platform(self):
        executor = NativeDesktopExecutor(platform_name="plan9")
        probe = executor.probe()
        self.assertFalse(probe["ok"])
        self.assertIn("Unsupported platform", probe["error"])


if __name__ == "__main__":
    unittest.main()
