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
  - `2dd264b` (`codex/the-space-in-between-novaprime-integration`)
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
  - signed mesh key rotation/scoping (`X-Mesh-Key-Id`, `MESH_REQUEST_SIGNING_KEY_IDS_JSON`, `MESH_REQUEST_SIGNING_KEYS_BY_ID_JSON`, `MESH_NODE_SIGNING_KEYS_BY_ID_JSON`, `MESH_NODE_SIGNING_KEYS_BY_NODE_JSON`)
  - asymmetric request signing (`X-Mesh-Signature-Scheme: ed25519-v1`) with HMAC compatibility fallback and node-side trusted public-key maps
  - one-time signed-request challenge flow (`/mesh/v1/auth/challenge`, `X-Mesh-Challenge-Id`, `MESH_REQUEST_SIGNING_USE_CHALLENGE`, `MESH_NODE_REQUIRE_SIGNED_CHALLENGE`)
  - recency-decay reputation scoring (`NOVAPRIME_REPUTATION_RECENCY_WEIGHT`, `NOVAPRIME_REPUTATION_RECENT_HALF_LIFE_DAYS`, `tools/test_reputation_recency_decay.py`)
  - peer discovery heartbeat + active filtering (`heartbeat_peer`, `list_peers(active_only=True, ...)`, `MESH_PEER_STALE_SEC`)
  - active-peer transport policy (`MESH_ACTIVE_PEERS_ONLY`, `MESH_ACTIVE_PEERS_MAX_STALE_SEC`) applied to mesh exchange and council routing
  - compute settlement idempotence (`ledger.transfer_once`, `transfer_refs`, `request_id_conflict`, `idempotent` + stable `tx_id` in settle responses)
  - mesh node authenticated rate-limit scopes (`MESH_NODE_RATE_LIMIT_SCOPE=ip|token|node|auto`, signed-node bucket support, regression coverage)
  - peer lifecycle API completion (`/api/v1/mesh/peers/heartbeat`, active-only peer listing query controls)
  - compute request-id integrity fix (unique-by-default request ids; explicit idempotence only when reusing request_id)
  - compute dispute governance flow (`/api/v1/mesh/compute/verify`, `/compute/dispute/open|resolve`, persistent dispute registry + penalty path)
  - compute job protocol lifecycle (`/api/v1/mesh/jobs` + `/submit|bid|award|execute|verify|settle`, persistent job board, execution/verification recording, optional `require_verified` settle gate, auto-bid collection + settle linkage)
  - identity element subclass compatibility hardening (accepts polarity + canonical subclass names; stores stable `subclass` + canonical `subclass_name`)
  - reconcile daemon service lifecycle wrappers (systemd + launchd installers/templates)

Important canonical constraints:
- NovaAdapt remains standalone-capable; NovaPrime is optional and must fail open unless explicitly required.
- Entropy is an in-game antagonist only, not a real-world representation.
- Public mesh must remain public-artifact-only (no private chats/memory/tool traces).
