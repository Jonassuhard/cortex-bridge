# Incremental native control framing

## Implemented

`IncrementalBrokerReader.step` performs at most eight nonblocking socket reads
per call, preserving prefix/payload fragments between calls. It caps payloads at
16 KiB before allocation, decodes only canonical objects, distinguishes clean
EOF from truncated input, and latches invalid/EOF/deadline terminal states.
It reads exactly one frame and leaves a following frame in the socket.

`readBrokerFrame` now uses the same reader with the existing absolute-deadline
poll wrapper. Thus production HELLO/START-handshake input and private grant input
use this implementation, not a separate test-only codec. The step interface is
available for the running-command control loop without waiting for a peer to
finish sending a partial frame. It does not itself authorize CANCEL or STATUS.

## Tests and limits

The test compiles unmodified production definitions with a test-only entry and
uses real AF_UNIX socket pairs. The sockets are deliberately not switched to
nonblocking mode: MSG_DONTWAIT must make each receive nonblocking itself.
Ten subcases in one unittest method cover empty input, bytewise fragmentation,
concatenated messages, clean EOF, sticky deadline, truncated prefix/payload,
oversize length, empty/noncanonical payload and an exactly 16-KiB payload
(some subcases cover more than one property).

Initial RED: missing IncrementalBrokerReader compilation failure. Initial GREEN
with handshake regression suite: 22 tests PASS in 18.309 seconds. A final decode
check after the eighth read avoids polling for a frame already fully buffered.

The added exact-limit subcase initially timed out in the fixture's same-thread
write-before-read setup (75-test run, 52.728 seconds, one error). Fresh socket
options showed 8,192-byte send/receive buffers, smaller than the 16,388-byte wire
frame. The fixture now interleaves 4-KiB writes with reader steps, retaining the
full 16-KiB acceptance boundary. The ten-subcase reader test then passed in
7.163 seconds; no production size limit or timeout was relaxed.

Final fresh regression command:

```sh
PYTHONPATH=.:console:tests PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest test_native_control_reader test_native_command_pump test_native_spawn_owner test_native_child_registration test_native_recovery_root test_storage_broker_handshake test_start_grant test_storage_broker test_storage_lock test_runtime_wheel -q
```

**75 tests PASS in 46.632 seconds**, exit 0. `git diff --check` also passed.

No disk image or Keychain effect is used. The fixture's SDK selection is local
macOS evidence, not cross-platform acceptance. The existing deprecated Keychain
UI constant warning remains. No commit, push or user installation occurred.

## Remaining acceptance

The authorized START route still rejects execution with INVALID_STATE. A real
running-command controller must validate exact envelope/payload, directional
cursors, nonce/workflow/generation and command digest before handling CANCEL or
STATUS. It must manage per-frame deadlines and bounded outbound frames, connect
the closed operation mapping, preserve unresolved child ownership, and implement
terminal acknowledgment and recovery. This framing work does not close those
gates or the broader 0.6 installation/product/release requirements.
