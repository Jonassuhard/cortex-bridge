# Native bootstrap integrity prerequisite

## Scope

Before composing native startup with the managed Python launcher, reject a
generation whose record, interpreter bytes or generation path has changed.
Keep the real installed application untouched.

## Plan

1. Extend the compiled native-launcher test with record, interpreter and path
   corruption; demonstrate rejection is missing before implementation.
2. Recompute the domain-separated generation digest, require a canonical UUID,
   and bind interpreter contents and identity to both manifest and record.
3. Run native tests and real generation installation with the updated source.
4. Record exact evidence and remaining gaps. Do not claim complete bootstrap
   attestation or mounted-storage readiness from these checks.

The native test uses a harmless shell executable to observe whether execution
occurred. It proves the rejection boundary, not real Python/server operation.
The installation suite separately exercises actual Python and HTTP.

## Changes

- Require the selector generation identifier to be a canonical lowercase UUID.
- Recompute the record SHA-256 using the existing domain and Python-compatible
  canonical encoding rather than trusting the embedded digest.
- Verify interpreter SHA-256 and device/inode/owner/mode against both the
  record and manifest before execution.
- Exercise nested canonical values, Unicode, slash/newline strings, booleans,
  null and UInt64 maximum in the compiled native fixture.

## Remaining boundaries

This is integrity against the expected local metadata, not an external trust
anchor. A same-user actor able to rewrite all metadata is not excluded.
Descriptor-pinned ancestor traversal, atomic interpreter execution, strict
duplicate-key rejection, complete app-tree verification before importing Python,
and the native-to-managed handoff remain open. The existing native launcher
still invokes the server directly; it is not yet connected to managed startup.
No release or encrypted-volume acceptance is claimed.

## Executed evidence — macOS arm64, 2026-09-09

Before implementation, the compiled launcher test failed for all three
corruptions: it exited 0 and executed the probe rather than rejecting with 78.
After implementation the same test passed (36.627 s).

Fresh final suites, using
`PYTHONPATH=.:console PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p PATTERN -v`:

| Pattern | Result | Duration |
| --- | --- | --- |
| test_installed_storage_runtime.py | PASS, 12 tests | 78.419 s |
| test_generation_install.py | PASS, 6 tests | 68.736 s |
| test_generation_metadata.py | PASS, 2 tests | 14.452 s |

20 targeted tests pass. The final native suite includes canonical encoding
compatibility inputs and pre-exec corruption rejection. The installation suite
uses real dependencies, signed helpers, installed HTTP and managed closure;
it does not route HTTP through the native bootstrap. Whitespace validation
passes. No commit/push or user-installation mutation.

Storage sessions: native `0fc11043af2f40969ec11334517df6b9`, tests
`e3ed2d2adf2241648b1136d8418c2173`, plans
`8e02a214dc2e45d388093dca2f0c5b55`, root
`e3c98b5a012143b6a888be4ea801df10`.
