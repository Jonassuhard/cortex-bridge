# Cortex Bridge S3 Owned-Process Supervision Design

**Status:** Revision 4 review candidate; implementation remains frozen until
these exact spec and plan bytes receive three fresh blind read-only reviews
with `P0=0`, `P1=0`, `P2=0` and `PASS`
**Date:** 2026-09-04
**Reviewed baseline:** `db5a40f822c115b3f06b93a8d0c4ef04a74cd026`
**Target:** v0.5.4 candidate
**Supersedes:** the S3 supervision and live-harness design in the current Phase
S plan; unrelated storage requirements remain in force

## Decision

S3 replaces boolean cleanup, caller-constructed live operands and raw process
identifiers with four closed mechanisms:

1. a private final Swift supervisor whose signal authority is a
   registry-issued `RunningSessionAnchor` or
   `ExitedUnreapedSessionAnchor`;
2. a private `SuspendedChildAnchor` that is atomically consumed into running
   authority or positive-PID abort/reap, never both;
3. Python object-identity registries for every capability, baseline, artifact,
   receipt, grant and disposition proof, plus one serialized effect executor;
4. a total one-byte control DFA, independent exhaustive process/effect models,
   and one non-suspended, self-expiring guardian/witness fixture.

This revision is a design candidate, not implementation evidence. No live
Keychain, DiskImages, `hdiutil`, mount, detach, quarantine, SecurityAgent,
Chrome, runtime, push, merge, tag or release action is authorized by it.

## Trust boundary and exact claim

Production supervision is deliberately narrow:

- the child executable is fixed to `/usr/bin/hdiutil`;
- production spawn uses a new session and starts suspended;
- signal authority never consists of a PID, PGID or copied data structure;
- settlement requires exact leader observation and reap, one original-group
  absence observation, and closure of the child/request/output descriptors;
- `NativeSettlementProof` excludes the helper control socket;
- Python separately requires the expected final control frame, control EOF and
  exact helper reap before it classifies a completed helper exchange.

`NativeSettlementProof` proves only the original leader and original process
group facts observed by the native supervisor. It does not prove that an
intentionally escaping descendant cannot exist. An observed escape, incomplete
lineage scan, identity change, non-`ESRCH` group observation, failed close,
abnormal control EOF or abnormal helper exit yields `UNCLEAR` or an unresolved
outcome according to the boundary where it occurs.

The real guardian/witness fixture is intentionally different from production:
it is not suspended, executes immediately in its own session, and arms a
0.90-second absolute self-expiry before writing `START`. It exercises anchored
running/exited finalization only. It supplies no evidence for the production
suspended bootstrap; scripted kernel matrices are the only proof for that
bootstrap. The fixture exposes no watchdog, PID or PGID receipt.

## Goals

- Prevent raw PID, PGID and field-equivalent values from becoming authority.
- Keep the original leader waitable until the last permissible group signal.
- Revalidate a running leader using the complete
  `proc_bsdinfo -> getsid -> proc_bsdinfo` sandwich.
- Revalidate an exited leader with exact `waitid(WNOWAIT)` and reap it only by
  exact `waitpid`.
- Bind each Swift command, settlement and compensation permit to one private
  command context and one supervisor generation.
- Stop ordinary Python effects at the first terminal observation, including a
  Keychain result that returns after the latch.
- Permit post-terminal work only through the exact registered
  detach/absence/quarantine/disposition chain.
- Bound request input, control traffic, preparation, observation, child work,
  cleanup and response publication by absolute monotonic deadlines.
- Zero application-owned entropy, Master, Wire and mutable Keychain staging
  allocations at their defined lifetime boundaries.
- Replace legacy process probes with independent models and one bounded real
  fixture.
- Preserve the public response, strict ten-key request schema, stable error
  codes, Keychain schema and no-UI policy.

## Non-goals and residual assumptions

- No general macOS sandbox, Endpoint Security client, privileged broker,
  launch daemon or pidfd substitute.
- No supervision claim for arbitrary hostile executables.
- No atomic Darwin identity-and-signal primitive is claimed.
- No live proof of Keychain UI suppression, DiskImages behavior, APFS mount
  behavior or SecurityAgent completeness.
- No claim that a synchronous Keychain syscall already in flight is
  preemptible. Its late result cannot authorize a new effect or success.
- No claim that killing `hdiutil` eliminates a partial disk-image effect.
- No S4 implementation code in the S3 range.
- No weakening of timeout, authorization, cleanup or review gates.

## Component and file boundary

| File | S3 responsibility |
| --- | --- |
| `native/macos/disk_image_keychain.swift` | Public helper, strict request/control parsers, private final Darwin supervisor and registries, command provenance, erasure, testing-only scripted adapters and fixture routes. |
| `tests/disk_image_keychain_harness.py` | Private authority registries, sealed preparation/live session, serialized executor, receipt algebra, exact process adapter, control client and independent process/effect reducers. |
| `tests/test_disk_image_keychain_helper.py` | Independent reference machines, exhaustive and long traces, branch matrices, route/source gates, guardian/witness launchers, dynamic inventory and separately selected live class. |

Only those three files may change between `IMPLEMENTATION_BASE` and
`S3_FINAL`. This spec and its plan are committed before that range.

## Swift authority and lifecycle

### Private final owner and issuance registries

`OwnedProcessSupervisor` is a `private final class`. Every issuance registry it
owns is also a `private final class`. Each supervisor has an unexported strong
reference-identity object; tokens hold that private `RegistryIdentity` reference
and a private generation number. The reference remains alive while any token
exists, so neither deallocation nor allocator reuse can turn a stale identity
into a valid registry. Validation requires object identity (`===`), not an
`ObjectIdentifier` value. Exact PID, birth, UID, PGID, SID, command, descriptor
and consumption state remain solely in registry records.

The non-public authority types are:

~~~swift
private final class RegistryIdentity {
    fileprivate init() {}
}

private struct SuspendedChildAnchor {
    private let registryIdentity: RegistryIdentity
    private let generation: UInt64
}

private struct RunningSessionAnchor {
    private let registryIdentity: RegistryIdentity
    private let generation: UInt64
}

private struct ExitedUnreapedSessionAnchor {
    private let registryIdentity: RegistryIdentity
    private let generation: UInt64
}

private struct ReapedGroupObservationToken {
    private let registryIdentity: RegistryIdentity
    private let generation: UInt64
}

private struct NoActiveChildProof {
    private let registryIdentity: RegistryIdentity
    private let generation: UInt64
}

private enum SignalAnchor {
    case running(RunningSessionAnchor)
    case exited(ExitedUnreapedSessionAnchor)
}

private final class AnchorRegistry {
    private let identity = RegistryIdentity()
    private var nextGeneration: UInt64 = 1
    private var records: [UInt64: AnchorRecord] = [:]
    private let lock: NSLock
}

private final class CommandIssuanceRegistry {
    private let identity = RegistryIdentity()
    private var nextGeneration: UInt64 = 1
    private var records: [UInt64: CommandRecord] = [:]
    private let lock: NSLock
}

private final class ControlIssuanceRegistry {
    private let identity = RegistryIdentity()
    private var nextGeneration: UInt64 = 1
    private var records: [UInt64: ControlRecord] = [:]
    private let lock: NSLock
}

