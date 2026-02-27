import json
import tempfile
import unittest
from pathlib import Path

from novaadapt_core.doctor import run_doctor


class _HealthyService:
    def models(self, config_path=None):
        _ = config_path
        return [{"name": "local-qwen"}]

    def check(self, config_path=None, model_names=None, probe_prompt="Reply with: OK"):
        _ = (config_path, model_names, probe_prompt)
        return [{"name": "local-qwen", "ok": True}]

    def memory_status(self):
        return {"ok": True, "enabled": True, "backend": "stub-memory"}

    def novaprime_status(self):
        return {"ok": True, "enabled": True, "backend": "novaprime-http"}

    def plugins(self):
        return [{"name": "novabridge"}, {"name": "sib_bridge"}]

    def plugin_health(self, plugin_name):
        return {"ok": True, "plugin": plugin_name}

    def directshell_probe(self):
        return {"ok": True, "transport": "stub"}

    def browser_status(self):
        return {"ok": True, "transport": "browser"}


class _UnhealthyService(_HealthyService):
    def check(self, config_path=None, model_names=None, probe_prompt="Reply with: OK"):
        _ = (config_path, model_names, probe_prompt)
        return [{"name": "local-qwen", "ok": False}]

    def memory_status(self):
        return {"ok": False, "enabled": True, "backend": "stub-memory", "error": "offline"}

    def novaprime_status(self):
        return {"ok": True, "enabled": False, "backend": "noop"}

    def plugin_health(self, plugin_name):
        return {"ok": False, "plugin": plugin_name, "error": "offline"}

    def directshell_probe(self):
        return {"ok": False, "error": "missing runtime"}

    def browser_status(self):
        return {"ok": False, "error": "playwright not installed"}


class DoctorTests(unittest.TestCase):
    def _write_config(self, path: Path, *, default_model: str = "local-qwen"):
        payload = {
            "default_model": default_model,
            "models": [
                {
                    "name": "local-qwen",
                    "provider": "openai-compatible",
                    "model": "qwen2.5:latest",
                    "base_url": "http://localhost:11434/v1",
                }
            ],
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def test_doctor_healthy_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "models.json"
            self._write_config(cfg)
            report = run_doctor(
                _HealthyService(),
                config_path=cfg,
                include_execution=True,
                include_plugins=True,
                include_model_health=True,
            )

        self.assertTrue(report["ok"])
        self.assertEqual(report["summary"]["fail"], 0)
        names = [str(item.get("name")) for item in report["checks"]]
        self.assertIn("config.exists", names)
        self.assertIn("models.health", names)
        self.assertIn("memory.status", names)
        self.assertIn("novaprime.status", names)
        self.assertIn("plugins.health.summary", names)
        self.assertIn("execution.directshell", names)

    def test_doctor_handles_missing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "missing.json"
            report = run_doctor(_HealthyService(), config_path=cfg)
        self.assertFalse(report["ok"])
        self.assertEqual(report["summary"]["fail"], 1)
        self.assertEqual(report["checks"][0]["name"], "config.exists")

    def test_doctor_reports_warnings_and_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "models.json"
            self._write_config(cfg)
            report = run_doctor(
                _UnhealthyService(),
                config_path=cfg,
                include_execution=True,
                include_plugins=True,
                include_model_health=True,
            )
        self.assertFalse(report["ok"])
        self.assertGreaterEqual(report["summary"]["warn"], 1)
        self.assertGreaterEqual(report["summary"]["fail"], 1)
        checks = {str(item["name"]): item for item in report["checks"]}
        self.assertEqual(checks["models.health"]["status"], "fail")
        self.assertEqual(checks["memory.status"]["status"], "warn")
        self.assertEqual(checks["novaprime.status"]["status"], "warn")
        self.assertEqual(checks["execution.directshell"]["status"], "fail")


if __name__ == "__main__":
    unittest.main()

