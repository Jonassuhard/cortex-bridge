# Private START grant producer — component evidence

Status: component PASS; production START acceptance remains UNCLEAR.

## Implemented

`console/storage_broker.py::_StartGrantChannel` owns one anonymous AF_UNIX
stream endpoint. Before sending, it requires active install/storage locks,
reloads the durable workflow and requires exact equality with OPEN_RUNNING,
reattests the executable and HELLO, and binds the accepted connection/boot
identity to the durable owner. It consumes and closes the endpoint after any
write attempt, including uncertain delivery. Validation before writing does
not consume the endpoint. Named sockets are rejected.

The private frame uses the existing canonical JSON/length-framed transport.
Its exact fields are `version`, `type`, `workflow_id`, `generation`,
`record_sha256`, `request_sha256`, `operation`, `effect_budget_ns`,
`cleanup_budget_ns`, `boot_seconds`, `boot_microseconds`, `connection_nonce`,
and `peer_audit_sha256`. Version is 1; type is START_GRANT. This private
capability frame is not a public broker control envelope.

## Executed evidence

Initial RED: four tests errored because `_StartGrantChannel` did not exist.
Initial GREEN: 19 tests passed in 0.190 seconds.

Fresh expanded regression command:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_start_grant test_storage_broker test_storage_lock test_runtime_wheel -q
```

Result: 39 tests passed in 4.639 seconds, exit 0. Seven grant cases cover exact
bindings/single use, PREPARED refusal, mismatched connection refusal, closed
peer/uncertain delivery, stale durable record, inactive lock, and named socket.

## Limits and next dependency

The tests use real sockets, locks and an on-disk ledger, but synthetic HELLO
and executable bytes. No native storage effect ran. The producer is not yet
called by a production launch/session owner. Swift still does not consume the
grant, and rejects all START controls. This does not establish journal
provenance against hostile same-UID mutation or native recovery correctness.

Next: implement and test the exact Swift grant consumer and START binding;
then wire production launch/exec-status/HELLO/durable RUNNING ordering. Preserve
fail-closed behavior until the supervised effect state machine is complete.