private final class OwnedProcessSupervisor {
    private let anchors: AnchorRegistry
    private let commands: CommandIssuanceRegistry
    private let controls: ControlIssuanceRegistry
    private let kernel: ProcessKernel
    private let io: ProcessIO
}
~~~

No token initializer or registry identity constructor is reachable outside the
private issuance file; an AST gate permits `RegistryIdentity()` only in the
private registry initializers. A forged, copied-and-replayed, stale,
cross-supervisor, cross-registry or consumed value is rejected while holding
the issuing registry lock and before any syscall. Copying a token preserves the
same strong private identity, never creates a second record, and therefore
loses to the first atomic consumption.

The control registry mints `NoActiveChildProof` only while the serialized
reducer holds its lock and its child table is empty. It is minted for a valid
cancel in `START` or `IDLE_ACCEPTED`, consumed by the one `0x13` transition, and
never contains or exposes a PID. A copied, stale or replayed proof writes no
frame and authorizes no effect.

### Suspended production bootstrap

Production uses exactly:

~~~text
POSIX_SPAWN_CLOEXEC_DEFAULT
POSIX_SPAWN_SETSID
POSIX_SPAWN_START_SUSPENDED
~~~

`POSIX_SPAWN_SETPGROUP` and `posix_spawnattr_setpgroup` are forbidden.
`spawnSuspendedSession` stores the positive PID and initial birth facts in the
registry and returns only `SuspendedChildAnchor`.

Under the same registry lock, exactly one transition may consume that anchor:

- `validateSuspendedIdentity` obtains two complete `proc_bsdinfo` records with
  `getsid(pid)` between them. Both must match stored PID, birth seconds, birth
  microseconds, effective UID and `processGroupID == pid`; the session must be
  the PID. Success consumes the suspended record and mints a
  `RunningSessionAnchor`.
- `abortAndReapSuspendedDirectChild` consumes the suspended record first, then
  performs only positive-PID abort and exact direct-child reap.

Validation and abort racing on the same anchor cannot both win. Invalid or
incomplete identity takes only the abort branch and issues no group signal,
SIGCONT or child input. A stale/cross-registry anchor performs no syscall.

### Non-suspended fixture bootstrap

The testing-only guardian/witness route uses
`POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSID` and never
`POSIX_SPAWN_START_SUSPENDED`. The fixture runs immediately, installs its
absolute 0.90-second self-expiry, then writes `START:<nonce>`.

The test-only spawn adapter keeps the positive PID private, performs the same
complete birth/UID/PGID/SID observation, and mints a `RunningSessionAnchor`
only for that exact running direct child. Failure to mint it permits only
positive-PID direct-child cleanup. Once minted, production and fixture paths
share the same running, exited, reap, group-absence and descriptor-finalization
reducers. The fixture never receives SIGCONT and is not evidence for
suspended-child validation.

### Closed kernel and I/O contracts

~~~swift
private protocol ProcessKernel {
    func spawnSuspendedSession(
        _ request: SpawnRequest,
        deadline: MonotonicInstant
    ) -> SpawnResult
    func validateSuspendedIdentity(
        _ anchor: SuspendedChildAnchor,
        deadline: MonotonicInstant
    ) -> IdentityResult
    func resumeSuspended(
        _ anchor: RunningSessionAnchor,
        deadline: MonotonicInstant
    ) -> ResumeResult
    func observeExitWithoutReaping(
        _ anchor: RunningSessionAnchor,
        deadline: MonotonicInstant
    ) -> ExitObservation
    func signalOwnedGroup(
        _ signal: TerminationSignal,
        anchoredBy anchor: SignalAnchor,
        deadline: MonotonicInstant
    ) -> SignalResult
    func reapObservedChild(
        _ anchor: ExitedUnreapedSessionAnchor,
        deadline: MonotonicInstant
    ) -> ReapResult
    func observeGroupAfterReap(
        _ token: ReapedGroupObservationToken,
        deadline: MonotonicInstant
    ) -> GroupPresence
    func abortAndReapSuspendedDirectChild(
        _ anchor: SuspendedChildAnchor,
        deadline: MonotonicInstant
    ) -> SuspendedAbortResult
}

private protocol ProcessIO {
    func poll(_ request: PollRequest, deadline: MonotonicInstant) -> PollResult
    func read(
        _ descriptor: OwnedDescriptor,
        limit: Int,
        deadline: MonotonicInstant
    ) -> IOResult
    func write(
        _ descriptor: OwnedDescriptor,
        bytes: UnsafeRawBufferPointer,
        deadline: MonotonicInstant
    ) -> IOResult
    func close(
        _ descriptor: inout OwnedDescriptor,
        deadline: MonotonicInstant
    ) -> CloseResult
}
~~~

The result enums are closed. Scripted tests cover every member:

| Result | Closed members | Sole advancing members |
| --- | --- | --- |
| `SpawnResult` | `spawned(SuspendedChildAnchor)`, `refused`, `deadlineExpired`, `failed` | `spawned` |
| `IdentityResult` | `exact(RunningSessionAnchor)`, `incomplete`, `changed`, `unavailable`, `deadlineExpired` | `exact` |
| `ResumeResult` | `resumed`, `childGone`, `identityChanged`, `deadlineExpired`, `interruptedAtDeadline`, `failed` | `resumed` |
| `ExitObservation` | `running`, `exactExited(ExitStatus, ExitedUnreapedSessionAnchor)`, `wrongPID`, `wrongSignal`, `wrongCode`, `interrupted`, `deadlineExpired`, `failed` | `running`, `exactExited` |
| `SignalResult` | `delivered`, `alreadyAbsent`, `identityChanged`, `notWaitable`, `permissionDenied`, `deadlineExpired`, `interruptedAtDeadline`, `failed` | `delivered`; `alreadyAbsent` only for exact exited authority |
| `ReapResult` | `exactlyReaped(ReapedGroupObservationToken)`, `stillRunning`, `noChild`, `wrongPID`, `deadlineExpired`, `interruptedAtDeadline`, `failed` | `exactlyReaped` |
| `GroupPresence` | `absentESRCH`, `present`, `permissionDenied`, `deadlineExpired`, `interruptedAtDeadline`, `failed` | `absentESRCH` |
| `PollResult` | `ready`, `timedOut`, `interrupted`, `deadlineExpired`, `failed` | `ready`; bounded retry for timeout/interruption |
| `IOResult` | `bytes`, `endOfFile`, `wouldBlock`, `interrupted`, `brokenPipe`, `deadlineExpired`, `failed` | positive bytes/EOF in valid position; bounded EAGAIN/EINTR retry |
| `CloseResult` | `closed`, `alreadyClosed`, `interruptedStateUnknown`, `deadlineExpired`, `failed` | `closed`, `alreadyClosed` |
| `SuspendedAbortResult` | `exactlyReaped`, `stillRunning`, `noChild`, `wrongPID`, `deadlineExpired`, `failed` | `exactlyReaped` |

The lifecycle is monotone:

~~~text
production: prepared -> suspended -> running -> exited-unreaped -> reaped
fixture:    prepared -------------> running -> exited-unreaped -> reaped
both:       reaped -> original-group-absent -> native-descriptors-closed
            -> wire-erased -> NativeSettlementProof
any unresolved observation -> unresolved, permanently
~~~

