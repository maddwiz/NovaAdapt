import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from novaadapt_core import cli


class DoctorCLITests(unittest.TestCase):
    def _run_cli(self, *argv: str):
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", ["novaadapt", *argv]), redirect_stdout(stdout):
            cli.main()
        raw = stdout.getvalue().strip()
        if not raw:
            return None
        return json.loads(raw)

    def test_doctor_command_defaults(self):
        fake_service = mock.Mock()
        fake_report = {"ok": True, "summary": {"pass": 1, "warn": 0, "fail": 0}, "checks": []}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=fake_service) as service_ctor:
            with mock.patch("novaadapt_core.cli.run_doctor", return_value=fake_report) as run_doctor_fn:
                payload = self._run_cli("doctor")

        self.assertTrue(payload["ok"])
        service_ctor.assert_called_once()
        run_doctor_fn.assert_called_once()
        kwargs = run_doctor_fn.call_args.kwargs
        self.assertFalse(kwargs["include_execution"])
        self.assertTrue(kwargs["include_plugins"])
        self.assertTrue(kwargs["include_model_health"])

    def test_doctor_command_with_flags(self):
        fake_service = mock.Mock()
        fake_report = {"ok": False, "summary": {"pass": 0, "warn": 1, "fail": 1}, "checks": []}
        with mock.patch("novaadapt_core.cli.NovaAdaptService", return_value=fake_service):
            with mock.patch("novaadapt_core.cli.run_doctor", return_value=fake_report) as run_doctor_fn:
                payload = self._run_cli(
                    "doctor",
                    "--execution",
                    "--skip-plugins",
                    "--skip-model-health",
                )

        self.assertFalse(payload["ok"])
        kwargs = run_doctor_fn.call_args.kwargs
        self.assertTrue(kwargs["include_execution"])
        self.assertFalse(kwargs["include_plugins"])
        self.assertFalse(kwargs["include_model_health"])


if __name__ == "__main__":
    unittest.main()

