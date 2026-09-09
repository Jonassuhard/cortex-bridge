# Positive cleanup budget admission

## Corrected policy

Python budget admission and native private START grant admission now both reject
zero cleanup duration. The approved limits remain 40 seconds for effect,
12 seconds for cleanup and 52 seconds total. Boolean/noninteger Python values,
zeros, negatives and over-limit durations are rejected. Native matching-grant
tests cover zero, boolean, exact maxima, maxima plus one and UInt64.max.

The private mounted-image probe now reserves the existing maximum cleanup budget
instead of silently requesting zero. It remains read-only and unavailable in the
production client until its native protocol path is connected; this duration
change grants no extra operation or mutation authority.

Unrelated positive test fixtures previously using zero now use the minimum valid
duration of one nanosecond. These fixtures test ledger/grant/launch boundaries,
not successful real effects within one nanosecond. The native mismatch fixture
uses a different positive duration so it still proves grant/payload mismatch.
Dedicated negative zero cases remain and must fail admission.

## Executed evidence

RED: two methods, two failures in 8.394 seconds. Python accepted (1, 0), and the
actual native broker accepted a matching grant/payload with that budget through
the unimplemented-effect boundary. GREEN: 48 broker/handshake/grant tests passed
in 15.069 seconds. Tests do not execute disk or Keychain effects.

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_storage_broker test_storage_broker_handshake test_start_grant -q
```

Existing user ledgers were not rewritten or inspected. A previously persisted
zero-budget request cannot gain new START authority through the tightened grant
validation. Recovery of old records is not declared complete by this change.

Additional fresh installation/lifecycle regression: **35 tests PASS in 277.350
seconds**, exit 0, including real disposable generation installation and HTTP
startup as well as update barriers:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_generation_install test_storage_lifecycle test_storage_transition test_storage_reconciliation -q
```

`git diff --check` passed. The installed encrypted-storage path and all product
journeys remain outside the claims established by these targeted tests.

The absolute-deadline construction and full running/terminal/recovery protocol
still require integration. Native START remains non-executing after validation;
the 0.6 product/release gates are not closed. No commit, push, user installation,
volume or Keychain change was performed.