A running anchor is revalidated immediately before SIGCONT, TERM and KILL.
An exited anchor is observed before TERM, KILL and exact reap by
zero-initialized `waitid(P_PID, pid, WEXITED | WNOHANG | WNOWAIT)`. It must
return the exact PID, `SIGCHLD`, and `CLD_EXITED`, `CLD_KILLED` or
`CLD_DUMPED`. Only exact `waitpid == pid` reaps and consumes the anchor;
`waitid(WNOWAIT)` never reaps. `getsid` is not called after exact exit, so
`getsid == ESRCH` for a zombie is not treated as an identity failure.

Exact `waitpid == pid` consumes the exited anchor and mints one
`ReapedGroupObservationToken`. `observeGroupAfterReap` consumes that token
before the sole negative-PGID signal-zero observation. TERM/KILL and signal
zero are separate private adapter methods; no `killpg` or other negative target
is allowed. KILL is terminal for group-signal issuance.

### Drain, settlement and control exclusion

The supervisor checks the absolute hard deadline before and after every poll,
read, write, append, identity observation, signal, reap and close. Control
readiness wins simultaneous readiness. Production stdout and stderr are capped
independently at 1 MiB. The drain loop never reaps.

Every failure latches unresolved permanently. Every owned descriptor is still
closed independently after another close fails. The native-settlement close
set is exact:

- helper request-input descriptor after bounded EOF and request erasure;
- child stdin;
- child stdout after EOF/cap validation;
- child stderr after EOF/cap validation.

The helper control socket is explicitly excluded. `NativeSettlementProof` is
issued only after exact leader reap, one `absentESRCH` observation for the
original group, all four native-settlement descriptors closed or already
closed, complete bounded outputs, no latched unresolved fact, and Wire
erasure. Its constructor is private.

Only after that issuance may Swift write the matching `0x12`. If cancellation
is already latched, it immediately follows that child-settlement frame with the
sole terminal `0x13`; it never suppresses the child's required `0x12`. Swift
then shuts down and closes its control endpoint independently. A failed control
close cannot be encoded in a later frame. Python therefore accepts neither a
proof-bearing frame nor helper exit alone: it requires valid frame order,
control EOF and exact helper reap. Abnormal/missing EOF, wrong helper exit, or
a missing final frame is `UNCLEAR`.

## Helper request, control and deadline boundary

### Exact production invocation and descriptor inventory

The production helper accepts exactly:

~~~text
disk-image-keychain --control-fd DECIMAL_FD --swift-hard-deadline-ns DECIMAL_NS
~~~

Decimal operands use ASCII digits only, have no sign or whitespace, reject a
leading zero except the single digit zero, and fit the target integer. Python
creates a CLOEXEC Unix stream socket. The only production spawn shape is:

~~~python
subprocess.Popen(
    argv,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    close_fds=True,
    pass_fds=(control_fd,),
    start_new_session=True,
)
~~~

Python closes the child socket endpoint immediately after successful spawn and
both endpoints on spawn failure. Before reading request bytes, Swift proves
the inherited FD is open, non-stdio, unique, connected, `AF_UNIX`,
`SOCK_STREAM`, and then sets `FD_CLOEXEC | O_NONBLOCK`. A bounded
`PROC_PIDLISTFDS` inventory must equal stdin, stdout, stderr and control for
production. The fixture route additionally admits only named guardian and
witness FDs. Missing, duplicate, regular-file, wrong-family, wrong-type,
incomplete or extra descriptors reject before request read, child creation or
write.

### Deadline validation before request read

Python forms the live deadlines after sealed preparation and a successful
bounded baseline:

~~~python
live_started_ns = time.monotonic_ns()
outer_hard_ns = checked_add_u64(live_started_ns, 115_000_000_000)
pre_observation_hard_ns = checked_add_u64(live_started_ns, 1_000_000_000)
swift_epoch_ns = time.monotonic_ns()
swift_hard_ns = checked_add_u64(swift_epoch_ns, 70_000_000_000)
outer_swift_limit_ns = checked_sub_u64(outer_hard_ns, 44_000_000_000)
assert swift_hard_ns <= outer_swift_limit_ns
~~~

Swift reads its clock once for admission and, before any request byte, checks
with overflow-safe arithmetic:

~~~text
now < swift_hard_ns
swift_hard_ns - now <= 70_000_000_000
swift_hard_ns >= 70_000_000_000
swift_epoch_ns = swift_hard_ns - 70_000_000_000
swift_epoch_ns <= now
~~~

Failure of any check rejects with zero request read, spawn or child write.
Tests cover `now + 70s + 1ns`, `UInt64.max`, subtraction underflow, addition
overflow, future derived epoch and a valid but phase-too-close deadline. The
last case passes arithmetic validation but fails the relevant phase-admission
fit before effect. Swift never computes a replacement epoch or extends the
received deadline.

The absolute phase boundaries from `swift_epoch_ns` are:

| Phase | Admission/hard stop | Reserved finalization |
| --- | --- | --- |
| create, attach, validation | fit before 36 s; stop 36 s | command work plus 6 s |
| attach receipt transition | stop 38 s | no child |
| compensation detach | admit through 38 s if full fit; stop 52 s | 8 s plus 6 s |
| detach/absence transition | stop 54 s | no child |
| absence info | admit through 54 s if full fit; stop 66 s | 6 s plus 6 s |
| response, erasure, close | stop 70 s | no new child |

Equality is admitted only when the complete phase budget still fits; one
nanosecond later refuses. No phase borrows from another. These boundaries apply
only to the original live helper's ordinary and receipt-compensation work; they
do not authorize a terminal continuation. The outer 115 seconds reserve
1 second initial observation, 70 seconds for the original live Swift
helper, 1 second final observation, 14 seconds for one receipt-bound detach
continuation, 12 seconds for one receipt-bound absence continuation, 2 seconds
descriptor quarantine/ledger publication, 6 seconds exact helper cleanup,
5 seconds scheduler/process margin and 4 seconds unallocated margin.

### Post-terminal continuation deadlines

The original live Swift helper never receives more than its original
70-second hard deadline and never borrows the outer continuation reserve.
After its valid final frame, control EOF and exact helper reap, Python may
launch a fresh Swift helper only from sealed disposition lineage:

| Continuation | Required sealed predecessor | Fixed new hard deadline | Refusal |
| --- | --- | --- | --- |
| detach | `DispositionStartReceipt(mounted)` | `now + 14 s`, only if checked addition fits within immutable `outer_hard_ns` | mint `PreservationReceipt(unresolved)`; zero spawn |
| absence | exact settled disposition `DetachCommandReceipt` | `now + 12 s`, only if checked addition fits within immutable `outer_hard_ns` | mint `PreservationReceipt(unresolved)`; zero spawn |

Each continuation receives the same production argv shape and independently
passes the pre-request deadline validator. Its sealed continuation context
selects only the exact detach or absence command and uses the received hard
deadline directly for its fixed 14- or 12-second admission/finalization
budget. The validator still derives `swift_epoch_ns = hard - 70 s` solely with
checked arithmetic to reject malformed/future values; a continuation never
uses that derived value to create a new phase origin, reset a deadline or extend
the outer envelope. No raw continuation operand, request field or caller path
can select this mode. Python launches no new Swift helper after an insufficient
fit, an unresolved predecessor, abnormal control EOF, wrong helper exit or a
missing terminal frame.

