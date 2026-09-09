# Managed generation startup

Implement the parent/child startup connection for an installed, verified
generation. Validate the current process and boot before consuming a lease;
verify storage under existing locks; hold independent shared install/storage
descriptors for the child lifetime; acknowledge READY only after actual HTTP
startup. Failures retain their evidence and do not claim readiness.

Tests: current-process lease binding, rejection before spawn, actual installed
server handshake and HTTP, graceful closure, replay rejection. Temporary homes
exercise storage-not-required with the real contract. Encrypted-volume S3 live
acceptance remains distinct and requires actual mounted storage evidence.

## Implemented connection

`startup_lease.launch_managed_runtime` now calls `managed_runtime.launch`.
`InstalledStorageRuntime.start_locked` composes that launcher with its own
storage lifecycle and contract; the contract uses the durable runtime readiness
probe instead of an unconditional false placeholder. The existing factory API
still creates a runtime and does not start a server automatically.

The launcher verifies the selected generation, opens independent shared lifetime
locks, starts its installed interpreter, and exchanges a one-shot lease over an
inherited socket. The child validates its kernel process identity, current boot
and launcher identity before consuming the lease. READY follows real Uvicorn
startup, and graceful shutdown records CLOSED. Caller-lock release does not
release the independent child locks. Failed startup is not automatically
reconciled: an unresolved STARTING record is preserved rather than overwritten.

## Defects reproduced during validation

- Test status projection omitted the mandatory recovery field; corrected the
  test's projection without changing the storage contract.
- Assigning CORTEX_HOME to HOME triggered the existing dedicated-directory
  safety check. The launcher now preserves the parent HOME separately.
- macOS boot identity used an optional sysctl import and a rounded fallback;
  separate processes could disagree. macOS now uses the existing exact kernel
  reader. A regression test failed before the fix and passed afterward.
- Socket framing now leaves subsequent frames queued, with a bounded read
  deadline. ACK and READY sent together are tested separately.

## Boundaries

The end-to-end fixture installs real wheel dependencies and native helpers into
a temporary dedicated home. It uses the real optional-storage contract, not a
fabricated encrypted mount. Test instrumentation captures child stderr only;
it does not replace execution, signatures, storage validation or HTTP startup.
This is not proof of mounted encrypted S3, native bootstrap hardening, GUI/CLI
rollout, browser missions, Windows compatibility or a clean macOS machine.
No user installation, account, version or remote branch is changed.

## Executed results — 2026-09-09, macOS arm64

Run each with `PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python
-m unittest discover -s tests -p PATTERN -v` from the checkout.

| Pattern | Result | Duration |
| --- | --- | --- |
| test_generation_install.py | PASS, 6 tests | 54.367 s |
| test_startup_lease.py | PASS, 11 tests | 0.053 s |
| test_storage_broker.py | PASS, 13 tests | 0.066 s |
| test_installed_storage_runtime.py | PASS, 12 tests | 89.379 s |
| test_storage_contract.py | PASS, 6 tests | 0.031 s |
| test_runtime_wheel.py | PASS, 1 test | 4.322 s |

49 targeted tests passed during this session; the final installation run includes
both HOME and exact-boot fixes, HTTP 200, kernel child identity, independently
contended lifetime locks after caller release, CLOSED after SIGTERM, and failed
second publication preserving the previous selector. Temporary fixtures are
cleaned up. This document records results, not a persisted raw-log bundle.
`git diff --check` passed; existing unrelated dirty changes remain uncommitted.

Storage session IDs: console `16eec716c196426cb348b205aa94d3a7`, tests
`d710775919d441be9b12c83c441eb706`, plans
`6020df321dc64ac0b9db62b452aeb572`, root
`6ed68f6e389741b7b5920de2278c254b`. Central folder-session structures describe
filesystem changes, not test correctness.

Next: validate and harden the native bootstrap-to-managed-start boundary, then
exercise actual encrypted-volume startup before enabling it in the user launcher.
