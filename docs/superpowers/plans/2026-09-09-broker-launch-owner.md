# Production broker launch owner

## Verdict and scope

PASS for tested normal launch, exec failure, identity checks, durable ordering
and native START rejection handling. Storage operations remain FAIL: the Swift
supervised effect/terminal state machine is not implemented. No encrypted image
or Keychain item was touched in this checkpoint.

## Actual implementation

`_BrokerLaunchOwner` now owns the process and owner connection. The default
`StorageBrokerClient._run_locked()` uses it instead of reporting an absent
transport. Injected transports remain separate fixture paths; the private
mounted-image probe and reconciliation are not connected to this launcher yet.

Launch creates a private recovery authority and a real listening Unix socket,
then fsyncs PREPARED. It reattests the executable immediately before `Popen`,
passes only listener/capability/recovery descriptors, uses a new session and
the exact PATH/LANG/LC_ALL environment, with no Python preexec hook. CPython's
fork_exec path observes its close-on-exec error pipe before Popen returns. This
was verified against the local CPython 3.14 subprocess implementation; the
Popen constructor itself does not expose a bounded exec timeout.

After HELLO, Python checks kernel peer PID/UID, reattests executable identity,
verifies the new session/group, fsyncs RUNNING, publishes the single-use grant,
then sends START. The actual process PID/SID/PGID are recorded, not Python's PID.
Incoming envelopes have exact workflow/generation/nonce/cursor checks.

The default client currently receives Swift's INVALID_STATE, reports a protocol
failure and persists OPEN_UNRESOLVED. It does not synthesize success or infer
cleanup from broker exit. Exec failure before START closes only PREPARED. Error
handling reloads the durable record before deciding its state, rather than
trusting a potentially stale in-memory copy after a failed fsync.

Closing an owner channel sends no process signals. The client waits boundedly
for broker exit and retains a still-live owner in its session collection. That
collection still needs integration with application-lifetime recovery ownership
when the persistent effect loop is added; a timeout is not cleanup proof.

## Bugs found by real execution

- Long home/external-volume paths exceed Darwin's Unix socket address limit.
  Only ephemeral IPC now lives under a short, newly created mode-0700 directory
  in `/private/tmp`; journal/recovery/application data remain in configured
  storage. The socket is mode 0600. Its location is journaled for recovery.
  Production finalization must later dispose of the exact owned IPC artifact;
  this implementation preserves it rather than deleting a live endpoint.
- A peer-PID check immediately after connect raced native accept. Testing the
  hypothesis that the PID always identified the parent disproved it. The final
  check runs after HELLO and still requires the exact launched child's PID.
  There is no sleep or relaxed PID fallback.

## Executed evidence

Initial two launch-owner tests failed because the implementation was missing.
The first implementation then reproduced the long socket-path error; after
fixing that, it reproduced the pre-HELLO credential race. A dedicated real
inherited-listener characterization now confirms the child's PID after HELLO.

The default-client integration test first failed with BROKER_UNAVAILABLE.
After wiring, it verifies the actual native refusal and unresolved ledger.
The old synthetic-executable test now requires AUTH_FAILED before any ledger
preparation; exec failure is covered separately with a truthfully attested but
invalid executable and a durable CLOSED_FAILURE record.

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel -q
```

**59 tests passed in 17.048 seconds**, exit 0. The suite includes compiled
production Swift, real subprocesses, real Unix sockets and durable ledgers.
No authorized native effect was exercised. `git diff --check` passed.

Adjacent regression command:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_guard test_storage_contract test_storage_lifecycle test_installed_storage_runtime -q
```

**37 tests passed in 66.441 seconds**, exit 0. Session total: 96 targeted tests.
These storage/lifecycle/installed-runtime cases do not establish clean-machine
installation, mounted encrypted-storage acceptance or release readiness.

## Next critical work

Implement native retained recovery authority and supervised operation dispatch,
then terminal RESULT/CLOSED_READY/durable COMMIT and recovery/finalization.
Complete application-lifetime ownership and bounded launch-failure acceptance,
private probes, installer/release gates. The full 0.6 objective is unchanged.