### Bounded request reader

`BoundedRequestReader` polls request input and control against the transmitted
deadline, prioritizes control, caps input at 65,536 bytes, requires EOF before
JSON parsing, and erases its mutable buffer on every exit. `readDataToEndOfFile`
is forbidden. EAGAIN and EINTR retry only while the same deadline remains.
Partial input, cap overflow, poll/read failure and deadline expiry never parse
or spawn.

Strict rejection before `0x10` exits with no effect and no control frame.
Valid cancellation in `START` produces `0x13` with a registry-issued
`NoActiveChildProof`. No cancellation or parse path may derive a new deadline.

### Total control DFA

Frames are exactly one byte:

| Direction | Byte | Meaning |
| --- | --- | --- |
| Python to Swift | `0x01` | Latch cancellation once. |
| Swift to Python | `0x10` | Strict request and deadline accepted; no child active. |
| Swift to Python | `0x11` | One exact child anchor is active. |
| Swift to Python | `0x12` | That child obtained `NativeSettlementProof`. |
| Swift to Python | `0x13` | Valid cancellation settled with no active child or with native proof. |
| Swift to Python | `0x14` | Native child/group/descriptor settlement is unresolved, whether or not cancellation was requested. |

States are exactly `START`, `IDLE_ACCEPTED`, `ACTIVE`, `TERMINAL` and
`NORMAL_EXIT`. `NORMAL_EXIT` retains one private, immutable
`NormalExitKind`: `strictRejected`, `acceptedNoChild` or
`protocolAbnormal`. The state is therefore total without conflating an
accepted harmless completion with a malformed exchange. The transition
function is total:

| State/input | Transition and output |
| --- | --- |
| `START` + valid request | `IDLE_ACCEPTED`, emit one `0x10`. |
| `START` + valid cancel | `TERMINAL`, emit one `0x13`, close control. |
| `START` + reject/unknown/duplicate/EOF | `NORMAL_EXIT(strictRejected)`, exit 64, no frame and no effect. |
| `START` + EAGAIN/EINTR | Stay while time remains; expiry goes `NORMAL_EXIT(strictRejected)`, exit 64, no frame. |
| `IDLE_ACCEPTED` + admitted child | `ACTIVE`, emit one `0x11`. |
| `IDLE_ACCEPTED` + accepted no-child completion | `NORMAL_EXIT(acceptedNoChild)`, exit 0; `0x10` is the last valid frame. |
| `IDLE_ACCEPTED` + cancel after zero or any settled pairs | `TERMINAL`, emit one `0x13`. |
| `IDLE_ACCEPTED` + unknown/duplicate/EOF/out-of-order | `NORMAL_EXIT(protocolAbnormal)`, exit 65, no additional frame. |
| `IDLE_ACCEPTED` + EAGAIN/EINTR | Stay while time remains; expiry is `NORMAL_EXIT(protocolAbnormal)`, exit 65. |
| `ACTIVE` + native settlement | `IDLE_ACCEPTED`, emit matching `0x12`. |
| `ACTIVE` + cancel then native settlement | Emit matching `0x12`, return through `IDLE_ACCEPTED`, then immediately enter `TERMINAL` and emit one `0x13`. |
| `ACTIVE` + cancel then unresolved finalization | `TERMINAL`, emit one `0x14`. |
| `ACTIVE` + unresolved without cancel | `TERMINAL`, emit one `0x14`. |
| `ACTIVE` + unknown/duplicate/EOF/out-of-order | Finalize; native failure emits `0x14`, otherwise `NORMAL_EXIT(protocolAbnormal)` with exit 65 and no cancellation frame. |
| `ACTIVE` + EAGAIN/EINTR | Stay while time remains; deadline finalizes to `0x14` if native settlement is unresolved. |
| `TERMINAL` + any byte/readiness/replay | No effect, frame or state change; close only. |
| `NORMAL_EXIT` + any byte/readiness/replay | Preserve `NormalExitKind`; no effect, frame or state change. |

Each active child has exactly one `0x11` and either one `0x12` settlement or a
sole terminal `0x14`. Cancellation after a narrow active-child settlement emits
that required `0x12` and then one `0x13`. Mount may produce two settled child
pairs before normal exit. Tests cover cancel after the first and second pair,
accepted no-child inspect/delete, not-spawned work, unresolved work without
cancel, helper exit in every state, EOF, EAGAIN, unknown, duplicate and
out-of-order bytes, and replay after both terminal states.

Python considers the helper protocol complete only when the operation-specific
last frame is valid, control EOF follows it, and the exact helper PID is reaped.
For normal child work the last frame is its final `0x12`; for accepted no-child
work it is `0x10` with `NormalExitKind.acceptedNoChild` and exit 0; for
cancellation it is `0x13` or `0x14`. A strict rejection is distinguishable as
no frame plus `NormalExitKind.strictRejected` and exit 64. Missing or abnormal
control EOF, wrong helper exit, missing terminal frame, wrong PID, an
`acceptedNoChild` exit mismatch, or `NormalExitKind.protocolAbnormal` is
`UNCLEAR`.

## Swift command provenance and secret scope

### Closed commands and single-use issuance

`HdiutilCommand` is a closed enum:

~~~swift
private enum InfoPurpose: Equatable {
    case baseline
    case validation
    case postDetachAbsence
}

private enum HdiutilCommand: Equatable {
    case create(image: String, volume: String, size: String, transaction: UUID)
    case attach(image: String, mount: String, transaction: UUID)
    case detach(device: String, image: String, mount: String, transaction: UUID)
    case info(image: String, mount: String, transaction: UUID, purpose: InfoPurpose)
    case isEncrypted(image: String, transaction: UUID)
}
~~~

The private command registry stores the enum, fixed `/usr/bin/hdiutil`, exact
argv, stdin policy, absolute phase, supervisor identity and invocation
generation. `SettledInvocation` exposes complete bounded stdout/stderr and exit
status but retains command context and `NativeSettlementProof` privately.

`issueAttachCompensationPermit` accepts only the exact settled attach, complete
output and one parsed device whose mount equals the registered context. The
device cannot be caller-supplied. Consuming it constructs the one exact detach.
`issueAbsenceQueryPermit` accepts only that exact settled detach and constructs
the one exact post-detach info query. Absence succeeds only on settled complete
output with zero matching devices and zero image entries.

All command permits reject copied replay, stale generation, cross-supervisor,
wrong command, wrong result, wrong image/mount/transaction/device or unresolved
settlement before spawn. `notSpawned` and `unresolved` expose no parseable
authority and close the enclosing request against later invocation.

### Application-controlled secret lifetime

Entropy staging, `MasterSecret`, `WireSecret` and mutable Keychain staging are
distinct application-owned erasable allocations. Their ranges never overlap.
No `String`, immutable `Data` or general `[UInt8]` owns secret bytes in the
application path.

Each child gets a fresh Wire copy. Wire is zeroed before every outcome,
settlement/control frame, error, close and return. Create Master remains live
exactly through `SecItemAdd` and is then zeroed on success or failure. Mount
Master is zeroed after its attach outcome. Entropy and mutable Keychain staging
are zeroed immediately after their sole consumer. Erasure failure is unresolved
and cannot emit success or `0x13`.

