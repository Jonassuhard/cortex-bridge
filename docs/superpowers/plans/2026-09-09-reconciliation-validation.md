# Reconciliation evidence validation checkpoint

## Scope

Source inspection showed that production reconciliation is not connected to the
retained native broker: `_reconcile_locked` still requires an injected transport.
The installer continues to refuse workflows needing reconciliation. This lot
does not enable acceptance using fabricated or merely hash-consistent files.

Before wiring that consumer, tests exposed incorrect evidence acceptance:

- A zero-mapping result could claim a nonempty mount point.
- Booleans were accepted as integer mapping/item counts.
- Absent/exact-mapping dispositions could contradict their counts and proof.
- Reload checked the outer digest without revalidating the postcondition,
  its digest, pending/final state or required predecessor.
- A mount observation could be used to reconcile a delete operation.
- Noncanonical or linked metadata could be loaded.

## Changes

Mount and detach observations now require consistent cardinality, emptiness,
disposition and proof fields. Delete requires its own observation, integer zero
items and literal transaction_match=true. Record construction/reload validates
state/result consistency, digest formats, the postcondition digest and a final
record's predecessor. Reload reads bounded private regular single-link metadata
without following the final link and requires canonical bytes; it does not
rewrite rejected evidence. Positive absent/exact-mount round trips remain tested.

## Executed evidence

- Initial mount/detach RED: six failed assertions, 0.018 s.
- Reload RED: four rehashed but semantically invalid records accepted, 0.006 s.
- Noncanonical RED: failed rejection, 0.002 s.
- An intermediate run failed from a missing stat import; corrected before the
  final verification, not treated as a passing run.
- Delete RED: three failed rejection assertions, 0.008 s.
- Final reconciliation/broker/transition/wheel/publication/storage-contract
  suites: 45 PASS, 4.128 s.
- Installer update-admission regressions: three PASS, 2.456 s. Total: 48
  targeted methods, not a full release run.

These are real file/CAS and component tests using synthetic observation data,
not observed DiskImages/Keychain results or native protocol acceptance.

## Remaining requirements

Implement the original retained-broker reconciliation exchange, durable exact
pending/final binding, RECONCILIATION_ACK/FINALIZED, recovery/replay semantics and
the installer consumer. Hash consistency and schema validity do not establish
broker provenance or prove native finalization. The full observation-union and
request-binding matrix, encrypted-volume acceptance and release gate remain
open. No user installation, mounted volume, Git commit, push or release changed.
