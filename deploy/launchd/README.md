# NovaAdapt launchd deployment (macOS)

This folder contains launchd wrappers/templates for running NovaAdapt as persistent user agents on macOS.

## Services

- `com.novaadapt.core`
- `com.novaadapt.bridge`
- `com.novaadapt.gateway` (optional persistent NovaAgent gateway daemon)

## Quick install

From the repo root:

```bash
./installer/install_launchd_services.sh --with-gateway --start
```

This script will:

- create `~/Library/Application Support/NovaAdapt/{launchd,env,data}`
- copy wrapper scripts into `~/Library/Application Support/NovaAdapt/launchd`
- install env files in `~/Library/Application Support/NovaAdapt/env` (if missing)
- generate `~/Library/LaunchAgents/com.novaadapt.*.plist`
- optionally bootstrap agents when `--start` is supplied

## Configure

Edit env files before starting:

- `~/Library/Application Support/NovaAdapt/env/core.env`
- `~/Library/Application Support/NovaAdapt/env/bridge.env`
- `~/Library/Application Support/NovaAdapt/env/gateway.env`

At minimum set:

- `NOVAADAPT_REPO_ROOT`
- `NOVAADAPT_CORE_TOKEN`
- `NOVAADAPT_BRIDGE_TOKEN`

## Manual controls

```bash
launchctl bootout "gui/$UID" "$HOME/Library/LaunchAgents/com.novaadapt.core.plist" || true
launchctl bootstrap "gui/$UID" "$HOME/Library/LaunchAgents/com.novaadapt.core.plist"
launchctl kickstart -k "gui/$UID/com.novaadapt.core"
```

Repeat for `com.novaadapt.bridge` and `com.novaadapt.gateway`.

Logs are written to:

- `~/Library/Logs/NovaAdapt/core.out.log`
- `~/Library/Logs/NovaAdapt/core.err.log`
- `~/Library/Logs/NovaAdapt/bridge.out.log`
- `~/Library/Logs/NovaAdapt/bridge.err.log`
- `~/Library/Logs/NovaAdapt/gateway.out.log`
- `~/Library/Logs/NovaAdapt/gateway.err.log`
