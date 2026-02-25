# mobile

Native mobile companion scaffolds.

## iOS Companion

`mobile/ios/NovaAdaptCompanion` contains a SwiftUI source module for:

- bridge/core API configuration and auth token entry.
- objective submission (`/run_async`) and pending-plan creation (`/plans`).
- operator controls for pending plan approve/reject, async failed-plan retry, and job cancel.
- dashboard polling surface for plans/jobs/audit events.
- optional bridge websocket feed for realtime command/audit traffic.

The scaffold is source-only and intended to be imported into an Xcode project.
