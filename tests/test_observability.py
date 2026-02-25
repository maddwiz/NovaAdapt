import unittest

from novaadapt_core.observability import configure_tracing, start_span


class ObservabilityTests(unittest.TestCase):
    def test_configure_disabled_is_false(self):
        self.assertFalse(configure_tracing(enabled=False))

    def test_start_span_noop_without_configuration(self):
        with start_span("unit-test") as span:
            self.assertIsNone(span)

    def test_configure_enabled_does_not_raise(self):
        result = configure_tracing(
            enabled=True,
            service_name="novaadapt-tests",
            exporter_endpoint="http://127.0.0.1:4318/v1/traces",
        )
        self.assertIn(result, {True, False})


if __name__ == "__main__":
    unittest.main()
