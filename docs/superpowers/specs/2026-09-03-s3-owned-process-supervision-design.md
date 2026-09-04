# Cortex Bridge S3 Owned-Process Supervision Design

**Status:** Revision 6 review candidate; implementation remains frozen until
these exact spec and plan bytes receive three fresh blind read-only reviews
with `P0=0`, `P1=0`, `P2=0` and `PASS`
**Date:** 2026-09-04
**Reviewed baseline:** `db5a40f822c115b3f06b93a8d0c4ef04a74cd026`
**Revision-6 parent:** `daa9702401b4f308fce310c854bd00520da9f2e6`
**Target:** v0.5.4 candidate
**Supersedes:** the S3 supervision and live-harness design in the current Phase
S plan; unrelated storage requirements remain in force

## Decision

S3 replaces boolean cleanup, caller-constructed live operands and raw process
identifiers with five closed mechanisms:

1. one private `NativeObligation` per direct child, moving monotonically from
   suspended ownership through exact reap, group absence, descriptor closure
   and settlement-frame publication;
2. private registry anchors including `ValidatedSuspendedAnchor` and
   `SuspendedCleanupAnchor`, so validation does not claim a child is running
   and every non-confirmed resume retains positive-PID cleanup authority until
   exact `waitpid == pid`;
3. one persistent bounded SecurityAgent observer, supervised by the same
   Python owned-process adapter from its first baseline through its final
   STOP/snapshot/EOF/exact-reap sequence;
4. Python object-identity registries with one private `ArtifactCursor`, one
   serialized effect executor and one 26-second detach-plus-absence helper for
   each sealed mounted disposition;
5. a total one-byte control DFA with closed frame/response/exit/EOF/reap
   tuples, independent exhaustive models, typed executable mutants and one
   report-GO-exec guardian/witness fixture.

This revision is a design candidate, not implementation evidence. No live
Keychain, DiskImages, `hdiutil`, mount, detach, quarantine, SecurityAgent,
Chrome, runtime, push, merge, tag or release action is authorized by it.

## Trust boundary and exact claim

Production supervision is deliberately narrow:

- the child executable is fixed to `/usr/bin/hdiutil`;
- production spawn uses a new session and starts suspended;
- signal authority never consists of a PID, PGID or copied data structure;
- every spawned direct child creates a registry-owned `NativeObligation` that
  remains active through exact leader reap, one original-group absence
  observation, closure of child/request/output descriptors and successful
  publication of its settlement frame;
- `NativeSettlementProof` excludes the helper control socket;
- Python separately requires the expected final control frame, control EOF and
  exact helper reap before it classifies a completed helper exchange.

`NativeSettlementProof` proves only the original leader and original process
group facts observed by the native supervisor. It does not prove that an
intentionally escaping descendant cannot exist. An observed escape, incomplete
lineage scan, identity change, non-`ESRCH` group observation, failed close,
abnormal control EOF or abnormal helper exit yields `UNCLEAR` or an unresolved
outcome according to the boundary where it occurs.

The obligation is process-local. Bounded cleanup retries retain authority while
the owning Swift helper remains alive, but S3 does not claim eventual reap if
that helper is itself externally destroyed. This owner-destruction boundary is
intentional. If the kernel refuses bounded cleanup, the observable result is
`UNCLEAR`. Zero-survivor liveness after owner destruction would require a
persistent broker and is explicitly outside S3.

The post-terminal authorization claim is equally narrow. The sealed Python
registry authorizes the unique current mapping for its registered
image/mount/UUID triple. A fresh helper does not receive or reconstruct a
historical Swift token and does not prove continuity with a former
`/dev/diskN`. It resolves the current mapping itself; a returned-device mismatch
against the earlier mount ledger is post-effect consistency evidence and yields
`UNCLEAR`, never proof of historical identity.

The real guardian/witness fixture is intentionally different from production:
it is not suspended, executes immediately in its own session, and arms a
2.50-second absolute self-expiry before writing `START`. It exercises anchored
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
- No claim that a Swift registry capability crosses an interpreter or helper
  process boundary. A hostile same-process Python caller and a concurrent
  same-UID remap are outside the frozen threat model; covering either requires
  an authenticated sideband or schema change.
- No claim of zero-survivor liveness after external destruction of the owning
  helper; that requires a persistent broker outside S3.
- No S4 implementation code in the S3 range.
- No weakening of timeout, authorization, cleanup or review gates.

## Component and file boundary

| File | S3 responsibility |
| --- | --- |
| `native/macos/disk_image_keychain.swift` | Public helper, strict request/control parsers, private final Darwin supervisor and registries, command provenance, erasure, testing-only scripted adapters and fixture routes. |
| `tests/disk_image_keychain_harness.py` | Private authority registries, sealed preparation/live session, persistent observer and sealed-bootstrap source bytes/hashes/protocol, serialized event-loop executor, receipt algebra, exact process adapter, control client and independent process/effect reducers. |
| `tests/test_disk_image_keychain_helper.py` | Independent reference machines, exhaustive and long traces, branch/cutoff/arbitration matrices, route/source/closure-hash gates, guardian/witness launchers, dynamic inventory and separately selected live class. |

Only those three files may change between `IMPLEMENTATION_BASE` and
`S3_FINAL`. This spec and its plan are committed before that range.
Task 5 owns all three implementation files because its Swift fixture change
requires the harness-owned helper/binary/observer hashes and route manifest to
change in the same task, and tests import those synchronized values.

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

private struct ValidatedSuspendedAnchor {
    private let registryIdentity: RegistryIdentity
    private let generation: UInt64
}

