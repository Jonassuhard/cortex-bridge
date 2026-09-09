# Native recovery-root retention

## Implemented and verified

`consumeRecoveryRoot` now returns a 32-byte `SecretBuffer`, reads directly into
its mutable allocation, and owns/closes the inherited read descriptor. It
requires exactly 32 bytes followed by EOF within the existing two-second I/O
deadline. Invalid length, a missing EOF or an invalid descriptor returns no
authority. Failed reads erase the allocation; any surplus byte is also erased.
There is no immutable Data/array copy of the recovery root in this reader.

`runPersistentBroker` retains the returned allocation for its lifetime and
explicitly zeroizes it on return. This fixes the former Bool-returning reader
that discarded all recovery authority immediately after initialization.
SecretBuffer also zeroizes on deinitialization. The broker does not yet perform
recovery authentication/reconnection; no recovery success is claimed.

## Evidence

The native resource test compiles all production definitions with a test-only
entry point replacing the final CLI call. It does not introduce production
test hooks or output root bytes. The test executes the actual reader and checks
retained content, descriptor closure, explicit/idempotent erasure, wrong lengths
and missing EOF. This is resource-component evidence, not a live recovery test.

Initial RED: three tests failed, seven failing cases, in 37.595 seconds; the old
reader left descriptor ownership to its caller and returned no retained buffer.
First GREEN plus regressions: 62 tests passed in 25.444 seconds.

A further production-profile broker test verifies invalid recovery lengths are
rejected before HELLO on an already connected socket.

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_native_recovery_root test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel -q
```

Final result: **63 tests passed in 22.744 seconds**, exit 0.
`git diff --check` passed. No user installation, volume, Keychain item, commit
or remote ref changed.

## Critical supervisor finding and next work

The legacy `spawnChild` is not the approved S3 supervisor: its spawn flags omit
START_SUSPENDED and its cleanup functions can signal without fresh registered
identity/waitability proof, including after reaping. These are inspected source
findings, not new runtime tests of unsafe signals. Do not connect that runner
unchanged to the persistent broker or call it S3-compliant.

Next dependency: implement suspended registration, exact native identity and
non-consuming waitability observation, guarded resume/signals and reap ordering.
Then connect the persistent effect/control loop, operation semantics, durable
terminal ACK and recovery HMAC/reconnection/finalization. The retained root is
one prerequisite, not proof that these later protocol states exist.
