# Data Safety Draft

This is a working draft for the Google Play Data safety form. Final answers should be confirmed against the deployed backend and enabled model providers at release time.

## Data Collected

- App info and performance:
  - crash information if Android/Play reporting is enabled
  - diagnostics from the Android runtime
- User-provided content:
  - bridge URLs
  - pairing payloads
  - operator-entered tokens
  - commands and prompts sent to the user's NovaAdapt runtime

## Data Shared

- The Android app itself is a remote operator surface. It sends user actions and tokens only to the NovaAdapt bridge/runtime configured by the operator.
- Downstream sharing to third-party model providers depends on the user's NovaAdapt backend configuration, not the Android shell itself.

## Data Handling

- Bridge URLs, tokens, and device identity are stored locally on-device in Android shared preferences.
- The app does not require a NovaAdapt-operated cloud account.
- Operators are responsible for the privacy posture of the bridge/runtime and any configured model providers.
