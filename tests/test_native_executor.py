import subprocess
import unittest

from novaadapt_core.native_executor import NativeDesktopExecutor


class _RecordingLinuxExecutor(NativeDesktopExecutor):
    def __init__(self):
        super().__init__(platform_name="linux")
        self.calls: list[tuple[list[str] | str, bool]] = []

    def _linux_has_xdotool(self) -> bool:
        return True

    def _run_subprocess(self, cmd, *, shell: bool):
        self.calls.append((cmd, shell))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok", stderr="")


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

    def test_linux_type_uses_xdotool(self):
        executor = _RecordingLinuxExecutor()
        result = executor.execute_action({"type": "type", "value": "hello world"})
        self.assertEqual(result.status, "ok")
        cmd, shell = executor.calls[-1]
        self.assertEqual(cmd, ["xdotool", "type", "--delay", "1", "--", "hello world"])
        self.assertFalse(shell)

    def test_linux_hotkey_uses_xdotool(self):
        executor = _RecordingLinuxExecutor()
        result = executor.execute_action({"type": "hotkey", "value": "ctrl+shift+k"})
        self.assertEqual(result.status, "ok")
        cmd, shell = executor.calls[-1]
        self.assertEqual(cmd, ["xdotool", "key", "ctrl+shift+k"])
        self.assertFalse(shell)

    def test_linux_click_uses_xdotool(self):
        executor = _RecordingLinuxExecutor()
        result = executor.execute_action({"type": "click", "target": "120,340"})
        self.assertEqual(result.status, "ok")
        cmd, shell = executor.calls[-1]
        self.assertEqual(cmd, ["xdotool", "mousemove", "120", "340", "click", "1"])
        self.assertFalse(shell)

    def test_linux_probe_includes_xdotool_flag(self):
        class _NoToolExecutor(NativeDesktopExecutor):
            def _linux_has_xdotool(self) -> bool:
                return False

        executor = _NoToolExecutor(platform_name="linux")
        probe = executor.probe()
        self.assertTrue(probe["ok"])
        self.assertFalse(probe["xdotool_available"])


if __name__ == "__main__":
    unittest.main()
