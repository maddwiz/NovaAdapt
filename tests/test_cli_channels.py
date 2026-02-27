import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from novaadapt_core import cli


class ChannelCLITests(unittest.TestCase):
    def _run_cli(self, *argv: str):
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["novaadapt", *argv]), redirect_stdout(stdout):
            cli.main()
        raw = stdout.getvalue().strip()
        if not raw:
            return None
        return json.loads(raw)

    def test_channels_and_channel_health_commands(self):
        service = mock.Mock()
        service.channels.return_value = [{"channel": "webchat", "ok": True, "enabled": True}]
        service.channel_health.return_value = {"channel": "webchat", "ok": True, "enabled": True}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            channels_payload = self._run_cli("channels")
            health_payload = self._run_cli("channel-health", "--channel", "webchat")

        service.channels.assert_called_once_with()
        service.channel_health.assert_called_once_with("webchat")
        self.assertEqual(channels_payload[0]["channel"], "webchat")
        self.assertTrue(health_payload["ok"])

    def test_channel_send_and_inbound_commands(self):
        service = mock.Mock()
        service.channel_send.return_value = {"ok": True, "channel": "webchat", "to": "room-1"}
        service.channel_inbound.return_value = {"ok": True, "channel": "webchat", "auto_run": True}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            send_payload = self._run_cli(
                "channel-send",
                "--channel",
                "webchat",
                "--to",
                "room-1",
                "--text",
                "hello",
                "--metadata",
                '{"adapt_id":"adapt-1"}',
            )
            inbound_payload = self._run_cli(
                "channel-inbound",
                "--channel",
                "webchat",
                "--payload",
                '{"sender":"player-1","text":"status"}',
                "--adapt-id",
                "adapt-1",
                "--auto-run",
            )

        service.channel_send.assert_called_once_with(
            "webchat",
            "room-1",
            "hello",
            metadata={"adapt_id": "adapt-1"},
        )
        service.channel_inbound.assert_called_once_with(
            "webchat",
            {"sender": "player-1", "text": "status"},
            adapt_id="adapt-1",
            auto_run=True,
            execute=False,
        )
        self.assertTrue(send_payload["ok"])
        self.assertTrue(inbound_payload["ok"])

    def test_channel_send_rejects_non_object_metadata(self):
        service = mock.Mock()
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            with mock.patch.object(
                sys,
                "argv",
                [
                    "novaadapt",
                    "channel-send",
                    "--channel",
                    "webchat",
                    "--to",
                    "room-1",
                    "--text",
                    "hello",
                    "--metadata",
                    "[1,2,3]",
                ],
            ):
                with self.assertRaises(SystemExit) as exc:
                    cli.main()
        self.assertIn("--metadata must be a JSON object", str(exc.exception))
        service.channel_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
