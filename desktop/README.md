# desktop

Desktop operator layer for NovaAdapt.

## Tauri Shell

`desktop/tauri-shell` is a Tauri v2 scaffold for the first-party desktop experience.

Current scope:
- Core API endpoint/token settings.
- Live dashboard fetch (`/dashboard/data`).
- Pending plan approval/rejection actions.
- Local-first shell for expanding into hotkeys, notifications, and one-tap undo.

Run locally (requires Node + Rust + Tauri prerequisites):

```bash
cd desktop/tauri-shell
npm install
npm run dev
```
