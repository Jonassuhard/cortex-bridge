# Descriptor-derived volume UUID

## Implementation

The native mount probe now reads ATTR_VOL_UUID through fgetattrlist on its
already-inherited directory descriptor. It emits a canonical lowercase
`volume_uuid`, rejecting unavailable metadata, an unexpected result length or a
zero UUID. It opens no pathname and adds no Keychain, DiskImages, shell or
arbitrary-command capability. The local SDK declares fgetattrlist and the
ATTR_VOL_INFO/ATTR_VOL_UUID flags used by this call.

This extends the probe's descriptor metadata beyond the fstat/fstatfs calls
listed in the original S3 description. That description must be reconciled in
the integration review before declaring the probe contract final; no review or
approval is fabricated here. Volume identity is not encryption identity, and it
does not alone prove the image-to-mount relationship.

The Python MountFacts type carries this observation as an optional field. None
means unobserved. Existing providers are not silently assigned an environment
UUID, nor does adding this field make InstalledStorageRuntime invoke the probe.

## Executed evidence

RED: five probe tests, one failure in 2.267 seconds for the missing UUID field.
An initial compilation failed because the SDK imports the two attribute flags
with different signed integer types; both are now explicitly converted to
attrgroup_t before combining them. The fresh probe/contract suite then passed:
14 tests in 2.646 seconds.

The real-directory test compares the executable's UUID to a separate Python
ctypes call to the OS metadata API on the same retained descriptor. It checks
the packed buffer length, nonzero UUID and exact value without printing it.
The existing invalid/closed/substituted descriptor tests remain. This is current
Mac evidence; unsupported-filesystem/older-macOS coverage is not implied.

Final fresh regression: **40 tests PASS in 72.467 seconds**, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_mount_probe test_workspace_handle test_executor_fd_ops test_storage_contract test_installed_storage_runtime -q
```

`git diff --check` passed.

No user image, Keychain entry, settings, installation, commit or remote ref was
changed. Next: connect the attested probe invocation, bind observed identities
to the transition and private broker image proof, and replace environment-derived
binding UUIDs. Native effect/terminal/recovery and full 0.6 acceptance remain open.
