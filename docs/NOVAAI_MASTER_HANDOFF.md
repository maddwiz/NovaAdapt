# NOVAAI MASTER HANDOFF POINTER

Canonical master handoff location:
- `NovaPrime/handoff/NOVAAI_MASTER_HANDOFF.md`

Current verification snapshot (2026-03-03):
- NovaAdapt full suite pass:
  - `PYTHONPATH=core:shared python3 -m unittest discover -s tests -p 'test_*.py' -v`
  - `292` tests passed.
- NovaPrime smoke bundle pass:
  - `PYTHONPATH=. ./tools/ci_local.sh`
- Latest NovaPrime handoff update includes:
  - sandbox isolation v1 (`local_restricted` + optional `docker`)
  - staking/slashing v1
  - reputation consensus + partition primitives v1
  - reputation gossip sync transport (`mesh/exchange.py`, `/mesh/v1/reputation`)
  - partition reconcile apply API (`/api/v1/mesh/partition/reconcile`)
  - automated slashing policy API (`/api/v1/mesh/security/slash/*`)
  - council-governed slash flow (`/api/v1/mesh/security/slash/propose|vote|finalize`) with high-severity governance hook in `slash/apply`
  - partition reconcile policy versioning + scheduler hooks (`policy=lww|weighted_median`, `/api/v1/mesh/partition/reconcile/schedule`)
  - persistent reconcile daemon worker + peer snapshot transport (`python3 -m tools.reconcile_daemon`, `/mesh|/api ... /snapshot/{reputation,ledger}`)
  - sybil analysis + guarded allocation (`/api/v1/mesh/security/sybil`, sybil-aware `/mesh/jobs/allocate`)
  - optional dilithium signature scaffolding (`MESH_SIGNING_SCHEME=dilithium-v1` with graceful fallback)

Important canonical constraints:
- NovaAdapt remains standalone-capable; NovaPrime is optional and must fail open unless explicitly required.
- Entropy is an in-game antagonist only, not a real-world representation.
- Public mesh must remain public-artifact-only (no private chats/memory/tool traces).
