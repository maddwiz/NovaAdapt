import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from novaadapt_core import cli


class AdaptCLITests(unittest.TestCase):
    def _run_cli(self, *argv: str):
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["novaadapt", *argv]), redirect_stdout(stdout):
            cli.main()
        raw = stdout.getvalue().strip()
        if not raw:
            return None
        return json.loads(raw)

    def test_adapt_toggle_get_and_set_commands(self):
        service = mock.Mock()
        service.adapt_toggle_get.return_value = {"adapt_id": "adapt-1", "mode": "ask_only", "source": "default"}
        service.adapt_toggle_set.return_value = {"adapt_id": "adapt-1", "mode": "in_game_only", "source": "cli"}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            get_payload = self._run_cli("adapt-toggle", "--adapt-id", "adapt-1")
            set_payload = self._run_cli(
                "adapt-toggle",
                "--adapt-id",
                "adapt-1",
                "--mode",
                "in_game_only",
                "--source",
                "cli",
            )

        service.adapt_toggle_get.assert_called_once_with("adapt-1")
        service.adapt_toggle_set.assert_called_once_with("adapt-1", "in_game_only", source="cli")
        self.assertEqual(get_payload["mode"], "ask_only")
        self.assertEqual(set_payload["mode"], "in_game_only")

    def test_adapt_bond_and_verify_commands(self):
        service = mock.Mock()
        service.adapt_bond_get.return_value = {"adapt_id": "adapt-1", "player_id": "player-1", "verified": True}
        service.adapt_bond_verify.return_value = {
            "ok": True,
            "adapt_id": "adapt-1",
            "player_id": "player-1",
            "verified": True,
            "source": "novaprime",
        }
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            bond_payload = self._run_cli("adapt-bond", "--adapt-id", "adapt-1")
            verify_payload = self._run_cli(
                "adapt-bond-verify",
                "--adapt-id",
                "adapt-1",
                "--player-id",
                "player-1",
                "--no-refresh-profile",
            )

        service.adapt_bond_get.assert_called_once_with("adapt-1")
        service.adapt_bond_verify.assert_called_once_with("adapt-1", "player-1", refresh_profile=False)
        self.assertTrue(bond_payload["found"])
        self.assertTrue(verify_payload["verified"])

    def test_adapt_persona_command(self):
        service = mock.Mock()
        service.adapt_persona_get.return_value = {
            "ok": True,
            "adapt_id": "adapt-1",
            "player_id": "player-1",
            "persona": {"adapt_id": "adapt-1", "trust_band": "bonded"},
        }
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            payload = self._run_cli("adapt-persona", "--adapt-id", "adapt-1", "--player-id", "player-1")

        service.adapt_persona_get.assert_called_once_with("adapt-1", player_id="player-1")
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["persona"]["adapt_id"], "adapt-1")


if __name__ == "__main__":
    unittest.main()

