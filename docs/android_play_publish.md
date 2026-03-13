# Android Play Publish

NovaAdapt now has the full repo-side path for Android operator release builds:

- local debug/release/AAB build via `scripts/build_android_shell.sh`
- Play listing bundle packaging via `scripts/package_play_store_kit.sh`
- GitHub Actions debug build via `.github/workflows/android-shell.yml`
- GitHub Actions Play upload via `.github/workflows/android-play.yml`
- release workflow integration via `.github/workflows/release.yml`

## What Is Already Done

- Gradle wrapper is committed in `mobile/android/NovaAdaptOperatorApp`
- local upload keystore generation is handled by `scripts/build_android_shell.sh`
- signed release APK/AAB builds are working locally
- GitHub repo secrets can be bootstrapped from the local keystore with `scripts/configure_android_github_secrets.sh`
- Play listing copy, privacy policy HTML, and release checklist live in `mobile/android/play-store`

## What Still Requires The Operator

Google Play publishing requires a Play Console service account JSON that belongs to the app owner.

You need to provide exactly one secret that cannot be derived from the repo:

- `NOVAADAPT_GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`

## Recommended Sequence

1. Bootstrap Android signing secrets from the local keystore:

```bash
cd /Users/desmondpottle/Documents/New project/NovaAdapt
./scripts/configure_android_github_secrets.sh
```

2. Add the Play service account JSON once you have it:

```bash
cd /Users/desmondpottle/Documents/New project/NovaAdapt
./scripts/configure_android_github_secrets.sh \
  --play-service-json /absolute/path/to/google-play-service-account.json
```

3. Open or merge the PR for `codex/god-tier-upgrades` so GitHub registers the Android workflows.

4. Run the Play publish workflow:

- workflow: `android-play`
- input `track`: `internal`, `alpha`, `beta`, `production`
- input `status`: typically `completed`

5. Package the listing bundle for handoff/review:

```bash
cd /Users/desmondpottle/Documents/New project/NovaAdapt
./scripts/package_play_store_kit.sh
```

That emits a zip in `dist/` containing:

- Play listing copy
- privacy policy HTML
- release checklist
- the latest built APK/AAB if present

## Secret Inventory

Secrets used by Android CI/release:

- `NOVAADAPT_ANDROID_KEYSTORE_BASE64`
- `NOVAADAPT_ANDROID_KEYSTORE_PASSWORD`
- `NOVAADAPT_ANDROID_KEY_ALIAS`
- `NOVAADAPT_ANDROID_KEY_PASSWORD`
- `NOVAADAPT_GOOGLE_PLAY_SERVICE_ACCOUNT_JSON`

The first four can be generated and configured by NovaAdapt. The last one must come from the Google Play owner.

## Replacing The Generated Upload Keystore

If you want full signing custody under your own keystore:

1. generate or provide your preferred upload keystore
2. update `~/.novaadapt/android/novaadapt-operator-signing.env`
3. rerun `scripts/configure_android_github_secrets.sh`

That will replace the GitHub signing secrets without changing repo code.
