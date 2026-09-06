# Cortex Bridge progress

## 2026-09-06

- Revalidated branch, HEAD, dirty files, frozen S3 plans, startup lease, server,
  bootstrap, installed runtime, and shell entrypoint.
- Created persistent planning files for this completion run.
- Confirmed the latest runtime lifespan writer and dual-Python focused evidence
  are real and reproducible.
- Confirmed the remaining launch path is not wired and the full cleanup harness
  still fails; no false PASS will be recorded.
- Completed the plan revalidation phase and moved to the bounded launcher gate.
- Added a RED regression proving the installed-runtime factory currently starts
  native attestation without validating the selector digest carried by its
  bootstrap handle. The test failed exactly at broker attestation as expected.
- Implemented descriptor-relative bootstrap-handle validation and reran the
  installed-runtime/startup-lease tests: 8/8 PASS on Python 3.14 and 8/8 PASS
  on Python 3.12.
- Phase 2 is complete; Phase 3 is now the dual-interpreter/full-suite gate.
- Added the launcher/doctor regression gate after reproducing the user's local
  `STORAGE_VOLUME_MISSING` failure. The source launcher now accepts explicit
  commands, `go` preserves the storage guard status, and doctor reports the
  configured external-storage state.
- Launcher/doctor focused regressions: 13/13 PASS.
- Full Python 3.14 run reached all 998 tests and all downstream UI, build,
  privacy, and runtime checks; only the final release-evidence commit-drift
  validator stopped the script.
- Full Python 3.12 run reached 998 tests with one observation-triggered
  descendant-cleanup error. The failing test passes in isolation, so it remains
  recorded as an honest hermetic blocker.
- Link check: 124/124 PASS. Privacy: 392 files and 43 images PASS.
- Fresh targeted rerun: launcher plus installer suites pass 101/101; the
  source `go` command returns code 3 with `STORAGE_VOLUME_MISSING` as designed;
  the exact privacy invocation passes 392 files and 43 images; release-evidence
  and link checks pass.
- The installed application bundle still differs from the source checkout and
  lacks the current storage/runtime modules. Its installer dry-run fails closed
  on the existing native-helper ownership mismatch, so no bundle overwrite was
  attempted.

## Next

Leave the missing installed-generation/managed-launch, external-volume, native
helper, and real macOS/provider gates explicit. The next required action is a
targeted owner decision to mount/unlock the configured volume and separately
authorize a safe installed-bundle synchronization path.
