# NovaAdapt Android Operator Surface

NovaAdapt ships an Android-ready operator surface as an installable PWA bundle built from `/Users/desmondpottle/Documents/New project/NovaAdapt/view`.

## What You Get

The Android PWA includes:

- bridge websocket control channel
- live terminal session polling + stdin input
- browser controls
- vision/mobile/IoT control-anything surfaces
- artifact history + preview retrieval
- template marketplace actions
- session token issuance / revoke controls

## Install

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

## Runtime Requirements

- reachable NovaAdapt bridge
- bridge token or scoped session token
- optional device allowlist entry if bridge device enforcement is enabled

## Current Tradeoffs

This is a packaged PWA, not a native Android shell.
That means:

- no Play Store wrapper in this repo
- browser-provided notification/background limits still apply
- terminal and audit feeds run through the bridge websocket / polling model

For the current handoff scope, this closes Android operator parity without forking a second mobile client stack.
