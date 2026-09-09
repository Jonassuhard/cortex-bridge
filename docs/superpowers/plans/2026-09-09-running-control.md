# Running native command controls

## Implemented scope

`BrokerRunningControl` consumes a borrowed, already-authenticated owner socket.
It binds frames to workflow, generation, connection nonce, exact envelope and
directional cursor. CANCEL additionally requires the current command digest and
one of the two specified reasons. Cursors are consumed before actions, advance
without wrapping, and become exhausted after UInt64.max. A failure latches owner
loss, never a successful cancellation authorization.

STATUS accepts an empty payload and emits the exact six-field running snapshot
without PID/PGID. Reap/group absence remain false while the command runs; terminal
proofs are not fabricated. Only one outbound frame is retained. Writes and reads
are incremental with two-second partial-frame/output deadlines; idle input alone
does not start that per-frame timer. The caller supplies the effect deadline.

The owned process pump is exercised with this real socket controller in tests.
**The persistent production START dispatcher is still not wired to it.** The
controller must only be constructed after START admission and STARTED cursor
consumption. It is not a replacement for peer authentication, grant validation
or the closed operation mapping. Error codes are retained locally; emitting
terminal protocol-error/RESULT frames belongs to the pending persistent loop.
Post-cancel cleanup STATUS service and terminal sequence handoff also remain.

## Executed evidence

Initial RED: missing BrokerRunningControl compilation failure. Initial GREEN:
three unittest methods PASS in 17.343 seconds (existing pump, wire controls and
incremental-reader scenarios).

The socket-backpressure subcase then reproduced a timeout after eight seconds.
A separate real socketpair reproducer accepted eight 1-KiB writes and blocked on
the ninth despite MSG_DONTWAIT. The reproducer was interrupted and exited 130.
The controller now explicitly enables O_NONBLOCK, retaining existing descriptor
flags, and fails closed if it cannot establish that invariant. The same test then
passed: three methods PASS in 18.974 seconds. No timeout or buffer gate was raised
to conceal the blocking behavior.

The wire scenarios use a real disposable child through NativeSpawnOwner and
NativeCommandPump. They verify cancellation, STATUS response then cancellation,
EOF, replay, wrong nonce/generation/command digest, extra keys, invalid reason,
replay after STATUS, cursor exhaustion, blocked output, unfinished input and an
idle peer that later cancels. Each asserts exact child reap, absent process group
and released ownership. They do not touch disk images, Keychain or user files.
The existing ten callback pump subcases and ten incremental-reader subcases are
retained. Subcase counts do not imply additional unittest methods.

Final fresh regression: **76 tests PASS in 60.642 seconds**, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_native_control_reader test_native_command_pump test_native_spawn_owner test_native_child_registration test_native_recovery_root test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel -q
```

`git diff --check` passed. These results cover the stated components, not all
product journeys or a deployed persistent broker.

## Remaining gates

Connect the controller to the authenticated persistent operation loop and closed
command mapping; preserve owner lifetime across unresolved cleanup. Complete
terminal ACK, recovery and reconciliation before claiming installed encrypted
storage or 0.6 readiness. The SDK/Keychain deprecation limitations documented in
the prior component reports remain. No commit, push or user installation occurred.
