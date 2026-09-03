# Cortex Bridge S3 Owned-Process Supervision Design

**Status:** Revision 3 review candidate; implementation is frozen until the
exact spec and plan bytes receive three fresh blind read-only reviews with
`P0=0`, `P1=0`, `P2=0` and `PASS`
**Date:** 2026-09-04
**Reviewed baseline:** `2b407be00c9ff95ee64d62b52e7634576f12e051`
**Target:** v0.5.4 candidate
**Supersedes:** the incremental S3 supervision and live-harness design in the
current Phase S plan; all unrelated storage requirements remain in force

## Decision

S3 replaces its boolean process-cleanup and generic effect-routing boundaries
with four closed mechanisms:

1. a Swift supervisor whose only group-signal authority is a private,
   consumable `RunningSessionAnchor` or `ExitedUnreapedSessionAnchor`;
2. exact Swift command provenance and single-use issuance registries for
   settlement, attach compensation and absence verification;
3. a Python `LiveExecutionCapability` minted only by the exact live triple
   gate, plus typed workflow requests and receipt-bound terminal disposition;
4. a bounded Unix control socket and two independent exhaustive test models,
   with one self-expiring direct fixture child as the only real child route.

The previous exact bytes were rejected by three independent reviewers. This
revision is a design candidate, not implementation evidence. Task 1 cannot
start until this revision and its implementation plan pass the three required
reviews.

No live Keychain, DiskImages, `hdiutil`, mount, detach, quarantine,
SecurityAgent, Chrome, runtime, push, merge, tag or release action is
authorized by this document.

## Trust boundary and claim

Production process supervision is deliberately narrow:

- the executable is fixed to `/usr/bin/hdiutil`;
- the supervisor proves exact leader reap, successful closure of every
  supervisor-owned pipe, and absence of the original process group at one
  post-reap signal-zero observation;
- that evidence is named `NativeSettlementProof`;
- it does not prove that an intentionally escaping descendant cannot exist.

An observed escape, a related incomplete observation, a non-`ESRCH` group
observation, or any failed close yields an unresolved outcome and cancellation
byte `0x14`. A hostile descendant that changes session and avoids every bounded
observation is a residual limit. Neither `NativeSettlementProof` nor byte
`0x13` is described as descendant containment.

The test fixture uses the production supervisor but is not the production
trust boundary. It proves only the behavior of one fixed self-expiring direct
child and the external witness/nonce observations defined below.

## Goals

- Prevent raw PID or PGID metadata from becoming signal authority or a durable
  receipt.
- Keep the original leader waitable until the final permissible original-group
  signal has completed.
- Revalidate a running leader with the complete
  `proc_bsdinfo -> getsid -> proc_bsdinfo` sandwich.
- Revalidate an exited, unreaped leader with a second exact
  `waitid(WNOWAIT)` observation, without depending on `getsid` for a zombie.
- Require exact `waitpid == pid` before issuing a post-reap group observation
  token.
- Bind every Swift settled outcome and permit to one exact command context,
  output, image, mount and transaction.
- Stop every ordinary Python effect at the first terminal observer event,
  independently of stdin use.
- Permit post-terminal work only through a pre-existing receipt chain for one
  exact detach, one exact absence query and descriptor-relative quarantine.
- Give request input, control traffic, every child, cleanup and response
  emission finite portions of one absolute monotonic deadline.
- Keep Master and Wire secret allocations distinct and erase Wire before every
  outcome or terminal control frame.
- Replace dangerous real process-tree tests with independent process/effect
  models and one bounded guardian/witness fixture.
- Preserve the public helper response, stable error codes, exact Keychain
  schema, strict request keys and no-UI policy.

## Non-goals

- No general macOS sandbox, Endpoint Security client, privileged broker,
  launch daemon or pidfd substitute.
- No supervision claim for arbitrary hostile executables.
- No atomic identity-and-signal claim for Darwin process metadata.
- No live proof of Keychain UI suppression, DiskImages behavior, APFS mount
  behavior or SecurityAgent completeness.
- No change to storage paths, vault lifecycle, Chrome transport or UI.
- No S4 code in the S3 implementation range.
- No weakening of timeouts, authorization, cleanup or review gates.

## Component and file boundaries

| File | Responsibility |
| --- | --- |
| `native/macos/disk_image_keychain.swift` | Public Keychain/DiskImages helper, bounded request/control parser, private Darwin supervisor, exact command provenance, secret lifetime and testing-only Swift adapters. |
| `tests/disk_image_keychain_harness.py` | New test-only process/effect models, typed live session, closed requests, process adapter, helper control client, ledgers and deterministic trace reducers. |
| `tests/test_disk_image_keychain_helper.py` | Assertions, independent reference predicates, exhaustive traces, build/route gates, guardian/witness launchers, dynamic test inventory and the separately gated live class. |

Only these three files may change between `IMPLEMENTATION_BASE` and
`S3_FINAL`. The spec and plan belong to the preceding reviewed documentation
commit, not the implementation range.

## Swift owned-process supervisor

### Exact private authority

The supervisor owns these non-public types:

~~~swift
struct ProcessBirthIdentity: Equatable {
    let pid: pid_t
    let startSeconds: UInt64
    let startMicroseconds: UInt64
    let effectiveUID: uid_t
    let processGroupID: pid_t
    let sessionID: pid_t
}

struct MonotonicInstant: Comparable {
    let nanoseconds: UInt64

    static func < (lhs: MonotonicInstant, rhs: MonotonicInstant) -> Bool {
        lhs.nanoseconds < rhs.nanoseconds
    }
}

private struct RunningSessionAnchor {
    fileprivate let issuanceID: UInt64
}

private struct ExitedUnreapedSessionAnchor {
    fileprivate let issuanceID: UInt64
}

private struct ReapedGroupObservationToken {
    fileprivate let issuanceID: UInt64
}

private enum SignalAnchor {
    case running(RunningSessionAnchor)
    case exited(ExitedUnreapedSessionAnchor)
}
~~~

The issuance registry stores the `ProcessBirthIdentity`, current lifecycle
generation and consumption state. Copying a Swift value does not duplicate its
authority:

