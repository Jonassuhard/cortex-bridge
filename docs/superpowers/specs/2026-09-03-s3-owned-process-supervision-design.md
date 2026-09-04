# Cortex Bridge S3 Owned-Process Supervision Design

**Status:** Revision 7 review candidate; implementation remains frozen until
these exact specification and plan bytes receive three fresh, mutually blind,
read-only reviews with `P0=0`, `P1=0`, `P2=0` and `PASS`
**Date:** 2026-09-05
**Reviewed baseline:** `db5a40f822c115b3f06b93a8d0c4ef04a74cd026`
**Revision-7 parent:** `7b3567637f2025c1b8c21338acad070d6561bcd9`
**Target:** v0.5.4 candidate
**Supersedes:** the S3 supervision and live-harness design in the current Phase
S plan; unrelated storage requirements remain in force

## Decision

S3 uses three persistent ownership layers rather than treating a helper PID,
a count or a decoded frame as authority:

1. the Python session owner holds artifact, Keychain, observer and lifecycle
   registries and starts one persistent Swift broker before live issuance;
2. that broker alone starts, observes, signals, waits and reaps every native
   `/usr/bin/hdiutil` child, including when an invocation worker disappears;
3. invocation workers validate strict requests, manage application secret
   lifetimes and exchange byte-exact bounded frames with the broker, but never
   own native process primitives.

The design also fixes one persistent SecurityAgent observer, one serial Python
effect executor, descriptor-attested artifact cursors, one exact
`BrokerChildFreeLease`, typed publication proofs and an explicit
`OPEN_UNRESOLVED` state. At the +115-second decision boundary a still-busy
native obligation does not authorize STOP, disposition or Python exit. The
owner, broker and observer remain alive in containment/observation mode until a
native terminal fact permits the sole late-close chain.

This revision is documentary candidate material, not implementation or
approval evidence. It authorizes no live Keychain, DiskImages, `hdiutil`, mount,
detach, quarantine, SecurityAgent, Chrome, runtime, push, merge, tag or release
action.

## Trust boundary and exact claim

Production native execution is fixed to `/usr/bin/hdiutil`. A direct child is
created suspended in a new session and is registered before any active frame.
Only the persistent broker owns its PID, original process group, descriptors,
waitability observations and signal permits. The worker receives no numeric
process authority. A worker EOF, EPIPE, partial frame, abnormal exit or kill
changes result delivery; it does not erase the broker's native safety
obligation.

Every TERM or KILL consumes a one-shot `WaitableSignalPermit` minted from an
exact same-generation WNOWAIT/identity observation in the same lifecycle turn.
EINTR mints nothing. `noChild`, wrong PID/status, identity change, lost
waitability, ECHILD or an unavailable observation irreversibly removes signal
authority for that attempt. TERM/KILL decisions precede reap. After exact reap,
only one registry-bound signal-zero observation of the original group is
representable.

A safely settled native command is not retired merely because its final frame
was written. Worker delivery requires a distinct exact final ACK. If the worker
is lost before that ACK, the broker uses the one-shot admin orphan route; only
an exact Python ACK retires the orphan ledger. Lost delivery can never become
worker success. A second worker for that generation is refused until the
orphan ledger is acknowledged or permanently unresolved.

The S3 guarantee is conditional on the Python owner, broker and kernel
remaining able to make the documented observations. External destruction of
the broker, loss of all admin delivery, hostile native nontermination or an
unobservable escaping descendant produces an open unresolved session, not a
false close. Achieving bounded caller exit under arbitrary broker destruction
requires an out-of-scope persistent system service.

Artifact authority is likewise narrow. The sealed Python registry authorizes
only the current registered image/mount/UUID lineage. A continuation resolves
the current mapping; a historical `/dev/diskN` never becomes detach authority.
Returned-device comparison is post-effect consistency evidence only.

## Goals

- Replace raw PID, PGID, copied-frame and bare-cardinality inputs with private,
  registry-minted, one-shot receipts.
- Preserve native cleanup through invocation-worker loss by keeping native
  ownership in one persistent broker.
- Make signal authority depend on exact observable waitability, identity,
  generation, target, signal, sequence and deadline.
- Admit every child-free Security.framework or filesystem mutation only under
  one mutually exclusive broker lease and a same-turn terminal-polled permit.
- Keep every artifact effect in a closed in-flight transition and carry exact
  old/new facts when completion is ambiguous.
- Bind response success to exact trace candidate, complete response write,
  publication receipt and proof; bind response-free exits to a separate proof.
- Bound every request, channel, output, JSON value, backlog, discard drain and
  deadline with equality and plus-one oracles.
- Keep the observer active from preparation through proved broker close and its
  own final snapshot/STOP/EOF/reap/group-absence sequence.
- Preserve the public strict ten-key request and six-key response contracts.
- Make every test, mutant, owner projection, closure hash, package and final
  commit identity reproducible without executing unreviewed candidate code.

## Non-goals and residual assumptions

- No general macOS sandbox, Endpoint Security client, launch daemon or pidfd
  substitute.
- No claim that synchronous Keychain calls are preemptible. A late return may
  update an uncertainty ledger but cannot authorize a successor effect.
- No claim that killing `hdiutil` reverses a partial disk-image effect.
- No claim that a sub-cadence SecurityAgent event must be observed.
- No claim that Swift registry objects cross a process boundary. Wire fields
  are validated only by the receiving registry, which mints a local receipt.
- No claim against a hostile same-UID replacement between final hash
  revalidation and `execve`; macOS provides no `fexecve` for this path.
- No S4 implementation in the S3 commit range.
- No relaxation of authorization, timeout, cleanup, review or immutable-tree
  gates.

## Component and process boundary

| File | S3 responsibility |
| --- | --- |
| `native/macos/disk_image_keychain.swift` | Public helper modes, persistent broker, invocation worker, byte-exact broker protocol, private native EFSM/registries, command provenance, erasure and testing-only fixture routes. |
| `tests/disk_image_keychain_harness.py` | Python registries, broker/worker FD transfer, sealed preparation/live session, exact observer Swift source bytes and hashes, observer/broker ownership, artifact effects, immutable review gate source and mutant machinery. |
| `tests/test_disk_image_keychain_helper.py` | Independent reference machines, full EFSM matrix, exhaustive/causal traces, process/channel/deadline/receipt oracles, immutable-tree runners, manifests and separately selected live class. |

