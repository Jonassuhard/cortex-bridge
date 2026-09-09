# Generation update admission checkpoint

## Reproduced defects

An actual OPEN_PREPARED storage ledger did not stop apply_install from reaching
file staging. A fault injected at the first copy boundary reproduced the missing
guard without installing dependencies: one failing test, 2.778 s.

The generation path also used the historical two-lock context. It now acquires
the full install-exclusive, storage-exclusive, admission-exclusive StorageLockSet
and passes that retained object into apply_locked. Admission is rechecked before
staging and immediately before bootstrap/selector publication.

## Read-only guard

The guard bounds and validates private ledger reads, rejects duplicate record
identities, verifies each record's digest, refuses open records, refuses closed
effects requiring reconciliation, and refuses started effects without literal
boolean cleanup proofs. It does not rewrite journals, start recovery processes,
mount disks, close workflows or manufacture reconciliation evidence.

A CLOSED_FAILURE before START is allowed: failure before an effect is not an
unresolved effect. Tests use real locks and actual ledger serialization; the
broker executable identity is synthetic and is never executed.

## Parent-directory defect

The real ledger fixture exposed a second issue: recursive recovery directory
creation made its intermediate storage parent mode 0755. The permission test
failed in 0.002 s. Recovery creation now creates each parent privately and
validates existing owner/mode/type without chmod of an existing unsafe directory.
An unsafe existing-parent test failed in 0.005 s before its correction.

A malformed cleanup proof containing the string "yes" instead of true reproduced
another failed assertion in 2.637 s; cleanup checks now require literal true.

## Verification

- Complete generation installation/migration suite: 14 PASS, 191.930 s.
  This process loaded before the final existing-parent/type hardening.
- Subsequent final-state targeted suites (broker, update admission, storage
  locks, publication and rebuilt runtime wheel): 43 PASS, 7.368 s.
- These commands cover 54 distinct methods with overlap; they are not a full
  release run against one frozen candidate. Diff whitespace validation passes.

## Remaining scope

This guard does not yet accept a required reconciliation by reading a canonical,
bound reconciliation record: that consumer is not wired into the product.
Such effects remain refused rather than treated as resolved. Recovery of open
workflows, canonical reconciliation acceptance, existing-bootstrap migration and
rollback, generation uninstall, mounted storage, live ChatGPT and cross-harness
missions remain open release gates. No user installation or Git publication.
