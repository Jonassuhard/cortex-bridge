# Native START grant consumption

## Verdict

PASS for private authorization binding; FAIL for production storage execution
(not implemented). This checkpoint is not a release or native-effect acceptance.

## Changes

The production Swift broker now reads one canonical START_GRANT from its
inherited anonymous capability endpoint, requires EOF after that frame, and
closes the endpoint. Truncated, duplicate, trailing, oversized or noncanonical
frames cannot authorize START. The existing outer envelope validation still
runs first; an invalid cursor, workflow, generation or nonce is not admitted.

Grant validation binds workflow/generation, kernel boot identity, owner nonce
and peer audit hash, record digest format, operation, request digest and both
budgets. START must contain exactly the four specified payload fields; its
canonical request is hashed with the REQUEST/V1 domain and compared to the
private grant. Budgets must be integer-valued, positive for effect, nonnegative
for cleanup, and within the approved 40/12-second bounds.

An authorized START currently returns INVALID_STATE and exits without STARTED.
That is a deliberately incomplete dispatch boundary, not successful execution.
The typed authorization result is ready for the future supervised dispatcher;
full operation semantics must still be checked there before any effect.

## Evidence

Test-first RED: the valid private grant test received AUTH_FAILED rather than
reaching the dispatch boundary (1 failed test, 7.082 seconds).

After implementation: 13 native tests passed in 11.725 seconds. Added malformed
and matching-invalid-budget cases: 54 combined tests passed in 14.912 seconds.

The additional cross-language test initially exposed a fixture ordering error:
it launched before the ledger generated the workflow UUID. The fixture was
corrected to prepare the real ledger before spawning; no production gate was
weakened. It now uses a freshly built production-profile Swift executable,
real executable attestation, real HELLO/peer identity, durable RUNNING, and the
Python `_StartGrantChannel` producer. Both sides receive the same recovery
bytes, but recovery retention/reconnection is not exercised.

Final command on the current candidate:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel -q
```

Result: **55 tests passed in 14.806 seconds**, exit 0 (16 native handshake/grant
tests plus 39 producer/ledger/lock/wheel regressions). `git diff --check` passed.

## Remaining critical path

1. Production launch/session ownership and exec-status ordering; the cross-
   language launch fixture is not a replacement for this implementation.
2. Native effect state machine and operation validation, supervised children,
   cancellation/EOF/timeouts and verifiable cleanup.
3. Retained recovery root and durable commit/reconciliation/finalization.
4. Installer acceptance and the unchanged product/release gates.

No user volume, Keychain item, installed runtime or remote Git ref was changed.
