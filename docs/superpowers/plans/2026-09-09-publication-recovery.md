# Generation publication recovery checkpoint

## Defect and correction

Before bootstrap migration, source inspection found that recovery treated an
existing symlink, dangling link, directory or FIFO journal as an absent journal.
Malformed journal schemas could also become pending recovery records.

Recovery now opens evidence without following the final link and without
blocking on a FIFO. It requires an owner-only regular single-link file, bounds
reads to 64 KiB, detects changes during the read, rejects duplicate JSON keys,
validates exact schema fields and canonical UUIDs, and admits only the three
publication states. Selector evidence receives the same file checks plus exact
fields and a lowercase SHA-256 representation. Recovery does not rewrite files.

## Executed evidence

- RED: seven test methods produced nine failed assertions in 0.026 s before
  production changes (nonregular journals, malformed schema, public journal).
- Final publication suite: eight test methods PASS in 0.031 s, including a
  dangling selector and hardlinked journal.
- Metadata suite: two PASS in 10.883 s.
- Runtime exclusion, storage locks and resource-tree suites: 35 PASS in 0.946 s.
- First installation regression run: six passed, one errored in 78.992 s because
  its pending-journal fixture lacked schema_version. The fixture now includes
  the schema emitted by the actual writer; rejection assertions are unchanged.
- Fresh complete installation regression: seven PASS in 81.566 s, including
  installed native-to-managed HTTP and shutdown. Final checkpoint: 52 targeted
  cases PASS (8 publication + 2 metadata + 35 regressions + 7 installation).

## Limits and next requirement

The recovery status describes publication state, not runtime acceptance or a
fresh verification of every selected application byte. Native startup still
performs that attestation. Callers retain the install lock; hostile same-UID
concurrent replacement remains outside the stated threat model.

Bootstrap migration is not implemented by this correction. Source/spec mapping
also found that bootstrap_install currently uses manifest.json and the
STABLE-BOOTSTRAP digest domain, whereas the normative S3 design names
bootstrap-v1.json and the BOOTSTRAP-MANIFEST domain. This mismatch must be
corrected and tested before declaring bootstrap format/migration compliant.
No user installation, commit, push or release was performed.