Only those three implementation files may differ between
`IMPLEMENTATION_BASE` and `S3_FINAL`. The observer remains constant Swift bytes
stored in `tests/disk_image_keychain_harness.py`; compilation creates only a
private ignored source and ephemeral binary. No fourth tracked implementation
file exists.

The process graph is exact:

~~~text
Python session owner
  |-- persistent SecurityAgent observer
  |-- persistent Swift broker over one admin AF_UNIX SOCK_STREAM
  `-- per invocation:
        Python creates one AF_UNIX socketpair
        Python transfers exactly broker endpoint with one SCM_RIGHTS message
        broker validates and ACKs transfer
        worker inherits only its endpoint and stdio/control
        broker alone owns every native child
~~~

Python and broker publish exact argv, environment and FD ledgers for success and
every failure. Each owned close is attempted independently. FD transfer rejects
`MSG_CTRUNC`, non-SCM ancillary data, zero/multiple FDs, aliases with stdio,
control or admin, wrong family/type, duplicate session/generation/digest,
missing or inverted ACK and worker-spawn failure without a closed orphan
ledger. The received FD is `FD_CLOEXEC|O_NONBLOCK` before insertion.

## Exact environments and interpreter TCB

The common non-inheriting environment is exactly:

~~~text
BASE_EXEC_ENV_ITEMS = (("LANG", "C"), ("LC_ALL", "C"),
                       ("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"))
CORTEX_S3_ENV_V1\0LANG=C\0LC_ALL=C\0PATH=/usr/bin:/bin:/usr/sbin:/sbin\0
SHA-256 = 332a3faa28f88fd67e9b9295487b7bbe9c0b41e2828f4283db4f339be9557e85
~~~

`BASE_EXEC_ENV` is the Python mapping; `sanitizedEnvironmentV1` is its
byte-equivalent Swift envp. It is used for compilers, private source copies,
clock reporters, observer, broker and ordinary/continuation workers. The R43
fresh interpreter adds only canonical UInt64
`CORTEX_S3_PARENT_HARD_DEADLINE_NS`. A sealed testing worker may additionally
receive `CORTEX_STORAGE_TEST_MUTANT` only with
`CORTEX_STORAGE_HELPER_TESTING` and the exact config/report digest. Production
contains neither lookup nor branch. Every reservation and report binds the
environment profile and digest.

The equipped CPython executable, loader and stdlib are explicit TCB.
`InterpreterTCBReceipt` binds absolute interpreter/loader paths, every lstat
chain, device/inode/mode/UID/size/hash, version, cache tag, trusted stdlib roots,
bootstrap hash and import-allowlist hash. Group/world-writable or changed facts
reject, and the receipt is revalidated immediately before GO.

The isolated bootstrap performs `import sys` first, installs its audit hook
before any later import, and has exactly these direct imports:

~~~text
errno, fcntl, hashlib, json, os, stat, sys, time
~~~

No `ImportFrom`, site, user/project/zip origin, dynamic import, `importlib`,
`__import__`, `eval` or `exec` is accepted. Preloaded interpreter modules and
transitive builtin/frozen/trusted-stdlib modules are part of the TCB, not
claimed absent.

## Broker protocol v2

### Common frame header

Admin and worker/broker channels use ASCII magic `CS3B` (`43 53 33 42`),
version `0x01`, admin channel `0x01`, worker channel `0x02`, flags `0x00` and
big-endian multi-byte fields. The exact 96-byte header is:

| Offset/size | Field |
| --- | --- |
| 0/4 | magic |
| 4/1 | version |
| 5/1 | channel |
| 6/1 | numeric type |
| 7/1 | flags |
| 8/2 | header length `0x0060` |
| 10/2 | reserved `0x0000` |
| 12/4 | payload length |
| 16/16 | raw session UUID |
| 32/8 | generation |
| 40/8 | directional sequence |
| 48/32 | raw context/command SHA-256 |
| 80/8 | stream offset |
| 88/4 | stream length |
| 92/4 | subject ordinal |

Sequences start at zero independently per direction, are contiguous UInt64 and
never wrap. ACK payload is the acknowledged u64 sequence; every ACK frame is
104 bytes and repeats the paired frame bindings. Wrong magic, version,
endianness, header length, reserved/flags, channel, type, context, sequence or
stream position rejects before allocation or effect.

Admin types are exact:

| Code | Type | Payload bytes | Ancillary bytes / FD |
| ---: | --- | ---: | ---: |
| `0x01` | `BROKER_READY` | JSON 1..4,000 | 0 |
| `0x02` | `BROKER_READY_ACK` | 8 | 0 |
| `0x03` | `TRANSFER_WORKER_FD` | exact JSON 145 | 16 / 1 |
| `0x04` | `TRANSFER_WORKER_FD_ACK` | 8 | 0 |
| `0x05` | `WORKER_SPAWN_FAILED` | JSON 1..4,000 | 0 |
| `0x06` | `WORKER_SPAWN_FAILED_ACK` | 8 | 0 |
| `0x07` | `BROKER_ORPHAN_SETTLEMENT` | JSON 1..4,000 | 0 |
| `0x08` | `BROKER_ORPHAN_SETTLEMENT_ACK` | 8 | 0 |
| `0x09` | `BROKER_STOP` | 0 | 0 |
| `0x0a` | `BROKER_STOPPED_ACK` | 8 | 0 |
| `0x0b` | `ADMIN_LEASE_ACQUIRE` | 0 | 0 |
| `0x0c` | `ADMIN_LEASE_GRANTED_ACK` | 8 | 0 |
| `0x0d` | `ADMIN_LEASE_RELEASE` | 0 | 0 |
| `0x0e` | `ADMIN_LEASE_RELEASED_ACK` | 8 | 0 |

Transfer JSON has only canonical keys `command_digest` (64 lowercase hex),
`generation` (1..7) and `session` (32 lowercase hex): 145 payload bytes, 241
with header.

Worker types are exact:

~~~text
COMMAND_JSON=0x20, WIRE_SECRET=0x21, COMMAND_ADMITTED_ACK=0x22,
COMMAND_CANCEL=0x23, COMMAND_CANCEL_ACK=0x24,
WORKER_LEASE_ACQUIRE=0x25, WORKER_LEASE_GRANTED_ACK=0x26,
WORKER_LEASE_RELEASE=0x27, WORKER_LEASE_RELEASED_ACK=0x28,
STDOUT_CHUNK=0x30, STDOUT_END=0x31,
STDERR_CHUNK=0x32, STDERR_END=0x33,
BROKER_SETTLED_COMMAND_JSON=0x34,
BROKER_UNRESOLVED_COMMAND_JSON=0x35, BROKER_FINAL_ACK=0x36
~~~

Command/final JSON is 1..4,000 bytes; Wire secret is exactly 44 bytes; controls
are zero-data; chunks are 1..65,440; END carries raw 32-byte digest with exact
total offset and zero stream length; ACK is eight bytes. Both END frames precede
the unique final frame, which repeats exact lengths/digests. A partial final
frame consumes its only route and is never retried. `BrokerSettledCommandFrame`
and `BrokerOrphanSettlementFrame` are wire values only; object identity never
crosses processes.

Golden vectors are byte-identical in Swift and Python for a 4,096-byte READY,
104-byte ACK, 241-byte transfer plus 16 ancillary bytes, 140-byte Wire frame,
1,632-byte final chunk for a 1 MiB stream, and empty/nonempty END digests.

### Caps, grammar and exact witnesses

| Resource | Exact cap or witness |
| --- | ---: |
| `ADMIN_FRAME_MAX` / payload | 4,096 / 4,000 |
| `WORKER_FRAME_MAX` / payload/chunk | 65,536 / 65,440 |
| native stdout / stderr | 1,048,576 each |
| commands in flight per session | 1 |
| commands per invocation / closed session | 7 / 20 |
| workers transferred per session | 7 |
| full stream fragmentation | 16 x 65,440 + 1,536 = 17 chunks; 34 for two streams |
| base maximal native command | 40 frames / 2,109,072 bytes |
| secret plus cancel/ACK command | 43 frames / 2,109,412 bytes |
| seven-command invocation | 287 frames / 238 chunks / 14,764,244 bytes |
| normal worker trace | 835 frames / 42,185,060 bytes |
| separate cancel trace | 829 frames / 42,184,460 bytes |
| admin frame maximum | 34 frames; approved-close witness 8,415 bytes |
| admin byte maximum | 12,215 bytes; separate 32-frame error witness |
| reachable combined frame maximum | 869 |
| conservative combined byte ceiling | 42,197,275; upper bound only |
| transfer ancillary total | 112 bytes |
| broker rolling memory | 131,168 bytes |
| worker rolling memory | 2,175,020 bytes |
| observer rolling retained | 16,781,364 bytes |
| Python retained maximum | 20,979,868 bytes |

The normal worker witness is 20 base commands, three Wire frames and eight
four-frame leases. The cancel witness is separate: 20 commands, three Wire
frames, six leases and one cancel/ACK; no later command or lease is legal. The
34-frame admin witness is READY/ACK, four four-frame leases, seven transfer/ACK
pairs and STOP/STOPPED_ACK. The 12,215-byte admin witness has three leases,
seven transfers, one 4,096-byte failure/orphan JSON plus ACK and STOP pair. The
combined byte ceiling is not asserted equality-reachable.

Darwin ancillary facts are `sizeof(cmsghdr)=12`, `sizeof(Int32)=4`,
`CMSG_SPACE(4)=CMSG_LEN(4)=16`, hence `ANCILLARY_MAX=16` and exactly one FD.
All non-transfer frames require zero ancillary.

Canonical JSON uses ASCII, sorted keys, separators `(",", ":")`,
`ensure_ascii=True`, `allow_nan=False`; floats are forbidden. Limits are depth
8 (root depth 1), 512 items, decoded key 64 bytes, decoded UTF-8 string 4,096,
encoded token 24,578, integer token 20 and private observer token 160. The
sealed global equality witness `JSON_LIMIT_FIXTURE_V1` encodes 4,096 U+0001
values into token 24,578 and payload 24,584 under the 65,532-byte report limit.
Broker equality is decoded string 3,992/token 3,994 using canonical
`{"e":"<3992 ASCII A>"}`; other dimensions have separate legal witnesses.
Production rejects the fixture profile.

Reads never use `communicate`, `readDataToEndOfFile`, unbounded reads or text
mode. A 4,096-byte scratch bounds memory. Discard budget is 1,048,576 bytes and
250,000,000 ns per FD, and 2,097,152 bytes/500,000,000 ns shared by native
stdout and stderr. The first overflow freezes byte/time budgets; EOF or a later
error cannot reset them. Exhaustion stops payload reads and allows only
authorized cleanup through the existing terminal deadline. Lost authority
enters `OPEN_UNRESOLVED`.

General channel caps are exact: helper stdin 65,536; helper stdout/stderr 4,096
each; control 1/16; native child aggregate 2,097,196 including Wire; helper
exchange 73,745; R43 139,290; observer/config/report frame 65,536 with payload
at most 65,532; observer backlog 4,096 frames and 16,777,216 stdout bytes;
compiler streams 1,048,576 each; clock 32/4,096; exec-status 8; GO one `0x01`
plus EOF; guardian/witness zero bytes plus EOF; prior Python accumulator
4,194,304. Observer STOP is exactly 52 bytes.

Observer backlog caps are rolling retained-memory limits, not lifetime frame
limits. Processed frames release backlog; checked UInt64 sequence continues.
Overflow is unresolved without wrap.

## Native lifecycle EFSM

The typed `NativeChildLifecycleEFSM` has exactly fourteen control states, in
this order:

~~~text
spawnedActiveFramePending, suspended, validatedSuspended, suspendedCleanup,
running, exitedUnreaped, reapedAwaitingGroup, groupAbsentAwaitingCloses,
settledPendingBrokerFrame, unresolvedNoSignalAwaitingCloses,
unresolvedPendingBrokerFrame, retiredSettled, retiredUnresolved,
channelLostCleanup
~~~

`spawn` is a factory from external `noObligation`, not a fifteenth state.
Applying it to an existing EFSM rejects without syscall. Retired states reject
every event. Channel loss changes delivery registers without erasing later
native safety facts.

The nineteen constructors and exact closed member counts are:

| # | Constructor | Closed members | Count |
| ---: | --- | --- | ---: |
| 1 | `spawn(SpawnResult)` | spawned, refused, deadlineExpired, failed | 4 |
| 2 | `publishActive(FrameWriteResult)` | fullyWritten, partial, brokenPipe, deadlineExpired, interruptedAtDeadline, failed | 6 |
| 3 | `validate(IdentityResult)` | exact, incomplete, changed, unavailable, deadlineExpired | 5 |
| 4 | `cancelObserved` | singleton | 1 |
| 5 | `resume(ResumeResult)` | resumed, childGone, identityChanged, deadlineExpired, interruptedAtDeadline, failed | 6 |
| 6 | `observeExit(ExitObservation)` | running, exactExited, noChild, wrongPID, wrongSignal, wrongCode, interrupted, deadlineExpired, failed | 9 |
| 7 | `observeWaitability(WaitabilityObservationResult)` | exactWaitable, exactExited, noChild, wrongPID, wrongSignal, wrongCode, identityChanged, notWaitable, interrupted, deadlineExpired, failed | 11 |
| 8 | `mintSignalPermit(SignalIntent, SignalPermitMintResult)` | four intents times minted, staleObservation, consumedObservation, foreignObservation, deadlineExpired, issuanceExhausted, registryClosed | 28 |
| 9 | `signal(WaitableSignalPermit, SignalResult)` | delivered, alreadyAbsent, permissionDenied, deadlineExpired, interruptedAtDeadline, failed | 6 |
| 10 | `wait(WaitResult)` | exactlyReaped, stillRunning, noChild, wrongPID, deadlineExpired, interruptedAtDeadline, failed | 7 |
| 11 | `reap(ReapResult)` | the same seven members as a distinct type | 7 |
| 12 | `observeGroup(GroupPresence)` | absentESRCH, present, permissionDenied, deadlineExpired, interruptedAtDeadline, failed | 6 |
| 13 | `closeNative(CloseSetResult)` | allClosed, partial, interruptedStateUnknown, deadlineExpired, failed | 5 |
| 14 | `workerChannelLost(WorkerChannelLoss)` | eof, brokenPipe, partialFrame, protocolViolation, workerExited, workerKilled, ioFailure | 7 |
| 15 | `adminChannelLost(AdminChannelLoss)` | eof, brokenPipe, partialFrame, protocolViolation, pythonExited, pythonKilled, ioFailure | 7 |
| 16 | `deliverWorkerFinal(WorkerFinalDeliveryResult)` | fullyWrittenMatching, partial, brokenPipe, deadlineExpired, interruptedAtDeadline, failed | 6 |
| 17 | `acknowledgeWorkerFinal(WorkerFinalAckResult)` | exact, eofBeforeAck, partial, malformed, mismatchedBinding, duplicate, deadlineExpired, interruptedAtDeadline, failed | 9 |
| 18 | `publishOrphan(OrphanPublicationResult)` | fullyWrittenMatching, partial, brokenPipe, deadlineExpired, interruptedAtDeadline, failed | 6 |
| 19 | `acknowledgeOrphan(OrphanAckResult)` | exact, eofBeforeAck, partial, malformed, mismatchedBinding, duplicate, deadlineExpired, interruptedAtDeadline, failed | 9 |

The member total is 145. The matrix contains exactly `14 * 145 = 2,030`
state/member pairs plus four external spawn assertions, for 2,034 assertions.
Opaque errno/count/identity data does not enlarge enum cardinality; equality
oracles cover it. Four signal intents count because they change legality.

Every entry returns only
`accepted(nextState, exactActionVector, exactRegistryDelta)` or
`rejectedNoSyscall(originalState, zeroActionVector, zeroRegistryDelta)`.
Reference equality includes obligation, cancel latch, delivery route,
observation/permit slots, signal stage, close ledger, frame-attempt ledger,
`workerFinalAckPending` and orphan-ACK ledger. Rejection preserves every byte
and performs zero syscall, frame, close, issue/consume or deadline resample.
Accepted entries may have a zero-syscall vector.

Exact validation advances only to `validatedSuspended`; only confirmed resume
advances to `running`. Every other validation/resume result enters retained
cleanup. Cleanup is decomposed into waitability observation, permit mint,
signal, wait and reap; there is no composite abort result. `stillRunning`
retains the obligation, not a permit. Permit equality binds registry identity,
session, generation, digest, PID/group target kind, signal, observation
sequence and deadline.

`deliverWorkerFinal(.fullyWrittenMatching)` creates exactly one
`workerFinalAckPending: Optional<WorkerFinalWriteReceipt>`. It neither retires
nor mints worker success. Only exact ACK with local channel identity, session,
generation, command digest, final sequence/hash, native outcome, transfer
generation and protocol tag consumes it. A non-exact ACK or loss before ACK
uses the orphan route once; lost admin remains unresolved.

The matrix is exhaustive; exponential `145^depth` enumeration is forbidden.
Causal traces are exactly waitability -> permit -> signal -> wait; exit ->
optional group TERM/KILL -> reap -> group-zero -> closes; worker loss -> native
settlement -> orphan publication -> ACK; and closes -> worker-final write ->
exact worker ACK. A route consumes its one publication attempt. One observation
produces ACK EOF or async channel-loss, never both.

## Child-free mutation authority

The broker arbitrates one mutually exclusive `BrokerChildFreeLease` across
admin and worker channels. While held, no native admission is possible; a
second or cross-channel lease is refused. `NoActiveChildProof` requires the
exclusive lease plus an empty broker registry and never comes from a replayable
idle snapshot.

Within Swift, each `SecRandomCopyBytes`, `SecItemCopyMatching`, `SecItemAdd`,
`SecItemDelete`, post-delete requery and child-free filesystem mutation
consumes a syscall/callsite-bound same-turn terminal-polled permit. Within
Python, every mutation is structurally dominated by:

~~~text
consume_admin_child_free_permit(callsite, generation, terminal_watermark)
~~~

The closed Python callsites are `prepareMountLeaf` mkdirat, quarantine rename,
image unlink/delete and final mount-leaf removal. Wrong/replayed identity,
wrong generation/callsite, stale poll, EOF, terminal, double lease or release
failure performs zero mutation and follows the total release/unresolved path.
Worker EOF and terminal paths cannot strand or reuse a lease.

## Artifact, mount and in-flight algebra

`ArtifactCursor` starts at `noArtifact`. Before create, `prepareMountLeaf` is a
named effect:

~~~text
ArtifactCursor(noArtifact)
-> InFlightOperation(prepareMountLeaf)
-> ArtifactCursor(mountLeafPrepared, MountLeafIdentity)
-> create
~~~

The leaf is created with descriptor-relative `mkdirat`, opened no-follow as a
directory, compared by fstat/fstatat, and must be current-UID mode 0700.
`MountLeafIdentity(dev,ino,mode,uid)` is carried by every relevant cursor. After
detach the leaf is reopened before comparison/enumeration; the pre-mount FD
sees the covered directory and cannot prove mount absence. Path-only iteration
is forbidden. Replacement, symlink, nonempty enumeration, identity mismatch or
any independent close failure is unresolved/preserve. Final leaf removal is a
separate named disposition effect with a closed outcome.

`InFlightPredecessor` is a closed union containing every artifact cursor,
preparation terminal, terminal event, detached-and-absent outcome, every
quarantine/deletion/preservation/disposition outcome, broker termination
outcome, disposition receipt and `OpenUnresolvedHandle`. The exact
predecessor+operation table has one successor per listed pair. Each arm is
registry-minted, one-shot and atomically consumed; `Any`, free tuples and
unlisted transitions reject.

The artifact cursor graph is exact:

~~~text
noArtifact
-> mountLeafPrepared(MountLeafIdentity)
-> created(cycle=0)
-> mounted(i) -> mountVerified(i) -> unmounted(i)
-> created(cycle=i+1), for i in {0,1}
-> cyclesComplete
-> keychainInspected
   | approved exact delete plus zero requery -> keychainAbsent -> imageAbsent
   | unapproved inspected-present -> imageQuarantined(keychainStillPresent)
   ` ambiguous/missing requery -> preserved(keychainPresenceUnknown)
