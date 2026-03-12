import io
import json
import sys
import tempfile
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

    def test_run_command_accepts_decompose_strategy(self):
        service = mock.Mock()
        service.run.return_value = {"ok": True}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            payload = self._run_cli(
                "run",
                "--objective",
                "Decompose this objective",
                "--strategy",
                "decompose",
            )
        self.assertTrue(payload["ok"])
        service.run.assert_called_once()
        run_payload = service.run.call_args.args[0]
        self.assertEqual(run_payload["strategy"], "decompose")

    def test_run_command_passes_auto_repair_controls(self):
        service = mock.Mock()
        service.run.return_value = {"ok": True}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            payload = self._run_cli(
                "run",
                "--objective",
                "Handle the failed cleanup",
                "--execute",
                "--auto-repair-attempts",
                "2",
                "--repair-strategy",
                "vote",
                "--repair-model",
                "local",
                "--repair-candidates",
                "local,backup",
                "--repair-fallbacks",
                "backup",
            )
        self.assertTrue(payload["ok"])
        service.run.assert_called_once()
        run_payload = service.run.call_args.args[0]
        self.assertTrue(run_payload["execute"])
        self.assertEqual(run_payload["auto_repair_attempts"], 2)
        self.assertEqual(run_payload["repair_strategy"], "vote")
        self.assertEqual(run_payload["repair_model"], "local")
        self.assertEqual(run_payload["repair_candidates"], "local,backup")
        self.assertEqual(run_payload["repair_fallbacks"], "backup")

    def test_plan_create_command_accepts_decompose_strategy(self):
        service = mock.Mock()
        service.create_plan.return_value = {"id": "plan-2", "status": "pending"}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            payload = self._run_cli(
                "plan-create",
                "--objective",
                "Decompose plan objective",
                "--strategy",
                "decompose",
            )
        self.assertEqual(payload["id"], "plan-2")
        service.create_plan.assert_called_once()
        plan_payload = service.create_plan.call_args.args[0]
        self.assertEqual(plan_payload["strategy"], "decompose")

    def test_plan_approve_command_passes_auto_repair_controls(self):
        service = mock.Mock()
        service.approve_plan.return_value = {"id": "plan-7", "status": "executed"}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            payload = self._run_cli(
                "plan-approve",
                "--id",
                "plan-7",
                "--allow-dangerous",
                "--auto-repair-attempts",
                "2",
                "--repair-strategy",
                "vote",
                "--repair-model",
                "local",
                "--repair-candidates",
                "local,backup",
                "--repair-fallbacks",
                "backup",
            )

        self.assertEqual(payload["id"], "plan-7")
        service.approve_plan.assert_called_once()
        plan_id, approve_payload = service.approve_plan.call_args.args
        self.assertEqual(plan_id, "plan-7")
        self.assertTrue(approve_payload["allow_dangerous"])
        self.assertEqual(approve_payload["auto_repair_attempts"], 2)
        self.assertEqual(approve_payload["repair_strategy"], "vote")
        self.assertEqual(approve_payload["repair_model"], "local")
        self.assertEqual(approve_payload["repair_candidates"], "local,backup")
        self.assertEqual(approve_payload["repair_fallbacks"], "backup")

    def test_voice_status_command(self):
        service = mock.Mock()
        service.voice_status.return_value = {"ok": True, "enabled": False}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            payload = self._run_cli("voice-status")
        self.assertTrue(payload["ok"])
        service.voice_status.assert_called_once_with(context="cli")

    def test_control_surface_commands(self):
        service = mock.Mock()
        service.vision_execute.return_value = {"status": "preview", "action": {"type": "click", "target": "10,10"}}
        service.mobile_status.return_value = {"ok": True, "android": {"ok": True}}
        service.mobile_action.return_value = {"status": "preview", "platform": "ios"}
        service.homeassistant_status.return_value = {"ok": True, "transport": "homeassistant-http"}
        service.homeassistant_discover.return_value = {"ok": True, "count": 1, "entities": [{"entity_id": "light.office"}]}
        service.homeassistant_action.return_value = {"status": "preview", "action": {"type": "ha_service"}}
        service.mqtt_status.return_value = {"ok": True, "transport": "mqtt-direct"}
        service.mqtt_subscribe.return_value = {"status": "ok", "data": {"count": 1, "messages": [{"payload": "ping"}]}}
        with tempfile.TemporaryDirectory() as tmp:
            screenshot = io.BytesIO(b"fake-png")
            screenshot_path = f"{tmp}/shot.png"
            with open(screenshot_path, "wb") as handle:
                handle.write(screenshot.getvalue())
            with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
                vision_payload = self._run_cli(
                    "vision-execute",
                    "--goal",
                    "Click continue",
                    "--screenshot-path",
                    screenshot_path,
                )
                mobile_status_payload = self._run_cli("mobile-status")
                mobile_action_payload = self._run_cli(
                    "mobile-action",
                    "--platform",
                    "ios",
                    "--goal",
                    "Tap continue",
                    "--screenshot-path",
                    screenshot_path,
                )
                homeassistant_status_payload = self._run_cli("homeassistant-status")
                homeassistant_discover_payload = self._run_cli("homeassistant-discover", "--domain", "light")
                homeassistant_action_payload = self._run_cli(
                    "homeassistant-action",
                    "--action-json",
                    '{"type":"ha_service","domain":"light","service":"turn_on","entity_id":"light.office"}',
                )
                mqtt_status_payload = self._run_cli("mqtt-status")
                mqtt_publish_payload = self._run_cli(
                    "mqtt-publish",
                    "--topic",
                    "novaadapt/test",
                    "--payload",
                    "ping",
                )
                mqtt_subscribe_payload = self._run_cli(
                    "mqtt-subscribe",
                    "--topic",
                    "novaadapt/test",
                    "--timeout-seconds",
                    "0.1",
                    "--max-messages",
                    "1",
                )

        self.assertEqual(vision_payload["status"], "preview")
        self.assertTrue(mobile_status_payload["ok"])
        self.assertEqual(mobile_action_payload["platform"], "ios")
        self.assertTrue(homeassistant_status_payload["ok"])
        self.assertEqual(homeassistant_discover_payload["count"], 1)
        self.assertEqual(homeassistant_action_payload["status"], "preview")
        self.assertTrue(mqtt_status_payload["ok"])
        self.assertEqual(mqtt_publish_payload["status"], "preview")
        self.assertEqual(mqtt_subscribe_payload["status"], "ok")
        service.vision_execute.assert_called_once()
        vision_args = service.vision_execute.call_args.args[0]
        self.assertTrue(vision_args["screenshot_base64"])
        service.mobile_status.assert_called_once_with()
        service.mobile_action.assert_called_once()
        mobile_args = service.mobile_action.call_args.args[0]
        self.assertEqual(mobile_args["platform"], "ios")
        self.assertTrue(mobile_args["screenshot_base64"])
        service.homeassistant_status.assert_called_once_with()
        service.homeassistant_discover.assert_called_once_with(domain="light", entity_id_prefix="", limit=250)
        self.assertEqual(service.homeassistant_action.call_count, 2)
        mqtt_args = service.homeassistant_action.call_args_list[1].args[0]
        self.assertEqual(mqtt_args["action"]["type"], "mqtt_publish")
        self.assertEqual(mqtt_args["action"]["transport"], "mqtt-direct")
        service.mqtt_status.assert_called_once_with()
        service.mqtt_subscribe.assert_called_once_with(topic="novaadapt/test", timeout_seconds=0.1, max_messages=1, qos=0)

    def test_voice_transcribe_and_synthesize_commands(self):
        service = mock.Mock()
        service.voice_transcribe.return_value = {"ok": True, "text": "hello"}
        service.voice_synthesize.return_value = {"ok": True, "output_path": "/tmp/out.mp3"}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            transcribe_payload = self._run_cli(
                "voice-transcribe",
                "--audio-path",
                "/tmp/in.wav",
                "--hints",
                "nav,combat",
                "--metadata",
                '{"realm":"game_world"}',
                "--backend",
                "static",
            )
            synth_payload = self._run_cli(
                "voice-synthesize",
                "--text",
                "route locked",
                "--output-path",
                "/tmp/out.mp3",
                "--voice",
                "alloy",
                "--metadata",
                '{"realm":"aetherion"}',
                "--backend",
                "openai",
            )
        self.assertTrue(transcribe_payload["ok"])
        self.assertTrue(synth_payload["ok"])
        service.voice_transcribe.assert_called_once_with(
            "/tmp/in.wav",
            hints=["nav", "combat"],
            metadata={"realm": "game_world"},
            backend="static",
            context="cli",
        )
        service.voice_synthesize.assert_called_once_with(
            "route locked",
            output_path="/tmp/out.mp3",
            voice="alloy",
            metadata={"realm": "aetherion"},
            backend="openai",
            context="cli",
        )

    def test_canvas_and_workflow_commands(self):
        service = mock.Mock()
        service.canvas_status.return_value = {"ok": True, "enabled": False}
        service.canvas_render.return_value = {"ok": True, "session_id": "sess-1"}
        service.canvas_frames.return_value = {"ok": True, "count": 1, "frames": [{"frame_id": "frame-1"}]}
        service.workflows_status.return_value = {"ok": True, "enabled": False}
        service.workflows_start.return_value = {"ok": True, "workflow_id": "wf-1"}
        service.workflows_advance.return_value = {"ok": True, "workflow_id": "wf-1", "status": "running"}
        service.workflows_resume.return_value = {"ok": True, "workflow_id": "wf-1", "status": "running"}
        service.workflows_get.return_value = {"ok": True, "workflow_id": "wf-1", "status": "running"}
        service.workflows_list.return_value = {"ok": True, "count": 1, "workflows": [{"workflow_id": "wf-1"}]}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service):
            canvas_status_payload = self._run_cli("canvas-status")
            canvas_render_payload = self._run_cli(
                "canvas-render",
                "--title",
                "Aetherion board",
                "--session-id",
                "sess-1",
                "--sections",
                '[{"heading":"Trade","body":"stable"}]',
                "--metadata",
                '{"realm":"aetherion"}',
            )
            canvas_frames_payload = self._run_cli("canvas-frames", "--session-id", "sess-1", "--limit", "5")
            workflows_status_payload = self._run_cli("workflows-status")
            workflows_start_payload = self._run_cli(
                "workflows-start",
                "--objective",
                "Patrol route",
                "--steps",
                '[{"name":"scan"}]',
                "--workflow-id",
                "wf-1",
            )
            workflows_advance_payload = self._run_cli(
                "workflows-advance",
                "--workflow-id",
                "wf-1",
                "--result",
                '{"ok":true}',
            )
            workflows_resume_payload = self._run_cli("workflows-resume", "--workflow-id", "wf-1")
            workflows_get_payload = self._run_cli("workflows-get", "--workflow-id", "wf-1")
            workflows_list_payload = self._run_cli("workflows-list", "--limit", "10")
        self.assertTrue(canvas_status_payload["ok"])
        self.assertTrue(canvas_render_payload["ok"])
        self.assertTrue(canvas_frames_payload["ok"])
        self.assertTrue(workflows_status_payload["ok"])
        self.assertEqual(workflows_start_payload["workflow_id"], "wf-1")
        self.assertTrue(workflows_advance_payload["ok"])
        self.assertTrue(workflows_resume_payload["ok"])
        self.assertTrue(workflows_get_payload["ok"])
        self.assertTrue(workflows_list_payload["ok"])
        service.canvas_render.assert_called_once_with(
            "Aetherion board",
            session_id="sess-1",
            sections=[{"heading": "Trade", "body": "stable"}],
            footer="",
            metadata={"realm": "aetherion"},
            context="cli",
        )
        service.workflows_start.assert_called_once_with(
            "Patrol route",
            steps=[{"name": "scan"}],
            metadata={},
            workflow_id="wf-1",
            context="cli",
        )

    def test_benchmark_publish_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            primary_path = f"{tmp}/primary.json"
            baseline_path = f"{tmp}/baseline.json"
            out_dir = f"{tmp}/publication"
            with open(primary_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "summary": {
                            "total": 10,
                            "passed": 9,
                            "failed": 1,
                            "success_rate": 0.9,
                            "first_try_success_rate": 0.9,
                            "avg_action_count": 4.2,
                            "blocked_count": 1,
                        }
                    },
                    handle,
                )
            with open(baseline_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "summary": {
                            "total": 10,
                            "passed": 7,
                            "failed": 3,
                            "success_rate": 0.7,
                            "first_try_success_rate": 0.7,
                            "avg_action_count": 5.0,
                            "blocked_count": 2,
                        }
                    },
                    handle,
                )

            payload = self._run_cli(
                "benchmark-publish",
                "--primary",
                primary_path,
                "--baseline",
                f"OtherAgent={baseline_path}",
                "--out-dir",
                out_dir,
                "--md-title",
                "CLI Bench Publish",
                "--notes",
                "cli smoke",
            )

            self.assertTrue(payload["comparison_json"].endswith("benchmark.compare.json"))
            self.assertTrue(payload["comparison_markdown"].endswith("benchmark.compare.md"))
            self.assertTrue(payload["readme"].endswith("README.md"))
            with io.open(f"{out_dir}/README.md", encoding="utf-8") as handle:
                self.assertIn("CLI Bench Publish", handle.read())

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
