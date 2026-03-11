# NovaAdapt Operator Android Shell

This is a native Android WebView shell for NovaAdapt's bundled operator console.

## What It Does

- loads the repo's `view/realtime_console.html` from packaged Android assets
- persists bridge/websocket/operator identity values in Android `SharedPreferences`
- injects those values into the console via query-parameter bootstrap
- supports auto-connect on launch for dedicated operator devices

## Import

1. Open `mobile/android/NovaAdaptOperatorApp` in Android Studio.
2. Let Android Studio provision the Android Gradle Plugin / Gradle distribution.
3. Run on an Android device or emulator with network access to your NovaAdapt bridge.

## Notes

- This shell is source-distributable; signing and store distribution are left to the operator.
- The app enables WebView file access and universal access from file URLs so the bundled console can talk to remote bridge/core endpoints.
- The bundled console itself still lives in `/Users/desmondpottle/Documents/New project/NovaAdapt/view` and remains the source of truth for operator UX.
