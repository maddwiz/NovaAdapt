# desktop

Desktop operator layer for NovaAdapt.

Release track: production-ready.

## Tauri Shell

`desktop/tauri-shell` is the first-party Tauri v2 desktop control plane.

Current scope:
- Core API endpoint/token settings.
- Objective console (`/run_async`, `/plans`) with strategy/candidate controls.
- Live dashboard fetch (`/dashboard/data`) with auto-refresh.
- Plan actions: approve/reject, async retry for failed-only actions, and plan undo controls.
- Job actions: cancel queued/running jobs.
- Recent audit event and metrics snapshot feed.

Production hardening in place:
- Input validation for API endpoint configuration.
- Request timeout + retry behavior for transient network/core faults.
- Optional token persistence controls (opt-in remember-token behavior).
- Release bundling enabled in Tauri config for installer artifact generation.
- NovaAI studio neon theme parity with in-app logo treatment.

Run locally (requires Node + Rust + Tauri prerequisites):

```bash
cd desktop/tauri-shell
npm install
npm run dev
```
