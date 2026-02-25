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
