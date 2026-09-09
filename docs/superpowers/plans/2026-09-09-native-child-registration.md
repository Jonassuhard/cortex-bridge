# Native suspended-child registration and control

## Scope and verdict

PASS for the six executed real-child scenarios below. The primitive is compiled
in the broker source but not yet connected to its operation loop or the legacy
spawn runner. It is not acceptance of storage execution or a complete supervisor.

## Implemented

`RegisteredNativeChild.captureSuspended` observes the direct child's PID, parent,
group, UID, exact start time and mapped executable vnode. It compares the vnode
to the caller's held executable FD, takes a non-consuming waitability/stopped
observation, and repeats the identity observation before returning registration.
Missing or contradictory evidence returns no registration.

The executable identity is obtained from the child's mapped region, not stat of
the current pathname. Bounded region traversal is based on the local SDK and
[Apple's proc_info implementation](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/proc_info.c).
Two seconds is a metadata ceiling, not a renewed operation budget: each action
also receives its caller's absolute deadline and respects the earlier bound.

Resume and TERM/KILL require fresh identity and waitability observations.
Resume and each signal are single-use; TERM/KILL EINTR retries preserve the same
deadline and refresh proof. Observational ambiguity revokes authority. A stop
request prevents all later resume attempts, even if the child ignores TERM.

Exit observation uses WNOWAIT before the exact reap. ECHILD does not count as
successful cleanup. After reap, the registration cannot resume or signal; group
absence is observation only. The controller must still decide all required
group cleanup before requesting reap, and retain unresolved native ownership.

## Bugs and evidence

- Initial test harness compilation failed because registration/control APIs did
  not exist. This was an API-missing RED, not a behavioral assertion failure.
- Swift does not import the compound PROC_PIDPATHINFO_MAXSIZE macro. The code
  uses its SDK definition, 4 * MAXPATHLEN, rather than an invented buffer size.
- The first kill/reap test failed. A focused native observation and
  [Apple's waitid source](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_exit.c)
  identified an unpopulated si_uid field. UID remains required in the fresh BSD
  identity before signals; exit confirmation uses PID, SIGCHLD and exit code.
- A stop-then-resume test with an ordinary TERM-sensitive child could not isolate
  controller state. The fixture was made TERM-ignoring; it then failed with code
  114, proving resume was still permitted after a shutdown request. A state
  guard fixed this without relying on the OS having already killed the child.

The test-only entry point uses the production definitions and a real suspended
fixture process that only writes one byte and exits. It verifies no byte before
registration, matching identity and non-consuming waitability, resume once,
wrong executable rejection, non-child rejection, SIGKILL/reap/no later signals,
expired deadlines, and no resume after TERM. The spawn and emergency cleanup in
that entry point are test infrastructure, not a wired production spawn owner.

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_native_child_registration test_native_recovery_root test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel -q
```

Final result: **69 tests passed in 28.911 seconds**, exit 0. Six are new native
registration/control scenarios. `git diff --check` passed. The compiler still
reports the pre-existing deprecated Keychain UI constant; this lot does not
claim a warning-free native build.

## Remaining critical path

1. Connect suspended spawning and registration to persistent broker ownership;
   preserve a suspended/unreaped child on identity ambiguity, never drop it.
2. Implement the poll-driven effect/control loop and operation validation, then
   real success/failure/CANCEL/EOF/timeout and descendant-group tests.
3. Implement terminal durable acknowledgment, recovery authentication,
   reconciliation/finalization and application-lifetime ownership.
4. Complete unchanged installation, product, live-provider and release gates.

No user volume, Keychain item, installed runtime, commit or remote ref changed.
