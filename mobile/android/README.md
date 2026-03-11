# NovaAdapt Android Operator Surface

NovaAdapt now ships two Android operator paths:

- installable PWA bundle built from `/Users/desmondpottle/Documents/New project/NovaAdapt/view`
- native Android shell sources in `/Users/desmondpottle/Documents/New project/NovaAdapt/mobile/android/NovaAdaptOperatorApp`

## What You Get

The Android PWA includes:

- bridge websocket control channel
- live terminal session polling + stdin input
- browser controls
- vision/mobile/IoT control-anything surfaces
- artifact history + preview retrieval
- template marketplace actions
- session token issuance / revoke controls

## PWA Install

From a release bundle:

- unpack `novaadapt-android-pwa-<version>.zip`
- host the contents on any HTTPS origin reachable by the device
- open `realtime_console.html` in Chrome or Edge on Android
- choose `Install app`

For local operator development:

```bash
cd /Users/desmondpottle/Documents/New project/NovaAdapt/view
python3 -m http.server 8088
```

Then open `http://<host>:8088/realtime_console.html` from Android and install it as an app.

## Native Shell Import

Open `/Users/desmondpottle/Documents/New project/NovaAdapt/mobile/android/NovaAdaptOperatorApp` in Android Studio.

The native shell:

- packages the repo operator console as Android assets
- stores bridge credentials and device identity in Android `SharedPreferences`
- bootstraps the console with prefilled bridge/websocket settings
- can auto-connect immediately on launch for dedicated operator devices

## Runtime Requirements

- reachable NovaAdapt bridge
- bridge token or scoped session token
- optional device allowlist entry if bridge device enforcement is enabled

## Current Tradeoffs

The PWA remains the fastest zero-build install path.
The native shell is the source-distributable path for operators who want Android Studio packaging and a dedicated app wrapper around the same control plane.
