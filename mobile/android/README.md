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
- imports pairing manifests from raw codes, JSON manifests, shared text, or `novaadapt://pair?...` deep links
- can auto-connect immediately on launch for dedicated operator devices

Command-line build path:

```bash
cd /Users/desmondpottle/Documents/New project/NovaAdapt
./scripts/build_android_shell.sh all
```

That will build the debug APK and, if needed, generate a local upload keystore plus signed release outputs.
GitHub secret bootstrap and Play publish notes live in `/Users/desmondpottle/Documents/New project/NovaAdapt/docs/android_play_publish.md`.

For local preflight before a device test:

```bash
cd /Users/desmondpottle/Documents/New project/NovaAdapt
./scripts/build_android_shell.sh verify
```

That runs Android unit tests and assembles the debug APK with the same setup assumptions used by CI.

Play listing copy, privacy policy HTML, and release checklist now live in `/Users/desmondpottle/Documents/New project/NovaAdapt/mobile/android/play-store`.

## Runtime Requirements

- reachable NovaAdapt bridge
- bridge token or scoped session token
- optional device allowlist entry if bridge device enforcement is enabled

## Easiest Setup Path

For non-technical operators, the intended path is now:

1. Generate a mobile pairing payload from the desktop realtime console `Mobile Pairing` card.
2. In the Android app, tap `Scan QR` to read the generated pairing QR, open the `novaadapt://pair?...` link directly, or paste the raw pairing code into the app.
3. Let the Android shell import the manifest and open the bundled operator console automatically.

Manual bridge URL / token entry is still available in Settings, but it is no longer the primary setup flow.

If you are on the same local network as the NovaAdapt host, the Android shell can also use `Discover Nearby` to find the bridge and prefill its host settings before pairing.

## Current Tradeoffs

The PWA remains the fastest zero-build install path.
The native shell is the dedicated app-wrapper path for operators who want Android Studio or CI packaging around the same control plane.