This proof scope is honest: copies internal to Security.framework, Keychain,
the kernel or a child process are opaque and outside direct zeroization
evidence.

## Python sealed live boundary

### Registry-minted roots only

The exact gate requires flags `--integration` and `--allow-effects`, each once,
and environment key `CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION` with exact
value `YES_DISPOSABLE_64_MIB_ONLY`. Optional `--cleanup-approved` is captured
inside the preparation registry. Missing, duplicate, prefix, suffix, wrong-case
or old-alias flags/keys/values reject with exit 64, empty streams and zero
observer/live object construction.

Every authority-bearing Python value is a frozen, slotted, identity-only shell:

~~~python
@dataclass(frozen=True, slots=True, eq=False)
class PreparationCapability:
    _issuance_id: object

@dataclass(frozen=True, slots=True, eq=False)
class LiveExecutionCapability:
    _issuance_id: object

@dataclass(frozen=True, slots=True, eq=False)
class ArtifactContext:
    _issuance_id: object

@dataclass(frozen=True, slots=True, eq=False)
class CommandReceipt:
    _issuance_id: object
~~~

The same shape is mandatory for `ObserverBaseline`,
`SecurityAgentSnapshot`, `TerminalEventReceipt`, `DispositionStartReceipt`,
`CreateCommandReceipt`, `MountCommandReceipt`, `MappingCommandReceipt`,
`DetachCommandReceipt`, `AbsenceCommandReceipt`, `CleanupGrant`,
`PreTerminalUnmountedProof`, `DetachedUnmountedProof`, `DetachPermit`,
`AbsencePermit`, `QuarantinePermit`, `QuarantineReceipt`,
`PreservationReceipt` and `DispositionReceipt`. Private final-style registry
classes own fresh `object()` issuance keys and all payload. Validation uses
`is`, not value equality.

Each root is minted by exactly one registry in one session epoch. A
field-equivalent shell, shallow/deep copy, wrong command/result/device, wrong
session/epoch/registry, stale issuance, unresolved receipt or replay rejects
under the registry lock before any effect.

### One-shot preparation and fixed artifacts

The parser can mint one `PreparationCapability`. Its registry record fixes:

- the reviewed Swift source path and expected source SHA-256;
- a private temporary helper target beneath the ignored SDD directory;
- the exact embedded observer Swift source and private temporary target;
- whether cleanup was explicitly approved.

`PreparationSession.compile_helper()` and
`PreparationSession.prepare_observer()` take no paths or argv. Each consumes a
finite portion of one 30-second absolute preparation deadline and uses the
exact Python running/exited/waitid/waitpid supervision contract. Observer
preparation compiles the reviewed source, captures the fixed baseline, and
registry-mints `ObserverBaseline` only when both process/window collections are
complete and empty.

Only after both preparations and baseline validation may the registry consume
the preparation capability and mint one `LiveExecutionCapability` and one
`ArtifactContext`. The 115-second live deadline begins then, not before or
during compilation. No caller-controlled path, target, request field, command
or argv enters either preparation or live issuance.

The `ArtifactContext` registry record contains the generated transaction UUID,
image leaf `CORTEX_BRIDGE_SPIKE_<32 lowercase hex>.sparsebundle`, mount path
`mount-<same 32 lowercase hex>`, volume `CORTEX_BRIDGE_SPIKE`, size `64m`,
filesystem `APFS`, disposable true and the expected encryption UUID once
created. At issuance, the registry captures the private parent directory's
device, inode, mode and UID through its no-follow descriptor. Settled create
then captures the image leaf's device, inode, mode and UID through that same
parent descriptor and stores those facts only in `CreateCommandReceipt`. A
later mount receipt carries the same sealed image facts. No caller supplies,
recomputes or string-resolves any quarantine identity fact.

### Serialized executor and no free operands

One session-owned executor/lock serializes every observation and effect. Its
linearization interval covers, without releasing the lock:

1. terminal-latch and capability revalidation;
2. absolute-deadline and phase-admission check;
3. exact registry lookup of context and predecessor receipt;
4. `Popen` creation;
5. running-handle registration;
6. authorization of the first stdin/control write.

Deterministic interleavings place the terminal latch before and after each
boundary and prove no spawn or first write crosses the latch. A synchronous
Keychain call already in flight may finish, but the result is registered only
as terminal evidence and cannot mint a receipt, authorize another effect or
produce success.

The complete callable catalogue has no raw live path/device/operation operand:

| Method | Exact producer/result |
| --- | --- |
| `PreparationSession.compile_helper()` | Fixed compile receipt in preparation registry. |
| `PreparationSession.prepare_observer()` | Fixed observer baseline and typechecked observer artifact. |
| `EffectSession.create_image(context)` | `CreateCommandReceipt`. |
| `EffectSession.mount_image(context, create)` | `MountCommandReceipt` containing the exact complete create command receipt and mount evidence. |
| `EffectSession.detach_normal(mount)` | `DetachCommandReceipt`. |
| `EffectSession.inspect_item(create)` | Exact registered `CommandReceipt`. |
| `EffectSession.delete_item(create, grant)` | Exact registered delete receipt. |
| `EffectSession.probe_encryption(create)` | Exact fixed isencrypted receipt. |
| `EffectSession.probe_disk(mount)` | Exact fixed diskutil receipt. |
| `EffectSession.probe_mapping(mount)` | `MappingCommandReceipt`. |
| `EffectSession.prove_preterminal_unmounted(mapping)` | `PreTerminalUnmountedProof`. |
| `EffectSession.observe_terminal_snapshot()` | Registry-minted `SecurityAgentSnapshot` from fixed observer evidence only. |
| `EffectSession.latch_terminal(snapshot)` | Consumes exact terminal `SecurityAgentSnapshot` and mints `TerminalEventReceipt`. |
| `EffectSession.begin_disposition(event)` | Consumes `TerminalEventReceipt` and mints `DispositionStartReceipt`; no effect. |
| `EffectSession.detach_permit(start)` | Single-use `DetachPermit` from sealed mounted lineage. |
| `EffectSession.detach_for_disposition(permit)` | `DetachCommandReceipt`. |
| `EffectSession.absence_permit(detach)` | Single-use `AbsencePermit`. |
| `EffectSession.prove_absence_for_disposition(permit)` | `AbsenceCommandReceipt`. |
| `EffectSession.detached_unmounted_proof(absence)` | `DetachedUnmountedProof`. |
| `EffectSession.preterminal_quarantine_permit(start)` | Single-use `QuarantinePermit` from sealed preterminal-unmounted lineage. |
| `EffectSession.quarantine_permit(proof)` | Single-use `QuarantinePermit` from sealed detached lineage. |
| `EffectSession.quarantine_for_disposition(permit)` | `QuarantineReceipt`. |
| `EffectSession.preserve_for_disposition(start)` | `PreservationReceipt` for no-artifact, create-only, mapping-unknown or unresolved lineage. |
| `EffectSession.finalize_disposition(outcome)` | `DispositionReceipt` from `QuarantineReceipt` or `PreservationReceipt`. |
| `EffectSession.close(disposition)` | Final verdict; this is the only `close` signature. |

There is no public `record_mount`, generic runner, mapping request, public argv,
`safety_only` or `disposition_active` switch.

### Exact ten-key request value matrix

Private builders emit exactly these keys:

