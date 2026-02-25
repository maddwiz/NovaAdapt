# NovaAdapt systemd deployment

This folder contains service units and startup wrappers for running NovaAdapt as managed Linux services.

## Files

- `novaadapt-core.service`
- `novaadapt-bridge.service`
- `start-core.sh`
- `start-bridge.sh`
- `core.env.example`
- `bridge.env.example`

Automated installer:

```bash
sudo ./installer/install_systemd_services.sh
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
sudo chmod 600 /etc/novaadapt/core.env /etc/novaadapt/bridge.env
sudo editor /etc/novaadapt/core.env
sudo editor /etc/novaadapt/bridge.env
```

3. Install units and startup wrappers:

```bash
sudo install -m 755 /opt/novaadapt/deploy/systemd/start-core.sh /opt/novaadapt/deploy/systemd/start-core.sh
sudo install -m 755 /opt/novaadapt/deploy/systemd/start-bridge.sh /opt/novaadapt/deploy/systemd/start-bridge.sh
sudo cp /opt/novaadapt/deploy/systemd/novaadapt-core.service /etc/systemd/system/
sudo cp /opt/novaadapt/deploy/systemd/novaadapt-bridge.service /etc/systemd/system/
sudo systemctl daemon-reload
```

4. Enable and start:

```bash
sudo systemctl enable --now novaadapt-core.service
sudo systemctl enable --now novaadapt-bridge.service
```

5. Verify:

```bash
systemctl status novaadapt-core.service --no-pager
systemctl status novaadapt-bridge.service --no-pager
curl -fsS http://127.0.0.1:8787/health
curl -fsS http://127.0.0.1:9797/health?deep=1
```

If bridge TLS is enabled, use `https://` and either trusted certs or `curl -k`.
