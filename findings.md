# Cortex Bridge findings

## Verified on 2026-09-06

- Branch: `codex/v054-storage-consolidation`.
- HEAD: `ca2c304a7419f9e322e327ccb10e719c6950cad4`.
- User-owned dirty files: `frontend/out/_next/static/chunks/3bvs1nl3bjmpb.js`,
  `primer.md`, `tests/test_storage_lock.py`; they must not be staged.
- Focused S3/runtime lifespan gate: 50 tests PASS on Python 3.14 and 50 tests
  PASS on Python 3.12.
- Full equipped hermetic gate: 994 tests, 6 failures and 1 related error on
  each interpreter; this older result is superseded by the fresh runs below.
- Fresh full Python 3.14 run: 998 tests reached the end of the suite with no
  unittest failure before the release-evidence validator stopped on commit
  drift.
- Fresh full Python 3.12 run: 998 tests, 1 error in
  `test_outer_timeout_and_observation_remove_separate_descendant_groups`
  (`trigger='observation'`). The same test passes in isolation; this remains an
  environment/order-sensitive hermetic blocker, not a relabeled pass.
- Swift compile checks pass for `native/macos/disk_image_keychain.swift` and
  `native/macos/storage_bootstrap.swift`.
- `scripts/verify-links.sh` passes 124/124 links.
- `scripts/check-public-privacy.sh` passes 392 files and 43 images after the
  launcher/doctor changes.
- Direct lifespan proof shows owner-only home `0700`, record `0600`, states
  `STARTING → READY → CLOSED`, and a valid hash chain.
- `launch_managed_runtime` in `console/startup_lease.py` still raises
  `STARTUP_RUNTIME_NOT_WIRED`.
- `native/macos/storage_bootstrap.swift` only validates `--home` and selector
  existence, sets a minimal environment, and exits; it does not acquire locks,
  attest a generation, or exec a fixed installed server.
- `console/installed_storage_runtime.py` composes storage authorities from an
  already-attested handle but explicitly leaves server launch to its caller.
- `scripts/cortex.sh` still starts `console/server.py` directly from the
  checkout.
- Release evidence validator currently reports source-commit drift and a dirty
  working tree; this is expected and must remain visible until a clean release
  candidate exists.
- The source double-click launcher now dispatches explicit commands such as
  `doctor --json`, preserves the storage guard's exit code, and prints a
  storage-specific remediation when the required volume is absent.
- The `doctor` command intentionally returns zero after completing diagnostics;
  required health failures remain explicit in the JSON `ok=false` field and in
  the per-check `status=fail` entries. This preserves the existing diagnostic
  command contract while `go` still returns the storage guard's code 3.
- Doctor now includes an `external_storage` check, so the local diagnostic no
  longer reports an apparently healthy installation when `go` is blocked by a
  missing required volume.
- The frozen installation plan requires a compiled `bootstrap/cortex-launch`, a
  complete immutable generation, and an installed fixed server entrypoint. The
  current tree has none of those artifacts; the Swift bootstrap is only a
  selector-presence stub and `scripts/cortex.sh` still launches checkout
  `console/server.py`.
- The installed-runtime factory now validates the retained install lock,
  selector, installed-generations root/directory, generation record, owned
  manifest, and interpreter descriptor before native broker/probe attestation.
  Selector schema, duplicate keys, generation binding, and the normative
  selector digest are checked first.

## Decision

Do not invent a generation layout or silently turn the startup stub into an
arbitrary checkout launcher. A truthful next step is either to implement the
exact installed-generation publisher/bootstrap contract from the frozen plan,
or to stop at a documented fail-closed checkpoint and request the missing
product entrypoint.
