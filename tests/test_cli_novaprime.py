import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from novaadapt_core import cli


class NovaPrimeCLITests(unittest.TestCase):
    def _run_cli(self, *argv: str):
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["novaadapt", *argv]), redirect_stdout(stdout):
            cli.main()
        raw = stdout.getvalue().strip()
        if not raw:
            return None
        return json.loads(raw)

    def test_novaprime_status_and_reason_commands(self):
        service = mock.Mock()
        service.novaprime_status.return_value = {"ok": True, "enabled": True, "backend": "novaprime-http"}
        service.novaprime_reason_dual.return_value = {"ok": True, "final_text": "plan"}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            status_payload = self._run_cli("novaprime-status")
            reason_payload = self._run_cli("novaprime-reason", "--task", "Map border")

        self.assertTrue(status_payload["ok"])
        self.assertTrue(reason_payload["ok"])
        service.novaprime_status.assert_called_once_with()
        service.novaprime_reason_dual.assert_called_once_with("Map border")

    def test_novaprime_identity_verify_command(self):
        service = mock.Mock()
        service.novaprime_identity_verify.return_value = {
            "ok": True,
            "adapt_id": "adapt-1",
            "player_id": "player-1",
            "verified": True,
            "verified_source": "novaprime",
        }
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            payload = self._run_cli(
                "novaprime-identity-verify",
                "--adapt-id",
                "adapt-1",
                "--player-id",
                "player-1",
            )

        self.assertTrue(payload["verified"])
        service.novaprime_identity_verify.assert_called_once_with("adapt-1", "player-1")

    def test_novaprime_resonance_commands(self):
        service = mock.Mock()
        service.novaprime_resonance_score.return_value = {"ok": True, "chosen_element": "light"}
        service.novaprime_resonance_bond.return_value = {"ok": True, "adapt_id": "adapt-1"}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            score_payload = self._run_cli(
                "novaprime-resonance-score",
                "--player-profile",
                '{"class":"sentinel"}',
            )
            bond_payload = self._run_cli(
                "novaprime-resonance-bond",
                "--player-id",
                "player-1",
                "--adapt-id",
                "adapt-1",
                "--player-profile",
                '{"class":"sentinel"}',
            )

        self.assertTrue(score_payload["ok"])
        self.assertTrue(bond_payload["ok"])
        service.novaprime_resonance_score.assert_called_once_with({"class": "sentinel"})
        service.novaprime_resonance_bond.assert_called_once_with(
            "player-1",
            {"class": "sentinel"},
            adapt_id="adapt-1",
        )

    def test_novaprime_emotion_set_rejects_non_object(self):
        service = mock.Mock()
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            with mock.patch.object(
                sys,
                "argv",
                [
                    "novaadapt",
                    "novaprime-emotion-set",
                    "--chemicals",
                    "[1,2,3]",
                ],
            ):
                with self.assertRaises(SystemExit) as exc:
                    cli.main()
        self.assertIn("--chemicals must be a JSON object", str(exc.exception))
        service.novaprime_emotion_set.assert_not_called()


if __name__ == "__main__":
    unittest.main()