~~~text
schema_version, operation, image_path, mount_path, volume_name, size,
transaction_id, expected_encryption_uuid, disposable, cleanup_approved
~~~

Every value comes from the method and registered `ArtifactContext` or approved
grant. Current global validation rules are preserved:

| Method | Exact `operation` | `expected_encryption_uuid` | `cleanup_approved` | Other seven registered values |
| --- | --- | --- | --- | --- |
| create | `create` | null | false | schema 1; registered image/mount/volume `CORTEX_BRIDGE_SPIKE`/size `64m`/transaction; disposable true |
| mount | `mount` | exact UUID from create | false | same registered values |
| detach | `detach` | exact UUID from create | false | same registered values |
| inspect | `inspect-item` | exact UUID from create | false | same registered values |
| delete | `delete-disposable-item` | exact UUID from create | true from consumed cleanup grant | same registered values |

`mount_path`, `volume_name` and `size` remain populated for all five
operations because the current helper validates them globally. Operation and
cleanup are never caller fields. Production size `256g`, volume
`CORTEX_BRIDGE_2026_09` and disposable false remain outside this fixture and
are not changed by S3.

### Receipt algebra and terminal disposition

`EffectSession` states are:

~~~text
PREPARING -> ACTIVE -> CLOSED
                 \-> TERMINAL -> DISPOSING -> CLOSED
~~~

The fixed observer bridge alone mints a terminal `SecurityAgentSnapshot` from
either complete SecurityAgent detection evidence or the closed
`observer_unavailable` observation result; no caller constructs a terminal
event. `latch_terminal(snapshot)` consumes that exact snapshot under the
session executor lock, sets `observerTerminalLatchedAt`, increments the session
epoch and revokes ordinary authority. In the same critical section it atomically
consumes any eligible active `MountCommandReceipt` or
`PreTerminalUnmountedProof` and re-mints its non-forgeable facts as one private
disposition lineage inside `TerminalEventReceipt`. No post-terminal method
accepts the old active token as an exception. SecurityAgent determines
`FAIL securityagent_detected` if ever observed; otherwise observer failure
determines `UNCLEAR observer_unavailable`. Cleanup errors remain secondary.

`begin_disposition(event)` consumes that exact terminal receipt and mints one
`DispositionStartReceipt`. Its private lineage kind is exactly one of
`no_artifact`, `create_only`, `mounted`, `preterminal_unmounted`,
`mapping_unknown` or `unresolved`. The source roots are already consumed at
the terminal latch, so a copied pre-terminal mount/proof cannot race, replay or
bypass the new disposition epoch.

Receipt producers and controlled consumers are exact. A consultation only
looks up immutable registry payload and cannot mint a permit, derivative,
capability, command or disposition; an effect-consuming rule atomically claims
the named one-shot slot before an effect.

| Registry-minted value | Exclusive producer | Effect-consuming rule; permitted consultation |
| --- | --- | --- |
| `NoActiveChildProof` | total control reducer under its lock after proving the active-child table empty | one `0x13` cancellation transition |
| `SecurityAgentSnapshot` | fixed observer bridge's complete detection evidence or closed `observer_unavailable` result | `latch_terminal` once; no caller-built snapshot |
| `TerminalEventReceipt` | `latch_terminal` after consuming the exact terminal snapshot and transferring active lineage | `begin_disposition` once |
| `DispositionStartReceipt` | `begin_disposition` | exactly one of `detach_permit` for `mounted`, `preterminal_quarantine_permit` for `preterminal_unmounted`, or `preserve_for_disposition` for `no_artifact`/`create_only`/`mapping_unknown`/`unresolved` |
| `CreateCommandReceipt` | settled `create_image`, including sealed image identity facts | one named derivative slot each for mount, allowed probe, inspect or approved delete; immutable consultation validates matching context only |
| `MountCommandReceipt` | settled `mount_image`; includes complete create receipt plus exact UUID/device/image/mount/transaction evidence | while ACTIVE, one named normal-detach or mapping slot; at terminal latch, one atomic transfer slot into `TerminalEventReceipt`; immutable consultation cannot fork either |
| `MappingCommandReceipt` | settled `probe_mapping` | one `prove_preterminal_unmounted` slot; unknown result consumes no further effect slot |
| `CommandReceipt` | settled exact `inspect_item`, `delete_item`, `probe_encryption` or `probe_disk` command in the current registry epoch | immutable same-session evidence ledger only; it has no effect-consuming derivative |
| `PreTerminalUnmountedProof` | exact registered mapping with zero device/image match | at terminal latch, one atomic transfer slot into `TerminalEventReceipt`; while active it cannot cross an epoch by consultation |
| `CleanupGrant` | one active issuance from cleanup-approved capability | exact delete builder once |
| `DetachPermit` | `DispositionStartReceipt` with mounted lineage | `detach_for_disposition` once |
| `DetachCommandReceipt` | exact disposition detach from `DetachPermit` | `absence_permit` once |
| `AbsencePermit` | exact disposition detach receipt | one exact post-detach info command |
| `AbsenceCommandReceipt` | settled bound absence query with zero matching device/image | `detached_unmounted_proof` once |
| `DetachedUnmountedProof` | exact absence receipt | `quarantine_permit` once |
| `QuarantinePermit` | sealed preterminal or detached disposition lineage | descriptor-relative quarantine once |
| `QuarantineReceipt` | exact quarantine rename, identity revalidation and independent close completion | `finalize_disposition` once |
| `PreservationReceipt` | `preserve_for_disposition` from a non-quarantine lineage | `finalize_disposition` once |
| `DispositionReceipt` | registry reduction over one `QuarantineReceipt` or `PreservationReceipt` plus exact terminal ledger | `close` once |

Every terminal lineage is total. Terminal before create produces a
`PreservationReceipt(no_artifact)`; terminal after create without mount produces
`PreservationReceipt(create_only)` with the sealed artifact ledger; a
mapping-unknown or unresolved lineage produces a preservation receipt without
information query, inspect, delete or quarantine. Mounted lineage may run only
the exact detach/absence/quarantine chain; preterminal-unmounted lineage may
run only descriptor-relative quarantine. Each branch then mints
`DispositionReceipt` and is consumed by `close`. After terminal, ordinary
compile/create/mount/detach, probes, inspect and delete are forbidden.

### Descriptor-relative quarantine

Quarantine never uses `Path.rename`, string-resolved absolute rename or an
absolute fallback. It:

1. opens the registered parent using
   `O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_DIRECTORY`;
2. opens the registered image leaf relative to that FD using
   `O_RDONLY | O_CLOEXEC | O_NOFOLLOW`;
3. verifies parent/image device, inode, mode and UID with `fstat` and
   `os.stat(old_leaf, dir_fd=parent_fd, follow_symlinks=False)` (the Python
   `fstatat` binding) against registry facts;
4. invokes
   `os.rename(old_leaf, new_leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)`
   where `new_leaf` is the registered old leaf plus `.quarantine`;
5. revalidates the destination and source absence descriptor-relatively;
6. closes image and parent descriptors independently on every branch.

Only complete revalidation mints `QuarantineReceipt`. Any mismatch or close
failure is unresolved and preserves the artifact ledger.

### Python process parity

