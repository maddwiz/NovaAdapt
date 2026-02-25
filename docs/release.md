# Release Operations

## Build Artifacts

```bash
./installer/build_release_artifacts.sh v0.1.0
```

Outputs to `dist/`:
- bridge binary
- python wheel/sdist
- runtime bundle tarball
- `SHA256SUMS`

## Token Rotation

Rotate core/bridge tokens across systemd and docker env files:

```bash
./installer/rotate_tokens.sh --restart-systemd
```

Dry-run:

```bash
./installer/rotate_tokens.sh --dry-run
```

## GitHub Releases

Tag-based releases use `.github/workflows/release.yml`:
- triggers on tags `v*`
- runs tests
- builds release artifacts
- publishes checksums
- optionally signs checksums when `COSIGN_PRIVATE_KEY`/`COSIGN_PASSWORD` are provided
