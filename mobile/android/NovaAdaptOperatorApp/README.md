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

## Command-Line Build

```bash
cd /Users/desmondpottle/Documents/New project/NovaAdapt
./scripts/build_android_shell.sh all
```

That script:

- builds the debug APK
- auto-generates a local upload keystore under `~/.novaadapt/android/` if one does not already exist
- builds signed release APK/AAB outputs

Generated signing state is stored outside the repo in `~/.novaadapt/android/novaadapt-operator-signing.env`.

## GitHub Automation

- `.github/workflows/android-shell.yml` builds the debug APK on pushes, pull requests, and manual dispatch.
- `.github/workflows/android-play.yml` performs manual Google Play uploads when the required GitHub secrets are configured.

## Notes

- This shell is buildable locally and in CI; store publishing still requires Google Play credentials/secrets.
- The app enables WebView file access and universal access from file URLs so the bundled console can talk to remote bridge/core endpoints.
- The bundled console itself still lives in `/Users/desmondpottle/Documents/New project/NovaAdapt/view` and remains the source of truth for operator UX.
