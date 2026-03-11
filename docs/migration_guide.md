# NovaAdapt Migration Guide

This guide is for operators upgrading from early desktop-only NovaAdapt builds to the current production-track runtime.

## Who Should Read This

Use this guide if your current setup predates any of the following:

- Native built-in execution runtime as the default DirectShell transport.
- Playwright browser automation routes.
- Vision / mobile / IoT control surfaces.
- Agent template export, share, and launch flows.
- Bridge websocket command relay and remote terminal support.
- NovaSpine consolidation / dream maintenance hooks.

## Upgrade Summary

Current NovaAdapt releases add these major runtime surfaces:

- `DIRECTSHELL_TRANSPORT=native` is now the default.
- Optional compatible transports: `http`, `grpc`, `daemon`, `subprocess`, `browser`.
- New control-anything endpoints:
  - `POST /execute/vision`
  - `POST /mobile/action`
  - `GET /mobile/status`
  - `GET /iot/homeassistant/entities`
  - `GET /iot/homeassistant/status`
  - `POST /iot/homeassistant/action`
  - `GET /iot/mqtt/status`
  - `POST /iot/mqtt/publish`
  - `POST /iot/mqtt/subscribe`
- New operator assets:
  - agent templates / gallery / sharing
  - control artifact history + preview retrieval
  - remote terminal sessions
  - live observability / governance

## Database and State Stores

No manual schema rewrite is required.

NovaAdapt now applies explicit SQLite migrations via `schema_migrations` for plan, audit, action, and template stores. On first launch after upgrade, the runtime will migrate forward automatically.

Recommended pre-upgrade backup:

```bash
cp ~/.novaadapt/actions.db ~/.novaadapt/actions.db.bak
cp ~/.novaadapt/plans.db ~/.novaadapt/plans.db.bak
cp ~/.novaadapt/audit.db ~/.novaadapt/audit.db.bak
```

If you use custom DB paths, back up those locations instead.

## Execution Runtime Migration

### Old Assumption

Older builds expected an external DirectShell binary or an early HTTP/daemon transport.

### New Default

The built-in native executor is now first-class and the default transport:

```bash
export DIRECTSHELL_TRANSPORT=native
```

Optional transports remain available:

```bash
export DIRECTSHELL_TRANSPORT=http
export DIRECTSHELL_HTTP_URL=http://127.0.0.1:8765/execute

export DIRECTSHELL_TRANSPORT=grpc
export DIRECTSHELL_GRPC_TARGET=127.0.0.1:8767

export DIRECTSHELL_TRANSPORT=daemon
export DIRECTSHELL_DAEMON_SOCKET=/tmp/directshell.sock
```

Install optional gRPC transport support when needed:

```bash
pip install -e '.[grpc]'
```

Probe the selected transport before enabling live execution:

```bash
novaadapt directshell-check
novaadapt directshell-check --transport grpc
```

## Browser Runtime Migration

Browser automation is no longer an external add-on concept. It is now a first-class NovaAdapt runtime surface.

Install optional browser dependencies if needed:

```bash
pip install -e '.[browser]'
python -m playwright install chromium
```

## Mobile and IoT Migration

If you previously treated mobile or Home Assistant integration as external experiments, move to the built-in endpoints and operator surfaces.

Check readiness:

```bash
novaadapt mobile-status
novaadapt homeassistant-status
novaadapt mqtt-status
```

Preview actions before execution:

```bash
novaadapt mobile-action --platform android --action-json '{"type":"open_app","package":"com.android.settings"}'
novaadapt homeassistant-action --action-json '{"type":"ha_service","domain":"light","service":"turn_on","entity_id":"light.office"}'
```

## Bridge Migration

The bridge now forwards more core routes than early builds did, including:

- control artifacts
- agent templates
- vision/mobile/IoT routes
- remote terminal routes
- dashboard data

If you use scoped bridge tokens, review scope assumptions. Read operations still map to `read`, but new POST control routes require `run`.

## Client Migration

### Desktop / iOS

Existing desktop and iOS clients continue to work, but now expose:

- repair tuning
- collaboration transcript visibility
- template sharing / launch
- control-anything actions
- terminal session controls

### Android

Android support is now available in two forms:

- installable operator PWA built from `view/`
- native Android shell source project at `mobile/android/NovaAdaptOperatorApp`

See `mobile/android/README.md`.

### Wearables

Wearable adapters are now packaged as release artifacts alongside a release manifest for supported device families. See `wearables/release_manifest.json`.

## Recommended Upgrade Checklist

1. Back up local SQLite state.
2. Upgrade the Python package / branch.
3. Run `novaadapt directshell-check`.
4. Run `make smoke`.
5. Re-issue bridge session tokens if you rotate credentials.
6. Re-test one preview flow for each critical surface you use:
   - desktop
   - browser
   - mobile
   - IoT
   - remote terminal
7. Refresh operator clients and wearable release bundles.

## Rollback Strategy

If a release introduces a regression:

1. Restore backed-up SQLite files.
2. Reset env vars for the selected DirectShell transport.
3. Revert to the prior release artifact bundle.
4. Re-run `novaadapt directshell-check` and `make smoke` against the restored environment.

## Validation Commands

```bash
make test
make smoke
PYTHONPATH=core:shared python3 -m unittest tests.test_native_grpc tests.test_native_http tests.test_native_daemon -v
```

Demo entrypoints for operator verification:

- `/Users/desmondpottle/Documents/New project/NovaAdapt/scripts/demo_vision_desktop.sh`
- `/Users/desmondpottle/Documents/New project/NovaAdapt/scripts/demo_mobile_banking.sh`
- `/Users/desmondpottle/Documents/New project/NovaAdapt/scripts/demo_iot_swarm.sh`
- `/Users/desmondpottle/Documents/New project/NovaAdapt/scripts/publish_benchmarks.sh`