- exact suspended identity validation issues one
  `RunningSessionAnchor`;
- an exact `waitid(P_PID, pid, WEXITED | WNOHANG | WNOWAIT)` terminal
  observation consumes that running issuance and issues one
  `ExitedUnreapedSessionAnchor`;
- exact `waitpid == pid` consumes the exited issuance permanently and issues
  one `ReapedGroupObservationToken`;
- `observeGroupAfterReap` consumes that token before its sole signal-zero
  observation;
- a stale, forged, wrong-generation, wrong-command or already consumed value
  is rejected before any syscall.

A running anchor is revalidated immediately before SIGCONT and each TERM/KILL
through a complete first `proc_bsdinfo`, `getsid(pid)`, and complete second
`proc_bsdinfo`. Both records must equal the stored PID, birth seconds,
birth microseconds, effective UID and process group, and `getsid` must equal
the stored session.

An exited anchor is revalidated immediately before each TERM/KILL and reap by
zero-initializing `siginfo_t` and repeating exact waitable `waitid`. The
second observation must return zero with the exact child PID, `SIGCHLD` and
one of `CLD_EXITED`, `CLD_KILLED` or `CLD_DUMPED`. `getsid` is not called
after the exact exit transition; `getsid == ESRCH` for the zombie therefore
does not invalidate an otherwise exact exited anchor.

### Closed kernel and I/O contracts

~~~swift
enum TerminationSignal {
    case term
    case kill
}

protocol ProcessKernel {
    func spawnSuspendedSession(
        _ request: SpawnRequest,
        deadline: MonotonicInstant
    ) -> SpawnResult
    func validateSuspendedIdentity(
        _ child: SuspendedChild,
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
        _ child: SuspendedChild,
        deadline: MonotonicInstant
    ) -> SuspendedAbortResult
}

protocol ProcessIO {
    func poll(
        _ request: PollRequest,
        deadline: MonotonicInstant
    ) -> PollResult
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

The result spaces are exhaustive:

| Type | Values | Success rule |
| --- | --- | --- |
| `SpawnResult` | `spawned(SuspendedChild)`, `refused(SpawnRefusal)`, `deadlineExpired`, `failed(POSIXFailure)` | Only `spawned` proceeds. |
| `IdentityResult` | `exact(RunningSessionAnchor)`, `incomplete`, `changed`, `unavailable`, `deadlineExpired` | Only `exact` proceeds. |
| `ResumeResult` | `resumed`, `childGone`, `identityChanged`, `deadlineExpired`, `interruptedAtDeadline`, `failed(POSIXFailure)` | Only `resumed` proceeds. |
| `ExitObservation` | `running`, `exactExited(ExitStatus, ExitedUnreapedSessionAnchor)`, `wrongPID`, `wrongSignal`, `wrongCode`, `interrupted`, `deadlineExpired`, `failed(POSIXFailure)` | Only `running` or `exactExited` is non-failing. |
| `SignalResult` | `delivered`, `alreadyAbsent`, `identityChanged`, `notWaitable`, `permissionDenied`, `deadlineExpired`, `interruptedAtDeadline`, `failed(POSIXFailure)` | `delivered` proceeds; `alreadyAbsent` proceeds only for an exact exited anchor. |
| `ReapResult` | `exactlyReaped(ReapedGroupObservationToken)`, `stillRunning`, `noChild`, `wrongPID`, `deadlineExpired`, `interruptedAtDeadline`, `failed(POSIXFailure)` | Only `exactlyReaped` proceeds. |
| `GroupPresence` | `absentESRCH`, `present`, `permissionDenied`, `deadlineExpired`, `interruptedAtDeadline`, `failed(POSIXFailure)` | Only `absentESRCH` contributes to settlement. |
| `PollResult` | `ready(ReadySet)`, `timedOut`, `interrupted`, `deadlineExpired`, `failed(POSIXFailure)` | Ready proceeds; interrupted retries only while time remains. |
| `IOResult` | `bytes(Int)`, `endOfFile`, `wouldBlock`, `interrupted`, `brokenPipe`, `deadlineExpired`, `failed(POSIXFailure)` | Positive bytes, EOF and bounded retry states are non-failing in their valid context. |
| `CloseResult` | `closed`, `alreadyClosed`, `interruptedStateUnknown`, `deadlineExpired`, `failed(POSIXFailure)` | Only `closed` and `alreadyClosed` satisfy settlement. |
| `SuspendedAbortResult` | `exactlyReaped`, `stillRunning`, `noChild`, `wrongPID`, `deadlineExpired`, `failed(POSIXFailure)` | Only `exactlyReaped` proves direct-child abort. |

Invocation results are closed and constructor-controlled:

~~~swift
struct OwnedProcessSupervisor {
    enum InvocationOutcome {
        case settled(SettledInvocation)
        case notSpawned(SpawnRefusal)
        case unresolved(UnresolvedInvocation)
    }

    struct SettledInvocation {
        let exitStatus: ExitStatus
        let stdout: CompleteCapturedOutput
        let stderr: CompleteCapturedOutput
        private let context: ExactCommandContext
        private let settlement: NativeSettlementProof

        private init(
            exitStatus: ExitStatus,
            stdout: CompleteCapturedOutput,
            stderr: CompleteCapturedOutput,
            context: ExactCommandContext,
            settlement: NativeSettlementProof
        ) {
            self.exitStatus = exitStatus
            self.stdout = stdout
            self.stderr = stderr
            self.context = context
            self.settlement = settlement
        }
    }

