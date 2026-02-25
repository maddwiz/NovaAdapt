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

## Backup Restore

Restore local state from a timestamped snapshot:

```bash
novaadapt restore --from-dir ~/.novaadapt/backups --timestamp 20260225T120000Z
```

If `--timestamp` is omitted, NovaAdapt restores the latest discovered snapshot and archives the current DB files into `~/.novaadapt/backups/pre-restore/<timestamp>/`.

## GitHub Releases

Release workflow `.github/workflows/release.yml`:
- triggers on any git tag push (publishes GitHub release)
- supports `workflow_dispatch` with optional `release_tag`
  - with `release_tag`: publishes GitHub release for that tag
  - without `release_tag`: builds and uploads workflow artifacts only
- runs tests before building artifacts
- builds release artifacts and checksums
- optionally signs checksums when `COSIGN_PRIVATE_KEY`/`COSIGN_PASSWORD` are provided
