import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from novaadapt_core import cli


class BridgeCLIAdminTests(unittest.TestCase):
    def _run_cli(self, *argv: str):
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["novaadapt", *argv]), redirect_stdout(stdout):
            cli.main()
        raw = stdout.getvalue().strip()
        if not raw:
            return None
        return json.loads(raw)

    def test_bridge_devices_command(self):
        client = mock.Mock()
        client.allowed_devices.return_value = {"enabled": True, "count": 1, "devices": ["iphone-1"]}
        with mock.patch("novaadapt_core.cli.NovaAdaptAPIClient", return_value=client) as ctor:
            payload = self._run_cli(
                "bridge-devices",
                "--base-url",
                "http://127.0.0.1:9797",
                "--token",
                "bridge-admin",
                "--timeout-seconds",
                "12",
            )

        ctor.assert_called_once_with(
            base_url="http://127.0.0.1:9797",
            token="bridge-admin",
            timeout_seconds=12,
        )
        client.allowed_devices.assert_called_once_with()
        self.assertEqual(payload["count"], 1)

    def test_bridge_session_issue_command(self):
        client = mock.Mock()
        client.issue_session_token.return_value = {"token": "na1.mock", "session_id": "sess-1", "scopes": ["read", "run"]}
        with mock.patch("novaadapt_core.cli.NovaAdaptAPIClient", return_value=client) as ctor:
            payload = self._run_cli(
                "bridge-session-issue",
                "--base-url",
                "http://bridge.local:9797",
                "--token",
                "admin-token",
                "--scopes",
                "read, run",
                "--subject",
                "ios-companion",
                "--device-id",
                "iphone-1",
                "--ttl-seconds",
                "600",
            )

        ctor.assert_called_once_with(
            base_url="http://bridge.local:9797",
            token="admin-token",
            timeout_seconds=30,
        )
        client.issue_session_token.assert_called_once_with(
            scopes=["read", "run"],
            subject="ios-companion",
            device_id="iphone-1",
            ttl_seconds=600,
        )
        self.assertEqual(payload["session_id"], "sess-1")

    def test_bridge_session_revoke_requires_identifier(self):
        with mock.patch("novaadapt_core.cli.NovaAdaptAPIClient"):
            with mock.patch.object(sys, "argv", ["novaadapt", "bridge-session-revoke"]):
                with self.assertRaises(SystemExit) as exc:
                    cli.main()

        self.assertIn("--session-token or --session-id is required", str(exc.exception))

    def test_bridge_device_add_and_remove_commands(self):
        client = mock.Mock()
        client.add_allowed_device.return_value = {"status": "ok", "added": True, "count": 1}
        client.remove_allowed_device.return_value = {"status": "ok", "removed": True, "count": 0}
        with mock.patch("novaadapt_core.cli.NovaAdaptAPIClient", return_value=client):
            add_payload = self._run_cli("bridge-device-add", "--device-id", "iphone-1")
            remove_payload = self._run_cli("bridge-device-remove", "--device-id", "iphone-1")

        client.add_allowed_device.assert_called_once_with("iphone-1")
        client.remove_allowed_device.assert_called_once_with("iphone-1")
        self.assertTrue(add_payload["added"])
        self.assertTrue(remove_payload["removed"])


if __name__ == "__main__":
    unittest.main()
