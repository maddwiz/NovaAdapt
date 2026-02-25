# Observability Stack

Bring up local OpenTelemetry collector:

```bash
cd deploy
docker compose -f docker-compose.observability.yml up -d
```

Run core with tracing enabled:

```bash
novaadapt serve \
  --otel-enabled \
  --otel-service-name novaadapt-core \
  --otel-exporter-endpoint http://127.0.0.1:4318/v1/traces
```

Notes:
- Tracing is optional and only activates when `opentelemetry` dependencies are installed.
- Current collector config exports traces to collector logs for quick verification.

## Prometheus Monitoring + Alerts

Start core+bridge with Prometheus monitoring:

```bash
cd deploy
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

Open Prometheus at `http://127.0.0.1:9090`.

Included files:
- `observability/prometheus.yml` (scrape config for core + bridge)
- `observability/prometheus-alerts.yml` (baseline alert rules)

Default scrape auth assumes core token is `core-token`.
If you change `NOVAADAPT_CORE_TOKEN`, update `authorization.credentials` in `observability/prometheus.yml` to match.