`PythonOwnedProcessAdapter` uses private registry-issued running and
exited-unreaped anchors with the same identity and consumption rules as Swift.
Before the private exact waitpid consumer, `Popen.poll`, `Popen.wait` and
`Popen.communicate` are forbidden. They remain forbidden after exact reap:
the adapter writes the exact `waitpid` status into its own private reaped-handle
record and never consults `Popen.returncode` as proof.

The adapter covers the full matrix:

- running `waitid` no-event, EINTR, ECHILD, wrong PID, signal or code;
- exact exited WNOWAIT, including zombie `getsid == ESRCH`;
- TERM/KILL revalidation and KILL terminality;
- exact `waitpid == pid`, EINTR retry only within the deadline, ECHILD, wrong
  PID, wrong exit code and signal status;
- post-reap private handle state, replayed `waitpid` refusal with zero syscall,
  and post-reap `Popen.poll`/`Popen.wait`/`Popen.communicate` refusal;
- post-reap signal-zero `ESRCH`, present, EPERM and other error;
- every independent stdin/stdout/stderr/request/control close result.

Raw process snapshots can contain numeric facts but never form signal or
receipt authority. Lineage is computed before UID filtering. Partial records,
foreign-UID bridges, tracked UID/SID/group changes, incomplete scans, late
children and reused births latch uncertainty. A zero-byte record is vanished
only after a complete reread yields `ESRCH`.

## Independent model architecture

### Process model

The ordered process alphabet is:

~~~python
PROCESS_EVENTS = (
    "spawn_valid",
    "exact_child",
    "related_partial",
    "foreign_uid_bridge",
    "tracked_uid_changed",
    "tracked_sid_changed",
    "group_changed",
    "request_signal",
    "root_exit_exact",
    "exact_reap",
    "original_group_absent",
    "pipes_closed",
    "scan_incomplete",
    "late_child",
    "parent_birth_reused",
)
~~~

### Effect model

The independent effect alphabet is:

~~~python
EFFECT_EVENTS = (
    "activate",
    "ordinary",
    "mount_receipt",
    "mapping_receipt",
    "preterminal_unmounted",
    "issue_detach",
    "terminal",
    "begin_disposition",
    "consume_detach",
    "settled_detach",
    "issue_absence",
    "consume_absence",
    "settle_absence",
    "issue_quarantine",
    "consume_quarantine",
    "quarantine",
    "preserve_artifact",
    "finalize_disposition",
    "unresolved",
    "inspect",
    "delete",
    "close",
)
~~~

Reducers return primitive unstamped actions and primitive final state. The
explorer, not either reducer, attaches the zero-based transition index. For
each raw trace, a separately implemented reference machine computes the entire
expected indexed action sequence and final primitive state. Tests compare both
for full equality; reference code imports no reducer state, registry or permit
type.

Every Cartesian prefix at depths zero through five is enumerated without a
visited set, state hashing or deduplication: 813,616 process traces and
5,399,043 effect traces. Positive counters require at least one valid group
signal, native settlement, ordinary success, quarantined disposition, preserved
disposition and close. Thus an empty reducer, reducer-stamped wrong index,
missing success or omitted valid path fails.

Explicit long traces exceed depth five. Process traces include a complete
spawn/identity/signal/exit/reap/group-absence/pipes-closed settlement and each
replay after consumption. Effect traces include complete
activate/mount/terminal/begin/detach/absence/quarantine/finalize/close,
preterminal mapping/proof/quarantine/finalize/close, terminal
no-artifact/create-only/mapping-unknown preservation/finalize/close, and replay
at every one-shot derivative, transfer, permit and disposition boundary.

## Closed routes and real fixture

### Exhaustive legacy removal

Before any default suite runs, the Swift literals, handlers, dispatch branches,
test launchers, test method names and documentation comments for all legacy
routes are absent:

~~~text
--spawn-probe
--fd-child
--deadline-drain-probe
--process-policy
--process-scenario
--process-child
~~~

The only testing-route literals are:

~~~text
--test-scenario
--test-supervisor-scenario
--guardian-witness-probe
--guardian-witness-child
~~~

They are all inside `#if CORTEX_STORAGE_HELPER_TESTING`. A production binary
rejects every exact testing flag with exit 64, empty stdout/stderr and zero
spawn, and contains neither route literals nor handler symbols.

### Guardian/witness contract

The parent creates guardian/witness pipes, the control socket and a random
32-lowercase-hex nonce. Before `Popen`, it creates one absolute deadline. For
each fresh R43 interpreter only, it passes the exact ASCII decimal deadline in
the test-only environment key `CORTEX_S3_PARENT_HARD_DEADLINE_NS`. The child
validates the decimal as a nonzero `UInt64`, reports the same value in its first
structured report, and can only shorten its own phase deadlines. The parent
compares that report with its locally retained value; a missing, malformed,
different or later value fails closed and never extends the parent deadline.

The parent deadline bounds interpreter import, the first structured report,
helper/fixture work, nonce scan and exact cleanup. The parent alone retains
authority to TERM/KILL/reap its one directly spawned, still-unreaped
interpreter; its nested helper cleanup is also bounded by that unchanged
deadline. The test-only key is absent from all default-suite environments and
is never accepted by the production helper parser.

The fixture creates no descendants, arms 0.90-second self-expiry before START,
writes bounded paced output, observes guardian EOF, closes witness on exit and
exposes no PID/PGID/watchdog receipt. Its closed transitive call graph permits
argument validation, `clock_gettime`, `poll`, `read`, `write`, bounded memory,
timer installation, `nanosleep`, `close` and `_exit`; it forbids spawn, fork,
exec, `system`, Foundation `Process`, `NSTask` and dynamic loading.

Each launched probe uses:

~~~text
work_cutoff = start + 0.50 seconds
supervisor_hard = start + 0.65 seconds
fixture_self_expiry = start + 0.90 seconds
cleanup_reserve_start = start + 1.00 seconds
parent_outer_hard = start + 1.20 seconds
~~~

The deadline probe requires matching START and witness EOF between 0.50 and
0.65 seconds. Cancellation requires `0x11`, one `0x01`, that active child's
matching `0x12`, witness EOF and then `0x13` before helper EOF and exact helper
reap; `0x12` must precede `0x13`. EOF and ACK may be observed in either poll
order but both are mandatory.

At `cleanup_reserve_start`, no new probe work, child spawn, report acceptance
or nonce scan may begin. The remaining 0.20 seconds are reserved only for
closing, TERM/KILL/reaping the exact still-unreaped direct interpreter and its
already registered nested helper, followed by one bounded in-memory nonce scan.
The parent stores no command line. Silent, malformed, delayed START and
far-future reports fail closed; running out of the reserved cleanup interval is
an R43 failure, never a deadline extension.

This real oracle does not observe the fixture child's internal `waitpid` and
makes no suspended-bootstrap claim. Scripted matrices prove omitted reap and
all production bootstrap branches.

## Test inventory, TDD and release evidence

`DEFAULT_TEST_CASES` is a closed ordered tuple. Runtime discovery includes
every module-defined direct or indirect `unittest.TestCase` subclass and
excludes only exact class identity `DiskImageKeychainLiveIntegrationTests`.
Discovered identities must equal the tuple. `REGRESSION_TEST_IDS` contains
exact keys from `R01` through `R45`; all 45 fully qualified values are unique
and appear exactly once in the flattened default suite.