every effect boundary -> unresolved(complete possible-ledger set)
eligible final artifact outcome -> mountLeafRemoved
~~~

The closed transition catalogue is:

| Predecessor arm | Named operation | Sole settled successor class |
| --- | --- | --- |
| `ArtifactCursor(noArtifact)` | `prepareMountLeaf` | `ArtifactCursor(mountLeafPrepared(identity))` |
| `ArtifactCursor(mountLeafPrepared)` | create | `ArtifactCursor(created(0))` |
| `ArtifactCursor(created(i))` | mount cycle | `ArtifactCursor(mounted(i))` |
| `ArtifactCursor(mounted(i))` | verify current mapping/APFS | `ArtifactCursor(mountVerified(i))` |
| `ArtifactCursor(mountVerified(i))` | public `detach26` plus absence | `ArtifactCursor(unmounted(i))` |
| `ArtifactCursor(unmounted(i))` | advance | `created(i+1)` or `cyclesComplete` after `i=1` |
| `ArtifactCursor(cyclesComplete)` | inspect item | `keychainInspected` plus exactly one presence receipt |
| inspected plus cleanup grant | delete and zero requery | `keychainAbsent` or presence-unknown preservation |
| `keychainAbsent` plus image permit | tombstone/unlink | `imageAbsent` |
| inspected-present without grant | quarantine | `imageQuarantined(keychainStillPresent)` |
| current cursor or registered in-flight record | terminal latch | `TerminalEventReceipt` or terminal-pending record |
| mounted terminal event | disposition detach/absence | `DetachedAndAbsentReceipt` or `UnresolvedContinuationReceipt` |
| exact unmounted/detached terminal predecessor | quarantine or preserve | exact disposition outcome or unresolved preservation |
| exact eligible artifact outcome | `removeMountLeaf` | leaf-removed outcome or unresolved preservation |
| settled artifact disposition | broker close | `BrokerTerminationOutcome` |
| proved broker close | final snapshot then observer close | `ObserverTerminationOutcome` |
| stopped observer plus settled disposition | mint disposition | `DispositionReceipt` |
| `DispositionReceipt` | close | `CLOSED_PROVED` |
| `OpenUnresolvedHandle` | native terminal then broker/observer late close | locked-non-PASS `DispositionReceipt` |

