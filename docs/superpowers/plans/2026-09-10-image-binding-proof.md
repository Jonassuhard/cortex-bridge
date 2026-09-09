# Journal-bound encrypted image proof consumption

StorageContract now requires its private broker mounted-image proof before
returning a binding. The encryption UUID comes from the committed transition
journal and must be canonical/nonzero; an environment assertion cannot supply
or override it. The image is the fixed managed child of the configured host,
opened through retained no-follow directory descriptors. Image identity is
rechecked after the private probe. Returned proof fields must match the mount,
image inode/device, observed APFS UUID, journal encryption UUID, fixed volume
name, one mapping, APFS, writable and encrypted flags.

The contract status path now opens/verifies/closes the same binding rather than
returning READY solely because the transition was committed. Shared status and
exclusive admission preserve their lock requirements. Missing/failed proof
returns UNCLEAR, not mounted and not runtime-allowed; opening raises
STORAGE_ENCRYPTED_IMAGE_UNPROVEN. The lower-level journal status function still
projects journal state and is not an independent runtime-readiness proof.

## Executed evidence

RED: committed journal plus APFS observations returned a binding without any
image proof. A second RED reproduced runtime_allowed=True for the same case.

48 tests PASS in 67.601 seconds, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_contract test_storage_lifecycle test_storage_transition test_storage_broker test_installed_storage_runtime -q
```

Positive contract fixtures explicitly construct a synthetic MountedImageProof
and synthetic journal encryption UUID to test consumption, not native production.
Negative variants reject encrypted=false, writable=false, mapping_count=2 and
wrong image inode. Actual directory descriptors and journal serialization are
used. These fixtures do not prove an encrypted disk image exists.

## Open gates

The production private broker method still returns BROKER_UNAVAILABLE without
an injected transport: native private-probe execution is not implemented. No
real encrypted-volume acceptance is claimed. Host identity is still not fully
bound: StorageBinding.host_fd/UUID fields need replacement with a retained,
observed host binding; ancestor-path confinement and post-proof mount races
need further coverage. Full terminal/recovery protocol, lifecycle publication
of validated journal evidence and complete 0.6 acceptance remain incomplete.
No user image, installation or Keychain changed. No commit or push.
