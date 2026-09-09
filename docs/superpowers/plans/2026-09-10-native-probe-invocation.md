# Native probe invocation

InstalledStorageRuntime now composes NativeMountReader instead of the unknown
Python fallback. The descriptor contract and lifecycle adapter share it.
The fixed --fd command inherits only the directory FD, with a minimal environment.
Executable vnode, mode, owner and hash are rechecked. No disk image or Keychain
operation is added.

The reader validates an exact JSON schema, unsigned integers, canonical nonzero
UUID and descriptor device identity. Output has a 16 KiB rejection limit (one
read chunk may cross it). Observation is bounded to two seconds, including
elapsed launch time, but Popen itself is not interruptible by this deadline.
Strict bounded launch remains open. A live timed-out child remains retained;
close and another invocation refuse until it exits. No Python signal or retry.
Application-wide retention after caller exceptions needs lifecycle testing.

## Evidence

RED: three tests failed because the reader was missing. Integration RED:
installed factory returned filesystem_type=unknown.

GREEN: 35 tests PASS in 69.107 seconds, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_native_mount_reader test_native_helpers test_storage_mount_probe test_storage_contract test_installed_storage_runtime -q
```

Additional adversarial coverage: seven reader tests PASS in 5.672 seconds.
These cover real compiled probe observation; closed attestation and regular
file rejection; installed factory integration; replaced executable rejection;
malformed output rejection; timeout retention and no restart. The harmless
sleep fixture exits naturally, without a cleanup signal.

The factory test supplies bootstrap bytes at the previously tested attestation
boundary and substitutes executable locations. Probe execution and observations
are real. This is not a complete clean-machine installation test.

## Open gates

Volume UUID is not encryption or image-to-mount proof. Journal identity binding,
private broker proof, native effects, durable terminal ACK, recovery and product
acceptance remain incomplete. The fgetattrlist extension to the original
fstat/fstatfs description awaits integration review. No user installation,
volume, Keychain, commit or remote ref was changed. No 0.6 readiness claim.