Every effectful row also has its typed unresolved successor carrying all
possible facts. No row can skip an intermediate predecessor, and no error or
exception silently returns the consumed predecessor.

Keychain state uses three incompatible receipts:
`KeychainStillPresentReceipt`, `KeychainAbsentReceipt` and
`KeychainPresenceUnknownReceipt`. Unapproved inspected-present cleanup goes
directly to `imageQuarantined(keychainStillPresent)` without fabricating
absence. Approved cleanup consumes its grant, deletes, then requires an exact
zero-item requery before absence can authorize image deletion. Ambiguous or
missing requery is presence-unknown/preserve. The deletion tombstone is
internal and is not the public unapproved quarantine state.

Quarantine and deletion use only no-follow parent/image descriptors,
fstat/fstatat identity and
`renameatx_np(parent_fd, old_leaf, parent_fd, new_leaf, RENAME_EXCL)`. Every
close is independent. Collision, replacement, removal error, revalidation or
close error preserves exact old/new facts and never becomes success.

## Invocation classes, deadlines and publication

Invocation class is authenticated and immutable:

- `workflow70` for public create, mount, inspect-item and
  delete-disposable-item workers;
- `detach26` for every public detach worker, ordinary or terminal.

A compensation detach inside public mount remains a broker subcommand in the
same `workflow70` worker and keeps its original origin/cutoff digest. It is not
another worker, cannot resample and cannot borrow terminal reserve. Every
broker command binds the worker origin/cutoff digest.

