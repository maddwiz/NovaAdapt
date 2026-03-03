# NOVAAI MASTER HANDOFF POINTER

Canonical master handoff location:
- `NovaPrime/handoff/NOVAAI_MASTER_HANDOFF.md`

Current verification snapshot (2026-03-03):
- NovaAdapt full suite pass:
  - `PYTHONPATH=core:shared python3 -m unittest discover -s tests -p 'test_*.py' -v`
  - `292` tests passed.
- NovaPrime smoke bundle pass:
  - `PYTHONPATH=. ./tools/ci_local.sh`
- NovaPrime integration branch head:
  - `f129f6c` (`codex/the-space-in-between-novaprime-integration`)
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
  - node identity attestation + sybil enforcement (`/api/v1/mesh/security/identity/attestation*`, `/api/v1/mesh/security/sybil/enforce`)
  - strict attestation policy path (`/api/v1/mesh/security/identity/policy`, strong-attestation sybil guard toggles)
  - sandbox hardening v2 (`gvisor|firecracker` modes + high-risk attestation policy gate)
  - sandbox hardening v3 firecracker external runner bridge (`NOVAPRIME_FIRECRACKER_RUNNER*`)
  - native Firecracker runner module (`python3 -m tools.firecracker_runner`) with API-socket VM orchestration + bridge/result contract
  - production Firecracker hardening (jailer profile wiring + guest result contracts: `host_bridge|vsock|serial|file|auto`)
  - hardened guest agent reference (`python3 -m tools.firecracker_guest_agent`) + smoke coverage
  - signature policy modes + key lifecycle (`MESH_SIGNATURE_POLICY_MODE`, signer registry enforcement, `python3 -m tools.signing_keys ...`)
  - distributed signer-key mesh sync (`/mesh/v1/signer-keys`, `/api/v1/mesh/security/signer-keys*`, mesh sync CLI key gossip/pull)
  - signer-key multisig governance flow (`/api/v1/mesh/security/signer-keys/propose|vote|finalize`, governed register/revoke/rotate)
  - strict provenance attestation checks (provenance chain, hardware fingerprint, measurement hash)
  - cluster-wide Sybil defaults wired into analysis/enforcement/allocation (`NOVAPRIME_SYBIL_*_DEFAULT`)
  - strict mesh TLS peer enforcement (`MESH_TLS_REQUIRED`, fail-closed on non-HTTPS peers)
  - mesh certificate pinning policy (`MESH_TLS_PINNED_CERT_SHA256*`) for peer transport verification
  - mesh node HTTPS/mTLS mode (`MESH_NODE_TLS_*`) + CLI TLS flags + transport policy tests
  - signed mesh request auth + anti-replay (`MESH_REQUEST_SIGNING_KEY`, `MESH_NODE_REQUIRE_SIGNED_REQUESTS`, nonce/timestamp verification)
  - reconcile daemon service lifecycle wrappers (systemd + launchd installers/templates)

Important canonical constraints:
- NovaAdapt remains standalone-capable; NovaPrime is optional and must fail open unless explicitly required.
- Entropy is an in-game antagonist only, not a real-world representation.
- Public mesh must remain public-artifact-only (no private chats/memory/tool traces).
