# Play Release Checklist

1. Confirm `com.novaadapt.operator` is reserved in Play Console.
2. Confirm upload keystore custody and GitHub Android signing secrets.
3. Add `NOVAADAPT_GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` to GitHub.
4. Host `privacy-policy/index.html` at a stable HTTPS URL.
5. Review `data-safety.md` against the actual runtime deployment.
6. Replace placeholder screenshots with real device captures.
7. Verify launcher icon and app name on a physical Android device.
8. Upload internal track build with `.github/workflows/android-play.yml`.
9. Install from the internal track and run the pairing QR smoke test.
10. Only then promote to broader tracks.