All ordinary workers share one normal epoch/cutoff. Ordinary detach is admitted
only when origin+26 fits the normal cutoff. Terminal detach starts only after
the +72 watermark and requires `now+26 <= live_started+98`. Both public detach
forms use stage stops +8/+14/+20/+26. All normal workers, EOFs, exact reaps and
broker settlements finish by +71. The full session cutoffs are first live
snapshot +1, normal settlement +71, strictly later snapshot +72, continuation
+98, quarantine/ledger publication +100, verdict +106 and decision boundary
+115. Equality is accepted only after the complete required transition has
settled; plus one nanosecond is terminal. Early completion moves no cutoff.

The 20-sample cross-language clock oracle accepts only
`p0 <= swift_sample <= p1` and `p1-p0 <= 50,000,000 ns`. This is a measured,
fail-closed sample acceptance criterion, not an operating-system scheduling
promise. Shared authority uses only Python
`time.clock_gettime_ns(time.CLOCK_MONOTONIC)` and Swift
`clock_gettime(CLOCK_MONOTONIC)`.

Zero-child publication is exact:

~~~text
0x10 + exclusive BrokerChildFreeLease evidence
-> CompleteTraceCandidate(empty trace, expected response bytes)
-> full response-line write
-> ResponsePublishedReceipt
-> CompleteTraceProof
-> acceptedSuccess/error
~~~

