# Public START schema and canonical control escapes

## Changes

The authenticated native START path now validates public request structure before
reaching its still-unimplemented effect boundary. It checks exact fields and
types, lexical absolute paths, canonical lowercase UUID strings, managed create
size/volume values, absence of create parameters on other operations and explicit
disposable deletion approval. Malformed authorized requests return INVALID_FRAME;
structurally accepted requests still return INVALID_STATE, without STARTED or an
effect. This does not grant native execution authority.

The new validator is separate from the legacy helper validator, which requires
create parameters even for non-create operations. **It is structural validation,
not retained-descriptor attestation:** managed host/mount/image identity,
transaction-owned disposable paths, journal consistency and encryption identity
must still be verified before execution. Private probe validation is separate
pending work. The legacy one-shot effect path is not used as a substitute.

A test containing a newline exposed a Python/Swift canonical JSON mismatch.
Python used JSON short escapes for five control scalars, while the approved S3
format and Swift require lowercase long escapes for all U+0000 through U+001F.
Python now converts escape pairs without altering literal backslash sequences.
The test covers all 32 control scalars and distinguishes a literal backslash-n.
The handshake fixture now hashes the actual canonical request bytes instead of
assuming json.dumps is the contract codec.

## Evidence

- Native schema RED: 18 subcase failures and one framing error in two methods,
  8.182 seconds. Previously malformed authorized requests reached INVALID_STATE.
- Python codec RED: five control-escape failures in 13 methods, 0.058 seconds.
- After implementation: 36 methods, three failures in older launch fixtures that
  omitted required encryption identity. Those fixtures now carry explicit test
  UUIDs; no filesystem or encryption-identity verification is inferred from them.
- Intermediate regression: 56 tests PASS in 12.865 seconds. Additional mount,
  detach and disposable-delete schema cases were added afterward.

Final fresh regression: **97 tests PASS in 68.610 seconds**, exit 0:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_native_control_reader test_native_command_pump test_native_spawn_owner test_native_child_registration test_native_recovery_root test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel test_storage_reconciliation test_storage_lifecycle test_storage_transition -q
```

`git diff --check` passed. The count is not a complete-product acceptance gate.

The tests launch the actual production broker, publish a matching private grant
and inspect its response. No image is created, mounted or deleted and no Keychain
operation runs. Known SDK portability and deprecated Keychain UI warnings remain.

## Open integration requirements

The Python lifecycle currently includes volume_name on detach and omits its
expected encryption UUID. The Python request class also requires a volume name
for mount/detach. These must be aligned with the approved null-create-fields
contract using freshly attested identities, not invented UUIDs or weakened native
validation. Native grant handling also still accepts a zero cleanup budget;
the approved budget policy and arithmetic need completion before effects.

Existing records are not rewritten. Records containing old short-control escape
bytes will fail canonical validation rather than be silently rehashed; migration
of such records, if present, is not proven. No user records were inspected or
mutated by this test run. This change does not establish full S3 interoperability.

Next: connect descriptor-attested lifecycle requests and the closed operation
mapping, then the persistent command controller and durable terminal/recovery
protocol. Product, installer and release gates remain open. No commit or push.