The complete default suite runs under equipped Python 3.11 and Python 3.14
with an empty environment except exact deterministic PATH/locale/hash seed.
Recorded ordered `startTest` streams are byte-identical, both succeed, neither
skips and neither includes the live class. Nested same-interpreter launches use
`sys.executable`.

Each implementation task defines `TASK_LOCAL_TEST_IDS` and
`TASK_LOCAL_MUTANTS`. Before the first production change to a boundary, its
task-local test is written and run individually to a natural RED. After GREEN,
the exact single production-branch mutant is enabled and that same test must
fail. Natural RED never substitutes for the post-GREEN mutant. Mutants never
alter tests/oracles and never combine branches with `or`. After every task
GREEN, every mapped normative mutant and task-local mutant must fail its exact
mapped method.

For a closed case key `K` and its mapped mutant `M`, the only acceptable mutant
assertion label is `MUTANT_K_M` after substituting the literal key and mutant
name, for example `MUTANT_R01_accept_unresolved_attach_output`. The runner
records that exact label, method ID and branch name. An import error, syntax
error, timeout, unrelated exception or different assertion label is not a
mutant-sensitivity receipt.

## Normative regressions

The implementation plan binds each ID to one unique fully qualified method and
one non-composite primary mutant.

| ID | Required oracle |
| --- | --- |
| R01 | Unresolved attach containing device text cannot mint compensation authority. |
| R02 | Exact output with present original group remains unresolved and cannot compensate. |
| R03 | Truncated attach output produces no receipt. |
| R04 | Capped attach output produces no receipt. |
| R05 | Settled attach permits one exact detach, one bound info and one absence proof. |
| R06 | Held-pipe leader exit uses exited anchor; zombie `getsid == ESRCH` does not block exact wait/reap. |
| R07 | PGID reuse after reap permits only one token-bound signal-zero observation. |
| R08 | Short/changed birth, UID, PGID or SID permits no SIGCONT, input or group signal. |
| R09 | Full waitid matrix mints exited authority only for the exact terminal child. |
| R10 | Reap ECHILD remains unresolved with no settlement proof. |
| R11 | Insufficient command/finalization fit permits zero spawn. |
| R12 | Detach cutoff equality admits only full fit; plus one nanosecond refuses. |
| R13 | Absence cutoff equality admits only full fit; plus one nanosecond refuses. |
| R14 | Normal cutoff cannot reset compensation deadlines. |
| R15 | Terminal pre-observation blocks every ordinary sealed method before spawn. |
| R16 | Terminal during compile/info triggers bounded cancellation and no continuation. |
| R17 | Caller operation, cleanup, path, device or argv cannot construct live work. |
| R18 | A replayed exact detach permit performs zero second spawn. |
| R19 | One mount receipt cannot issue two detach permits. |
| R20 | Only the exact settled bound detach issues one absence permit. |
| R21 | Every terminal lineage transfers once, then produces exact quarantine or preservation disposition and one close. |
| R22 | Unknown mapping preserves artifacts without further query or mutation. |
| R23 | Every terminal artifact state performs zero Keychain inspect/delete. |
| R24 | SecurityAgent verdict has priority; otherwise observer unavailability has priority. |
| R25 | Complete nonzero create/mount evidence is registered before terminal propagation. |
| R26 | Related partial or foreign-UID bridge permanently blocks cleanup. |
| R27 | Partial bridge to exact grandchild yields no signal or cleanup. |
| R28 | Zero record followed by live full reread stays partial. |
| R29 | Zero record followed by complete ESRCH reread is vanished. |
| R30 | Late child after adoption closure is never adopted or signalled. |
| R31 | Reused parent birth is never adopted or signalled. |
| R32 | Tracked UID, SID or group change expires authority before syscall. |
| R33 | TERM-to-KILL exited-anchor matrix blocks KILL on changed waitability/identity. |
| R34 | Once KILL is attempted, no later TERM/KILL is possible. |
| R35 | Suspended-anchor forged/stale/replay/cross-registry and validate-vs-abort race permit at most exact positive-PID reap. |
| R36 | Observer/process failure and every close branch normalize terminal state while attempting all closes. |
| R37 | Valid-looking output with unresolved native settlement cannot succeed or mint a permit. |
| R38 | Clock jumps at every boundary permit no new action after the original hard deadline. |
| R39 | Entropy/Master/Wire/Keychain staging are disjoint and erased at exact app-owned boundaries. |
| R40 | Active fixture cancellation requires `0x01`, matching `0x12` before narrow `0x13`, witness EOF, control EOF and exact helper reap. |
| R41 | Production/testing route and descriptor matrices reject invalid routes/FDs before effect. |
| R42 | Dynamic Python 3.11/3.14 inventories and ordered starts are identical with zero skip. |
| R43 | Parent-deadline deadline/cancel probes reserve cleanup before hard stop, pass twenty fresh runs each and reject silent/malformed/delayed/future reports. |
| R44 | Every legacy route literal, handler and test is absent before the default suite. |
| R45 | Every near-miss of each flag and the authorization key/value constructs zero live objects. |

## Review, checkpoint and S4 separation

Before Task 1, the ignored evidence ledger freezes `IMPLEMENTATION_BASE`, exact
reviewed spec/plan SHA-256 and
`PRIMER_DIFF_SHA256 = sha256(git diff --binary -- primer.md)`. Every task
records base/head, changed paths, RED/GREEN/mutant receipts and the unchanged
primer-diff hash. `primer.md` is never edited, staged or committed.

The blind review package contains only exact candidate bytes, their hashes,
the declared baseline/requirements and necessary source context. It excludes
all previous review findings, consolidated findings, verdicts and reviewer
conclusions. The three reviewers are fresh, read-only and mutually blind.

Before `S3_FINAL`, exact repository state must be:

~~~text
git status --short --untracked-files=all
 M primer.md
~~~

The staged path list is empty. Spec, plan and primer-diff hashes are recomputed
and recorded immediately before the tag/checkpoint. Local evidence additionally
requires all normative and task-local tests/mutants, exhaustive/long models,
all branch matrices, Python 3.11/3.14 full suites, one in-suite and twenty fresh
runs of each real probe, executable production and observer Swift typechecks,
AST/source/route/FD/deadline/secret gates, `git diff --check`, both Gitleaks
scans and exact implementation paths.

After three fresh final implementation reviews pass, freeze `S3_FINAL` before
any S4 documentation. A separate documentation-only S4 rebaseline may update
only:

- `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md`;
- `docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md`;
- `docs/superpowers/plans/2026-09-02-v054-completion-program.md`.

That later commit documents internal control-socket creation, the exact
absolute deadline, sole approved descriptor and cancellation acknowledgement.
It is outside `IMPLEMENTATION_BASE..S3_FINAL` and requires new hashes and its
own independent review before S4 code begins.

## Compatibility

- Public response keys remain `schema_version`, `operation`, `code`,
  `encryption_uuid`, `device` and `item_count`.
- Stable error codes, Keychain attributes, 43-character Base64URL secret,
  no-UI queries and the strict ten-key request remain unchanged.
- The live class remains separately selected and requires fresh action-time
  authorization; the default suite cannot select it.
- Models and the real fixture do not prove live Keychain, DiskImages,
  SecurityAgent or APFS behavior.
- The documented malicious same-UID filesystem replacement race remains
  outside the frozen threat model.