Child-bearing publication is exact:

~~~text
last BrokerSettledCommandReceipt
-> final helper 0x12 fully published
-> CompleteTraceCandidate(expected response bytes)
-> full response-line write
-> ResponsePublishedReceipt
-> CompleteTraceProof
-> acceptedSuccess/error
~~~

Response-bearing cancellation and operational errors use the same candidate,
write, receipt and proof. A partial/failed response consumes the candidate into
`protocolAbnormal`; it cannot mint a proof. Pre-accept and otherwise
response-free rows consume `NoResponseRequiredProof`. Settlement or `0x12` on
a true zero-child path is protocol error. Every path still requires exact EOFs
and helper/worker reap.

The public code/exit/response-presence table is independent and exact:

| Public code(s) | Exit | Response presence |
| --- | ---: | --- |
| `OK` | 0 | exact operation-specific six-key response |
| `INVALID_REQUEST` | 64 | none; pre-accept only |
| `CLEANUP_NOT_AUTHORIZED` | 64 | exact six-key response after accept |
| `PROTOCOL_ERROR` | 65 | exact six-key response iff stdout remains usable |
| `RANDOM_GENERATION_FAILED`, `HDIUTIL_FAILED`, `IMAGE_ENCRYPTION_INVALID`, `KEYCHAIN_ITEM_COLLISION`, `KEYCHAIN_ITEM_NOT_FOUND`, `KEYCHAIN_ITEM_AMBIGUOUS`, `KEYCHAIN_INTERACTION_FORBIDDEN`, `KEYCHAIN_SECRET_INVALID`, `KEYCHAIN_FAILED`, `MOUNT_MAPPING_INVALID`, `MOUNT_CLEANUP_UNCLEAR`, `INTERNAL_ERROR` | 70 | exact six-key response after accept |
| `SUPERVISION_UNRESOLVED` | 74 | exact six-key response iff stdout remains usable |
| `CANCELLED` | 75 | none pre-accept; exact six-key response post-accept |

Internal `PROCESS_*` facts are never public codes. Every post-accept non-OK
response has exact keys `schema_version`, `operation`, `code`,
`encryption_uuid=null`, `device=null`, `item_count=null`. OK results are create
`(uuid,null,1)`, mount `(uuid,device,1)`, detach `(uuid,device,null)`, inspect
`(uuid,null,1)` and delete `(uuid,null,0)`. Python compares all six values,
frame grammar, output EOFs, control EOF and exact reap.

## Observer, closure and open-unresolved progress

`ObserverTerminationOutcome` is exactly
`stopped(ObserverStoppedReceipt) | terminalFailure(ObserverTerminalFailureReceipt)`.
A stopped receipt requires the accepted final snapshot first, then full
52-byte STOP write and stdin flush/close, contiguous STOPPED, stdout/stderr
EOFs, reader joins, exit 0, exact
waitpid, one-shot post-reap token, `kill(-originalPGID,0)==ESRCH`, and every FD
closed. Every other STOP/snapshot/frame/EOF/join/exit/reap/group result records
the last proved step plus unknown facts and cannot mint disposition, close or
PASS.

The only proved-close order is:

~~~text
artifact disposition settled
-> every broker invocation retired
-> exclusive BrokerChildFreeLease plus empty broker registry
-> broker STOP, EOFs, exact reap, group ESRCH
-> final observer snapshot
-> observer STOP, EOFs, exact reap, group ESRCH
-> DispositionReceipt
-> CLOSED_PROVED
~~~

At +115 with any broker/orphan obligation, the session transitions to
`OPEN_UNRESOLVED`. No `DispositionReceipt`, broker STOP, observer STOP, close or
Python owner exit occurs. The registry mints one strong-identity, one-shot
`OpenUnresolvedHandle`, a closed in-flight predecessor arm. It authorizes only:

~~~text
nativeTerminalObserved
-> brokerProvedClose
-> observerFinalization
-> DispositionReceipt(locked non-PASS)
~~~

It authorizes no artifact, Keychain or ordinary effect and cannot close
directly. `SessionProgress` is exactly
`closed(DispositionReceipt) | openUnresolved(OpenUnresolvedHandle)`.

Verdict and closure are independent and monotone. Busy broker/orphan with a live
observer is `UNCLEAR/supervision_unresolved`; actual observer loss is
`UNCLEAR/observer_unavailable`; any latched SecurityAgent observation is
`FAIL/securityagent_detected`. Detection after +115 escalates UNCLEAR to FAIL.
Later proved close never restores PASS.

## Sealed Python authority and observer build

Every Python authority shell is frozen, slotted and `eq=False`, holding only a
private issuance object. Private registries retain all payload and compare with
`is`. Copy, field-equivalent construction, stale epoch, wrong registry/session,
wrong result/context or replay rejects before an effect. Generation overflow
closes issuance without wrap.

Preparation owns one `ArtifactCursor(noArtifact)`. It writes and hashes the
constant observer source bytes, typechecks, compiles and links a private
executable, checks regular executable type, records compiler identity/exact
argv/env/mode/device/inode plus measured source/binary digests, removes all
static-gate artifacts and proves zero residue. Static build and live-launch
functions are separate. The source digest is literal/reproducible; linked
binary identity is ephemeral for that build. The exact inode/digest is
revalidated immediately before spawn. No cross-build binary digest is claimed.
Replacement between link and revalidation rejects.

