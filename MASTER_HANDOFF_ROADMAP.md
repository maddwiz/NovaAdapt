# MASTER HANDOFF ROADMAP

Last Updated: 2026-03-05  
Repo: `maddwiz/NovaAdapt`  
Kernel Pair: `maddwiz/NovaPrime`

This file is the continuation map for future Codex sessions working from NovaAdapt first.

## 1) Current State (Verified)

- NovaAdapt remains standalone-ready (no NovaPrime required).
- Kernel optional path is implemented via:
  - `core/novaadapt_core/novaprime/kernel_adapter.py`
  - `core/novaadapt_core/novaprime/client.py`
  - `core/novaadapt_core/service.py`
- `NoopNovaPrimeClient` graceful fallback is present.
- Multi-channel adapter/connector surface is present (including iMessage).
- XREAL/X1 integration path is present (`xreal-intent` CLI + connector/bridge support).
- Gateway components are present (`agent_gateway/*`) with queue/worker/delivery/scheduler modules.
- NovaPrime now exposes additional SIB/Aetherion routes:
  - `/api/v1/sib/imprinting/start|session|resolve`
  - `/api/v1/sib/phase/evaluate`
  - `/api/v1/sib/void/create|tick`
  - `/api/v1/mesh/aetherion/state`
  - `/api/v1/narrative/bond/history`
- NovaAdapt now wires the above NovaPrime routes end-to-end:
  - `NovaPrimeClient` methods
  - `NovaAdaptService` passthrough methods
  - HTTP API routes (`/novaprime/...`)
  - MCP tools (`novaadapt_novaprime_*`)
  - shared SDK methods (`shared/novaadapt_shared/api_client.py`)
  - OpenAPI path documentation
  - Test coverage updated in `tests/test_service.py`, `tests/test_server.py`, `tests/test_mcp.py`, `tests/test_api_client.py`
- Live contract test added: `tests/test_novaprime_contract_e2e.py` (spins real NovaPrime API and verifies NovaAdapt `/novaprime/*` proxy surface).
- CI job added for live contract coverage: `.github/workflows/ci.yml` job `novaprime-live-contract`.
- CI live-contract checkout is now fork-safe: NovaPrime checkout is attempted with `continue-on-error`, and test runs in skip mode when unavailable.
- Live contract test now includes negative-path assertions (missing IDs, not-found sessions, invalid payload shapes).
- Live contract test is now version-tolerant against `NovaPrime@main`: it capability-probes advanced SIB/Aetherion routes and `skipTest`s when those optional routes are absent (prevents false-red CI on cross-repo drift).
- Live contract coverage now includes auth-required mode: with `NOVAPRIME_API_TOKEN` enabled upstream, NovaAdapt route calls correctly fail without bearer token and succeed when `NOVAADAPT_NOVAPRIME_TOKEN` is configured.
- Latest verification run: `PYTHONPATH=core:shared python3 -m unittest discover -s tests` → `293 tests OK`.

## 2) Hard Invariants

1. Never remove standalone behavior.
2. NovaPrime integration is opt-in, fail-open by default unless explicitly required.
3. Gateway layer is plumbing/routing/delivery, not cognition.
4. Public mesh/game perks are additive, not mandatory for OSS users.
5. Entropy is game storyline only, not a real-world representation.

## 3) Open Gaps (Priority)

### P0

1. Keep NovaPrime route parity in sync when NovaPrime adds/churns API routes (fail-open behavior required).
2. Track and fix noisy ResourceWarnings in test suite (unclosed HTTPError/sqlite handles) to reduce CI noise.

### P1

4. Add `decompose` strategy to shared model router while preserving `single`/`vote`.
5. Add voice module (STT/TTS/wake) as optional backend adapters.
6. Add canvas/workflow modules behind flags, keeping default footprint minimal.

## 4) Continuation Checklist

1. Validate local state:
   - `git status --short --branch`
2. Run targeted tests:
   - `PYTHONPATH=core:shared python3 -m unittest tests.test_service tests.test_novaprime_client tests.test_kernel_adapter`
   - `PYTHONPATH=core:shared python3 -m unittest tests.test_agent_gateway tests.test_cli_channels tests.test_cli_xreal tests.test_server`
   - If NovaPrime-facing files changed: `PYTHONPATH=core:shared python3 -m unittest tests.test_mcp tests.test_api_client`
   - If sibling `NovaPrime` exists: `PYTHONPATH=core:shared python3 -m unittest tests.test_novaprime_contract_e2e`
3. Confirm standalone health payload still reports `requires_novaprime: false`.
4. Only stage source/test/docs files.

## 5) Cross-Repo Contract

- Keep API compatibility with NovaPrime’s optional route surface.
- Any new NovaPrime route usage in NovaAdapt must degrade safely when unavailable.
- Update this roadmap with exact next tasks and command-based verification at end of each session.