    struct UnresolvedInvocation {
        let reason: UnresolvedReason
        let stdoutByteCount: Int
        let stderrByteCount: Int
        let stdoutTruncated: Bool
        let stderrTruncated: Bool
    }
}
~~~

`CompleteCapturedOutput` is issued only after EOF, a successful cap check and
successful closure. `UnresolvedInvocation` exposes no captured bytes, command
context, device, UUID or permit source. `SpawnRefusal` contains only a closed
non-secret reason. All successful constructors, including
`NativeSettlementProof`, remain private to validating supervisor reducers.

Every failing branch latches the invocation unresolved permanently. Later
success cannot erase it. Every owned descriptor is passed independently to
`ProcessIO.close` even after an earlier close result fails. If its deadline
has passed, the adapter returns `deadlineExpired` without issuing a new I/O
syscall; the invocation remains unresolved and process exit provides the final
kernel descriptor closure.

### Spawn, drain and lifecycle

Production spawn uses:

~~~text
POSIX_SPAWN_CLOEXEC_DEFAULT
POSIX_SPAWN_SETSID
POSIX_SPAWN_START_SUSPENDED
~~~

`POSIX_SPAWN_SETPGROUP` and `posix_spawnattr_setpgroup` are forbidden. Before
SIGCONT or child stdin, exact identity requires PID, birth seconds,
birth microseconds, effective UID, `processGroupID == pid` and
`sessionID == pid`. Invalid identity invokes only a positive-PID
direct-child abort while the suspended child remains waitable. It never issues
a group signal.

The monotone lifecycle is:

~~~text
prepared
  -> suspended
  -> running(RunningSessionAnchor)
  -> exited(ExitedUnreapedSessionAnchor)
  -> reaped(ReapedGroupObservationToken)
  -> originalGroupAbsent
  -> pipesClosed
  -> settled(NativeSettlementProof)

Any state -> unresolved
~~~

The supervisor:

1. refuses a spawn that cannot contain minimum work, finalization and epilogue
   inside the received absolute deadline;
2. creates nonblocking CLOEXEC pipes and the suspended session;
3. validates identity, rechecks control, revalidates the running anchor, then
   sends SIGCONT;
4. polls control, stdout, stderr and child stdin fairly; control readiness wins
   any simultaneous readiness set;
5. checks the hard deadline before and after poll, read, write, append,
   observation, signal, reap and close;
6. caps production stdout and stderr independently at 1 MiB;
7. never reaps in the drain loop;
8. on finalization, closes child stdin, revalidates the current running or
   exited anchor before TERM, repeats before KILL, and emits no signal after a
   KILL attempt;
9. obtains an exact exited anchor, exact reap token and one post-reap
   `absentESRCH` observation in that order;
10. attempts every pipe close independently and erases Wire;
11. issues `NativeSettlementProof` only when no unresolved branch was latched.

There are exactly two negative-PGID syscall categories inside each private
Darwin adapter:

- `signalOwnedGroup` translates a valid running or exited-unreaped anchor to
  TERM or KILL;
- `observeGroupAfterReap` translates a valid reap token to signal zero.

The Swift source has one call site for each category inside
`DarwinProcessKernel`. The Python live adapter has one call site for each
category inside `DarwinOwnedProcessAdapter`. Every `killpg` use and every
other negative target is forbidden. Positive-PID direct-child abort remains a
separate, typed suspended-child operation.

Both post-reap observation methods consume their token before the syscall, so
a copied or replayed token produces zero additional observation.

### Exact native settlement

`NativeSettlementProof` has a private initializer and is issued only after:

- exact `waitpid == originalLeaderPID` consumed the exited anchor;
- every supervisor-owned pipe returned `closed` or `alreadyClosed`;
- `observeGroupAfterReap` returned `absentESRCH` once for the original group;
- no failure, deadline overrun, identity change or incomplete observation was
  latched.

It proves those facts only. `present`, `permissionDenied`, an error, an
observed related escape, an incomplete descriptor close, or missing evidence
produces unresolved and cancellation byte `0x14`.

## Helper request and control boundary

### Production command line and descriptor provenance

The production helper accepts exactly:

~~~text
disk-image-keychain --control-fd DECIMAL_FD --swift-hard-deadline-ns DECIMAL_NS
~~~

Both decimals use ASCII digits only, have no sign or whitespace, reject a
leading zero except the single digit zero, and must fit their destination
integer. The deadline must be nonzero and later than the current
`CLOCK_MONOTONIC` value.

Python creates the Unix stream socket with CLOEXEC. `subprocess.Popen`
temporarily makes the child end inheritable because it is named in
`pass_fds`. Production therefore uses exactly:

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

Python closes the child socket end immediately after successful spawn and
closes both socket ends on spawn failure. No other descriptor is passed.

Before reading an effectful request, Swift validates that the inherited FD is
open, non-stdio, unique, connected, `AF_UNIX` and `SOCK_STREAM`. It then
immediately sets both `FD_CLOEXEC` and `O_NONBLOCK`. The FD is excluded from
all `hdiutil` file actions. A bounded `PROC_PIDLISTFDS` inventory must equal
stdin, stdout, stderr and that control FD in production; the testing route's
inventory additionally admits only its named guardian and witness FDs. An
absent, duplicate, closed, stdio, regular-file, wrong-family, wrong-type,
incomplete inventory or extra descriptor fails before request parsing, child
creation or write.

### Bounded request reader

`readDataToEndOfFile()` is forbidden. `BoundedRequestReader` shares the
received Swift hard deadline with `HelperControlChannel` and:

- polls stdin and control together;
- processes control first when both are ready;
- accepts at most 65,536 request bytes;
- requires stdin EOF before parsing;
- performs no JSON parse on a partial request;
- treats EAGAIN as a bounded retry, EINTR as a same-deadline retry, and every
  other read/poll failure as unresolved;
- discards and erases its request buffer on cancellation or terminal failure.

Cancellation before parse or before child creation issues a private
`NoActiveChildProof` and returns terminal frame `0x13`. A partial request
without EOF never spawns. If no cancellation arrives before the hard deadline,
the helper closes descriptors and exits invalid/unresolved; Python reports
`UNCLEAR` because no accepted-request or terminal acknowledgement exists.

### Binary grammar

Each frame is exactly one byte:

| Direction | Byte | Meaning |
| --- | --- | --- |
| Python to helper | `0x01` | Latch cancellation once. |
| Helper to Python | `0x10` | Strict ten-key request and transmitted absolute deadline accepted; no child is active. |
| Helper to Python | `0x11` | One original-group anchor is active. |
| Helper to Python | `0x12` | That active child produced `NativeSettlementProof`. |
| Helper to Python | `0x13` | Cancellation settled either before any child activation or through `NativeSettlementProof`. |
| Helper to Python | `0x14` | Cancellation unresolved; original-group or escaped-descendant survival is possible. |

The helper grammar is:

~~~text
start -> accepted
accepted -> active -> settled -> active
accepted -> active -> settled -> normal-exit
accepted -> cancel-settled
accepted -> active -> cancel-settled
accepted -> active -> cancel-unresolved
start -> cancel-settled
~~~

`accepted` emits `0x10` once. Each `active` emits `0x11` once. Its matching
`settled` emits `0x12` once. A mount request may repeat the
`0x11 -> 0x12` pair for distinct exact command contexts. `0x13` or `0x14` is
terminal and appears at most once.

Unknown Python bytes, a duplicate cancel byte, control EOF, socket close,
partial frames, duplicate `0x10`, `0x12` without an unmatched `0x11`,
two unmatched `0x11` frames, a nonterminal frame after cancellation, any
frame after `0x13` or `0x14`, helper exit without a terminal frame after
cancel, and a missing acknowledgement remain `UNCLEAR`. EAGAIN alone is not
terminal; it is retried only within the same deadline.

`observerTerminalLatchedAt` is the first Python terminal-observer timestamp.
After it, Python issues no new ordinary command, capability or unbound effect.
Only the already receipt-rooted disposition chain may continue.

`helperCancelLatchedAt` is the first Swift `0x01` timestamp. After it, Swift
does not spawn, SIGCONT, write child stdin, emit normal response bytes or emit
nonterminal control frames. The cancellation reducer may emit exactly one
`0x13` or `0x14` and close descriptors. Swift rechecks control immediately
before every spawn, SIGCONT, child write and nonterminal control write.

## Absolute deadlines

### Python outer and transmitted Swift deadline

For each live helper invocation Python creates one outer deadline at the first
pre-observation:

~~~python
outer_started_ns = time.monotonic_ns()
outer_hard_ns = outer_started_ns + 115_000_000_000
pre_observation_hard_ns = outer_started_ns + 1_000_000_000
~~~

After successful pre-observation, Python creates the Swift deadline exactly
once:

~~~python
swift_hard_ns = min(
    time.monotonic_ns() + 70_000_000_000,
    outer_hard_ns - 44_000_000_000,
)
~~~

It passes that exact non-secret integer through
`--swift-hard-deadline-ns`. Retry, parse delay, spawn delay, late `0x10`,
observer event, cancellation or disposition never changes either deadline.
Python does not TERM, KILL or reap a running helper before
`swift_hard_ns` unless the helper exits or sends terminal `0x13` or `0x14`.
A missing acknowledgement waits to the transmitted deadline, then exact
helper cleanup remains `UNCLEAR descendant_potentially_surviving`.

Swift never computes `now + 70 seconds`. It validates the received value and
derives `swift_epoch_ns = swift_hard_ns - 70_000_000_000`. Late request parse,
late `0x10` and delayed child spawn shorten the remaining phase. An expired,
overflowing or too-close deadline refuses work; it never creates a replacement
epoch.

### Swift production phase cutoffs

All values below are absolute offsets from `swift_epoch_ns`:

| Phase | Admission | Hard stop | Required work and finalization |
| --- | ---: | ---: | --- |
| normal create/attach/validation | command-specific fit before 36 s | 36 s | create/attach: 8 s work plus 6 s finalization; info/isencrypted: 4 s work plus 6 s finalization |
| attach receipt transition | 36 s | 38 s | no child |
| compensation detach | at or before 38 s | 52 s | 8 s work plus 6 s finalization |
| detach/absence transition | 52 s | 54 s | no child |
| absence info | at or before 54 s | 66 s | 6 s work plus 6 s finalization |
| response, close and erasure | 66 s | 70 s | no new child |

Cutoff equality is admitted only when the entire command-specific budget still
fits. Cutoff plus one monotonic nanosecond is refused. A phase never borrows
time from its successor.

The 115-second outer envelope reserves 1 second pre-observation, at most
70 seconds through the transmitted Swift deadline, 1 second post-observation,
14 seconds receipt-derived detach, 12 seconds absence proof, 2 seconds
descriptor quarantine/ledger publication, 6 seconds exact helper cleanup,
5 seconds scheduler/process margin and 4 seconds unallocated margin.

These are operational bounds, not syscall preemption claims.

## Swift command provenance and single-use permits

`HdiutilCommand` is a closed enum:

~~~swift
enum InfoPurpose: Equatable {
    case baseline
    case validation
    case postDetachAbsence
}

enum HdiutilCommand: Equatable {
    case create(image: String, volume: String, size: String, transaction: UUID)
    case attach(image: String, mount: String, transaction: UUID)
    case detach(device: String, image: String, mount: String, transaction: UUID)
    case info(image: String, mount: String, transaction: UUID, purpose: InfoPurpose)
    case isEncrypted(image: String, transaction: UUID)
}
~~~

`ExactCommandContext` stores the enum value, fixed executable, exact argv,
stdin policy, phase window and invocation generation. It is created only by
the closed command catalogue.

~~~swift
protocol HdiutilInvoking {
    func invoke(
        _ command: HdiutilCommand,
        secret: WireSecret?,
        window: InvocationWindow
    ) -> OwnedProcessSupervisor.InvocationOutcome
}
~~~

Every `SettledInvocation` privately retains its exact command context and
`NativeSettlementProof`. The supervisor's private issuance registry enforces:

- `issueAttachCompensationPermit(from:)` accepts only a settled
  `.attach(image, mount, transaction)`, complete uncapped stdout and exactly
  one valid device whose output mount equals that context's mount;
- callers cannot supply or replace the parsed device;
- consuming that permit constructs the single exact
  `.detach(device, image, mount, transaction)` command;
- `issueAbsenceQueryPermit(from:consuming:)` requires the exact settled detach
  produced by that permit and binds the next command to
  `.info(image, mount, transaction, purpose: .postDetachAbsence)`;
- absence succeeds only from that settled complete info output with zero
  matching devices and zero image entries;
- copied values, wrong context, wrong output, stale generation, second
  issuance and replay are rejected before spawn.

`notSpawned` and `unresolved` never expose parseable receipt authority.
Either outcome latches the enclosing helper request closed and prohibits every
later `HdiutilInvoking.invoke` call in that request.
Settled nonzero attach output may issue a compensation permit only when all
the preceding conditions hold. Missing evidence returns
`MOUNT_CLEANUP_UNCLEAR`.

## Secret lifetime

`MasterSecret` and `WireSecret` are distinct final classes backed by separate
erasable `UnsafeMutableRawPointer` allocations. Wire construction copies bytes
directly from Master without using `String`, `[UInt8]` or non-erasable
`Data`. Their allocation ranges must never overlap.

For create:

1. Master is generated once.
2. Each secret-consuming child receives a fresh Wire allocation.
3. Wire is erased before every `notSpawned`, spawn failure, invalid suspended
   identity, partial write, EPIPE, output cap, timeout, TERM/KILL result,
   `0x13`, `0x14`, close failure or returned invocation outcome.
4. Master remains readable through the exact `SecItemAdd` call.
5. Master is erased on every return or throw immediately after
   `SecItemAdd` completes or fails.

For mount, the Keychain result is held in a Master allocation, copied once to
Wire for attach, and erased after that invocation outcome. No outcome or
terminal frame may be emitted while Wire remains nonzero. Erasure failure is
unresolved and cannot produce success or `0x13`.

## Python live execution boundary

### Sealed capability and typed requests

The exact triple gate is:

- flags `--integration` and `--allow-effects`, each exactly once;
- environment key exactly
  `CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION`;
- environment value exactly `YES_DISPOSABLE_64_MIB_ONLY`.

`--cleanup-approved` is an optional third flag recorded inside the minted
capability. Prefix, suffix, case variants, duplicate flags, omitted flags,
extra flags and the old aliases are refused before observer or effects factory
construction.

Only the private gate function can register a `LiveExecutionCapability`.
`EffectSession` validates capability identity against that issuance registry
in its constructor. A field-equivalent or directly constructed value is
rejected.

`EffectSession.authorize_cleanup()` accepts no argument. It issues one
`CleanupGrant` only while ACTIVE and only if the registered capability
contains cleanup approval.

Workflow methods accept these frozen request types:

~~~python
@dataclass(frozen=True, slots=True)
class CreateImageRequest:
    image_path: Path
    volume_name: str
    size: str
    transaction_id: uuid.UUID

@dataclass(frozen=True, slots=True)
class MountImageRequest:
    image_path: Path
    mount_path: Path
    transaction_id: uuid.UUID
    expected_encryption_uuid: str

@dataclass(frozen=True, slots=True)
class DetachImageRequest:
    image_path: Path
    mount_path: Path
    transaction_id: uuid.UUID
    expected_encryption_uuid: str

@dataclass(frozen=True, slots=True)
class InspectItemRequest:
    image_path: Path
    transaction_id: uuid.UUID
    expected_encryption_uuid: str

@dataclass(frozen=True, slots=True)
class DeleteItemRequest:
    image_path: Path
    transaction_id: uuid.UUID
    expected_encryption_uuid: str
~~~

No request type contains `operation` or `cleanup_approved`. Private builders
construct the exact ten-key JSON object and set both values from the fixed
method and validated grant. Callers cannot provide a generic mapping or argv.

The public workflow catalogue is:

| Method | Authority and fixed effect |
| --- | --- |
| `compile_helper(source: Path, target: Path) -> CommandReceipt` | Ordinary capability; fixed Swift compiler invocation. |
| `create_image(request: CreateImageRequest) -> CommandReceipt` | Ordinary capability; exact create JSON. |
| `mount_image(request: MountImageRequest) -> CommandReceipt` | Ordinary capability; exact mount JSON. |
| `detach_normal(request: DetachImageRequest) -> CommandReceipt` | Ordinary capability; exact normal detach JSON. |
| `inspect_item(request: InspectItemRequest) -> CommandReceipt` | Ordinary capability; exact inspect JSON. |
| `delete_item(request: DeleteItemRequest, grant: CleanupGrant) -> CommandReceipt` | Active cleanup grant; exact delete JSON with approval true. |
| `probe_encryption(image: Path) -> CommandReceipt` | Ordinary capability; fixed `hdiutil isencrypted -plist`. |
| `probe_disk(device: str) -> CommandReceipt` | Ordinary capability; fixed `diskutil info -plist`. |
| `probe_mapping(image: Path, mount: Path) -> CommandReceipt` | Ordinary capability; fixed `hdiutil info -plist` parser. |
| `detach_for_disposition(permit: DetachPermit) -> DetachReceipt` | Exact `/usr/bin/hdiutil detach RECEIPT_DEVICE`. |
| `prove_absence_for_disposition(permit: AbsencePermit) -> DetachedUnmountedProof` | One exact `/usr/bin/hdiutil info -plist`. |
| `quarantine_for_disposition(permit: QuarantinePermit) -> QuarantineReceipt` | Descriptor-relative rename only. |

There is no generic runner, public argv, `safety_only` or
`disposition_active`.

### Separate observer and process data

`ObserverBaseline` and `SecurityAgentSnapshot` are frozen observer types.
`ProcessSnapshot` is the Darwin process-lineage type. They share no base class
or conversion. `EffectSession.activate` accepts only an exact complete
`ObserverBaseline`; observation accepts only `SecurityAgentSnapshot`; the
process tracker accepts only `ProcessSnapshot`. Cross-use raises before any
spawn. Activation also requires both observer collections to be empty; a
complete but nonempty baseline returns
`UNCLEAR securityagent_baseline_nonempty` before capability use or effect.

~~~python
@dataclass(frozen=True, slots=True)
class ObserverBaseline:
    processes: frozenset
    windows: frozenset
    complete: bool

@dataclass(frozen=True, slots=True)
class SecurityAgentSnapshot:
    processes: frozenset
    windows: frozenset
    complete: bool
    observed_at_ns: int
~~~

Every collection is defensively converted to tuple or frozenset in
`__post_init__`.

### Terminal state and receipts

~~~text
PREPARING -> ACTIVE -> CLOSED
                 \-> TERMINAL -> DISPOSING -> CLOSED
~~~

`EffectSession` exposes only these state transitions:

~~~python
def activate(self, baseline: ObserverBaseline) -> OrdinaryPermit
def ordinary_permit(self) -> OrdinaryPermit
def authorize_cleanup(self) -> CleanupGrant
def record_mount(self, receipt: MountReceipt) -> None
def record_preterminal_unmounted(
    self,
    receipt: CommandReceipt,
) -> PreTerminalUnmountedProof
def latch_terminal(self, event: TerminalEvent) -> None
def begin_disposition(self) -> None
def detach_permit(self, receipt: MountReceipt) -> DetachPermit
def absence_permit(self, receipt: DetachReceipt) -> AbsencePermit
def quarantine_permit(
    self,
    proof: PreTerminalUnmountedProof | DetachedUnmountedProof,
) -> QuarantinePermit
def close_success(self, receipt: CommandReceipt) -> FinalVerdict
def close(self, receipt: DispositionReceipt) -> FinalVerdict
~~~

The first SecurityAgent or observer-unavailable event sets
`observerTerminalLatchedAt` once and increments the session epoch. It revokes
ordinary authority permanently and immediately starts bounded cancellation of
the active command, with or without stdin. SecurityAgent determines
`FAIL securityagent_detected` whenever observed; otherwise observer
unavailability determines `UNCLEAR observer_unavailable`. Cleanup errors are
secondary evidence.

`DetachPermit` is issued at most once after `begin_disposition` from an exact
mount receipt recorded in the immediately preceding ACTIVE epoch. The registry
binds both that origin epoch and the current disposition epoch together with
session, transaction, image, mount, encryption UUID and device.
`AbsencePermit` is issued only from its exact successful detach in the same
disposition epoch.
`QuarantinePermit` requires the same descriptor-bound image and either a
pre-terminal exact unmounted proof or the exact detach/absence chain.

All permit values use a private issuance/consumption registry. Copying a value
does not duplicate authority. Wrong session, stale epoch, forged token, second
issuance or replay produces zero spawn.

After terminal, inspect, delete, compile, create, mount, normal detach,
encryption/disk/mapping probes and ordinary reconciliation are forbidden.
Only exact receipt-rooted detach, one absence query and descriptor-relative
quarantine may run. Unknown mapping preserves every artifact without query,
inspection, deletion or quarantine.

The receipt-to-permit derivation is internal safety-state reduction, not a new
ordinary effect or capability. A receipt from any epoch other than the
immediately preceding ACTIVE epoch is stale and cannot enter disposition.

Artifact state is:

~~~text
image: absent | exact | quarantined | deleted | unknown
mount: proven_unmounted | exact_mounted | unknown
keychain: absent | exact_present | deleted | unknown
~~~

Complete non-secret create or mount receipts are recorded before terminal or
nonzero propagation. Unresolved native output is never receipt authority.

### Python owned-process adapter

Direct compile and plist commands use private
`PythonRunningSessionAnchor` and `PythonExitedUnreapedSessionAnchor` values
with the same transition and revalidation rules as Swift. The adapter does not
use `Popen.communicate()` as terminal proof.

`ProcessSnapshot` retains exact PID, PPID, PGID, UID, SID and birth seconds/
microseconds, plus partial records retaining PID, PPID, PGID and UID. Raw
numeric fields may exist transiently inside these snapshots. They never form
signal authority or a durable receipt.

~~~python
@dataclass(frozen=True, slots=True)
class ExactProcessIdentity:
    pid: int
    ppid: int
    pgid: int
    uid: int
    sid: int
    start_seconds: int
    start_microseconds: int

@dataclass(frozen=True, slots=True)
class PartialProcessIdentity:
    pid: int
    ppid: int
    pgid: int
    uid: int
    missing_fields: frozenset[str]

@dataclass(frozen=True, slots=True)
class ProcessSnapshot:
    exact_identities: tuple
    partial_identities: tuple
    vanished_pids: frozenset[int]
    enumeration_complete: bool
    tree_complete: bool
    uncertainty_reasons: tuple
~~~

Lineage is computed before UID filtering. Related partial or foreign-UID
records, tracked UID/SID/group changes, late children, reused births,
incomplete scans and zero-byte records that remain live latch uncertainty
permanently. Only a zero-byte read followed by a full reread and `ESRCH`
produces a vanished PID.

For the native-helper path, `HelperControlClient` uses the exact transmitted
Swift deadline and frame grammar. It sends cancel once after
`observerTerminalLatchedAt` and never escalates early. `0x14`, missing ACK,
invalid order, socket failure or expiry returns
`UNCLEAR descendant_potentially_surviving`.

## Independent test architecture

### Process model

`ProcessModelReducer` owns its state and private permit registry. Its ordered
alphabet is:

~~~python
PROCESS_EVENTS = (
    "spawn_valid",
    "exact_child",
    "related_partial",
    "foreign_uid_bridge",
    "tracked_uid_changed",
    "tracked_sid_changed",
    "group_changed",
    "root_exit_exact",
    "exact_reap",
    "scan_incomplete",
    "late_child",
    "parent_birth_reused",
)
~~~

### Effect model

`EffectModelReducer` is independent of the process reducer and has its own
private permit registry. Its ordered alphabet is:

~~~python
EFFECT_EVENTS = (
    "activate",
    "ordinary",
    "mount_receipt",
    "issue_detach",
    "terminal",
    "consume_detach",
    "settled_detach",
    "consume_absence",
    "inspect",
    "delete",
)
~~~

Every model action records a zero-based `transition_index`. The reference
predicates live in `tests/test_disk_image_keychain_helper.py`, replay the raw
trace prefix through that index, consume only primitive action fields, import
no reducer state or permit type, and maintain their own expected issuance and
consumption sets.

Both explorers enumerate every product at every depth zero through five with
no visited set, state hash or deduplication. The process count is 271,453
traces and the effect count is 111,111 traces.

The reference predicates reject fresh forged permits, copied replay, stale
permits, raw numeric signals, signal after reap, signal after uncertainty,
omitted reap, false cleanup, and ordinary spawn/inspect/delete after terminal.

Separate scripted Swift matrices cover every value of `ResumeResult`,
`SignalResult`, `ReapResult`, `GroupPresence`, `PollResult`, `IOResult` and
`CloseResult`. Each pipe position fails independently. Process model cases
cover tracked UID and SID changes.

### Removal and closed testing routes

Before any default suite may run, source and tests for these routes are removed
completely:

~~~text
--spawn-probe
--fd-child
--deadline-drain-probe
--process-policy
--process-scenario
--process-child
~~~

Their Swift handler symbols and Python tests are also absent. Wire and CLOEXEC
assertions move to scripted scenarios or the new guardian/witness route.

The final closed testing-only route literal is:

~~~text
--test-scenario
--test-supervisor-scenario
--guardian-witness-probe
--guardian-witness-child
~~~

Every route is inside `#if CORTEX_STORAGE_HELPER_TESTING`. A production binary
rejects each supplied route with exit 64, empty stdout/stderr and zero spawn,
while `strings` finds neither route token nor handler symbol in that binary.
`--guardian-witness-child` is the only real child route.

### Guardian/witness probe

The test launcher owns guardian and witness pipes, a Unix control socket and a
random 32-hex nonce. The fixture:

- creates no descendant;
- arms its absolute self-expiry at start plus 0.90 seconds before emitting
  `START:NONCE`;
- emits bounded paced output;
- watches guardian EOF;
- closes witness on exit;
- exposes no PID or PGID receipt.

Its transitive closed call graph permits only argument validation,
`clock_gettime`, `poll`, `read`, `write`, bounded memory operations,
`nanosleep`, `close` and `_exit`. Reachability of `posix_spawn`, `fork`,
`vfork`, `exec`, `system`, Foundation `Process`, `NSTask` or dynamic loading
fails the structural test.

Each probe creates exactly:

~~~text
workCutoff = start + 0.50 seconds
supervisorHard = start + 0.65 seconds
outerHard = start + 1.20 seconds
~~~

The helper receives `supervisorHard` as its absolute test deadline. No
supervisor I/O or group signal is issued after it. Direct exact-helper
kill/reap containment and one bounded `/bin/ps -axo command=` nonce scan must
finish before `outerHard`. Command lines are filtered in memory and never
logged or stored.

The deadline probe requires witness EOF between 0.50 and 0.65 seconds. The
cancellation probe requires `0x11`, one `0x01`, witness EOF and `0x13` before
helper exit/exact helper reap; EOF and ACK may arrive in either polling order.
The real oracle does not claim to observe the fixture child's internal
`waitpid`. Exact child reap remains a scripted-kernel assertion with an
omitted-reap mutant.

### Dynamic default inventory

`DEFAULT_TEST_CASES` is a closed ordered tuple. At runtime a meta-test discovers
every class defined in `tests.test_disk_image_keychain_helper` whose direct or
indirect base is `unittest.TestCase` and whose `__module__` equals that module.
It excludes only the exact identity
`DiskImageKeychainLiveIntegrationTests`. The discovered identities must equal
the tuple identities; no class-name allowlist may replace this comparison.

`REGRESSION_TEST_IDS` has exact keys `R01` through `R45` and fully qualified
unittest IDs. Its 45 values are unique and each appears exactly once in the
flattened default suite.

The complete default suite runs independently under equipped Python 3.11 and
Python 3.14 in:

~~~text
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0
~~~

A recording result captures the ordered `startTest` ID stream. Both streams
must be byte-identical, both runs succeed, and neither contains a skip or the
live class. R42 compares the two interpreters through a non-executing
`default_test_ids()` subprocess so it cannot recursively run itself; the final
external gate runs both complete suites and compares their recorded
`startTest` streams. Nested same-interpreter launches use `sys.executable`.

## Normative regressions

Each identifier maps to one unique method in the implementation plan.

| ID | Boundary and required oracle |
| --- | --- |
| R01 | Unresolved attach containing device text: compensation reducer logs attach only and returns `MOUNT_CLEANUP_UNCLEAR`. |
| R02 | Attach has complete output and exact exit/reap but original group observation is present: supervisor returns unresolved and compensation reducer logs attach only. |
| R03 | Truncated attach output: compensation reducer logs attach only and issues no receipt. |
| R04 | Capped attach output: attach only, no receipt. |
| R05 | Exact settled attach: one detach, one bound info query, one absence proof. |
| R06 | Leader exit with held pipe, including post-WNOWAIT `getsid == ESRCH`: exited-anchor validation, all signals before exact reap. |
| R07 | PGID reuse after reap: token-bound signal-zero observation only, zero TERM/KILL. |
| R08 | Short or changed birth, UID, PGID or SID: zero SIGCONT, stdin and group signal. |
| R09 | waitid no-event, wrong PID, wrong signal/code, prefilled buffer and EINTR: only exact terminal child issues exited anchor. |
| R10 | `ECHILD` from reap: unresolved and no settlement proof. |
| R11 | Insufficient command work/finalization window: zero spawn. |
| R12 | Detach cutoff equality versus next nanosecond: equality admitted only if full fit; later refused. |
| R13 | Absence cutoff equality versus next nanosecond: equality admitted only if full fit; later refused. |
| R14 | Normal cutoff: compensation windows retain their original absolute bounds. |
| R15 | Terminal pre-observation across every ordinary typed method: zero spawn. |
| R16 | Terminal during compile or info: immediate bounded cancellation and no continuation. |
| R17 | Caller operation, cleanup mapping or arbitrary argv: construction rejected before live factory. |
| R18 | Wrong, stale, forged or replayed detach permit: zero spawn; exact first permit consumed once. |
| R19 | Two permits requested from one mount receipt: second issuance rejected. |
| R20 | Absence permit before versus after exact detach: only exact bound detach issues one. |
| R21 | Exact terminal disposition: direct receipt-device detach, one info query, descriptor rename. |
| R22 | Unknown mapping after terminal: preserve without info, inspect, delete or quarantine. |
| R23 | Every terminal artifact state: zero Keychain inspect/delete. |
| R24 | Every terminal/cleanup ordering: SecurityAgent priority, otherwise observer-unavailable priority. |
| R25 | Complete nonzero create/mount plus terminal: UUID/device recorded before propagation. |
| R26 | Related partial or foreign-UID record: permanent lineage uncertainty and cleanup false. |
| R27 | Partial bridge to exact grandchild: no grandchild signal and cleanup false. |
| R28 | Zero/full-reread/live: partial, not vanished, cleanup false. |
| R29 | Zero/full-reread/ESRCH: exact vanished result. |
| R30 | Late child after adoption closes: no adoption/signal and no recovery. |
| R31 | Reused parent birth: no adoption/signal and no recovery. |
| R32 | Tracked UID, SID or group change: permit expires before syscall. |
| R33 | TERM-to-KILL exited-anchor matrix, including `getsid == ESRCH`: exact second waitid can proceed; identity/waitability change blocks KILL. |
| R34 | KILL already issued: zero later TERM/KILL. |
| R35 | Invalid suspended identity: bounded positive-PID abort, exact reap, zero group signal. |
| R36 | Observer init/scan/cap/timeout/termination and every native/Python close result: normalized terminal outcome and every independent close attempt. |
| R37 | Valid output with unresolved native settlement: no success or permit. |
| R38 | Clock jump before/after every request/control/poll/read/write/append/close/reap/scan boundary: no new action after hard deadline. |
| R39 | Create/mount Master/Wire matrix across every terminal path: no alias, Wire erased first, create Master lives exactly through `SecItemAdd`. |
| R40 | Active-child cancellation: `0x01`, narrow `0x13` and witness EOF before helper exit/reap and outer deadline. |
| R41 | Production/testing route and FD matrices: production symbols absent; invalid descriptors refuse before spawn/write. |
| R42 | Dynamic default inventory on Python 3.11/3.14: byte-identical ordered IDs, every non-live class once, zero skip. |
| R43 | Deadline and cancellation probes twenty fresh runs each: 40/40 within bounds, matching nonce, EOF, ACK and no nonce survivor. |
| R44 | Structural scan: old routes absent, fixed command/capability factories sealed, and only typed signal sites remain. |
| R45 | Authorization-key prefix/suffix/case/old-alias and complete flag matrix: exit 64, empty streams and zero live object construction. |

## RED chronology and local proof gates

Before production code in each task, every mapped regression runs individually.
The ignored SDD ledger records the test-source SHA-256, interpreter path and
version, command, exit code, failing assertion and expected reason. If the
current implementation already passes a regression, the plan's exact unsafe
mutant for that ID is enabled and the same test must reject it, including R45.

Final local approval requires:

- every individual RED or mutant-sensitivity receipt;
- both exhaustive models through depth five without deduplication;
- complete result/close branch matrices;
- dynamic default inventory and executable `REGRESSION_TEST_IDS` proof;
- independent Python 3.11 and 3.14 default-suite passes with byte-identical
  ordered started-test streams and zero skip;
- one in-suite and twenty fresh runs of each real probe;
- Swift production and extracted observer typechecks without execution;
- four missing-authorization CLI shapes plus every key/flag near miss refusing
  before any live factory;
- production/test route and descriptor boundary proof;
- Python AST proof for absolute deadlines, `close_fds=True`, the exact
  production `pass_fds` tuple and `start_new_session=True`;
- source proof for no old routes, no `readDataToEndOfFile`, no generic request
  mappings, no process-success booleans, no unauthorized signal sites and no
  production testing symbol;
- `git diff --check` and both Gitleaks scans;
- exact implementation path set of the three component files;
- three fresh blind read-only final reviews with zero P0/P1/P2 and `PASS`.

No local gate implies a live integration result.

## Checkpoint, primer and S4 separation

Before Task 1 the ignored ledger freezes:

- `IMPLEMENTATION_BASE`;
- reviewed spec and plan SHA-256 values;
- `PRIMER_DIFF_SHA256` from
  `git diff --binary -- primer.md | shasum -a 256`.

Every task records `TASK_N_BASE`, `TASK_N_HEAD`, exact changed paths, test
receipt and the unchanged primer-diff hash. Reviewers receive both
`TASK_N_BASE..TASK_N_HEAD` and
`IMPLEMENTATION_BASE..TASK_N_HEAD`. `primer.md` is never edited, staged or
committed.

After final S3 review, freeze `S3_FINAL` before any S4 documentation. The
separate documentation-only S4 rebaseline commit may change exactly:

- `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md`;
- `docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md`;
- `docs/superpowers/plans/2026-09-02-v054-completion-program.md`.

That commit updates `run_attested_helper` to create and validate the helper
control socket internally, pass the exact absolute Swift deadline and sole
approved descriptor, preserve the cancellation acknowledgement contract, and
keep the single-source helper manifest. It is outside
`IMPLEMENTATION_BASE..S3_FINAL` and requires its own hashes and independent
review before S4 code starts.

## Compatibility and residual limits

- The public response remains exactly
  `schema_version`, `operation`, `code`, `encryption_uuid`, `device` and
  `item_count`.
- Existing stable error codes, Keychain attributes, 43-character Base64URL
  secret, no-UI queries and strict ten-key request remain unchanged.
- The live class remains separately selected and requires fresh action-time
  authorization; the default suite cannot select it.
- Darwin lacks a public pidfd equivalent. An unreaped leader prevents reuse of
  that leader identity while signals remain possible but is not an atomic
  identity-and-signal primitive.
- Synchronous Darwin and Security.framework calls are not mathematically
  preemptible; overruns fail closed.
- Killing `hdiutil` does not prove that no partial disk-image effect occurred.
- An escaped hostile descendant may evade the one original-group observation.
- Model and fixture tests do not prove real Keychain, DiskImages,
  SecurityAgent or APFS behavior.
- The previously documented malicious same-UID filesystem replacement race
  remains outside the frozen threat model.
