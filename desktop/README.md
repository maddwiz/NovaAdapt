# desktop

Desktop operator layer for NovaAdapt.

## Tauri Shell

`desktop/tauri-shell` is a Tauri v2 scaffold for the first-party desktop experience.

Current scope:
- Core API endpoint/token settings.
- Objective console (`/run_async`, `/plans`) with strategy/candidate controls.
- Live dashboard fetch (`/dashboard/data`) with auto-refresh.
- Plan actions: approve/reject and plan undo controls.
- Job actions: cancel queued/running jobs.
- Recent audit event and metrics snapshot feed.

Run locally (requires Node + Rust + Tauri prerequisites):

```bash
cd desktop/tauri-shell
npm install
npm run dev
```
