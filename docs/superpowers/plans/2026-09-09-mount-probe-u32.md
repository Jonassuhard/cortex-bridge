# Descriptor probe identity format and remaining identity wiring

## Verified implementation change

The real descriptor-only Swift mount probe now emits `st_dev_u32` and
`fsid_u32`, preserving signed Darwin observations with UInt32 bit-pattern
conversion. It no longer exposes the old signed `st_dev`/`fsid` fields. This
aligns its schema with the approved S3 unsigned identity contract and the Python
MountFacts model. It still accepts only one inherited directory descriptor and
performs fstat/fstatfs; no path-open, disk or Keychain effect was added.

The real-directory contract test failed before the change (five tests, one
failure, 2.863 seconds), because the executable emitted the old field names.
The test now checks exact field names, the actual descriptor device bit pattern,
and unsigned ranges for both fsid components. Closed, regular-file, substituted
and malformed descriptor cases remain. This is not proof that a disposable
encrypted volume has been installed or mounted.

The wider 38-test run then failed one installed bootstrap test in 95.110 seconds:
the launcher rejected a generation containing a newline encoding fixture. Root
cause: its independent canonical string encoder still delegated to Foundation's
short escapes, unlike the corrected Python S3 encoder and native broker. The
bootstrap now emits the specified long lowercase escapes itself. The real
generation-selection test was expanded to all 32 control scalars and literal
backslash/quote sequences. This is a root-cause fix, not removal of the fixture
or relaxation of the generation digest check.

The expanded real bootstrap test passed in 41.807 seconds. Final fresh
regression: **51 tests PASS in 114.616 seconds**, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_mount_probe test_native_helpers test_process_helper_build test_installed_storage_runtime test_storage_contract test_storage_reconciliation -q
```

`git diff --check` passed. This verifies the stated probe/build/bootstrap/contract
components, not full encrypted installation or all 0.6 product journeys.

## Fresh integration findings

InstalledStorageRuntime attests the mount-probe executable but still passes the
fallback `probe_mount_fd` into StorageContract. That fallback intentionally
reports unknown filesystem data. It is not an actual invocation of the native
probe, and must not be presented as a successful APFS identity check.

StorageContract.open_locked currently fills host/APFS/encryption UUID fields from
environment variables after checking mount facts. Those values alone are not
fresh encryption or image-to-mount identity proof. Merely connecting the real
fstatfs probe would not establish those identities. The private broker-mounted
image proof, transition consistency and retained descriptors must be connected
before those values authorize detach or runtime storage admission.

StorageLifecycle.detach_locked still constructs a request without verified
encryption identity; replacing that absence with a random UUID or unverified
environment value would be incorrect. Its volume parameter also needs alignment
with the native null-create-fields contract. These gates remain open.

No installed helper, user disk, Keychain item, user configuration or Git remote
was changed. The worktree source changes require verified generation publication
later; old helper binaries are not silently accepted as the new schema.
