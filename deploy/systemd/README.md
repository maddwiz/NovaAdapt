# NovaAdapt systemd deployment

This folder contains service units and startup wrappers for running NovaAdapt as managed Linux services.

## Files

- `novaadapt-core.service`
- `novaadapt-bridge.service`
- `novaadapt-runtime.service` (optional built-in execution endpoint)
- `novaadapt-gateway.service` (optional persistent NovaAgent gateway daemon)
- `start-core.sh`
- `start-bridge.sh`
- `start-runtime.sh`
- `start-gateway.sh`
- `core.env.example`
- `bridge.env.example`
- `runtime.env.example`
- `gateway.env.example`

Automated installer:

```bash
sudo ./installer/install_systemd_services.sh --with-runtime --with-gateway --start
```

## Install steps

1. Copy repo to `/opt/novaadapt` and create a runtime user:

```bash
sudo useradd --system --home /opt/novaadapt --shell /usr/sbin/nologin novaadapt || true
sudo mkdir -p /var/lib/novaadapt /etc/novaadapt
sudo chown -R novaadapt:novaadapt /var/lib/novaadapt /opt/novaadapt
```

2. Install env files and edit secrets:

```bash
sudo cp /opt/novaadapt/deploy/systemd/core.env.example /etc/novaadapt/core.env
sudo cp /opt/novaadapt/deploy/systemd/bridge.env.example /etc/novaadapt/bridge.env
sudo cp /opt/novaadapt/deploy/systemd/runtime.env.example /etc/novaadapt/runtime.env
sudo cp /opt/novaadapt/deploy/systemd/gateway.env.example /etc/novaadapt/gateway.env
sudo chmod 600 /etc/novaadapt/core.env /etc/novaadapt/bridge.env /etc/novaadapt/runtime.env /etc/novaadapt/gateway.env
sudo editor /etc/novaadapt/core.env
sudo editor /etc/novaadapt/bridge.env
sudo editor /etc/novaadapt/runtime.env
sudo editor /etc/novaadapt/gateway.env
```

3. Install units and startup wrappers:

```bash
sudo install -m 755 /opt/novaadapt/deploy/systemd/start-core.sh /opt/novaadapt/deploy/systemd/start-core.sh
sudo install -m 755 /opt/novaadapt/deploy/systemd/start-bridge.sh /opt/novaadapt/deploy/systemd/start-bridge.sh
sudo install -m 755 /opt/novaadapt/deploy/systemd/start-runtime.sh /opt/novaadapt/deploy/systemd/start-runtime.sh
sudo install -m 755 /opt/novaadapt/deploy/systemd/start-gateway.sh /opt/novaadapt/deploy/systemd/start-gateway.sh
sudo cp /opt/novaadapt/deploy/systemd/novaadapt-core.service /etc/systemd/system/
sudo cp /opt/novaadapt/deploy/systemd/novaadapt-bridge.service /etc/systemd/system/
sudo cp /opt/novaadapt/deploy/systemd/novaadapt-runtime.service /etc/systemd/system/
sudo cp /opt/novaadapt/deploy/systemd/novaadapt-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
```

4. Enable and start:

```bash
sudo systemctl enable --now novaadapt-core.service
sudo systemctl enable --now novaadapt-bridge.service
sudo systemctl enable --now novaadapt-runtime.service
sudo systemctl enable --now novaadapt-gateway.service
```

5. Verify:

```bash
systemctl status novaadapt-core.service --no-pager
systemctl status novaadapt-bridge.service --no-pager
systemctl status novaadapt-runtime.service --no-pager
systemctl status novaadapt-gateway.service --no-pager
curl -fsS http://127.0.0.1:8787/health
curl -fsS http://127.0.0.1:9797/health?deep=1
curl -fsS http://127.0.0.1:8765/health
```

If bridge TLS is enabled, use `https://` and either trusted certs or `curl -k`.

`core.env` also exposes `NOVAADAPT_AUDIT_RETENTION_SECONDS` and `NOVAADAPT_AUDIT_CLEANUP_INTERVAL_SECONDS` to bound audit log growth in long-running deployments, plus `NOVAADAPT_OTEL_*` settings for OTLP trace export. Set `DIRECTSHELL_TRANSPORT` + endpoint vars in `core.env` when routing core execution to the runtime service.
`bridge.env` supports optional bridge->core TLS/mTLS settings (`NOVAADAPT_CORE_CA_FILE`, `NOVAADAPT_CORE_CLIENT_CERT_FILE`, `NOVAADAPT_CORE_CLIENT_KEY_FILE`, `NOVAADAPT_CORE_TLS_SERVER_NAME`).
`runtime.env` controls the built-in execution endpoint mode (`NOVAADAPT_RUNTIME_MODE=native-http|native-daemon`) and optional transport token enforcement.
`gateway.env` configures persistent queue and routing behavior for `gateway-daemon`.

Token rotation helper:

```bash
/opt/novaadapt/installer/rotate_tokens.sh --core-env /etc/novaadapt/core.env --bridge-env /etc/novaadapt/bridge.env --restart-systemd
```