private struct SuspendedCleanupAnchor {
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

private enum NativeObligationState {
    case suspended
    case validatedSuspended
    case suspendedCleanup
    case running
    case exitedUnreaped
    case reapedAwaitingGroup
    case groupAbsentAwaitingCloses
    case settledPendingFrame
}

private struct NativeObligation {
    let generation: UInt64
    var state: NativeObligationState
    var activeFramePublished: Bool
    // PID, birth, UID, PGID, SID and owned descriptors remain private here.
}

private final class AnchorRegistry {
    private let identity = RegistryIdentity()
    private var nextGeneration: UInt64 = 1
    private var obligations: [UInt64: NativeObligation] = [:]
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

private final class LifecycleExecutor {
    private let lock = NSLock()
}

private final class OwnedProcessSupervisor {
    private let lifecycle: LifecycleExecutor
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

Every generation increment uses checked arithmetic. If any Swift issuance
counter is `UInt64.max`, that registry permanently closes issuance, latches an
unresolved cause and never wraps or reuses a generation. Any Python issuance
counter exposed as a bounded integer follows the same close-on-overflow rule.
Neither language may recover PASS after issuance exhaustion.

One serial `LifecycleExecutor` is outermost for every control read, admission,
spawn and obligation transition. Whenever more than one registry must be
mutated, the only lock order is lifecycle executor, control registry, then
anchor/command registry; inverse acquisition is rejected by an executable lock
order oracle. No subordinate registry lock is held across a blocking syscall.
The executor nevertheless keeps the logical lifecycle turn exclusive across
the bounded syscall and resumes with the same turn before another lifecycle
action may run.

The control registry mints `NoActiveChildProof` only while that executor owns
the lifecycle turn and the obligation table is empty. A reaped but unsettled
obligation, a descriptor close still pending or a settlement frame still
pending therefore blocks the proof. The proof is minted for a valid cancel in
`START` or genuinely idle `IDLE_ACCEPTED`, consumed by one `0x13` transition,
and never contains or exposes a PID. A copied, stale or replayed proof writes no
frame and authorizes no effect.

### Suspended production bootstrap

Production uses exactly:

~~~text
POSIX_SPAWN_CLOEXEC_DEFAULT
POSIX_SPAWN_SETSID
POSIX_SPAWN_START_SUSPENDED
~~~

`POSIX_SPAWN_SETPGROUP` and `posix_spawnattr_setpgroup` are forbidden.
`spawnSuspendedSession` stores the positive PID, initial birth facts and owned
descriptors as one `NativeObligation(state: .suspended)` and returns only
`SuspendedChildAnchor`.

Within one lifecycle turn exactly one atomic transition consumes that anchor.
`validateSuspendedIdentity` obtains two complete `proc_bsdinfo` records with
`getsid(pid)` between them. Both must match stored PID, birth seconds, birth
microseconds, effective UID and `processGroupID == pid`; the session must be
the PID. Exact validation consumes `SuspendedChildAnchor`, advances the same
obligation to `.validatedSuspended` and mints `ValidatedSuspendedAnchor`; it
does not claim the child is running. Any incomplete, changed, unavailable or
expired validation also consumes the old suspended anchor and directly
advances to `.suspendedCleanup` with `SuspendedCleanupAnchor`. The failed
validation anchor cannot be retried.

Control is polled immediately after exact validation and again immediately
before SIGCONT. A queued cancel at either boundary atomically converts the
validated anchor to `SuspendedCleanupAnchor` without sending SIGCONT.
`resumeSuspended` accepts only `ValidatedSuspendedAnchor`. Confirmed `.resumed`
alone consumes it, advances the obligation to `.running` and mints
`RunningSessionAnchor`. Every other `ResumeResult`, including a result where
SIGCONT delivery may have occurred but cannot be confirmed, atomically
advances to `.suspendedCleanup` and mints only `SuspendedCleanupAnchor`. That
name describes retained cleanup authority rather than guaranteed physical
suspension. The branch may issue only positive-PID TERM/KILL and exact waitpid;
it emits no input, group signal, success or cancellation success.

A cancel that linearizes only after `.resumed` has been confirmed consumes the
`RunningSessionAnchor` through the ordinary active-child cancellation path; it
cannot retroactively claim that SIGCONT was withheld. A cancel observed before
confirmation always takes the suspended-cleanup path above.

`beginSuspendedCleanup` handles a cancel before validation by consuming the
original suspended anchor into `SuspendedCleanupAnchor` and advancing the same
obligation to `.suspendedCleanup`. `abortAndReapSuspendedDirectChild` accepts
only that cleanup anchor.

Every suspended-cleanup result other than exact `waitpid == pid` leaves the
obligation and cleanup anchor record active. While the same immutable deadline
has time, only bounded positive-PID TERM/KILL and exact waitpid retries are
permitted; no group signal, SIGCONT or child input is permitted. Exact reap
advances the obligation to `.reapedAwaitingGroup`; it does not erase the record.
An unresolved attempt emits terminal `0x14` after the active `0x11` and can
never produce normal success or cancellation success.

Validation, cancellation and cleanup racing on one suspended or validated
anchor cannot both win. The helper publishes `0x11` for the extant obligation,
then either completes its `0x12,0x13` settlement or publishes `0x14`. Matrices
cover cancel before and after validation, before and after the SIGCONT attempt,
all `IdentityResult` and `ResumeResult` members, and the exact obligation/
no-active-child state at every boundary. A stale/cross-registry/consumed anchor
performs no syscall.

### Non-suspended fixture bootstrap

The testing-only guardian/witness route uses
`POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSID` and never
`POSIX_SPAWN_START_SUSPENDED`. The fixture runs immediately, installs its
absolute 2.50-second self-expiry, then writes `START:<nonce>`.

The test-only spawn adapter keeps the positive PID private, inserts one
`.running` `NativeObligation`, performs the same
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
        _ anchor: ValidatedSuspendedAnchor,
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
        _ anchor: SuspendedCleanupAnchor,
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
| `IdentityResult` | `exact(ValidatedSuspendedAnchor)`, `incomplete(SuspendedCleanupAnchor)`, `changed(SuspendedCleanupAnchor)`, `unavailable(SuspendedCleanupAnchor)`, `deadlineExpired(SuspendedCleanupAnchor)` | `exact` advances only to `validatedSuspended`; every other member advances only to `suspendedCleanup` |
| `ResumeResult` | `resumed(RunningSessionAnchor)`, `childGone(SuspendedCleanupAnchor)`, `identityChanged(SuspendedCleanupAnchor)`, `deadlineExpired(SuspendedCleanupAnchor)`, `interruptedAtDeadline(SuspendedCleanupAnchor)`, `failed(SuspendedCleanupAnchor)` | `resumed` alone advances to `running`; every other member advances only to `suspendedCleanup` |
| `ExitObservation` | `running`, `exactExited(ExitStatus, ExitedUnreapedSessionAnchor)`, `wrongPID`, `wrongSignal`, `wrongCode`, `interrupted`, `deadlineExpired`, `failed` | `running`, `exactExited` |
| `SignalResult` | `delivered`, `alreadyAbsent`, `identityChanged`, `notWaitable`, `permissionDenied`, `deadlineExpired`, `interruptedAtDeadline`, `failed` | `delivered`; `alreadyAbsent` only for exact exited authority |
| `ReapResult` | `exactlyReaped(ReapedGroupObservationToken)`, `stillRunning`, `noChild`, `wrongPID`, `deadlineExpired`, `interruptedAtDeadline`, `failed` | `exactlyReaped` |
| `GroupPresence` | `absentESRCH`, `present`, `permissionDenied`, `deadlineExpired`, `interruptedAtDeadline`, `failed` | `absentESRCH` |
| `PollResult` | `ready`, `timedOut`, `interrupted`, `deadlineExpired`, `failed` | `ready`; bounded retry for timeout/interruption |
| `IOResult` | `bytes`, `endOfFile`, `wouldBlock`, `interrupted`, `brokenPipe`, `deadlineExpired`, `failed` | positive bytes/EOF in valid position; bounded EAGAIN/EINTR retry |
| `CloseResult` | `closed`, `alreadyClosed`, `interruptedStateUnknown`, `deadlineExpired`, `failed` | `closed`, `alreadyClosed` |
| `SuspendedAbortResult` | `exactlyReaped(ReapedGroupObservationToken)`, `stillRunning`, `noChild`, `wrongPID`, `deadlineExpired`, `interruptedAtDeadline`, `failed` | `exactlyReaped` only; every other member retains the cleanup obligation |

The obligation lifecycle is monotone and the registry record is never replaced
by an untracked gap:

~~~text
suspended -> validatedSuspended -> running -> exitedUnreaped
    |                |                          |
    |                v                          v
    +-------> suspendedCleanup -------> reapedAwaitingGroup <- exact waitpid
    -> groupAbsentAwaitingCloses -> settledPendingFrame
    -> successful matching 0x12 publication -> obligation removed

exact validation only -> validatedSuspended; it never implies running
only confirmed SIGCONT resume -> running
failed validation or every non-resumed result -> suspendedCleanup
any non-exact suspended cleanup result -> remain suspendedCleanup
any unresolved later observation -> obligation remains active and 0x14 terminal
~~~

A validated-suspended anchor is revalidated immediately before SIGCONT. A
running anchor is revalidated immediately before TERM and KILL. An exited
anchor is observed before TERM, KILL and exact reap by
zero-initialized `waitid(P_PID, pid, WEXITED | WNOHANG | WNOWAIT)`. It must
return the exact PID, `SIGCHLD`, and `CLD_EXITED`, `CLD_KILLED` or
`CLD_DUMPED`. Only exact `waitpid == pid` reaps and consumes the anchor;
`waitid(WNOWAIT)` never reaps. `getsid` is not called after exact exit, so
`getsid == ESRCH` for a zombie is not treated as an identity failure.

Exact `waitpid == pid` consumes the exited or suspended-cleanup anchor, advances
the same obligation to `.reapedAwaitingGroup` and mints one
`ReapedGroupObservationToken`. `observeGroupAfterReap` consumes that token
before the sole negative-PGID signal-zero observation and advances success to
`.groupAbsentAwaitingCloses`. TERM/KILL and signal zero are separate private
adapter methods; no `killpg` or other negative target is allowed. KILL is
terminal for group-signal issuance.

### Drain, settlement and control exclusion

The supervisor checks the absolute hard deadline before and after every poll,
read, write, append, identity observation, signal, reap and close. Control
readiness wins simultaneous readiness. Production stdout and stderr are capped
independently at 1 MiB. The drain loop never reaps.

Cancellation linearizes only when the lifecycle executor reads `0x01`. It
polls control before spawn; after a successful spawn it inserts the suspended
obligation before `0x11`; it polls immediately after insertion, immediately
after exact validation, immediately before SIGCONT and before each child-input
write. A queued cancel at any pre-resume poll consumes the current suspended or
validated-suspended anchor into suspended cleanup. No second lock or reader may
consume control bytes.

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

Successful native descriptor closure advances the obligation to
`.settledPendingFrame`; `NoActiveChildProof` remains unavailable. Only after
that state and proof issuance may Swift write the matching `0x12`. A successful
write removes the obligation. If cancellation
is already latched, it immediately follows that child-settlement frame with the
sole terminal `0x13`; it never suppresses the child's required `0x12`. Swift
continues using the same control channel for any later child in the operation
and shuts it down only after the final normal or terminal transition. A failed control
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

After sealed preparation has started the persistent observer and obtained its
empty preparation baselines, Python forms the immutable live schedule:

~~~python
live_started_ns = shared_clock_ns()
outer_hard_ns = checked_add_u64(live_started_ns, 115_000_000_000)
first_snapshot_cutoff_ns = checked_add_u64(live_started_ns, 1_000_000_000)
helper_total_cutoff_ns = checked_add_u64(live_started_ns, 71_000_000_000)
post_reap_snapshot_cutoff_ns = checked_add_u64(live_started_ns, 72_000_000_000)
continuation_cutoff_ns = checked_add_u64(live_started_ns, 98_000_000_000)
publication_cutoff_ns = checked_add_u64(live_started_ns, 100_000_000_000)
verdict_cutoff_ns = checked_add_u64(live_started_ns, 106_000_000_000)

first_live_snapshot = observer.require_snapshot(
    scan_started_at_or_after_ns=live_started_ns,
    delivered_by_ns=first_snapshot_cutoff_ns,
)
# No helper is started unless the snapshot is accepted.
swift_epoch_ns = shared_clock_ns()
swift_hard_ns = checked_add_u64(swift_epoch_ns, 70_000_000_000)
assert swift_hard_ns <= helper_total_cutoff_ns
~~~

A missing, detected, malformed, late or unavailable first live snapshot
atomically consumes the current no-effect transition into a terminal no-effect
receipt and starts no helper. The original helper's complete six-value tuple,
stdout/stderr/control EOFs and exact direct-helper reap are all required by
absolute `helper_total_cutoff_ns`. Only after that reap may the executor accept
the first strictly later observer frame whose
`scan_started_ns >= helper_reaped_ns`; it must be delivered by absolute
`post_reap_snapshot_cutoff_ns`. Equality at either cutoff is accepted only when
the complete required transition has already settled; one nanosecond later is
terminal and permits no continuation.

`shared_clock_ns()` is the sole Python producer for any timestamp transmitted
to or compared with Swift and is exactly
`time.clock_gettime_ns(time.CLOCK_MONOTONIC)`. Swift uses exactly
`clock_gettime(CLOCK_MONOTONIC)`. A harmless cross-language oracle brackets a
Swift sample `s` with Python samples `p0` and `p1`; it requires
`p0 <= s <= p1` and `p1 - p0 <= 50_000_000` nanoseconds for each of 20 fresh
samples. This is a fail-closed acceptance SLA for the observed sample, not a
promise that the OS schedules work within 50 ms. Any unavailable sample or
wider bracket is `UNCLEAR`, never a relaxed tolerance. Python's convenience monotonic-nanosecond API and
`CLOCK_UPTIME_RAW` are structurally forbidden for shared deadlines. One atomic
source-copy mutant substitutes the convenience API for the exact Python call;
the unchanged cross-language oracle must then fail naturally while the
checkout and oracle remain untouched.

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
| response, erasure, final control close | stop 70 s | no new child |

Equality is admitted only when the complete phase budget still fits; one
nanosecond later refuses. No phase borrows from another. These boundaries apply
only to original live helper work; they do not authorize a terminal
continuation. The executable outer schedule is fixed to `live_started`: the
first accepted live snapshot by +1; original Swift hard and the helper's total
tuple/EOF/exact-reap by +71; a strictly post-reap accepted observer snapshot by
+72; the sole 26-second continuation complete by +98; quarantine and ledger
publication by +100; and the irrevocable verdict cutoff at +106. The +106..+115
tail permits only idempotent endpoint close, positive-PID TERM/KILL and exact
waitpid cleanup. Any work first settling after +106 locks `UNCLEAR`; later
cleanup cannot restore PASS. Early completion never moves an absolute cutoff
forward or creates another reserve.

### One post-terminal detach-plus-absence continuation

The original live Swift helper never receives more than its original
70-second hard deadline and never borrows the outer continuation reserve.
After its valid final frame, six-key response, control EOF and exact helper
reap, and only after the strictly later accepted observer watermark delivered
by absolute +72, the sealed Python object-identity registry may consume one
mounted cursor state and start exactly one fresh direct Swift helper invocation. No Swift
receipt, token, PID or registry identity crosses the process boundary.

The invocation uses the unchanged strict ten-key request with public
`operation=detach`. Python fixes image, mount, UUID, transaction and every
other value from the current cursor record. Swift reads the mounted secret,
proves encryption facts, resolves the unique current device for that exact
image/mount/UUID triple, detaches that device and performs its bound
post-detach `hdiutil info -plist` absence query before one response. The
Python registry authorizes only that current mapping. It does not authorize or
claim continuity with the historical device stored by a prior helper. The
returned device is compared with the mount ledger only after the effect; a
mismatch yields unresolved preservation evidence.

The single invocation samples `now` only through Python `shared_clock_ns()` and
has one checked absolute `continuation_hard_ns = now + 26_000_000_000`,
admitted only when that value is at or before immutable absolute
`continuation_cutoff_ns` (+98). Its origin is recovered by checked subtraction of exactly
26 seconds after the detach request is parsed. The fixed, non-resettable
schedule is:

| Stage | Work stop | Failure finalization stop |
| --- | --- | --- |
| bind registered context, Keychain read, encryption and current-mapping info | `origin + 8 s` | `origin + 14 s` |
| exact current-device detach | `origin + 14 s` | `origin + 20 s` |
| bound absence info, six-key response and terminal control transition | `origin + 26 s` | `origin + 26 s` |

No stage may reset the origin, borrow from a later helper or extend the outer
envelope. There is no second helper and no inter-helper token. The closed
result is either `DetachedAndAbsentReceipt` with complete tuple/current-device
consistency/empty mount-directory evidence, or
`UnresolvedContinuationReceipt` retaining the full cursor ledger. External
Python verification of the registered mount directory is part of this result:
it must be the same no-follow directory and contain exactly zero entries after
detach. Nonempty, error, symlink or identity mismatch yields only
`UnresolvedContinuationReceipt`, never quarantine or deletion. Insufficient
fit, ambiguous current mapping, device mismatch, abnormal tuple or incomplete
absence starts no later helper and resolves only to the latter. Normal cycle
detach uses the same self-contained detach/current-mapping/absence semantics;
terminal disposition is the only path that consumes the special 26-second
continuation slot.

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
`NormalExitKind`:

~~~swift
private enum NormalExitKind {
    case strictRejected
    case acceptedSuccess(Operation, CompleteTraceProof)
    case acceptedOperationalError(Operation, StableCode, SettledPrefixProof)
    case protocolAbnormal(Operation, SettledPrefixProof, ExactStdoutState)
}
~~~

`CompleteTraceProof` binds every declared child command and its last state
transition through the final response. `SettledPrefixProof` binds the exact
valid prefix and its last transition; it never claims the remaining suffix.
Both proofs are registry-minted from complete per-child settlement tuples.
Settled-child count is derived from the typed proof and is never authority by
itself. The state is therefore total without conflating accepted zero-child
success, accepted operational error and protocol failure. The transition
function is total:

| State/input | Transition and output |
| --- | --- |
| `START` + valid request | `IDLE_ACCEPTED`, emit one `0x10`. |
| `START` + valid cancel | `TERMINAL`, emit one `0x13`; then publish the pre-accept-cancel tuple and close control. |
| `START` + reject/unknown/duplicate/EOF | `NORMAL_EXIT(strictRejected)`, exit 64, no frame and no effect. |
| `START` + EAGAIN/EINTR | Stay while time remains; expiry goes `NORMAL_EXIT(strictRejected)`, exit 64, no frame. |
| `IDLE_ACCEPTED` + admitted child | `ACTIVE`, emit one `0x11`. |
| `IDLE_ACCEPTED` + accepted zero-child success | Mint the operation's exact empty `CompleteTraceProof`, write its six-key `OK`, then `NORMAL_EXIT(acceptedSuccess(operation, proof))`, exit 0; `0x10` is the last valid frame. |
| `IDLE_ACCEPTED` + complete final child prefix | Mint `CompleteTraceProof` only after the last declared transition and response, then `NORMAL_EXIT(acceptedSuccess(operation, proof))`, exit 0. |
| `IDLE_ACCEPTED` + operational error after a valid prefix | Mint the exact `SettledPrefixProof`, write one six-key stable error response, then `NORMAL_EXIT(acceptedOperationalError(operation, code, proof))`, exit 64 or 70 from the closed error map. |
| `IDLE_ACCEPTED` + cancel after zero or any settled pairs | `TERMINAL`, emit one `0x13`. |
| `IDLE_ACCEPTED` + unknown/duplicate/EOF/out-of-order | Preserve the exact accepted operation/prefix/stdout state in `NORMAL_EXIT(protocolAbnormal(operation, prefixProof, stdoutState))`, exit 65, no additional frame. |
| `IDLE_ACCEPTED` + EAGAIN/EINTR | Stay while time remains; expiry preserves the exact accepted operation/prefix/stdout state in `NORMAL_EXIT(protocolAbnormal(operation, prefixProof, stdoutState))`, exit 65. |
| `ACTIVE` + native settlement | `IDLE_ACCEPTED`, emit matching `0x12`; keep control open if the command trace has another child. |
| `ACTIVE` + cancel then native settlement | Emit matching `0x12`, return through `IDLE_ACCEPTED`, then immediately enter `TERMINAL` and emit one `0x13`. |
| `ACTIVE` + cancel then unresolved finalization | `TERMINAL`, emit one `0x14`. |
| `ACTIVE` + unresolved without cancel | `TERMINAL`, emit one `0x14`; write `SUPERVISION_UNRESOLVED` only in the closed stdout-usable variant. |
| `ACTIVE` + unknown/duplicate/EOF/out-of-order | Finalize; native failure emits `0x14`, otherwise preserve operation/prefix/stdout state in `NORMAL_EXIT(protocolAbnormal(operation, prefixProof, stdoutState))` with exit 65 and no cancellation frame. |
| `ACTIVE` + EAGAIN/EINTR | Stay while time remains; deadline finalizes to `0x14` if native settlement is unresolved. |
| `TERMINAL` + any byte/readiness/replay | No effect, frame or state change; close only. |
| `NORMAL_EXIT` + any byte/readiness/replay | Preserve `NormalExitKind`; no effect, frame or state change. |

Each active child has exactly one `0x11` and either one `0x12` settlement or a
sole terminal `0x14`. Cancellation after a narrow active-child settlement emits
that required `0x12` and then one `0x13`. An intermediate `0x12` never closes
control; only the final normal or terminal transition does. Tests cover cancel
after every settled pair, accepted zero-child inspect/delete, accepted success
with children, accepted operational errors, not-spawned work,
unresolved work without cancel, helper exit in every state, EOF, EAGAIN,
unknown, duplicate and out-of-order bytes, and replay after both terminal
states.

Successful public operations have a closed child-command trace, hence one
exact `k`:

| Operation | Exact settled child trace | `k` |
| --- | --- | ---: |
| `create` | `create`, `isEncrypted` | 2 |
| `mount` | `baselineInfo`, `attach`, `validationInfo`, `isEncrypted`, `finalInfo` | 5 |
| `detach` | `isEncrypted`, `currentMappingInfo`, `detachCurrentDevice`, `postDetachAbsenceInfo` | 4 |
| `inspect-item` | no child | 0 |
| `delete-disposable-item` | no child | 0 |

An operational-error trace is the exact typed settled prefix of one row. Each
prefix names its last state transition; a settled nonzero child is derived from
the proof, while failure before a child is admitted adds no pair. Mount
compensation, when a settled attach created a mapping before a later validation
error, appends only the closed `detachCurrentDevice,postDetachAbsenceInfo`
suffix. No other command ordering is accepted.

The complete helper exchange algebra is:

| Outcome | Frames on control | Stdout response | Exit | Required tail |
| --- | --- | --- | ---: | --- |
| pre-accept reject | `[]` | none | 64 | bounded stderr/stdout closure, control EOF, exact helper reap |
| pre-accept cancel | `[0x13]` | none | 75 | bounded stderr/stdout closure, control EOF, exact helper reap |
| accepted success with `k` children | `[0x10,(0x11,0x12)^k]` | one exact six-key `OK` | 0 | bounded stderr/stdout closure, control EOF, exact helper reap |
| accepted operational error after `k` settled children | same settled prefix | one exact six-key stable error | 64 or 70 from the closed error map | bounded stderr/stdout closure, control EOF, exact helper reap |
| settled cancel | valid prefix; an active child finishes `0x11,0x12`, then `0x13` | one exact six-key `CANCELLED` | 75 | bounded stderr/stdout closure, control EOF, exact helper reap |
| unresolved active child, stdout usable | valid prefix ending `0x11,0x14` | one exact six-key `SUPERVISION_UNRESOLVED` | 74 | bounded stderr/stdout closure, control EOF, exact helper reap |
| unresolved active child, stdout unusable | valid prefix ending `0x11,0x14` | none | 74 | bounded close attempts, control EOF, exact helper reap |
| accepted protocol abnormality, stdout usable | valid prefix only | one exact six-key `PROTOCOL_ERROR` | 65 | bounded stderr/stdout closure, control EOF, exact helper reap |
| accepted protocol abnormality, stdout unusable | valid prefix only | none | 65 | bounded close attempts, control EOF, exact helper reap |

Every response-producing non-OK row has exactly these six values:

~~~text
schema_version = 1
operation = <accepted operation>
code = <closed stable code>
encryption_uuid = null
device = null
item_count = null
~~~

Partial UUID/device/count values never become evidence or authority. An
`INVALID_REQUEST` or any other pre-accept exit-64 row produces no response.
Successful rows preserve the exact operation-specific values:

| Operation | `encryption_uuid` | `device` | `item_count` |
| --- | --- | --- | ---: |
| `create` | exact created UUID | null | 1 |
| `mount` | exact created UUID | exact mounted device | 1 |
| `detach` | exact created UUID | exact detached current device | null |
| `inspect-item` | exact created UUID | null | 1 |
| `delete-disposable-item` | exact created UUID | null | 0 |

The stable operational-error map fixes each accepted code to exit 64 or 70;
control outcomes remain exactly 65, 74 or 75 as declared. Every post-accept
response has empty stderr. Python compares all six response values, complete
frame sequence, stdout/stderr EOF, control EOF and exact waitpid.

Ordering is constrained independently on stdout and control; no cross-FD read
order is inferred. Python considers a tuple complete only when the exact frame
grammar, exact six-key response presence/value, exact exit, bounded stream
closure, control EOF and exact direct-helper reap all match one row. Every
missing or mismatched component is `UNCLEAR`, mints no artifact/effect
authority and routes the current cursor ledger to one disposition.

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

The same shape is mandatory for `ObserverBinaryReceipt`, `ObserverBaseline`,
`ObserverStoppedReceipt`, `NoObserverSpawnProof`, `HelperBinaryReceipt`, `SecurityAgentSnapshot`,
`PreparationTerminalReceipt`, `TerminalCause`, `TerminalEventReceipt`,
`ArtifactCursor`, `CreateCommandReceipt`,
`MountCommandReceipt`, `MountVerificationReceipt`,
`DetachedAndAbsentReceipt`, `CleanupGrant`, `KeychainDeletePermit`,
`KeychainAbsentReceipt`, `ImageDeletePermit`, `ImageAbsentReceipt`,
`QuarantinePermit`, `QuarantineReceipt`,
`UnresolvedEffectReceipt`, `UnresolvedContinuationReceipt`, `UnresolvedDeletionReceipt`,
`PreservationReceipt` and `DispositionReceipt`. Private final-style registry
classes own fresh `object()` issuance keys and all payload. Validation uses
`is`, not value equality.

Each root is minted by exactly one registry in one session epoch. A
field-equivalent shell, shallow/deep copy, wrong command/result/device, wrong
session/epoch/registry, stale issuance, unresolved receipt or replay rejects
under the registry lock before any effect.

### One-shot preparation and fixed artifacts

The parser atomically mints one `PreparationCapability` and one registry record
for `ArtifactCursor(noArtifact)`. They are not copies of one another, but the
cursor has exactly one transition slot: it is consumed by either successful
`mint_live` or one `PreparationTerminalReceipt`, never both. The preparation
registry record fixes:

- the reviewed Swift source path and expected source SHA-256;
- a private temporary helper target beneath the ignored SDD directory;
- the exact embedded observer Swift source and private temporary target;
- whether cleanup was explicitly approved.

`PreparationSession.prepare_observer()` and
`PreparationSession.compile_helper()` take no paths or argv. They consume
finite portions of one 30-second absolute preparation deadline and use the
exact Python running/exited/waitid/waitpid supervision contract. The enforced
order is exact:

1. write the fixed reviewed observer bytes exclusively, verify their hash,
   typecheck and compile them to the fixed private target;
2. run that observer and capture one complete empty process/window baseline;
3. while that same observer remains active, compile the fixed reviewed helper;
4. capture a fresh complete empty baseline after helper compilation;
5. only then consume preparation authority and the existing no-artifact cursor,
   mint live authority/context plus the live successor cursor and start the
   115-second clock.

Detection, observer unavailability or compiler failure during preparation
atomically consumes the no-artifact cursor and mints
`PreparationTerminalReceipt(noArtifact, cause)`. The compiler is cancelled and
exact-reaped under the preparation deadline. The sole
`finalize_preparation_terminal(receipt)` transition mints
`DispositionReceipt(noArtifact, cause)`, after the observer's required final
shutdown sequence, and `close` consumes it once. No `LiveExecutionCapability`,
live context or live effect authority is minted on this path. R16 therefore
observes a real closed preparation outcome instead of asking an observer that
was not yet prepared to report an earlier event. Failed preparation and
successful live issuance race on the same registry record, so a duplicated
no-artifact cursor cannot authorize both paths.

If failure occurs before an observer process is spawned, the adapter instead
mints a private no-observer-spawn proof after exact compiler cleanup and
independent descriptor closes; no fictitious STOP/reap is claimed. Once an
observer PID has been registered, the full STOP/final-snapshot/EOF/exact-reap
sequence is mandatory.

Reviewed helper and observer source bytes, their expected SHA-256 values and
their fixed private targets live in `tests/disk_image_keychain_harness.py`.
Tests import these values; they do not duplicate or recompute a second source
constant. No caller-controlled path, target, request field, command or argv
enters preparation or live issuance.

### Persistent observer session and protocol

One private `ObserverSession`, owned entirely by
`PythonOwnedProcessAdapter`, persists from its first preparation baseline
through helper compilation, every live/continuation/disposition effect, and
the final pre-receipt shutdown. `LiveSecurityAgentObserver` delegates all
process ownership to that adapter and never calls `Popen.poll`, `Popen.wait` or
`Popen.communicate`.

The observer executable is compiled only from the exact
`REVIEWED_SECURITY_AGENT_OBSERVER_SOURCE` bytes stored in
`tests/disk_image_keychain_harness.py`; the same file stores their literal
expected SHA-256 and all protocol constants. Compilation occurs in a private
temporary directory after the harness hashes the exact bytes. This creates no
fourth tracked implementation file. Its only spawn shape is:

~~~python
subprocess.Popen(
    [absolute_reviewed_observer_binary],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    close_fds=True,
    pass_fds=(),
    env={
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "C",
        "LC_ALL": "C",
    },
    start_new_session=True,
)
~~~

Control and report frames use the one reviewed framing constant: unsigned
four-byte big-endian payload length followed by canonical UTF-8 JSON, with a
65,536-byte total-frame cap. Every report contains fixed header
`CORTEX_S3_OBSERVER_V1`, closed type `READY`, `SNAPSHOT` or `STOPPED`, a
contiguous checked `UInt64` sequence, and shared-clock
`scan_started_ns`/`scan_finished_ns`. `READY` carries the first complete empty
baseline. `SNAPSHOT` carries only bounded arrays of the pre-reviewed
SecurityAgent process/window comparison tokens. Tokens contain no titles,
paths, environment, command lines or user text. `STOPPED` follows the final
snapshot and contains no unbounded payload. Duplicate, skipped, out-of-order,
oversize, malformed or unknown frames, stderr data, unexpected EOF, sequence
overflow or silence through the applicable snapshot cutoff atomically latches
`observerUnavailable`.

Sampling is scheduled from absolute `CLOCK_MONOTONIC` ticks with a maximum
accepted 50 ms interval. Sequence numbers must be contiguous; every frame must
land inside its declared acceptance window; and every Swift scan executes in a
fresh autorelease pool. A late tick or delivery is terminal even if a later
frame looks empty. This is a fail-closed acceptance SLA, not an OS scheduling
guarantee, and cannot prove absence of a SecurityAgent event shorter than the
sampling interval.

The serial lifecycle executor multiplexes observer stdout/stderr, helper or
compiler channels and cancellation/control readiness without a long blocking
call. Observer/control events in one readiness batch are reduced before any
helper-completion event. Observer frames remain bounded in memory and are
never persisted.

Intentional shutdown sends exactly the single framed `STOP` protocol constant,
flushes and closes observer stdin, then requires a final accepted `SNAPSHOT`,
one `STOPPED`, exact stdout/stderr EOF, bounded reader join, exit 0 and exact
raw `waitpid` of the observer leader. The adapter uses bounded process-group
TERM/KILL fallback and exact final reap on timeout. EOF before intentional
shutdown, bad close/reap, surviving group or any shutdown mismatch latches
observer-unavailable and `UNCLEAR`. The cause accumulator remains open through
the final snapshot, STOPPED, both EOFs and exact reap. SecurityAgent detection
in that final snapshot changes the verdict to `FAIL`; no
`DispositionReceipt`—including a nominal PASS receipt—may be minted earlier.

The `ArtifactContext` registry record contains the generated transaction UUID,
image leaf `CORTEX_BRIDGE_SPIKE_<32 lowercase hex>.sparsebundle`, mount path
`mount-<same 32 lowercase hex>`, volume `CORTEX_BRIDGE_SPIKE`, size `64m`,
filesystem `APFS`, disposable true and the expected encryption UUID once
created. At issuance, the registry captures the private parent directory's
device, inode, mode and UID through its no-follow descriptor. Settled create
then captures the image leaf's device, inode, mode and UID through that same
parent descriptor and stores those facts in the cursor's `created(cycle=0)`
ledger. Every later cursor state carries the same sealed image facts. No caller
supplies, recomputes or string-resolves any quarantine identity fact.

### Serialized executor and no free operands

One session-owned serial lifecycle executor is the sole submitter and consumer
of every observation, process lifecycle operation and effect. It has one FIFO
queue and one worker identity; no competing observer/control reader or second
effect lock exists. Before every syscall, `Popen` or first request write, it
atomically consumes the predecessor transition slot into one registry-owned
record:

~~~text
InFlightOperation(
  predecessorAuthority = cursor | terminalReceipt | dispositionReceipt,
  predecessorLedger,
  operation,
  generation,
  predictedEffectClass,
  phase = reserved | spawned | requestStarted,
  helperAndControlHandles,
  terminalTransferSlot,
)
~~~

The same requirement covers normal effects and every detach, quarantine,
preservation, deletion, observer-stop or close effect in disposition; no
disposition effect starts from an unregistered receipt. The predecessor shell
is consumed when the reservation is made and cannot be replayed while work is
in flight.

The executor is a nonblocking event loop. Registry locks are held only for
in-memory transitions, never across a syscall, wait or pipe drain. Helper,
observer and cancellation/control readiness is multiplexed. When several
events arrive in one readiness batch, accepted observer events and
cancellation/control events are applied before raw helper completion.

If an ordinary completion is observed first, the record becomes
`CompletionPendingObservation`; completion alone cannot mint a cursor. It may
advance only after the exact total helper tuple, every stream/control EOF,
exact direct-helper reap and a strictly later accepted observer frame whose
`scan_started_ns >= helper_reaped_ns`. If a terminal cause wins first, the
same record becomes `TerminalPendingEffect`, consumes the cause through its
terminal-transfer slot and permanently revokes ordinary success.

Cancellation/native settlement resolves each `TerminalPendingEffect` to
exactly one `TerminalEventReceipt`: the predecessor ledger when no effect is
proved, the exact updated ledger when a complete effect result is observed, or
a bounded non-authorizing uncertainty envelope over the possible ledgers when
the result is partial, late or ambiguous. The envelope is not a selected
concrete or "maximum" ledger and cannot authorize detach, quarantine, delete,
PASS or any ordinary successor. A late synchronous Keychain result may enrich
only diagnostic or exact-ledger facts of the pending terminal record; it cannot
mint an ordinary cursor, permit, new effect or PASS.

No terminal disposition begins until every registered in-flight operation is
settled or has one closed uncertainty envelope. Deterministic interleavings
cover the terminal latch before/after reservation, spawn, registration, first
write, raw completion, each EOF/reap and the post-reap observer watermark.
Every branch then reaches exactly one disposition outcome and, only after the
observer's final shutdown sequence, one `DispositionReceipt`.

The complete callable catalogue has no raw live path/device/operation operand:

| Method | Exact producer/result |
| --- | --- |
| `PreparationSession.prepare_observer()` | Fixed compiled observer plus first complete empty `ObserverBaseline`. |
| `PreparationSession.compile_helper()` | Fixed `HelperBinaryReceipt` plus refreshed complete empty observer baseline, or `PreparationTerminalReceipt` after consuming the no-artifact cursor. |
| `PreparationSession.mint_live()` | Consumes the sole prepared no-artifact cursor and returns `LiveExecutionCapability`, `ArtifactContext`, its live no-artifact successor and optional registry-minted `CleanupGrant`; no operands. |
| `PreparationSession.finalize_preparation_terminal(receipt)` | After registered compiler settlement and either final observer STOP/snapshot/EOF/reap or exact no-observer-spawn proof, returns `DispositionReceipt(noArtifact, cause)`; no live capability. |
| `EffectSession.create_image(cursor)` | Closed settled successor `ArtifactCursor(created(cycle=0))` or unresolved ledger outcome. |
| `EffectSession.mount_cycle(cursor)` | Closed settled successor `ArtifactCursor(mounted(i))` or unresolved ledger outcome. |
| `EffectSession.verify_mount(cursor)` | Exact diskutil/mapping/APFS evidence and `ArtifactCursor(mountVerified(i))`, or unresolved ledger outcome. |
| `EffectSession.detach_and_prove_absence_normal(cursor)` | One self-contained detach/absence helper and `ArtifactCursor(unmounted(i))`, or unresolved ledger outcome. |
| `EffectSession.advance_cycle(cursor)` | `created(cycle=i+1)` and, after cycle 1, `cyclesComplete`; no effect. |
| `EffectSession.inspect_item(cursor)` | Exact one-item inspect and `ArtifactCursor(keychainInspected)`, or unresolved outcome. |
| `EffectSession.keychain_delete_permit(cursor, grant)` | Consumes the exact `CleanupGrant` after `keychainInspected` and returns one `KeychainDeletePermit`; no effect. |
| `EffectSession.delete_item(cursor, permit)` | Consumes one `KeychainDeletePermit`; exact delete plus zero-count re-query yields `KeychainAbsentReceipt` and `ArtifactCursor(keychainAbsent)`, otherwise unresolved. |
| `EffectSession.image_delete_permit(cursor, absent)` | Consumes exact current `KeychainAbsentReceipt` and returns one `ImageDeletePermit`; no effect. |
| `EffectSession.delete_image(cursor, permit)` | Exclusive tombstone rename plus fd-relative removal yields `ImageAbsentReceipt` and `ArtifactCursor(imageAbsent)`, otherwise `UnresolvedDeletionReceipt`. |
| `EffectSession.quarantine_unapproved(cursor)` | Exclusive quarantine and `ArtifactCursor(imageQuarantined)` with `keychainStillPresent=true`, or unresolved. |
| `EffectSession.observe_terminal_snapshot()` | Registry-minted `SecurityAgentSnapshot` from fixed observer evidence only. |
| `EffectSession.latch_terminal(snapshot)` | Consumes the snapshot, registry-mints `TerminalCause` and converts the current cursor or in-flight record to one terminal-pending transfer. |
| `EffectSession.detach_for_disposition(event)` | One 26-second detach-plus-absence continuation from current mounted lineage, returning `DetachedAndAbsentReceipt` or `UnresolvedContinuationReceipt`. |
| `EffectSession.quarantine_for_disposition(predecessor)` | `QuarantineReceipt` or unresolved preservation from the current unmounted cursor ledger. |
| `EffectSession.preserve_for_disposition(event)` | `PreservationReceipt` with the complete current ledger and no new effect. |
| `EffectSession.finalize_disposition(outcome)` | Registers final observer shutdown; only its final snapshot, STOPPED, EOFs and exact reap permit exactly one `DispositionReceipt` for normal PASS, cleanup-not-authorized, or any failure/terminal branch. |
| `EffectSession.close(disposition)` | Final verdict; this is the only `close` signature. |

There is no public `record_mount`, generic runner, mapping request, public argv,
`safety_only` or `disposition_active` switch. Every consuming effect claims one
named cursor slot before work and returns a closed settled/unresolved outcome;
no exception or boolean can strand a consumed capability.

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
PREPARING -> ACTIVE -> DISPOSING -> FINALIZING_OBSERVER -> CLOSED
     |          \-> TERMINAL_PENDING -> DISPOSING --^
     \-> PREPARATION_TERMINAL ---------------------^
~~~

The registry owns exactly one current `ArtifactCursor`; no historical receipt
is scanned for precedence. Its legal states and transitions are exactly:

~~~text
noArtifact
  -> created(cycle=0)
  -> mounted(i)
  -> mountVerified(i)
  -> unmounted(i)
  -> created(cycle=i+1)
  -> cyclesComplete
  -> keychainInspected
  -> keychainAbsent
  -> imageQuarantined
  -> imageAbsent

every state -> unresolved(ledger)
~~~

For each `i in {0,1}`, a fresh mount helper must return its exact complete
tuple and UUID; diskutil must prove the returned device, registered mount and
APFS filesystem; `hdiutil info` must prove the exact current mapping; one
self-contained detach/absence helper must settle; its returned device must
match the cycle ledger as post-effect consistency evidence; and the registered
mount directory must be empty. Only then may the cursor advance to the next
cycle. After `unmounted(1)`, the registry advances through
`created(cycle=2)` to `cyclesComplete`. Inspect is issuable exactly once and
only from `cyclesComplete`.

Only the current cursor or its registered `InFlightOperation` has one
terminal-transfer slot. Every cursor advance consumes the predecessor slot, so
cycle-0 evidence can never outrank a cycle-1 mount. The fixed observer bridge
alone mints a `SecurityAgentSnapshot`. Under one executor event,
`latch_terminal` consumes that snapshot and registry-mints exactly one cause.
An idle current cursor transfers directly; an effect already reserved becomes
`TerminalPendingEffect` and produces `TerminalEventReceipt` only after its
settled/exact/uncertain ledger resolution. Cause priority is separate from
artifact state:

~~~text
securityAgentDetected > observerUnavailable > deadlineOrUnresolved
  > operationalFailure > cleanupNotAuthorized
~~~

Callers cannot construct any cause. SecurityAgent determines
`FAIL securityagent_detected` if ever observed; otherwise observer failure
determines `UNCLEAR observer_unavailable`; all other causes preserve their
closed stable verdict/code. The cursor ledger determines permitted cleanup,
never cause priority.

The success cleanup is total and ordered. A cleanup-approved preparation mints
one `CleanupGrant`; after exact inspect-count one it is consumed into one
`KeychainDeletePermit`. Exact delete followed by exact zero-count re-query
mints `KeychainAbsentReceipt` and advances to `keychainAbsent`. That receipt
alone mints one `ImageDeletePermit`. No image deletion can precede proven
Keychain absence.

Cleanup-not-approved after both cycles and inspect consumes the current cursor
into a registered exact descriptor-relative quarantine attempt, records
`keychainStillPresent=true`, and returns `UNCLEAR cleanup_not_authorized`.
A terminal cause after Keychain deletion performs no later Keychain inspect,
delete or re-query; it quarantines, deletes only if its already-issued image
permit remains exact, or preserves the image using the current ledger. Every
consuming effect returns a closed settled or unresolved result. Rename success
followed by revalidation or close failure retains both old/new leaf facts in an
unresolved ledger; it is never retroactively reported as success.

Receipt producers and controlled consumers are exact. Every effect-consuming
row first creates `InFlightOperation`; a receipt listed as predecessor is not
free-standing syscall authority:

| Registry-minted value | Exclusive producer | Sole effect-consuming rule |
| --- | --- | --- |
| `NoActiveChildProof` | lifecycle executor while the obligation table is empty | one `0x13` transition |
| `ArtifactCursor` | preparation registry or one legal predecessor transition | reservation into its one named `InFlightOperation` or terminal transfer |
| `PreparationTerminalReceipt` | preparation failure consuming the sole no-artifact cursor | one preparation-terminal finalization after compiler settlement and observer shutdown |
| `SecurityAgentSnapshot` | fixed observer bridge | `latch_terminal` once |
| `TerminalCause` | preparation/lifecycle/observer/effect registries only | sealed into one `PreparationTerminalReceipt` or `TerminalEventReceipt` |
| `TerminalEventReceipt` | terminal latch plus idle cursor transfer, or settled `TerminalPendingEffect` | reservation into one disposition route |
| `CleanupGrant` | cleanup-approved preparation record | one `KeychainDeletePermit` after `keychainInspected` |
| `KeychainDeletePermit` | exact cursor plus grant | one exact delete and re-query |
| `KeychainAbsentReceipt` | exact delete and zero-count re-query | one `ImageDeletePermit` |
| `ImageDeletePermit` | exact Keychain-absent receipt | one exclusive tombstone/delete chain |
| `DetachedAndAbsentReceipt` | one complete 26-second continuation tuple | cursor advance or quarantine route |
| `QuarantinePermit` | exact current unmounted cursor state | one exclusive quarantine rename |
| `QuarantineReceipt` | exact exclusive rename, revalidation and independent closes | one disposition finalization |
| `ImageAbsentReceipt` | exact tombstone removal, both absence checks and independent closes | one disposition finalization |
| `UnresolvedContinuationReceipt` | any non-settled continuation result | one unresolved disposition finalization |
| `UnresolvedEffectReceipt` | any ordinary or terminal-pending ambiguity | one bounded non-authorizing uncertainty envelope for disposition |
| `UnresolvedDeletionReceipt` | any non-total rename/removal/revalidation/close result | one unresolved disposition finalization |
| `PreservationReceipt` | a no-effect terminal route carrying the current ledger | one disposition finalization |
| `ObserverStoppedReceipt` | exact final snapshot, STOPPED, stdout/stderr EOF and observer waitpid | required input to disposition minting; no standalone effect |
| `NoObserverSpawnProof` | preparation registry after proved zero observer spawn plus compiler/descriptor cleanup | substitutes only for observer shutdown on a pre-spawn preparation terminal path |
| `DispositionReceipt` | registry reduction of exactly one normal or terminal outcome plus `ObserverStoppedReceipt`, or pre-spawn preparation terminal plus `NoObserverSpawnProof` | registered `close` once |

Normal approved success, unapproved quarantine and every operational,
protocol, deadline, observer or native-supervision failure each mint exactly
one `DispositionReceipt`, but only after every in-flight record has resolved
and the final observer STOP/snapshot/EOF/exact-reap sequence has completed. It
contains the terminal cause or normal-success marker, exact ledger or bounded
non-authorizing uncertainty envelope, cleanup facts, tuple receipts and
verdict. A shutdown failure is `UNCLEAR`; final-snapshot SecurityAgent is
`FAIL`, and neither can coexist with PASS. There is no alternate success
return and no failure branch that bypasses the receipt. `close` accepts only
that receipt, registers its close operation and consumes it once. After terminal, ordinary
compile/create/mount/detach, probes, inspect and Keychain cleanup are forbidden
except the already-authorized total disposition route.

### Descriptor-relative quarantine

Quarantine and approved image deletion never use a high-level rename, a
string-resolved absolute rename or an absolute fallback. Their shared routine:

1. opens the registered parent using
   `O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_DIRECTORY`;
2. opens the registered image leaf relative to that FD using
   `O_RDONLY | O_CLOEXEC | O_NOFOLLOW`;
3. verifies parent/image device, inode, mode and UID with `fstat` and
   `os.stat(old_leaf, dir_fd=parent_fd, follow_symlinks=False)` (the Python
   `fstatat` binding) against registry facts;
4. invokes libc `renameatx_np(parent_fd, old_leaf, parent_fd, new_leaf, RENAME_EXCL)`
   through a typed `ctypes` binding, where `new_leaf` is a unique registry-minted
   private quarantine or tombstone leaf;
5. treat `EEXIST` as `UnresolvedDeletionReceipt` with zero overwrite;
6. revalidate destination identity and source absence descriptor-relatively;
7. for approved deletion only, remove the tombstone fd-relatively without
   following symlinks, then prove old/tombstone absence;
8. close image and parent descriptors independently on every branch.

Only complete quarantine revalidation mints `QuarantineReceipt`; only complete
tombstone removal, both absence checks and every close mint
`ImageAbsentReceipt`. Collision, mismatch, removal error, revalidation error or
close failure is unresolved and preserves the exact old/new artifact ledger.

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
    "create",
    "mount",
    "verify_mount",
    "detach_absence",
    "advance_cycle",
    "cycles_complete",
    "inspect_one",
    "issue_cleanup_grant",
    "delete_keychain_zero",
    "delete_image",
    "terminal",
    "begin_disposition",
    "continuation_detach_absence",
    "issue_quarantine",
    "quarantine",
    "preserve_artifact",
    "cleanup_not_authorized",
    "terminal_after_keychain",
    "unresolved",
    "finalize_disposition",
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
5,399,043 effect traces; both alphabets therefore have exact cardinalities 15
and 22. Positive counters require at least one valid group signal, native
settlement, complete two-cycle success, Keychain-first approved deletion,
cleanup-not-authorized quarantine, unresolved preservation and disposition
close. Thus an empty reducer, reducer-stamped wrong index, missing success or
omitted valid path fails.

Explicit long traces exceed depth five. Process traces include a complete
spawn/identity/signal/exit/reap/group-absence/pipes-closed/frame-published
settlement, suspended cleanup with repeated non-exact wait results followed by
exact reap, and each replay after consumption. Effect traces include complete
create plus both indexed mount/verify/detach-absence cycles, one inspect,
Keychain delete/re-query before image deletion, cleanup-not-authorized
quarantine, terminal continuation, terminal after Keychain deletion,
unresolved preservation, exact disposition/final close, and replay at every
cursor, permit, terminal-transfer and disposition boundary.

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

The guardian probe route has this exact fixed vector; flag/value pairs are
strictly ordered:

~~~text
HELPER_PATH
--guardian-witness-probe MODE
--guardian-fd DECIMAL_FD
--witness-fd DECIMAL_FD
--control-fd DECIMAL_FD
--nonce LOWERCASE_HEX32
--test-supervisor-hard-deadline-ns DECIMAL_NS
~~~

`--test-supervisor-hard-deadline-ns` and its checked short-deadline validator
exist only inside `#if CORTEX_STORAGE_HELPER_TESTING` and only for
`--guardian-witness-probe`. They never enter the production argv parser or its
70-second admission. The testing binary accepts an exact
`CLOCK_MONOTONIC start + 2 s` supervisor hard deadline only on this route. A
production binary rejects both the testing flag and a production hard deadline
with only two seconds of phase fit before request acceptance, child spawn or
write. The guardian vector never contains the production deadline flag. A
paired oracle and atomic source mutant prove this separation.

### Guardian/witness contract

Before `Popen`, the outer parent creates the report pipe, GO pipe,
guardian/witness pipes, control socket, exec-status pipe, random
32-lowercase-hex nonce, reviewed helper path/source hash/binary hash and every
absolute phase deadline. It owns `report_r`, `GO_w`, `guardian_w`, `witness_r`,
`exec_status_r`, the control-parent endpoint and the one registered direct-child
obligation, plus the parent ends returned for the interpreter's stdin, stdout
and stderr pipes. The fresh interpreter owns the complementary endpoints. The
parent caps and drains report/stdout/stderr independently, requires every final
EOF and closes all parent endpoints independently. Every
child endpoint is greater than 2 and all are pairwise distinct.

The parent puts the exact ASCII decimal `parent_outer_hard` only in test-only
environment key `CORTEX_S3_PARENT_HARD_DEADLINE_NS`; the interpreter parses it
as a nonzero `UInt64`-range value and reports the identical integer. This key is
absent from ordinary/default environments and is never accepted by production
helper request parsing.

`FRESH_BOOTSTRAP_SOURCE` and literal `FRESH_BOOTSTRAP_SOURCE_SHA256` live in
`tests/disk_image_keychain_harness.py`. The parent hashes those exact UTF-8
bytes before every launch. The bootstrap is sealed: it performs no project
import or path lookup before its report and GO transition. `fresh_argv` is
exactly the absolute interpreter, isolation flags, source bytes and this
strictly ordered decimal-FD suffix:

~~~python
fresh_argv = [
    absolute_sys_executable,
    "-I", "-S", "-u", "-c", FRESH_BOOTSTRAP_SOURCE,
    str(report_w), str(go_r), str(guardian_r), str(witness_w),
    str(control_child), str(exec_status_w),
]
fresh_env = {
    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    "LANG": "C",
    "LC_ALL": "C",
    "CORTEX_S3_PARENT_HARD_DEADLINE_NS": str(parent_outer_hard),
}
~~~

The six operands accept canonical ASCII unsigned decimals only, are pairwise
distinct and greater than 2. A single bounded canonical configuration frame on
the child's stdin supplies the already sealed nonce, helper path/vector/digest,
source hash, binary hash and registered file facts; it is not argv or
environment authority. `fresh_env` has exactly the four keys above: no
inherited `HOME`, `PYTHONPATH`, `PYTHON*`, `DYLD*`, virtualenv or user-site
variable. `-I -S` plus the fixed source block prevents site/custom startup and
implicit project imports. The only parent spawn shape is exact:

~~~python
subprocess.Popen(
    fresh_argv,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    close_fds=True,
    pass_fds=(
        report_w,
        go_r,
        guardian_r,
        witness_w,
        control_child,
        exec_status_w,
    ),
    env=fresh_env,
    start_new_session=True,
)
~~~

The parent creates `exec_status_w` close-on-exec, but `pass_fds` necessarily
carries it through the first exec into the fresh interpreter. The fixed
bootstrap therefore immediately reasserts `FD_CLOEXEC` on `exec_status_w`,
verifies that every other passed child endpoint has the flag clear, and only
then inventories or reports. At that point `exec_status_w` alone has
`FD_CLOEXEC`. Before GO, the interpreter's bounded inventory must equal exactly
`{0,1,2,report_w,go_r,guardian_r,witness_w,control_child,exec_status_w}`.
Missing, extra, duplicate, stdio-aliased or wrong-CLOEXEC descriptors reject
before GO. Wrong flag order, missing isolation, extra/inherited environment,
changed bootstrap bytes/hash or any import before the report likewise rejects
before GO.

The interpreter executes only the fixed bootstrap, validates the inherited
shared-clock deadline, bounded configuration and descriptor inventory, and revalidates the
private helper target and parent as owner-only mode `0700`, plus the target's
registered device, inode, mode, UID and binary SHA-256. It writes one capped
structured report containing its exact `getpid`, absolute helper path, argv0,
complete fixed route vector and its digest, source SHA-256, binary SHA-256 and
deadline, plus `FRESH_BOOTSTRAP_SOURCE_SHA256`. It then waits for one GO byte and has not started or loaded the
helper/fixture. The parent requires report PID equal to registered
`Popen.pid`, exact nonce/deadline/path/argv/vector/digest/source/binary/
bootstrap hashes and exact FD inventory. Only then does it write one GO byte.

The interpreter closes report/GO endpoints and calls exactly
`os.execve(helper_path, helper_argv, helper_env)`. Successful exec atomically
closes `exec_status_w` through CLOEXEC; exact EOF on `exec_status_r` is the
parent's sole exec-success evidence. Exec failure writes exactly eight bytes,
ASCII `EXEC` followed by the unsigned big-endian errno, then `_exit(127)` for
`ENOENT` or `_exit(126)` for every other `OSError`. The parent accepts only
exec-status EOF or that fixed record plus reserved exit, and exact-waits the
same direct PID in either case.

macOS exposes no `fexecve` for this path. The design therefore does not claim
to eliminate the residual hash-to-`os.execve` replacement race against a
hostile same-UID actor; that actor remains outside the frozen threat model.

After successful exec, the helper's bounded inventory is exactly
`{0,1,2,guardian_r,witness_w,control_child}`. The helper remains the original
`Popen.pid`, owns and reaps its fixture, and never reports the fixture PID to
the parent. A silent, malformed, delayed or mismatched interpreter receives no
GO, is terminated/reaped as the direct child, and can have created no helper or
fixture. Dedicated matrices cover missing/extra/duplicate descriptors,
wrong-CLOEXEC status, malformed exec-status records and both reserved exec
failure exits.

Endpoint ownership and closure are executable, not advisory:

| Owner/transition | Required independent closes |
| --- | --- |
| Parent after successful `Popen` | Close child copies `report_w`, `go_r`, `guardian_r`, `witness_w`, `control_child`, `exec_status_w` immediately; write the sole bounded configuration frame, then flush and close the returned stdin writer. |
| Parent on spawn failure | Attempt both ends of report, GO, guardian, witness, control and exec-status independently; one close failure never suppresses another. |
| Bootstrap after its sole report | Close `report_w`; after its sole GO read close `go_r`; both close before `execve`; keep only `exec_status_w` CLOEXEC. |
| Helper after exec | Own only stdio, `guardian_r`, `witness_w`, `control_child`. |
| Helper after fixture spawn | Close its duplicate `guardian_r` and `witness_w`; the fixture owns only those two endpoints and never control. |
| Parent at terminal/mode cutoff | Close GO/report ends as soon as terminal, close `guardian_w` at the exact mode cutoff, drain/cap stdout, stderr, control, exec-status and witness, then exact-waitpid the direct helper. |

Every failure branch attempts every endpoint it still owns. One atomic retained
duplicate mutant exists for each EOF class—report, GO, exec-status, witness and
control—and no combined FD mutant may stand in for any of them.

A distinct Python-AST/source oracle verifies the parent call rather than
inferring it from runtime observations: exact bootstrap source/hash, absolute
`fresh_argv[0] == sys.executable`, ordered `-I -S -u -c`, the strict six
numeric operands, exact minimal environment, all three stdio pipes,
`close_fds=True`, the exact six-entry `pass_fds` tuple and
`start_new_session=True`. It separately proves the only handoff is absolute
`os.execve`, `helper_argv[0] == helper_path` and the exact registered test route
vector. Atomic mutants separately change one argv flag/order, environment key,
bootstrap byte/hash or pre-report import; omit one passed FD; inherit one stdio
stream; change only argv0 or exec path; or replace direct exec with a
process/shell launch. Each must fail its unchanged oracle.

Every cross-process timestamp uses the shared `CLOCK_MONOTONIC` domain:
Python calls only `time.clock_gettime_ns(time.CLOCK_MONOTONIC)` and Swift calls
only `clock_gettime(CLOCK_MONOTONIC)`. Python's convenience monotonic-nanosecond
API and `CLOCK_UPTIME_RAW` are forbidden for transmitted or cross-process
compared authority. Process-local elapsed diagnostics may use a local clock
only when they never enter a request, report, comparison, deadline or receipt.

The fixture creates no descendants, arms its `CLOCK_MONOTONIC` absolute
2.50-second self-expiry before START, writes bounded paced output, observes
guardian EOF, closes witness on exit and exposes no PID/PGID/watchdog receipt.
A compiler-AST oracle first requires the target to pass the unchanged
testing-mode `swiftc -typecheck` command, then obtains the AST only from the
same target with `xcrun swiftc -dump-ast -D
CORTEX_STORAGE_HELPER_TESTING`, using the Security, CoreFoundation and
CoreGraphics frameworks in both invocations. It starts at the exact
fixture-child entrypoint, resolves every reachable project-local function and
rejects unknown or dynamic call edges. Leaves are limited to an explicit
Darwin allowlist for argument validation, `clock_gettime`, `poll`, `read`,
`write`, bounded allocation, timer installation, `nanosleep`, `close` and
`_exit`. Spawn, fork, exec, shell, Foundation process APIs and dynamic loading
are not reachable leaves.

Each launched probe uses this immutable schedule from the parent's shared-clock
start:

~~~text
report_cutoff = start + 0.75 seconds
work_cutoff = start + 1.50 seconds
supervisor_hard = start + 2.00 seconds
fixture_self_expiry = start + 2.50 seconds
cleanup_reserve_start = start + 3.00 seconds
parent_outer_hard = start + 5.00 seconds
~~~

In deadline mode the parent closes `guardian_w` at exact work cutoff
`start + 1.50 s`. In cancellation mode it sends one `0x01` after `0x11` and
then closes `guardian_w`. Both modes require the fixture to observe guardian
EOF, exit, publish witness EOF, let the helper settle and let the parent
exact-reap the helper before `start + 2.00 s`. The `start + 2.50 s` fixture
self-expiry is only an independent failure-containment net and is never
accepted as a normal PASS witness. Cancellation additionally requires the
active child's matching `0x12`, witness EOF and then `0x13`, followed by
control EOF and exact direct-helper reap; `0x12` precedes `0x13`. Per-FD
ordering is exact, while witness EOF and control readiness may be observed in
either poll order.

Missing settlement at `start + 2.00 s` marks the helper/probe unresolved. The
fixture must nevertheless self-expire before cleanup reserve at
`start + 3.00 s`; witness EOF and complete libproc absence remain mandatory by
`start + 5.00 s`. A dedicated mutant that counts self-expiry as ordinary
success must fail the normal-deadline oracle.

At `cleanup_reserve_start`, no new report acceptance, GO, helper/fixture work
or child spawn may begin. The remaining two seconds permit only endpoint
closes, positive direct-PID TERM/KILL, exact waitpid, witness EOF verification
and one capped in-process survivor scan. The scan spawns no command. It checks
the unchanged deadline before and after every native call and returns exactly
`absent`, `found`, `incomplete`, `deadline` or `error`.

The first `proc_listallpids(NULL, 0)` result is treated as a PID count. After
checked capacity selection capped at 4,096 PIDs, the second call receives
exactly `capacity * MemoryLayout<pid_t>.size` bytes. A negative return, a
return equal to capacity, growth between count and fill, truncation or any
count/byte-unit inconsistency is `incomplete`, never absence. Complete
`proc_bsdinfo` filters current-UID candidates first. For each remaining
candidate, `sysctl(KERN_PROCARGS2)` first obtains a checked size and then reads
at most 4,096 bytes; exact argc and NUL framing are mandatory. `ESRCH`, `EPERM`,
`ENOMEM`, identity change, malformed framing or any other read error produces
`incomplete` or `error`, never absence. Candidate bytes are compared to the
nonce then zeroed/discarded immediately; no command line is retained. Only a
complete `absent` result passes. Mutants separately cover count-as-bytes,
full-buffer-as-absent, skipped procargs error, unbounded enumeration, retained
command bytes and replacement by a process-spawning scanner. Running out of
reserve is R43 failure, never a deadline extension.

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
`TASK_LOCAL_MUTANTS`. A missing new behavior is written first and must produce
a natural assertion RED before its implementation. Behavior intentionally
preserved from the baseline has `red_policy=baseline_characterization`; it must
be GREEN on `IMPLEMENTATION_BASE`, GREEN after its owner task and then fail its
post-GREEN mutant. The exact characterization-policy set is `R45`,
`S3T4_07` through `S3T4_11`, and `S3C4_01`. It is forbidden to manufacture a
RED by changing preserved behavior or an oracle. `S3C4_01` exercises all eight
valid unique permutations: both orders of the two required flags and all six
orders when `--cleanup-approved` is also present. Its mutant is exactly
`reject_permuted_effect_flags`.

Acceptance mechanisms such as manifest sealing, package generation and final
hash/path comparison use independently runnable synthetic self-tests before
the Task 5 commit. Their negative fixtures may be RED before the mechanism
exists; they never claim that a correct final repository state itself was RED.
Real-target spec-hash, plan-hash and cumulative-path runs occur only after the
Task 5 commit has frozen immutable `S3_FINAL=HEAD`. Each is then rerun against
`S3_FINAL`, followed by its synthetic negative fixture and mapped mutant using
code read from `S3_FINAL`, then restored to real-target GREEN without altering
that commit. Final implementation reviews cannot start earlier.

For a closed case key `K` and its mapped mutant `M`, the only acceptable mutant
assertion label is `MUTANT_K_M` after substituting the literal key and mutant
name, for example `MUTANT_R01_accept_unresolved_attach_output`. The runner
records that exact label, method ID and branch name. An import error, syntax
error, timeout, unrelated exception or different assertion label is not a
mutant-sensitivity receipt.

`MUTANT_MANIFEST` is a read-only mapping from every case in the three mutant
maps to one typed discriminated record:

~~~python
@dataclass(frozen=True, slots=True)
class RuntimeMutant:
    kind: Literal["runtime"]
    case: str
    owner: int
    test_id: str
    mutant_name: str
    target_file: str
    unique_anchor: str
    runtime_branch: str
    oracle_id: str
    oracle_sha256: str
    assertion_label: str
    red_policy: Literal["natural", "baseline_characterization", "synthetic_gate"]

@dataclass(frozen=True, slots=True)
class SourceMutant:
    kind: Literal["source"]
    case: str
    owner: int
    test_id: str
    mutant_name: str
    target_file: str
    unique_anchor: str
    replacement: str
    oracle_id: str
    oracle_sha256: str
    assertion_label: str
    red_policy: Literal["natural", "baseline_characterization", "synthetic_gate"]

MUTANT_MANIFEST: MappingProxyType[str, RuntimeMutant | SourceMutant]
~~~

Its keys equal exactly the union of `R01` through `R45`, every task-local key
and every characterization key: 45 normative, 123 task-local and one
separately named characterization case, hence 169 records. Its `test_id` and `mutant_name` projections
equal the corresponding test and mutant maps exactly. Each entry records one
owner, mapped test, kind, target file, unique literal or
compiler-AST anchor, one runtime branch or one replacement, transitive
oracle-closure SHA-256, exact assertion label and one `red_policy`.

Oracle closure hashing uses one non-recursive canonical serialization. It
starts with exact domain separator `CORTEX_S3_ORACLE_CLOSURE_V1\0`, then a
canonical metadata record for case/test/oracle/kind/target/anchor/
transformation, then the sorted source records
`(relative_path,start_byte,end_byte,bytes)` for the test method, every
transitively called oracle helper, runtime/source oracle constants and its
scanner/compiler wrapper. Strings and byte ranges use unsigned big-endian
length prefixes; integers are unsigned big-endian 64-bit; paths are normalized
repository-relative UTF-8; map keys and records are bytewise sorted.

Expected attestation-value fields—including every `oracle_sha256`, every value
in the literal `ORACLE_CLOSURE_SHA256` map and every duplicate expected-closure
field in a materialized manifest—are excluded from the closure payload and serialized at
their structural location with the single fixed placeholder
`<CORTEX_S3_EXPECTED_ATTESTATION_EXCLUDED>`. Field names, locations and all
other structural metadata remain covered. The computed digest is compared
outside that payload to the literal expected value. No oracle hashes bytes
that recursively contain the digest it is expected to equal. A determinism
oracle requires repeat serialization/digest equality; four atomic mutants
change one covered byte, the domain separator, the excluded-field rule and the
serializer to raw self-referential input respectively.

The resulting digest is frozen as a 64-lowercase-hex value when the owner task
reaches GREEN and recomputed before and after every mutant run.
Duplicate cases, names, anchors, tests, labels or manifest values fail import.
`red_policy` is exactly `natural`, `baseline_characterization` or
`synthetic_gate`; characterization and final-hash/package gates may not claim a
natural RED.

A runtime mutant operates only through its one named test-only branch in the
checkout. A source mutant exclusively creates one regular file with link count
one under the ignored SDD directory, verifies target and oracle hashes, applies
one unique typecheckable transformation, records original/derived/closure
hashes, runs the unchanged original oracle against the private copy, then
deletes the copy and proves no residual. It refuses tests, oracle files,
symlinks, hardlinks, multiple anchors and changed oracle closures. Source
mutants never edit or copy an oracle.

R44 and every structural declaration, signature or call-graph check are
normatively `kind=source`. R44's one replacement inserts a real
testing-only legacy route entry containing both handler and dispatch at the
unique Swift route-table anchor; the transformed Swift copy must typecheck and
the unchanged pre-default absence oracle must fail with
`MUTANT_R44_retain_legacy_process_route`. The fixture call-graph source mutant
likewise inserts one reachable forbidden spawn/exec leaf, must typecheck, and
must fail the unchanged compiler-AST oracle. String-only map checks are not
mutation evidence.

## Normative regressions

The implementation plan binds each ID to one unique fully qualified method and
one non-composite primary mutant.

| ID | Required oracle |
| --- | --- |
| R01 | Unresolved attach containing device text cannot mint compensation authority. |
| R02 | Exact output with present original group remains unresolved and cannot compensate. |
| R03 | Truncated attach output produces no receipt. |
| R04 | Capped attach output produces no receipt. |
| R05 | Settled attach permits one exact current-device detach plus its bound absence query and no free device input. |
| R06 | Held-pipe leader exit uses exited anchor; zombie `getsid == ESRCH` does not block exact wait/reap. |
| R07 | PGID reuse after reap permits only one token-bound signal-zero observation. |
| R08 | Validation consumes the suspended anchor; only exact validation mints validated-suspended authority, and every failed validation or non-resumed result permits no input/group signal and retains only positive-PID cleanup. |
| R09 | Full waitid matrix mints exited authority only for the exact terminal child. |
| R10 | Reap ECHILD remains unresolved with no settlement proof. |
| R11 | Insufficient command/finalization fit permits zero spawn. |
| R12 | The one-helper detach stage admits its exact full-fit cutoff; plus one nanosecond refuses. |
| R13 | The one-helper absence/response stage stops at exact `origin + 26 s`; plus one nanosecond refuses. |
| R14 | No normal, compensation or continuation stage can reset its original deadline. |
| R15 | Terminal pre-observation blocks every ordinary sealed method before spawn. |
| R16 | The persistent observer is compiled and baselined before helper compilation; detection/unavailability/compile failure consumes the sole no-artifact cursor into a preparation terminal receipt, closes through disposition and mints no live capability. |
| R17 | Caller operation, cleanup, path, device or argv cannot construct live work. |
| R18 | A replayed mounted-cursor continuation slot performs zero second helper spawn. |
| R19 | Each indexed mount cursor can issue only its one self-contained detach/absence transition. |
| R20 | Detach and absence occur inside one 26-second helper; no second helper or cross-process Swift token exists. |
| R21 | Every cursor/receipt effect is registered in flight; every normal/failure branch resolves its exact ledger or non-authorizing uncertainty envelope, completes observer STOP/final snapshot/EOF/reap, then mints exactly one `DispositionReceipt` and closes once. |
| R22 | Ambiguous current mapping advances only to `unresolved(ledger)` with no detach, query replay or mutation. |
| R23 | A terminal cause after Keychain deletion performs zero later Keychain effect and preserves the cursor ledger. |
| R24 | SecurityAgent verdict has priority through the final STOP snapshot; otherwise observer unavailability, including STOP/EOF/reap failure, has priority and cannot coexist with PASS. |
| R25 | Complete create and current indexed mount evidence is stored only in the advancing `ArtifactCursor` before terminal transfer. |
| R26 | Related partial or foreign-UID bridge permanently blocks cleanup. |
| R27 | Partial bridge to exact grandchild yields no signal or cleanup. |
| R28 | Zero record followed by live full reread stays partial. |
| R29 | Zero record followed by complete ESRCH reread is vanished. |
| R30 | Late child after adoption closure is never adopted or signalled. |
| R31 | Reused parent birth is never adopted or signalled. |
| R32 | Tracked UID, SID or group change expires authority before syscall. |
| R33 | TERM-to-KILL exited-anchor matrix blocks KILL on changed waitability/identity. |
| R34 | Once KILL is attempted, no later TERM/KILL is possible. |
| R35 | Exact validation creates only `validatedSuspended`; cancel and every non-resumed result atomically transfer to retained suspended cleanup, which survives every non-exact reap; all validation/resume/cancel races are total. |
| R36 | Every helper outcome carries a complete or settled-prefix trace proof and matches all six response values plus exact frame/exit/EOF/reap facts; count-only authority and skipped closes are rejected. |
| R37 | Valid-looking output with unresolved native settlement cannot succeed or mint a permit. |
| R38 | Shared `CLOCK_MONOTONIC` deadlines and clock jumps at every boundary permit no new action after the original hard deadline. |
| R39 | Entropy/Master/Wire/Keychain staging are disjoint and erased at exact app-owned boundaries. |
| R40 | Active fixture cancellation requires `0x01`, matching `0x12` before narrow `0x13`, witness EOF, control EOF and exact helper reap. |
| R41 | Production/testing route plus pre-GO/post-exec descriptor matrices reject missing, extra, duplicate or wrong-CLOEXEC FDs before effect. |
| R42 | Dynamic Python 3.11/3.14 inventories and ordered starts are identical with zero skip. |
| R43 | Exact sealed-bootstrap report-GO-exec probes use `-I -S -u -c`, minimal environment and complete FD-close ledger, keep the helper at `Popen.pid`, prove exec by CLOEXEC EOF, use bounded libproc absence, reserve 3-5 s cleanup, pass twenty fresh runs each and reject malformed/silent/delayed reports, retained EOF duplicates or exec failure. |
| R44 | Every legacy route literal, handler and test is absent before the default suite. |
| R45 | Every near-miss of each flag and the authorization key/value constructs zero live objects. |

## Review, checkpoint and S4 separation

Before Task 1, the ignored evidence ledger freezes `IMPLEMENTATION_BASE`, exact
reviewed spec/plan SHA-256 and
`PRIMER_DIFF_SHA256 = sha256(git diff --binary -- primer.md)`. Every task
records base/head, changed paths, RED/GREEN/mutant receipts and the unchanged
primer-diff hash. `primer.md` is never edited, staged or committed.

The documentation-review package uses the exact allowlist below and no glob:

~~~text
docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md
docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md
native/macos/disk_image_keychain.swift
tests/test_disk_image_keychain_helper.py
~~~

Its generator reads every byte with `git show DOC_CANDIDATE:path`, stores exact
path/size/SHA-256 in a canonical manifest, refuses a missing or extra entry,
symlink, hardlink or hash mismatch, and never traverses the ignored SDD review
tree. Prior findings, review receipts, verdicts, identities and conclusions are
outside the allowlist by construction. Negative self-tests inject one extra
entry, one wrong hash and one forbidden review path; each must fail before a
package exists. The three reviewers are fresh, read-only and mutually blind.

Before the Task 5 commit, final spec-hash, plan-hash and changed-path mechanisms
run only against synthetic positive/negative fixtures; no test may pretend a
real `S3_FINAL` exists. After that commit, freeze `S3_FINAL=HEAD` and require
exact repository state:

~~~text
git status --short --untracked-files=all
 M primer.md
~~~

The staged path list is empty. Spec, plan and primer-diff hashes are recomputed
and recorded from the immutable commit. The three real-target mechanisms then
run against `git show S3_FINAL:path` and the exact
`IMPLEMENTATION_BASE..S3_FINAL` diff. Each mapped synthetic negative fixture
and mutant runs afterward using code loaded from `S3_FINAL`; after restoration,
the real-target mechanism must be GREEN again and `S3_FINAL` must remain the
same commit. Local evidence additionally
requires all normative, task-local and characterization tests/mutants,
exhaustive/long models,
all branch matrices, Python 3.11/3.14 full suites, one in-suite and twenty fresh
runs of each real probe, executable production and observer Swift typechecks,
AST/source/route/FD/deadline/secret gates, `git diff --check`, both Gitleaks
scans and exact implementation paths.

The final implementation-review package is built only from
`git show S3_FINAL:path` blobs for this exact allowlist:

~~~text
docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md
docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md
native/macos/disk_image_keychain.swift
tests/disk_image_keychain_harness.py
tests/test_disk_image_keychain_helper.py
~~~

The same canonical manifest and three negative package self-tests apply. Before
generation and before any final review, independently recompute spec and plan SHA-256 from the
`S3_FINAL` blobs and compare them for equality with the frozen reviewed hashes;
recording without comparison fails. Independently compare the sorted
`IMPLEMENTATION_BASE..S3_FINAL` changed-path list with exactly the three
implementation paths declared in this design. Any mismatch, extra path or documentation drift freezes
S3.

Only after those post-commit receipts and status/hash/path comparisons pass may
three fresh final implementation reviews start. `S3_FINAL` is already frozen
before review and is not rewritten afterward. If all three pass, a separate
documentation-only S4 rebaseline may update
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
