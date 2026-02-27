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

    def test_run_command_passes_adapt_and_mesh_context(self):
        service = mock.Mock()
        service.run.return_value = {"ok": True}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            payload = self._run_cli(
                "run",
                "--objective",
                "Map border patrol",
                "--adapt-id",
                "adapt-1",
                "--player-id",
                "player-1",
                "--realm",
                "game_world",
                "--activity",
                "patrol",
                "--post-realm",
                "aetherion",
                "--post-activity",
                "idle",
                "--toggle-mode",
                "in_game_only",
                "--mesh-node-id",
                "node-1",
                "--mesh-probe",
                "--mesh-probe-marketplace",
                "--mesh-credit-amount",
                "10.5",
                "--mesh-transfer-to",
                "node-2",
                "--mesh-transfer-amount",
                "3.25",
                "--mesh-marketplace-list",
                '{"capsule_id":"capsule-1","seller":"node-1","price":25,"title":"Storm Slash"}',
                "--mesh-marketplace-buy",
                '{"listing_id":"listing-1","buyer":"node-2"}',
            )
        self.assertTrue(payload["ok"])
        service.run.assert_called_once()
        run_payload = service.run.call_args.args[0]
        self.assertEqual(run_payload["adapt_id"], "adapt-1")
        self.assertEqual(run_payload["player_id"], "player-1")
        self.assertTrue(run_payload["mesh_probe"])
        self.assertTrue(run_payload["mesh_probe_marketplace"])
        self.assertEqual(run_payload["mesh_marketplace_list"]["capsule_id"], "capsule-1")
        self.assertEqual(run_payload["mesh_marketplace_buy"]["listing_id"], "listing-1")

    def test_plan_create_command_passes_adapt_and_mesh_context(self):
        service = mock.Mock()
        service.create_plan.return_value = {"id": "plan-1", "status": "pending"}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            payload = self._run_cli(
                "plan-create",
                "--objective",
                "Plan mesh strategy",
                "--adapt-id",
                "adapt-2",
                "--player-id",
                "player-2",
                "--toggle-mode",
                "ask_only",
                "--mesh-node-id",
                "node-2",
                "--mesh-credit-amount",
                "4",
                "--mesh-marketplace-buy",
                '{"listing_id":"listing-2","buyer":"node-2"}',
            )
        self.assertEqual(payload["id"], "plan-1")
        service.create_plan.assert_called_once()
        plan_payload = service.create_plan.call_args.args[0]
        self.assertEqual(plan_payload["adapt_id"], "adapt-2")
        self.assertEqual(plan_payload["player_id"], "player-2")
        self.assertEqual(plan_payload["toggle_mode"], "ask_only")
        self.assertEqual(plan_payload["mesh_marketplace_buy"]["listing_id"], "listing-2")

    def test_run_rejects_invalid_mesh_json(self):
        service = mock.Mock()
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            with mock.patch.object(
                sys,
                "argv",
                [
                    "novaadapt",
                    "run",
                    "--objective",
                    "x",
                    "--mesh-marketplace-list",
                    "[1,2,3]",
                ],
            ):
                with self.assertRaises(SystemExit) as exc:
                    cli.main()
        self.assertIn("--mesh-marketplace-list must be a JSON object", str(exc.exception))
        service.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
