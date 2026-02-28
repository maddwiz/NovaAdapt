import sys
import unittest
from unittest import mock

from novaadapt_core import cli


class _StubJob:
    def __init__(self, payload: dict):
        self.payload = payload


class GatewayCLITests(unittest.TestCase):
    def test_gateway_daemon_command_wires_components(self):
        service = mock.Mock()
        service.run.return_value = {"ok": True, "results": []}
        queue = mock.Mock()
        worker = mock.Mock()
        delivery = mock.Mock()
        router = mock.Mock()
        daemon = mock.Mock()
        connectors = {"webchat": mock.Mock()}

        with (
            mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service) as service_ctor,
            mock.patch("novaadapt_core.cli.GatewayJobQueue", return_value=queue) as queue_ctor,
            mock.patch("novaadapt_core.cli.build_gateway_connectors", return_value=connectors) as connectors_fn,
            mock.patch("novaadapt_core.cli.DeliveryManager", return_value=delivery) as delivery_ctor,
            mock.patch("novaadapt_core.cli.GatewayRouter", return_value=router) as router_ctor,
            mock.patch("novaadapt_core.cli.GatewayWorker", return_value=worker) as worker_ctor,
            mock.patch("novaadapt_core.cli.NovaAgentDaemon", return_value=daemon) as daemon_ctor,
            mock.patch.object(
                sys,
                "argv",
                [
                    "novaadapt",
                    "gateway-daemon",
                    "--default-workspace",
                    "ops",
                    "--default-profile",
                    "developer",
                    "--channel-workspace-map",
                    '{"webchat":"ops"}',
                    "--channel-profile-map",
                    '{"webchat":"developer"}',
                    "--retry-delay-seconds",
                    "3",
                    "--max-attempts",
                    "4",
                    "--poll-interval-seconds",
                    "0.5",
                ],
            ),
        ):
            cli.main()

        queue_ctor.assert_called_once()
        service_ctor.assert_called_once()
        connectors_fn.assert_called_once_with()
        delivery_ctor.assert_called_once()
        router_ctor.assert_called_once_with(
            default_workspace="ops",
            default_profile="developer",
            channel_workspace_map={"webchat": "ops"},
            channel_profile_map={"webchat": "developer"},
        )
        worker_ctor.assert_called_once()
        daemon_ctor.assert_called_once_with(
            worker=worker,
            delivery=delivery,
            router=router,
            connectors=connectors,
            poll_interval_seconds=0.5,
        )
        daemon.run_forever.assert_called_once_with()

        runner = worker_ctor.call_args.kwargs["runner"]
        out = runner(_StubJob({"objective": "ping"}))
        self.assertTrue(out["ok"])
        run_payload = service.run.call_args.args[0]
        self.assertEqual(run_payload["objective"], "ping")
        self.assertFalse(run_payload["use_kernel"])
        self.assertFalse(run_payload["kernel_required"])

    def test_gateway_daemon_rejects_non_object_maps(self):
        with mock.patch.object(
            sys,
            "argv",
            [
                "novaadapt",
                "gateway-daemon",
                "--channel-workspace-map",
                "[1,2,3]",
            ],
        ):
            with self.assertRaises(SystemExit) as exc:
                cli.main()
        self.assertIn("--channel-workspace-map must be a JSON object", str(exc.exception))

    def test_gateway_daemon_kernel_mode_on_passes_kernel_flags(self):
        service = mock.Mock()
        service.run.return_value = {"ok": True, "results": []}
        queue = mock.Mock()
        worker = mock.Mock()
        delivery = mock.Mock()
        router = mock.Mock()
        daemon = mock.Mock()
        connectors = {"webchat": mock.Mock()}

        with (
            mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=service),
            mock.patch("novaadapt_core.cli.GatewayJobQueue", return_value=queue),
            mock.patch("novaadapt_core.cli.build_gateway_connectors", return_value=connectors),
            mock.patch("novaadapt_core.cli.DeliveryManager", return_value=delivery),
            mock.patch("novaadapt_core.cli.GatewayRouter", return_value=router),
            mock.patch("novaadapt_core.cli.GatewayWorker", return_value=worker) as worker_ctor,
            mock.patch("novaadapt_core.cli.NovaAgentDaemon", return_value=daemon),
            mock.patch.object(
                sys,
                "argv",
                [
                    "novaadapt",
                    "gateway-daemon",
                    "--gateway-kernel-mode",
                    "on",
                    "--gateway-kernel-required",
                ],
            ),
        ):
            cli.main()

        runner = worker_ctor.call_args.kwargs["runner"]
        out = runner(_StubJob({"objective": "ping"}))
        self.assertTrue(out["ok"])
        run_payload = service.run.call_args.args[0]
        self.assertTrue(run_payload["use_kernel"])
        self.assertTrue(run_payload["kernel_required"])


if __name__ == "__main__":
    unittest.main()
