# Owned suspended native spawning

## Scope

`NativeSpawnOwner` now performs real suspended spawning and retains each child
before registration is attempted. `NativeOwnedProcess` owns the held executable
and parent pipe endpoints. These primitives are compiled into the broker source;
the persistent operation/control loop has not yet been wired to call them.
This is not an operational-storage or complete-supervisor acceptance verdict.

## Implemented guarantees

- Spawn uses START_SUSPENDED, SETPGROUP and CLOEXEC_DEFAULT. Only stdin/stdout/
  stderr are mapped, and original pipe endpoints are explicitly closed in the
  child. The environment is the existing exact native allowlist.
- The executable is opened no-follow and its path/vnode/owner/mode are compared
  immediately before exec. Setup failure closes acquired descriptors.
- The owner stores the returned PID and its descriptors while the child remains
  suspended. Registration is a distinct, one-attempt step using the previously
  verified identity/waitability primitive and the caller's absolute deadline.
- Resume before registration is rejected. Failed/expired registration remains
  unresolved, retained and suspended; it does not gain signal authority through
  a hidden retry or release path.
- Completed ownership is released only after the registration proves exact reap
  and group absence. Release closes parent endpoints and the executable FD.

The eventual persistent controller must retain this owner and stay alive while
its child collection is nonempty. That integration obligation is not proven by
these component tests. The legacy one-shot runner remains separate and must not
be used as a substitute for this ownership/control protocol.

## Executed tests

The test entry replaces only the final main call, keeping production definitions.
Unlike the previous registration tests, the production factory itself performs
the spawn. Its harmless child writes one byte and verifies a foreign descriptor
was not inherited. No hdiutil, diskutil, Keychain operation or user data is used.

Initial RED: compilation reported missing NativeSpawnOwner. First GREEN: three
tests passed in 6.378 seconds. An additional exec-format error test checks that
setup descriptors are closed and no child owner is fabricated.

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_native_spawn_owner test_native_child_registration test_native_recovery_root test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel -q
```

**73 tests passed in 40.352 seconds**, exit 0. Four new scenarios cover actual
spawn/registration/resume/descriptor isolation, retained failed registration,
missing executable and exec-format failure. `git diff --check` passed. The
previously recorded deprecated Keychain UI constant warning remains.

## Next

Wire owned spawning into the persistent poll-driven effect/control state machine
with operation-specific validation, output/input handling and budgets. Exercise
CANCEL, owner EOF, failure, timeout and descendant groups. Then implement durable
terminal acknowledgment and recovery/reconciliation/finalization. No part of the
broader installation/product/live-provider/release objective is removed.

No user installation, volume, Keychain item, commit or remote Git ref changed.
