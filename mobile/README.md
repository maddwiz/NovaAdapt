# mobile

Native mobile companion applications.

Release track: production-ready.

## iOS Companion

`mobile/ios/NovaAdaptCompanion` contains a SwiftUI source module for:

- bridge/core API configuration and auth token entry.
- optional admin-token entry for privileged bridge auth routes.
- bridge device-id entry for allowlisted deployments and runtime trusted-device management (`/auth/devices*`).
- scoped session token issue/revoke controls (`/auth/session`, `/auth/session/revoke`).
- objective submission (`/run_async`) and pending-plan creation (`/plans`).
- operator controls for pending plan approve/reject, async failed-plan retry, and job cancel.
- dashboard polling surface for plans/jobs/audit events.
- bridge websocket feed for realtime command/audit traffic.
- remote terminal controls (`/terminal/sessions*`) with live stdin/stdout polling over websocket command relay.

The iOS companion is source-only and intended to be imported into an Xcode project for signing/distribution.

Production hardening in place:
- Sensitive credentials are persisted in iOS Keychain.
- Operator settings persist across launches via `UserDefaults`.
- API and WebSocket endpoints are validated before use.
- Destructive actions require explicit confirmation prompts.
- NovaAI studio neon theme parity with in-app logo treatment.
