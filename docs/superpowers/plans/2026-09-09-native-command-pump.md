# Native command pump: component evidence

## Scope and status

The private `NativeCommandPump` uses the owned suspended-spawn and registered
identity primitives. It handles bounded nonblocking input/output, deadlines,
cancellation and owner-loss callbacks, checked TERM/KILL escalation, exact reap
and group absence. It retains unresolved ownership instead of reporting cleanup.
Input secrets are borrowed; their caller remains responsible for zeroization.

This is **not** persistent broker acceptance: the production START route still
returns INVALID_STATE after authorization. Control callbacks in this fixture are
not protocol frames. Operation-specific command validation, persistent control,
terminal acknowledgment, recovery and reconciliation remain unimplemented there.
No user disk, Keychain item or installation is exercised by this test.

## Executed evidence

The fixture compiles the production definitions with a test-only entry point and
launches real harmless subprocesses. Ten subcases cover success, nonzero exit,
43-byte secret plus NUL delivery, cancellation, TERM ignored then KILL, owner
loss, deadline expiration, signal termination, output overflow and closed output
streams while the child remains alive. These are ten subcases in one unittest
method, not ten independent unittest methods.

- Initial implementation RED: missing pump compilation failure.
- Signal-classification RED: signal termination was conflated with normal
  nonzero exit (fixture exit 98); production classification corrected.
- Earlier nine-subcase combined run: 74 tests PASS in 49.836 seconds.
- Closed-output check: PASS in 10.389 seconds. The elapsed interval initially
  included spawn/registration, so the fixture was tightened to start the interval
  at its first control callback. The tightened test PASS in 9.343 seconds.
  The suspected busy-loop defect was **not reproduced**; no speculative poll
  implementation change was made. This bounded callback-count check is not a
  general CPU or UI performance benchmark.

Fresh combined verification after tightening the tenth subcase: **74 tests PASS
in 47.009 seconds**, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_native_command_pump test_native_spawn_owner test_native_child_registration test_native_recovery_root test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel -q
```

The fixture currently uses the local macOS SDK; this does not establish clean
machine, older macOS or Windows compatibility. The known deprecated Keychain UI
constant warning is not resolved by this work.

## Next integration gate

Connect a validated, closed operation mapping and real control-frame reader to
this owned execution path, preserving absolute budgets and unresolved children.
Then prove durable RESULT/CLOSED_READY/COMMIT_ACK and recovery/reconciliation.
Do not use the legacy one-shot runner to claim this protocol is implemented.

No commit, push, tag or user installation was performed for this component.
