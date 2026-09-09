# Production native path audit and corrected implementation order

## Follow-up: private START grant implemented

Latest follow-up: 2026-09-09-native-recovery-root.md records mutable root
retention and 63 passing targeted tests. HMAC/reconnection is not implemented.
Legacy child spawning/cleanup is not S3-compliant and cannot be plugged into
the persistent broker unchanged.

The original findings below describe the baseline, not the updated authorization
path. Python producer and Swift consumer now pass 55 targeted tests including
real cross-language authorization (14.806 s). See
2026-09-09-native-start-grant.md. Valid START reaches INVALID_STATE, not STARTED:
the supervised effect/commit loop remains absent. Subsequent launcher work is
recorded in 2026-09-09-broker-launch-owner.md: the default public client now
launches the broker; 59 targeted tests pass. The table below remains the original
audit baseline, not the latest implementation status.

## Verified finding at audit baseline

The persistent broker is currently a pre-effect handshake implementation, not
an operational storage backend. This is a code finding, not an inference from
test counts. The previous completion sequence put reconciliation too early.

| Boundary | Current authoritative source | Verdict |
| --- | --- | --- |
| Broker executable/peer HELLO | runPersistentBroker emits actual executable, boot and peer identity | PASS for targeted handshake tests |
| Inherited START authorization | validateCapabilitySocket verifies descriptor role, but no START_GRANT consumer exists | FAIL: implementation missing |
| Recovery root retention | consumeRecoveryRoot reads and zeroes a local buffer, returning only Bool | FAIL: no retained key for later recovery |
| Authorized controls | protocolErrorCode returns AUTH_FAILED for every owner-control message | FAIL: no admitted START/CANCEL/commit path |
| Native command loop | runPersistentBroker reads one frame, emits PROTOCOL_ERROR, exits | FAIL: state machine missing |
| Python production launch | StorageBrokerClient with transport=None closes preexec failure and raises BROKER_UNAVAILABLE | FAIL: native transport missing |
| Terminal commit | close_from_ready_locked can validate/store an injected result, but no production COMMIT_ACK/COMMITTED exchange | FAIL: not connected |
| Reconciliation | _reconcile_locked requires injected transport; native enum names are not handlers | FAIL: producer missing |
| Installer acceptance | workflows requiring reconciliation remain refused | Correct refusal, not working reconciliation |

Existing one-shot helper operations are not a replacement for the approved
persistent-broker protocol. Do not route around this gap using one-shot helpers,
direct Python disk commands or injected-success transports.

## Fresh execution

`PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_storage_broker_handshake.py -q`

Nine tests PASS in 9.446 s. They compile/run the production profile and test
HELLO, descriptor/environment checks, malformed frames and unauthorized command
rejection. There is no positive authorized-effect test in this suite. This is
not an encrypted-volume, native-effect, recovery or release PASS.

## Required implementation order

1. Implement the exact one-use START_GRANT producer and native consumer from
   the approved S3 design. Bind record/request, operation, budgets, boot,
   workflow/generation and owner nonce/audit identity. Test same-UID non-owner,
   mismatches and replay, with an actual accepted grant as positive control.
2. Add the production Python launch/session owner: attested exec, exec-status
   EOF, real HELLO validation, durable OPEN_RUNNING before grant and START.
   Retain the recovery root and original native broker/session.
3. Implement the native command/effect state machine, using suspended child
   registration and real cleanup proof. Exercise success, failure, timeout,
   CANCEL and EOF on disposable authorized resources. No synthetic success arm.
4. Implement durable CLOSED_READY -> ledger fsync -> COMMIT_ACK -> COMMITTED.
   Test exact ACK replay, mismatched hashes and interrupted acknowledgment.
5. Implement original-broker reconciliation and RECONCILIATION_ACK/FINALIZED,
   bound pending/final records, recovery reattachment and cached exact replay.
6. Connect verified reconciliation to installation admission and mounted-storage
   Doctor. Then complete existing-bootstrap migration/rollback and uninstall.
7. Continue the unchanged product scope: profiles/continuity in mission flow,
   real adapters, Chrome-only user journeys, files/missions/resilience, English
   documentation, privacy, frozen candidate regression and publication approval.

All seven steps remain part of the existing 0.6 objective. This order does not
reduce it to installation or redefine a fail-closed stub as functional support.
No product code, user installation, volume, commit or remote ref changed in this
audit checkpoint.
