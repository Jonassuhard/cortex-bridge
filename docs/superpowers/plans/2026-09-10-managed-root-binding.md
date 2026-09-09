# Bind the managed root to the held mount

## Corrected defects

StorageContract.open_locked previously accepted an unrelated configured root as
long as it shared the mount's filesystem device. It also reopened that root by
absolute path after opening the mount, permitting a replaced mount pathname to
bind two different directories on the same device.

The root must now be exactly the configured mount's `20_WORKSPACES` child. It is
opened descriptor-relatively with the existing no-follow directory traversal
primitive. Before returning, the named mount and descriptor-relative root must
still match the held directory device/inode identities. Failure closes acquired
descriptors and reports a storage-contract error.

## Executed evidence and scope

The first real-filesystem test reproduced unrelated same-device root admission
(seven tests, one failure, 0.033 seconds). The second reproduced mount pathname
replacement after descriptor open (eight tests, two failures, 0.049 seconds).
After correction, 16 contract/lifecycle/transition tests passed in 0.092 seconds.

Further checks verify closure of the rejected mount descriptor and exact inode
retention for an ordinary managed root. The race test wraps the real open syscall
solely to rename a disposable fixture directory after opening it. It does not
mock away the filesystem operations being asserted.

Final fresh regression: **29 tests PASS in 92.191 seconds**, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_contract test_storage_lifecycle test_storage_transition test_installed_storage_runtime -q
```

`git diff --check` passed.

Mount facts in these tests are explicitly synthetic to isolate root binding.
The tests do not establish APFS/encryption identity or a valid encrypted vault.
UUID provenance, retained host/image authority, no-follow ancestry of the mount
path and private broker image-to-mount proof remain separate open requirements.
Environment UUIDs are still not authoritative proof. The native probe wiring and
persistent effect/terminal/recovery implementation remain unfinished.

No user configuration, disk image, Keychain item, installation, commit or remote
Git ref changed. This result is a directory-binding fix, not a 0.6-ready verdict.