One persistent observer spans the first empty baseline, helper compilation,
second empty baseline, every live/continuation/disposition action and final
shutdown. Frames are u32be length plus canonical JSON, total at most 65,536,
with `CORTEX_S3_OBSERVER_V1`, READY/SNAPSHOT/STOPPED, contiguous checked
sequence, shared-clock scan timestamps and privacy-bounded tokens. Titles,
paths, environment, command lines and user text are never retained.

One FIFO lifecycle executor owns observations and effects. It reduces observer
and cancel/control readiness before helper completion in a shared batch. Every
ordinary or disposition effect first consumes a closed predecessor into an
`InFlightOperation`. Raw completion remains pending until the complete tuple,
all EOFs, exact reap and a strictly later observer scan. A terminal cause first
moves the record to terminal-pending and revokes ordinary success. Ambiguity is
a bounded, non-authorizing set that retains every possible ledger; none of its
members is selected as the successor.

The request builder emits exactly ten keys:

~~~text
schema_version, operation, image_path, mount_path, volume_name, size,
transaction_id, expected_encryption_uuid, disposable, cleanup_approved
~~~

All values come from the current registry context/grant. No live method accepts
caller path, device, operation or argv. Application-owned entropy, Master,
Wire and mutable Keychain staging use disjoint erasable storage. Wire is erased
before every outcome/frame; entropy, Master and staging are erased after their
single consumers. External framework/kernel/child copies are outside direct
erasure evidence.

## Independent model architecture

The independent lineage alphabet has exactly 22 symbols:

~~~python
PROCESS_EVENTS = (
    "spawn_valid", "validation_exact", "validation_failed",
    "resume_confirmed", "resume_nonconfirmed",
    "suspended_abort_nonexact", "suspended_abort_exact",
    "exact_child", "related_partial", "foreign_uid_bridge",
    "tracked_uid_changed", "tracked_sid_changed", "group_changed",
    "request_signal", "root_exit_exact", "exact_reap",
    "original_group_absent", "pipes_closed",
    "settlement_frame_published", "scan_incomplete", "late_child",
    "parent_birth_reused",
)
~~~

Depths 0..5 contain exactly 5,399,043 raw sequences. The lineage model is
independent of the native EFSM and has its own reference oracle.

The effect alphabet has exactly 24 symbols after adding
`prepare_mount_leaf` and `remove_mount_leaf`; depths 0..5 contain exactly
8,308,825 sequences. Its other semantic events cover activation, create,
mount, verification, detach/absence, two cycle advances, inspect, approved
Keychain/image cleanup, unapproved quarantine, terminal transfer, disposition,
unresolved preservation and close. Reducers return primitive unstamped actions;
the explorer attaches transition indices. Independent reference machines
compare complete action vectors and final primitive state without importing
implementation registries or permit types.

Long traces cover exact suspended/running settlement, worker loss and orphan
ACK, all one-shot replays, both artifact cycles, mount-leaf prepare/removal,
three Keychain presence variants, late open-unresolved close and one final
close. There is no exponential native-EFSM trace enumeration.

## Guardian/witness fixture and closed routes

Legacy routes remain absent. Testing compilation exposes only
`--test-scenario`, `--test-supervisor-scenario`,
`--guardian-witness-probe` and `--guardian-witness-child`. Production contains
no testing route literal or handler and rejects testing flags before effect.

The guardian fixture is deliberately non-suspended, creates no descendants,
arms a 2.50-second absolute self-expiry before START, observes guardian EOF and
closes witness on exit. Self-expiry is containment, never success. The sealed
bootstrap uses an absolute equipped interpreter, `-I -S -u -c`, exact FDs and
common environment plus only the parent hard deadline. Report validation
precedes one GO. `exec_status_w` alone is CLOEXEC; EOF proves direct
`os.execve`, preserving the registered `Popen.pid`. Failure emits exactly
`EXEC` plus u32be errno and reserved exit 127 for ENOENT, 126 otherwise.

The fixed schedule is +0.75 report, +1.50 work, +2.00 supervisor settlement,
+2.50 fixture self-expiry, +3.00 cleanup reserve and +5.00 parent hard stop.
Cleanup reserve allows only independent endpoint closes, authorized positive
PID TERM/KILL, exact waitpid, witness EOF and one capped in-process libproc
scan. PID count and byte capacity remain distinct; full buffer, growth,
identity change, malformed procargs, ESRCH/EPERM/ENOMEM or cap/error is not
absence. No process-spawning scanner is reachable.

The observer and fixture Swift sources are compiler/typechecked; observer also
links without launch. The fixture AST closure resolves every local call and
allows only predeclared Darwin leaves. Unknown/dynamic/spawn/fork/exec/shell or
dynamic-loading edges reject.

## Test inventory, mutants and closure

The final sets are exact:

| Set | Cardinality |
| --- | ---: |
| normative `R01..R45` | 45 |
| Task 1 `S3T1_01..S3T1_31` | 31 |
| Task 2 `S3T2_01..S3T2_45` | 45 |
| Task 3 `S3T3_01..S3T3_08` | 8 |
| Task 4 `S3T4_01..S3T4_157` | 157 |
| Task 5 `S3T5_01..S3T5_110` | 110 |
| separate `S3C4_01` | 1 |
| `ALL_TEST_IDS`, `ALL_MUTANTS`, `ORACLE_CLOSURE`, `MUTANT_MANIFEST` | 397 each |

Thus task-local IDs total 351 and global IDs total 397. Red policies are
exactly 364 `natural`, 26 `synthetic_gate` and seven
`baseline_characterization`. The characterization set is exactly `R45`,
`S3T4_07..S3T4_11` and `S3C4_01`. New activations are 120 runtime, 88 source
and 20 synthetic. `SWIFT_RUNTIME_CASES` remains exactly 41;
`SOURCE_MUTANT_TARGETS` is 123 total (35 existing plus 88 new).

Each manifest record freezes, before mutation, `owning_suite_test_ids`,
`expected_failure_test_ids` and `exclusivity_claim`. Expected failures are never
learned from output. The runner executes the entire frozen owning suite and
compares exact failure/error/skip/timeout/unexpected-success sets. Structural
atomicity is a separately named pre-frozen policy with its own oracle.

Manifest kinds are a closed union of `RuntimeMutant`, `SourceMutant` and
`SyntheticMutant`. A synthetic record contains exactly fixture builder ID,
builder source/closure SHA, transformation ID, private fixture-root contract,
cleanup/zero-residue contract, expected assertion label, policy and the three
pre-frozen suite fields. Target file/range/anchor and runtime selector are
structurally absent and reject if supplied. Its closure includes builder and
cleanup logic.

