# mobile

Native mobile companion applications.

Release track: production-ready.

## Android Operator Paths

`mobile/android` now includes:

- PWA release metadata for the static operator console
- `NovaAdaptOperatorApp`, a native Android Studio WebView shell for the same control plane

The native shell is source-distributable and intended for operators who want a dedicated Android wrapper around the bundled NovaAdapt console without maintaining a second UI stack.

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
