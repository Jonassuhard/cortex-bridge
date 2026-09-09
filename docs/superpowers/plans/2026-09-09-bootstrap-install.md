# Stable bootstrap deployment through generation installation

## Scope

Generation install plans now include native bootstrap source/profile hashes and
the currently verified bootstrap state. The installer compiles/signs/strictly
verifies an ABI-v1 launcher in private staging, retaining its exact source and
profile. A digest-bound manifest records the executable hash, CDHash and inode.

After generation construction succeeds, the installer publishes the immutable
bootstrap directory without replacement under its existing exclusive lock, then
publishes the generation selector. It returns launcher_path and launch_argv;
it does not automatically start the runtime.

Subsequent generation installs verify/reuse the existing bootstrap instead of
replacing it. Tampered bootstrap data is rejected. Changed bootstrap code or
profile requires an explicit migration rather than implicit replacement.

## Failure behavior and limits

- A failed selector publication retains the previous selected generation.
- A previously installed bootstrap retains its bytes and inode.
- On first installation, a successfully published bootstrap can remain after a
  later generation failure. Staging/journal remain for reconciliation; this is
  not an all-or-nothing multi-file transaction and no installed success is returned.
- An existing selected generation without a bootstrap returns
  BOOTSTRAP_MIGRATION_REQUIRED before staging. A reviewed migration for that
  development-era layout is still required.
- Bootstrap code updates return BOOTSTRAP_UPDATE_REQUIRES_MIGRATION.
- This lot does not validate required encrypted storage or update the user's
  installed application. No Git publication or version bump.

## Proof contract

The real installation test no longer compiles a launcher itself: it runs the
path returned by apply_install, requires native-to-managed READY/HTTP/CLOSED and
no orphan, verifies generation integrity, corrupts/rejects/restores the temporary
launcher, tests source-change refusal, then injects a second selector-publication
failure and checks both the old selector and bootstrap identity are preserved.

The pre-implementation run failed because launcher_path was absent (31.419 s).
The first actual installed-launcher run passed (6 tests, 86.387 s). Final results
include the corruption/source-change assertions and signature verification.

## Final targeted verification

- `PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_generation_install.py -q`: six cases PASS, 81.383 s (suite loaded before the seventh case was added).
- `PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_generation_install.GenerationInstallTests.test_prebootstrap_generation_is_preserved_for_explicit_migration -q`: one case PASS, 2.614 s.
- Runtime wheel suite: one case PASS, 3.797 s, including import of bootstrap_install.
- Total: eight targeted cases, not a full release verdict. The migration fixture proves refusal/preservation, not acceptance of a legacy runtime.
- No user installation, commit, push or version bump performed.
