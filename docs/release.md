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

Tag-based releases use `.github/workflows/release.yml`:
- triggers on tags `v*`
- runs tests
- builds release artifacts
- publishes checksums
- optionally signs checksums when `COSIGN_PRIVATE_KEY`/`COSIGN_PASSWORD` are provided
