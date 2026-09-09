# Disposable Keychain lifecycle confirmation

## Corrected behavior

StorageLifecycle.keychain_spike_locked previously returned SPIKE_PASSED after
only a create call, even when its terminal response was absent. It now performs
create, inspect-item and delete-disposable-item using one transaction UUID and
one transaction-named image in the quarantine directory. The encryption UUID
comes from the confirmed create response; subsequent requests must use and
confirm exactly that identity. Non-create requests contain no create parameters.

Each step requires CLOSED_SUCCESS, matching transaction, success/OK, exact local
response fields, correct operation and item count, canonical encryption UUID,
actual reap/group/cleanup flags and consumed recovery authority. Missing final
confirmation stops the sequence. It does not attempt deletion after ambiguous
creation/inspection or claim that unknown state is successful cleanup.

Explicit cleanup approval is required before any broker request. The deletion
operation concerns the exact disposable Keychain item; the image is retained in
quarantine, not silently erased. No production volume deletion was added.

## Evidence scope

RED: three tests ran in 0.007 seconds, with two failures: only create was called,
and missing terminal evidence still produced PASS. Initial GREEN: 21 lifecycle,
broker and transition tests passed in 0.079 seconds.

Further cases check missing finalization, wrong transaction, invalid UUID,
missing inspected item, changed UUID, boolean item count, leftover item count,
failure outcome and absent/nonboolean cleanup approval. Sequence tests verify
the shared transaction/image, operation order, request fields and exact lock.

Final fresh regression: **35 tests PASS in 82.269 seconds**, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_lifecycle test_storage_broker test_storage_transition test_installed_storage_runtime -q
```

`git diff --check` passed.

These are orchestration tests with explicit fake broker records, not native
Keychain or encrypted-volume acceptance. The real broker still rejects effects
at its unimplemented START dispatch boundary. Synthetic records in these tests
do not create production authority or prove the terminal protocol is complete.

## Remaining integration

Connect the actual persistent native effect/ACK/reconciliation protocol and
descriptor-attested lifecycle identities. The native mount probe is still not
invoked by InstalledStorageRuntime, and environment UUIDs alone must not become
volume proof. create_vault_locked and detach_locked also require response and
identity integration; this change does not claim those routes are complete.

No user image, Keychain item, installation, commit or remote ref changed.
