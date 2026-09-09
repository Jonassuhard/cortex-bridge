# Observed APFS volume binding

StorageContract.open_locked now uses the native descriptor observation's
canonical nonzero volume UUID, rather than copying an environment value into
the binding. Missing or malformed observations fail. If configuration supplies
an APFS UUID, disagreement fails instead of overriding the observation.
StorageContract.revalidate_locked also rejects UUID changes with unchanged
device and filesystem IDs.

## Executed evidence

Two RED tests reproduced the defects: the binding returned unknown instead of
the supplied observation, and revalidation accepted a different UUID.
The older positive directory fixture now explicitly supplies a synthetic UUID;
this fixture proves descriptor handling, not encryption.

37 tests PASS in 74.434 seconds, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_contract test_native_mount_reader test_workspace_handle test_storage_lifecycle test_installed_storage_runtime -q
```

Coverage includes observed UUID propagation, configuration disagreement,
missing/empty/zero UUID rejection and same-device/fsid UUID change rejection.
Native reader tests use an actual compiled probe; contract identity fixtures
are explicitly synthetic and do not demonstrate an encrypted mounted image.

## Remaining integration gates

Host identity and encryption UUID are still not bound to a validated private
broker image proof. A committed transition still reports ready without that
full proof. WorkspaceHandle revalidation does not yet compare volume UUID;
mission-wide propagation remains open. Native effects/ACK/recovery, complete
installation and all 0.6 product acceptance remain incomplete. No readiness
claim, user image/Keychain modification, commit or push occurred.