Owner completeness is independent:

~~~python
OWNER_SUITE[n] = bytewise_sorted(
    case for case in ALL_TEST_IDS if owner_for(case) == n
)
~~~

`S3C4_01` belongs to owner 4. Every manifest entry's owning suite equals the
full owner projection, never a selected or observed subset.

The non-executing Python semantic closure resolver starts from
`(path,qualname)` and covers reached module initializers, top-level symbol
mutations, class bodies, bases, metaclasses, MRO, executable annotations,
decorators/defaults, descriptors/properties, `super`, context managers,
iterators, operators, explicit imports, functions/methods and constants.
External leaves require a hashed literal allowlist. Star imports, unresolved
calls, dynamic attributes, `getattr`, globals/locals, eval/exec/importlib,
`__import__` and subscript callees reject. Cycles use `visited`; serialization
is sorted, domain-separated and non-recursive.

Every expected SHA field normalizes to exactly 64 ASCII zeroes before byte
ranges/offsets are computed. Populating real 64-hex digests leaves offsets
unchanged; variable-length placeholders reject. The two arithmetic mutants are
fixed: `S3T4_84/omit_stop_from_observer_total` produces and rejects
16,781,312; `S3T4_90/omit_admin_from_python_retained_total` produces and
rejects 20,975,668.

## Normative regression ownership

| IDs | Required boundary |
| --- | --- |
| R01-R05 | Only exact broker-settled attach facts mint one bound compensation detach and absence query. |
| R06-R10 | WNOWAIT identity, signal-permit, exact wait/reap and post-reap group rules reject wrong or missing native facts. |
| R11-R14 | Immutable invocation origin/class/cutoff; no stage resampling or one-nanosecond overrun. |
| R15-R25 | Terminal pre-observation, sealed operands, current cursor, in-flight ownership, two cycles, current-mapping continuation, Keychain-first cleanup and verdict priority. |
| R26-R32 | Independent lineage uncertainty for partial bridges, identity changes, late children and reused births. |
| R33-R35 | Permit-aware TERM/KILL order, KILL terminality and total suspended validation/resume cleanup. |
| R36-R39 | Complete response/frame/EOF/reap proof, no authority from valid-looking unresolved output, shared clock and secret erasure. |
| R40-R43 | Contained guardian/witness, FD inventories, cross-version suite and report-GO-exec/libproc fresh runs. |
| R44 | Every obsolete route literal, handler and test is absent before default suite selection. |
| R45 | Every authorization near miss constructs zero live objects; baseline characterization only. |

Task-local ownership and all 397 exact method/mutant rows are frozen in the
implementation plan. Task 1 additionally owns the 2,034 native EFSM assertions;
Task 2 owns broker/worker authority and publication; Task 3 owns invocation
class/provenance; Task 4 owns environments, protocol, mounts, observer,
open-unresolved and Python admin permits; Task 5 owns immutable review and
execution, manifests, semantic closure and final comparison.

## Non-circular review and immutable final tree

The first documentation review never executes candidate code. Each reviewer is
given the exact commit, four allowed paths and an external literal Git-plumbing
identity command whose exact bytes/SHA are part of the task. The reviewer uses
`ls-tree -z`, `cat-file -s` and streamed `cat-file blob` to verify one `100644
blob` per path, then reads both documents fully. Its canonical receipt binds
schema/profile/candidate, identity-command SHA, embedded-gate source SHA, every
path/mode/type/size/SHA tuple, axis, finding counts and verdict.

Only three matching `P0=P1=P2=0/PASS` receipts authorize extraction of the
single embedded `CORTEX_S3_DOC_GATE_V1` program. Its independently generated
four-blob package must be byte-identical to the external identities. Mixed
candidate/profile/manifest/gate/receipt pairs reject. Task 5 may reuse only the
approved gate SHA and its fixed five-path final profile.

Every Git identity subprocess uses exact `/usr/bin/git --no-replace-objects
--git-dir=<absolute validated gitdir>` under an empty environment containing
only the common map plus `GIT_NO_REPLACE_OBJECTS=1`,
`GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`. It inherits no HOME,
Git directory/worktree/object/alternate/config/replace variables. Hostile
commit/blob replacement refs and hostile configuration are synthetic negative
fixtures.

Before Task 1, `HEAD == IMPLEMENTATION_BASE == DOC_CANDIDATE`, the index is
empty, only the known unstaged `primer.md` diff exists, all four blobs and
manifest match three reviews, and approved-gate self-tests pass.

Before the real Task 5 commit, exactly the three implementation files are
staged, no worktree delta exists for them, and `S3_PRECOMMIT_TREE=git
write-tree` is frozen. An unreferenced temporary commit with that exact tree and
parent `TASK_5_BASE` is checked out in a private detached worktree. All final
GREEN/mutant/restored-GREEN receipts bind tree, temporary commit, ordinal,
case, phase, test, mutant, target blob, closure hash, interpreter, argv, result
and assertion label. CWD/PYTHONPATH/imports are restricted to the detached
tree; every project module resolves beneath it. Removal proves zero worktree
residue.

Commit occurs without restaging. Require `S3_FINAL^{tree} ==
S3_PRECOMMIT_TREE`, expected parent and exact receipt order. Then create a fresh
private detached worktree at exact `S3_FINAL` and rerun complete suites, every
mutant and Git-dependent gate with explicit repository/commit arguments.
Precommit receipts cannot substitute for final receipts. Only after these
postcommit checks may a five-path package and three fresh blind implementation
reviews begin.

## Compatibility

- Public response keys remain `schema_version`, `operation`, `code`,
  `encryption_uuid`, `device` and `item_count`.
- Stable codes, Keychain attributes, 43-character Base64URL public secret
  representation, no-UI queries and the strict ten-key request remain stable.
- The live class remains separately selected and requires fresh action-time
  authorization; default tests cannot select it.
- Models and harmless fixtures do not prove live Keychain, DiskImages,
  SecurityAgent or APFS behavior.
- This Revision 7 candidate still requires three fresh blind documentation
  reviews. It is not approved merely because its static gates pass.
