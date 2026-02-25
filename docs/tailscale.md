# Tailscale Relay Setup

NovaAdapt can expose the bridge endpoint over a tailnet using an optional Docker Compose overlay.

## Prerequisites

- Docker / Docker Compose
- A Tailscale auth key

## Run With Tailscale Enabled

```bash
NOVAADAPT_WITH_TAILSCALE=1 \
NOVAADAPT_TAILSCALE_AUTHKEY=tskey-... \
./installer/run_docker_stack.sh --with-tailscale
```

Optional environment values (can be added to `deploy/.env`):

- `NOVAADAPT_TAILSCALE_HOSTNAME` (default: `novaadapt-bridge`)
- `NOVAADAPT_TAILSCALE_EXTRA_ARGS` (default: `--ssh=false`)

Compose files used:

- `deploy/docker-compose.yml`
- `deploy/docker-compose.tailscale.yml`

The `tailscale` container shares the bridge network namespace, so remote clients connect to the same bridge routes (`/health`, `/ws`, `/run_async`, `/terminal/sessions`, etc.) through the tailnet.
