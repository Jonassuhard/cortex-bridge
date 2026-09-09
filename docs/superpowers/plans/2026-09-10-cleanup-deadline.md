# Cleanup starts at the first stop condition

## Fixed behavior

NativeCommandPump previously used the planned effect-end plus cleanup duration
even when cancellation occurred early. It now latches the first failure time and
sets its cleanup deadline to the smaller of the original final bound and that
time plus the cleanup duration. Checked arithmetic prevents wraparound. Later
failures cannot restart or extend the budget. Output errors, cancellation, owner
loss, effect expiration, stdin errors and polling failures share this rule.

Signals, drains, reap checks and group-absence checks consume the reduced bound.
If a TERM-ignoring child cannot be cleaned within that bound, the result remains
SUPERVISION_UNRESOLVED with retained ownership, not a fabricated successful reap.
No signal is issued after the deadline to force a green cleanup result.

## Evidence

The real-child short-cleanup test reproduced the defect: one method with one
failing subcase in 14.537 seconds (fixture exit 108). After correction, two pump
methods passed in 27.287 seconds, including the existing real wire scenarios.
The new case gives cleanup 300 ms and checks unresolved ownership before 900 ms
from cancellation; the old two-second effect budget would allow overrun. The
equivalent owner-loss case was then added. The test child sets TERM ignored
before reporting readiness. Emergency disposal of an unreaped test child belongs
only to the fixture, not the production cleanup algorithm.

Final fresh regression: **100 tests PASS in 67.156 seconds**, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_native_control_reader test_native_command_pump test_native_spawn_owner test_native_child_registration test_native_recovery_root test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel test_storage_reconciliation test_storage_lifecycle test_storage_transition -q
```

`git diff --check` passed.

This proves component behavior, not the persistent broker's installed execution
path. Native START dispatch, zero-cleanup admission, complete checked duration
policy, terminal acknowledgment and recovery remain unfinished. No deadline or
test threshold was increased to hide the defect. No user disk/Keychain/install,
commit or Git remote changed.
