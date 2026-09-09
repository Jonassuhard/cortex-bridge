# Native to managed runtime handoff

## Contract

The native launcher validates the selected generation and passes six retained
descriptors: installation lock, selector, generation directory, generation
record, owned manifest and interpreter. Retained file bytes are rebound to the
verified digests before exec. Isolated installed Python consumes and revalidates
the descriptors through InstalledStorageRuntime rather than launching the
server directly.

Python adopts the inherited shared install lock, constructs the real installed
storage contract/lifecycle, and starts managed runtime with its one-shot lease.
After READY, the supervisor releases admission and bootstrap descriptors while
the child holds independent lifetime locks. This allows status/control requests.

The supervisor retains the actual Popen child object; no background reaper can
free its PID before signal delivery. SIGINT/SIGTERM are forwarded only to that
owned child; an eight-second shutdown timeout escalates to killing that child.
The supervisor returns the child's exit code and always reaps it.

## Test-first evidence

The real generation-install test initially reached HTTP through native startup
but failed because runtime-lifespan.json did not exist (57.215 s). This proved
native startup bypassed the managed path. It now requires READY, a child PID
different from the supervisor, usable locked status during execution, CLOSED
after SIGTERM, supervisor exit 0, and no remaining child.

The first composed integration run passed all six installation tests (85.613 s).
Final verification follows the explicit Popen ownership implementation.

## Limits

The test uses real dependencies, signed native helpers and actual installed
Python/HTTP in a temporary optional-storage home. It does not fabricate a mounted
encrypted volume. Required-volume acceptance remains open. The test compiles
the native launcher explicitly; apply_install does not yet deploy a stable
bootstrap entrypoint. The user installation, accounts and remote Git are unchanged.

Retained descriptors are revalidated against their expected paths; this does
not establish an external trust anchor or kernel-atomic execution against an
unrestricted malicious same-user writer. Existing unresolved startup records
remain fail-closed rather than automatically erased.

## Final executed results — macOS arm64, 2026-09-09

Run with `PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p PATTERN -q`.

| Pattern | Result | Duration |
| --- | --- | --- |
| test_generation_install.py | PASS, 6 tests | 84.298 s |
| test_installed_storage_runtime.py | PASS, 12 tests | 68.026 s |
| test_startup_lease.py | PASS, 11 tests | 0.048 s |
| test_storage_lock.py | PASS, 16 tests | 0.414 s |

45 targeted tests passed. The final real install run verifies the composed
native-to-managed path, unlocked admission for status, clean shutdown and child
reaping, then unchanged generation metadata and failure-safe second publication.
No encrypted-volume or full 0.6 release verdict is inferred.

Storage sessions: native `a0d96e2e2bd04864a19eaa07000d0433`, console
`b9a8eb1477654011b255401ceb885729`, tests
`96ac850847d2445e9acddf0554c9d0fc`, plans
`df92c21208d14bbb8fc3f636e0845b76`, root
`cddad2eb8b42487ab8899fbdf0f22483`.
