# Cortex Bridge S3 Owned-Process Supervision Design

**Status:** Architecture A and written specification approved by the owner
**Date:** 2026-09-03
**Target:** v0.5.4 candidate
**Supersedes:** the incremental S3 supervision and live-harness design in the
current Phase S implementation plan; all other storage requirements remain in
force

## Decision

S3 will replace its current boolean-based process cleanup and effect routing
with three explicit boundaries:

1. a Swift owned-process supervisor whose only signal authority is an exact,
   unreaped Darwin session anchor;
2. a Python integration session whose monotone state and typed permits decide
   which commands may run after a terminal observer event;
3. a safe test architecture that models process trees in memory and gives the
   helper only one self-expiring direct fixture child for the real deadline
   probe; that fixture creates no descendants;
4. a bounded binary control channel through which Python asks the helper to
   cancel and settle its own active `hdiutil` session before Python may reap or
   escalate against the helper.

This is an architectural replacement, not a sixth incremental patch. S4 and
all later Phase S work remain blocked until this design is implemented, passes
the no-effect gates, and receives an independent approval.

No live Keychain, DiskImages, `hdiutil`, mount, detach, quarantine,
SecurityAgent, Chrome, runtime, push, merge, tag or release action is implied
or authorized by this design.

## Verified failure state

The candidate at `2b85e504f762dbc4ae89ce88c3478ccacedb6889` passed its
reported fake suite but failed independent review. The failure is structural:

- `ProcessInvocationFailure` exposes independently forgeable
  `directChildReaped` and `processGroupGone` booleans. Mount compensation can
  consume stdout containing a device receipt without first requiring a
  terminal process proof.
- Swift can reap the direct child and subsequently signal `-pid`. A recycled
  process-group identifier can therefore receive TERM or KILL without a
  current owned identity.
- Python uses `input_text` and `safety_only` as effect classification. A
  no-stdin compile or plist command can continue after a terminal observation,
  and the generic safety boolean can authorize arbitrary argv.
- The short Darwin process record contains PID, PPID, PGID and UID, but the
  current fallback retains only UID. A related foreign-UID or partial process
  can be excluded before lineage uncertainty is recorded.
- The default test suite creates real process trees, persists numeric PID/PGID
  receipts, probes them numerically, and can call `os.killpg` during cleanup.
  Those tests are not harmless merely because they avoid Keychain.
- The production mount compensation reserve overlaps two complete child
  teardown budgets. It can construct a verification command that has no valid
  work window.

The root cause is the absence of unforgeable process ownership, explicit
effect capabilities, and independent test oracles. Adding more conditionals to
the existing booleans would retain those defects.

## Goals

- Make it impossible for application or test code to signal a process group
  using only a numeric PID or PGID.
- Keep the exact direct child/session identity alive and unreaped until the
  last permissible group signal has been issued.
- Permit a mount compensation only after the preceding invocation has a
  complete output and a supervisor-created quiescence proof.
- Revoke every ordinary effect at the first SecurityAgent or observer-
  unavailable event, independently of stdin usage.
- Permit only exact, receipt-derived detach, absence verification and
  descriptor-relative quarantine after a terminal event.
- Preserve terminal cause priority and already parsed image/device receipts
  through nonzero responses and cleanup failures.
- Treat incomplete process metadata, lineage ambiguity, identity change,
  deadline exhaustion and cleanup uncertainty as fail-closed outcomes.
- Give every child invocation a disjoint work and finalization window inside
  one absolute request deadline.
- Preserve the helper as the sole owner of any isolated `hdiutil` session
  during terminal cancellation, and require a quiescent/unresolved
  acknowledgement before Python escalates against the helper.
- Replace dangerous real process-tree tests with deterministic model
  exploration and one harmless, externally witnessed direct-child probe.
- Retain the existing public helper JSON schema, Keychain schema, secret
  handling rules and effect gates.

## Non-goals

- No general macOS sandbox, cgroup substitute, Endpoint Security client,
  launch daemon or privileged broker.
- No attempt to supervise arbitrary hostile executables. Production execution
  remains limited to fixed Apple system binaries and the compiled Cortex
  helper.
- No claim that polling Darwin process metadata is an atomic proof against a
  malicious descendant that deliberately changes session.
- No live proof of Keychain UI suppression, `hdiutil` behavior, APFS mount
  behavior or SecurityAgent observation in this implementation phase.
- No change to storage paths, vault lifecycle, manifest installation, Chrome
  transport or user interface. S4's helper invocation interface must be
  rebaselined for the new deadline/control-channel contract before S4 starts.
- No weakening of timeouts, review thresholds, authorization gates or cleanup
  requirements to make tests pass.

## Alternatives considered

### A. Anchored supervisor and typed effect session — selected

Use a suspended, isolated Darwin session whose leader remains unreaped while
signals are possible. Replace generic Python runners with a closed command
catalogue and receipt-derived permits. Use a pure process model plus one direct
child probe.

This closes the identified races without introducing a privileged service or
changing the helper's public protocol.

### B. Separate broker or launch daemon — rejected for v0.5.4

A persistent native broker could own process lifetime and effects more
strongly, but it would add installation, upgrade, IPC, signing, permissions and
recovery surfaces before S4 exists. It is disproportionate to the fixed local
`hdiutil` use case.

### C. Extend the current booleans — rejected

Checking two more flags before detach would not close PGID reuse, generic
safety authorization, partial lineage, overlapping deadlines or dangerous
test cleanup. Five fix rounds have already demonstrated that this boundary is
not stable.

## Component boundaries

| File | Responsibility |
| --- | --- |
| `native/macos/disk_image_keychain.swift` | Production Keychain/DiskImages helper plus the internal typed Darwin supervisor. It remains one Swift source so S4's reviewed single-source attestation contract does not change. |
| `tests/disk_image_keychain_harness.py` | Test-only process model, scripted adapters, terminal effect session and gated live orchestration. It is not discovered as a test module and contains no default live execution. |
| `tests/test_disk_image_keychain_helper.py` | Assertions, exhaustive state traces, safe direct-child probe, CLI gate tests and authorized-live suite selection. It contains no raw process-tree cleanup. |

No S4-owned file changes in this rearchitecture.

## Swift owned-process supervisor

### Closed types

The production helper replaces `ProcessInvocationFailure` and its two booleans
with outcomes nested under `OwnedProcessSupervisor`:

```swift
struct ProcessBirthIdentity {
    let pid: pid_t
    let startSeconds: UInt64
    let startMicroseconds: UInt64
    let effectiveUID: uid_t
    let processGroupID: pid_t
    let sessionID: pid_t
}

struct OwnedProcessSupervisor {
    enum InvocationOutcome {
        case settled(SettledInvocation)
        case notSpawned(SpawnRefusal)
        case unresolved(UnresolvedInvocation)
    }

    struct SettledInvocation {
        let cause: InvocationCause
        let exitStatus: ExitStatus
        let stdout: CompleteCapturedOutput
        let stderr: CompleteCapturedOutput
        private let quiescence: ProcessQuiescenceProof
        private init(cause: InvocationCause, exitStatus: ExitStatus,
                     stdout: CompleteCapturedOutput,
                     stderr: CompleteCapturedOutput,
                     quiescence: ProcessQuiescenceProof) {
            self.cause = cause
            self.exitStatus = exitStatus
            self.stdout = stdout
            self.stderr = stderr
            self.quiescence = quiescence
        }
    }

    struct CompensableAttach {
        let device: String
        private let quiescence: ProcessQuiescenceProof
        private init(device: String, quiescence: ProcessQuiescenceProof) {
            self.device = device
            self.quiescence = quiescence
        }
    }

    private struct ProcessQuiescenceProof {
        let terminalGeneration: UInt64
    }
}
```

The proof, settled outcome, compensable attach, unreaped session anchor and raw
numeric process identifiers have nested `private` initializers. A static gate
permits their construction only inside the supervisor's validating reducers.
Scripted tests drive kernel events; they cannot instantiate a successful proof
or compensation permit.

`UnresolvedInvocation` may expose a stable reason, captured byte counts and
truncation flags. It never exposes captured stdout as a source of a device or
Keychain receipt.

`OwnedProcessSupervisor.compensableAttach(from:mountPath:)` is the only
`CompensableAttach` factory. It accepts a `SettledInvocation`, parses that
invocation's complete attach output internally, and returns a permit only for
exactly one device bound to the requested mount. Callers cannot supply a device
string independently of the settled output.

The create operation separates two secret lifetimes:

- `MasterSecret` remains owned by `perform` until `SecItemAdd` completes, then
  is zeroized in its enclosing `defer`;
- `WireSecret` is a per-invocation mutable copy used only by the child pipe and
  zeroized by the supervisor before any invocation outcome is returned.

Settling one child can therefore never zeroize the master before the Keychain
add.

### Kernel boundary

The supervisor is the only consumer of these closed kernel and I/O protocols:

```swift
enum TerminationSignal { case term, kill }

enum ExitObservation {
    case running
    case exited(ExitStatus)
    case interrupted
    case invalid(WaitFailure)
}

protocol ProcessKernel {
    func spawnSuspendedSession(_ request: SpawnRequest) throws -> SuspendedChild
    func exactIdentity(of child: SuspendedChild) -> IdentityObservation
    func resumeSuspended(
        _ anchor: UnreapedSessionAnchor,
        deadline: MonotonicInstant
    ) -> ResumeResult
    func abortAndReapSuspended(
        _ child: SuspendedChild,
        deadline: MonotonicInstant
    ) -> SuspendedAbortResult
    func observeExitWithoutReaping(
        _ anchor: UnreapedSessionAnchor
    ) -> ExitObservation
    func signalOwnedGroup(
        _ signal: TerminationSignal,
        anchoredBy anchor: UnreapedSessionAnchor,
        deadline: MonotonicInstant
    ) -> SignalResult
    func reapObservedChild(
        _ anchor: UnreapedSessionAnchor,
        deadline: MonotonicInstant
    ) -> ReapResult
    func observeGroupAfterReap(_ group: ReapedOwnedGroup) -> GroupPresence
}

protocol ProcessIO {
    func poll(_ request: PollRequest, deadline: MonotonicInstant) -> PollResult
    func read(_ descriptor: OwnedDescriptor, limit: Int,
              deadline: MonotonicInstant) -> IOResult
    func write(_ descriptor: OwnedDescriptor, bytes: UnsafeRawBufferPointer,
               deadline: MonotonicInstant) -> IOResult
    func close(_ descriptor: inout OwnedDescriptor,
               deadline: MonotonicInstant) -> CloseResult
}
```

The supporting types are closed as follows:

| Type | Closed values or fields |
| --- | --- |
| `MonotonicInstant` | finite monotonic seconds; ordering only, no wall clock |
| `SpawnRequest` | fixed executable, argv, sanitized environment, stdin/stdout/stderr and test-only inherited descriptor tuple |
| `SuspendedChild` | private spawned PID plus unconsumed ownership token |
| `IdentityObservation` | `exact(ProcessBirthIdentity)`, `incomplete`, `changed`, `unavailable` |
| `ResumeResult` | `resumed`, `childGone`, `unresolved` |
| `SuspendedAbortResult` | `exactlyReaped`, `unresolved` |
| `SignalResult` | `delivered`, `alreadyGone`, `identityChanged`, `unresolved` |
| `ReapResult` | `exact(ReapedOwnedGroup)`, `unresolved` |
| `GroupPresence` | `absent`, `present`, `unknown` |
| `PollResult` | ready-descriptor tuple, timeout, interrupted, failure |
| `IOResult` | byte count, EOF, would-block, interrupted, failure |
| `CloseResult` | closed, already-closed, failure |

`ScriptedProcessKernel`, `ScriptedProcessIO` and `ScriptedClock` emit only
these observations. They never return a settled invocation directly.

The Darwin adapter uses `POSIX_SPAWN_CLOEXEC_DEFAULT`,
`POSIX_SPAWN_SETSID` and `POSIX_SPAWN_START_SUSPENDED`. Before SIGCONT or one
stdin byte, it reads full `proc_bsdinfo`, obtains `getsid(pid)`, then rereads
full `proc_bsdinfo`. Both records must describe the same birth identity. It
requires:

- the spawned PID;
- the captured birth timestamp;
- the current effective UID;
- `processGroupID == pid`;
- `sessionID == pid`.

Any short, missing or contradictory identity kills only the still-suspended
direct child while it remains waitable, reaps that exact child, and returns
`unresolved`. `abortAndReapSuspended` uses no group signal and accepts success
only from `waitpid == exact pid` before its deadline.

With `POSIX_SPAWN_CLOEXEC_DEFAULT`, the production child inherits only stdin,
stdout and stderr. Testing builds may additionally inherit the exact guardian
and witness descriptors through `posix_spawn_file_actions_addinherit_np`; no
other descriptor is admitted.

### Lifecycle algorithm

The lifecycle is monotone:

```text
prepared
  -> suspended(anchor)
  -> running(anchor)
  -> exitObserved(anchor)
  -> terminating(anchor)
  -> reaped
  -> groupAbsent
  -> settled

Any state -> unresolved
```

Rules:

1. Reject spawn if the invocation window cannot contain its minimum work and
   complete finalization budget.
2. Create nonblocking CLOEXEC pipes and spawn the isolated suspended session.
3. Capture and validate the exact session anchor, then call
   `resumeSuspended(anchor, deadline)` before stdin.
4. Drain stdout and stderr fairly. Check the absolute work and hard deadlines
   before and after every read and append. Enforce an independent 1 MiB limit
   per stream in production.
5. Zero-initialize `siginfo_t`, then observe exit with
   `waitid(P_PID, childPID, WEXITED | WNOHANG | WNOWAIT)`. An exit exists only
   when return code is zero, `si_pid == childPID`, `si_signo == SIGCHLD`, and
   `si_code` is `CLD_EXITED`, `CLD_KILLED` or `CLD_DUMPED`. `si_pid == 0`
   means running. `EINTR` retries within the same deadline. Never reap in the
   drain loop.
6. During finalization, revalidate the unreaped anchor immediately before each
   permitted TERM or KILL. The adapter accepts the anchor token, never a raw
   integer.
7. Once KILL has been attempted, issue no further group signal.
8. Reap only after an exact exit observation. Only `waitpid == exact pid`
   proves reap; `ECHILD`, zero, identity mismatch or timeout is unresolved.
9. After reap, perform only a no-signal group absence observation. `ESRCH` is
   absent; success, `EPERM` or another error is unresolved.
10. Close every pipe independently, zeroize only the per-invocation wire
    secret and remain inside the hard deadline. Only then can the supervisor create
    `ProcessQuiescenceProof` and return `settled`.

The adapter's one internal negative-PGID signal site is allowed only inside
`signalOwnedGroup`, after exact unreaped-anchor validation. Its closed signal
enum permits TERM and KILL only. No other Swift or Python code can call it or
recover the raw PGID, and no TERM may follow a KILL.

### Invocation and compensation outcomes

`HdiutilRunning` changes from a throwing `Data` API to:

```swift
protocol HdiutilInvoking {
    func invoke(
        _ command: HdiutilCommand,
        secret: WireSecret?,
        window: InvocationWindow
    ) -> OwnedProcessSupervisor.InvocationOutcome
}
```

Every operation must pattern-match the outcome:

- `notSpawned` and `unresolved` prohibit every subsequent helper invocation;
- only `settled` output is parsed;
- a settled nonzero attach may yield `CompensableAttach` only from complete
  stdout containing exactly one valid device for the requested mount;
- truncated, capped, malformed or ambiguous output never yields a receipt;
- a detach requires `CompensableAttach`;
- the absence proof requires a separately settled `hdiutil info` response with
  zero matching devices and zero image entries;
- any missing proof returns the stable public code `MOUNT_CLEANUP_UNCLEAR`.

The helper's six-key JSON response remains unchanged.

### Helper cancellation control channel

Every production `disk-image-keychain` invocation receives one inherited Unix
`SOCK_STREAM | SOCK_CLOEXEC` control descriptor through
`--control-fd <decimal-fd>`. The JSON request remains on stdin and no secret
uses the control channel. The helper rejects an absent, duplicate, stdio,
closed, non-socket or extra control descriptor before parsing an effectful
request.

The binary protocol is one byte per frame:

| Direction | Byte | Meaning |
| --- | --- | --- |
| Python → helper | `0x01` | cancel the current operation |
| Helper → Python | `0x10` | request parsed; no child is active |
| Helper → Python | `0x11` | child anchor validated; child is active |
| Helper → Python | `0x12` | active child has a quiescence proof |
| Helper → Python | `0x13` | cancellation settled; no owned child remains |
| Helper → Python | `0x14` | cancellation unresolved; descendant survival is possible |

The helper sets the descriptor nonblocking and includes it in the same bounded
poll loop as stdin/stdout/stderr. On `0x01`, it closes child stdin, performs
anchored finalization, sends exactly one terminal cancellation frame, closes
the control descriptor and exits. `0x13` is emitted only after
`ProcessQuiescenceProof`; `0x14` never authorizes compensation or success.

Python sends `0x01` once when its observer enters terminal state. It waits for
the helper's terminal frame within the original absolute outer deadline. It
does not TERM/KILL/reap the helper before `0x13`, `0x14`, helper exit or expiry
of the helper's complete 70-second inner budget. If escalation is required
after that bound, Python may terminate only its exact unreaped helper child and
must return `UNCLEAR descendant_potentially_surviving`; it cannot claim that
the isolated `hdiutil` session was reached.

## Deadline policy

All deadlines are absolute monotonic timestamps. A retry never receives a new
request budget.

Production mount request:

```text
request hard deadline: 70 s
[ 0 s, 36 s) normal attach and validation, including child finalization
[36 s, 38 s) receipt parse and detach-permit transition
[36 s, 52 s) detach phase; admission closes at 38 s
[52 s, 54 s) detach-receipt and absence-permit transition
[54 s, 66 s) absence phase; admission closes at 54 s
[66 s, 70 s) pipe close, secret zeroization and response epilogue
```

Each spawned child reserves six seconds inside its own phase for TERM, KILL,
exact reap and final group observation. Therefore:

- `create` and `attach` require at least eight seconds of work before their
  six-second finalization reserve;
- `info` and `isencrypted` require at least four seconds of work before their
  six-second finalization reserve;
- the normal phase stops spawning whenever the selected command's minimum work
  plus six seconds no longer fit;
- detach is admitted no later than 38 seconds and has at least eight seconds
  of work plus six seconds of finalization before 52 seconds;
- absence is admitted no later than 54 seconds and has six seconds of work plus
  six seconds of finalization before 66 seconds;
- the two two-second transition reserves are not child work and cannot be
  borrowed;
- no compensation phase borrows from its successor.

The Python outer deadline is 115 seconds and is created once:

```text
1 s pre-observation
+ 70 s complete Swift request
+ 1 s post-observation
+ 14 s receipt-derived safety detach
+ 12 s receipt-derived absence proof
+ 2 s descriptor quarantine and ledger publication
+ 6 s Python helper/process finalization
+ 5 s scheduler/process margin
+ 4 s unallocated hard margin
= 115 s configured
```

No retry, observer event, cancellation frame or disposition transition resets
this timestamp. Admission is tested both at every cutoff and at cutoff plus one
monotonic tick.

These values are operational bounds, not real-time guarantees. A syscall that
does not return before a deadline produces an unclear/fail-closed result; the
deadline is not described as preemption.

## Python terminal effect session

### Monotone state

The live harness uses one session state:

```text
PREPARING -> ACTIVE -> CLOSED
                 \-> TERMINAL -> DISPOSING -> CLOSED
```

- `PREPARING`: no accepted observer baseline, zero effects.
- `ACTIVE`: complete baseline and ordinary permit available.
- `TERMINAL`: first SecurityAgent or observer-unavailable event, irreversible.
- `DISPOSING`: only receipt-derived safety permits are accepted.
- `CLOSED`: final verdict and artifact ledger frozen.

Terminal events are appended as immutable records containing cause, command,
stage and monotonic observation time. SecurityAgent always determines `FAIL
securityagent_detected`; otherwise observer unavailability determines
`UNCLEAR observer_unavailable`. Later cleanup errors are secondary evidence and
never overwrite that verdict.

### Typed permits

- `OrdinaryPermit(session, epoch)` is valid only in `ACTIVE` and is revoked
  permanently at `TERMINAL`.
- `CleanupGrant` is issued once by `authorize_cleanup(True)` only in `ACTIVE`
  when the separately gated CLI selection recorded cleanup approval. It can
  authorize exact disposable Keychain deletion only while the same session and
  epoch remain active.
- `DetachPermit` is created only from a parsed, recorded mount receipt and is
  bound to session, transaction, image, mount, UUID, device and epoch. It is
  emitted at most once and consumed at most once.
- `AbsencePermit` is emitted at most once from a successful exact detach and
  authorizes one fixed `hdiutil info -plist` absence query.
- `QuarantinePermit` requires the descriptor-bound image identity plus an
  immutable `PreTerminalUnmountedProof` or `DetachedUnmountedProof`. The first
  is recorded while `ACTIVE` from an already completed mapping receipt; the
  second is emitted only from the exact detach/absence chain.

All receipt collections are converted defensively to tuples in
`__post_init__`. Permits carry a closure-local token checked by identity plus a
private issuance/consumption registry and an epoch incremented on every
observation, including failed observations. This is a trusted-harness boundary,
not resistance to hostile Python introspection.

There is no `safety_only` argument, `disposition_active` flag or public generic
argv runner.

### Closed command catalogue

Workflow code can call only fixed methods:

```text
compile_helper
create_image
mount_image
detach_normal
inspect_item
delete_item
probe_encryption
probe_disk
probe_mapping
detach_for_disposition
prove_absence_for_disposition
quarantine_for_disposition
```

Each method owns a fixed executable, argv/request schema, effect class, stdin
policy, accepted return codes, output parser, cap and deadline profile.

After `TERMINAL`, compile, create, mount, inspect, delete, encryption/disk/
mapping probes and ordinary filesystem reconciliation are forbidden before
spawn. Only `detach_for_disposition`, its one exact absence proof and
descriptor-relative quarantine can proceed with matching permits. If any
permit or proof is unavailable, the artifacts are preserved without an
improvised query or deletion.

If a terminal event is observed while any ordinary process is already running,
the runner begins bounded cancellation immediately whether or not the command
has stdin. For the native helper it uses the control channel and preserves the
helper as owner of its `hdiutil` session. For direct compile/info processes it
uses the exact Python session anchor. Complete output may be parsed only to
retain a non-secret artifact receipt; it cannot authorize another ordinary
command.

Post-terminal detach does not call the helper's public `.detach` operation.
`detach_for_disposition` executes exactly
`/usr/bin/hdiutil detach <device-from-receipt>` through the anchored Python
adapter. `prove_absence_for_disposition` then executes exactly one
`/usr/bin/hdiutil info -plist`. No `isencrypted`, generic mapping preflight,
Keychain inspection or extra reconciliation is permitted between them.

### Artifact and disposition ledger

Replace `preserve_image_and_item` with typed states:

```text
image: absent | exact | quarantined | deleted | unknown
mount: proven_unmounted | exact_mounted | unknown
keychain: absent | exact_present | deleted | unknown
```

Every transition records its causal command receipt. A disposition receipt
states whether exact detach, absence proof and quarantine occurred and why any
artifact was preserved. A generic workflow exception cannot erase a captured
UUID, device or terminal cause.

## Exact process snapshots in the Python harness

The process adapter returns deeply immutable snapshots:

```python
@dataclass(frozen=True)
class ProcessSnapshot:
    exact_identities: tuple
    partial_identities: tuple
    vanished_pids: frozenset[int]
    enumeration_complete: bool
    tree_complete: bool
    uncertainty_reasons: tuple

    def __post_init__(self):
        object.__setattr__(self, "exact_identities", tuple(self.exact_identities))
        object.__setattr__(self, "partial_identities", tuple(self.partial_identities))
        object.__setattr__(self, "vanished_pids", frozenset(self.vanished_pids))
        object.__setattr__(self, "uncertainty_reasons", tuple(self.uncertainty_reasons))
```

An exact identity includes PID, PPID, PGID, UID and birth seconds/
microseconds. A short BSD record remains partial but retains PID, PPID, PGID
and UID.

Rules:

- collect the complete snapshot before filtering by UID;
- a partial or foreign-UID record linked by PPID/PGID to an owned identity is
  never adopted or signalled, but permanently marks lineage uncertain;
- zero bytes mean vanished only after an immediate full reread and `ESRCH`;
- adoption requires an exact same-UID child whose exact parent is active in the
  same complete snapshot;
- after adoption closes, a new related process permanently marks lineage
  uncertain;
- a historical or reused PID never becomes a parent;
- a signal permit requires a fresh complete snapshot proving the exact,
  same-UID anchored session membership and expires at the next observation;
- cleanup succeeds only with exact root reap, a complete final snapshot, no
  tracked survivor, no related partial/foreign process, no identity reuse and
  no lineage uncertainty.

The gated real harness uses the same unreaped-session-anchor rule as Swift. Its
private `DarwinOwnedProcessAdapter.signal_owned_group` is the only Python site
allowed to translate a validated, unconsumed anchor into a group signal. The
adapter revalidates the complete root/session identity immediately before the
signal; no caller receives its numeric PGID. The default suite never executes
that gated signal path. The harness does not use `Popen.communicate()` as a
terminal proof because that API reaps the child before group finalization.

## Safe test architecture

### Pure exhaustive model

All descendant, PID reuse, PGID reuse, UID transition, partial metadata,
observer ordering and deadline cases use scripted adapters and a deterministic
breadth-first exploration of short state traces. No third-party property-test
dependency is added.

After every transition, the model asserts:

- zero ordinary spawn or stdin write after a terminal event;
- no signal without a fresh exact identity and unreaped session anchor;
- no signal after reap;
- incomplete snapshot or uncertain lineage implies cleanup is not verified;
- no adoption after closure;
- no inspect or delete after a terminal event;
- complete response capture precedes nonzero/terminal propagation;
- no phase consumes another phase's deadline;
- all pipes receive an independent close attempt.

### Real harmless deadline and cancellation probes

The only default real-process test launches the testing helper as Python's
owned child. The helper exercises the production supervisor with exactly one
direct fixture child compiled into the testing build. That fixture creates no
descendant and exposes no PID or PGID receipt.

- Python owns a guardian pipe, witness pipe, control socket and random nonce.
- The child emits `START:<nonce>`, produces bounded continuous output, watches
  guardian EOF and arms its independent 0.90-second monotonic death timer before
  emitting START.
- The deadline case lets the 0.50-second supervisor deadline fire. The
  cancellation case sends `0x01` and requires helper `0x13` plus witness EOF
  before helper exit/final reap. The two descriptors may become readable in
  either polling order; the scripted kernel proves `0x13` is emitted only after
  internal quiescence.
- The test closes the guardian in `finally`, requires matching START and
  witness EOF, and reaps its own still-unreaped helper `Popen` child.
- If containment fails, direct `Popen.kill()` is permitted only while that
  exact child remains unreaped; no group signal is used.
- Test-owned limits are hard `0.50 s`, scheduler tolerance `0.15 s`, output cap
  `64 KiB`, outer containment `1.20 s`, and a final direct-helper kill/reap
  reserve of `0.15 s` inside that same absolute deadline.
- Helper completion and witness EOF are polled together. `witnessEOFAt` must be
  between 0.50 and 0.65 seconds after start in the deadline case; measuring
  before EOF is forbidden.
- After EOF and helper reap, one bounded `/bin/ps -axo command=` snapshot is
  filtered in memory for the nonce. Any scan failure/incompleteness or nonce
  match fails the probe; command lines are never logged or stored.
- External wall time, control frame, witness EOF and nonce absence are the real
  oracles. Exact fixture-child `waitpid` remains a scripted kernel-adapter proof
  with an omitted-reap mutant; the real probe does not claim to observe that
  syscall.
- Every wait derives its timeout from the one `started + 1.20 s` deadline. No
  relative timeout is added after it expires.

The real `ignore-term-grandchild` and numeric process-tree cleanup probes are
removed before the default suite can run again.

## Required regressions

The identifiers below are normative. The implementation plan maps every row to
one selected test ID and records its RED reason before the corresponding
implementation change.

| ID | Required test boundary | Required oracle |
| --- | --- | --- |
| R01 | unresolved attach containing device text | zero detach; `MOUNT_CLEANUP_UNCLEAR` |
| R02 | settled attach with group still present | zero detach |
| R03 | truncated attach output | zero receipt and zero detach |
| R04 | capped attach output | zero receipt and zero detach |
| R05 | exact settled attach | one detach followed by one absence proof |
| R06 | leader exit while descendant holds a pipe | all signals precede exact reap |
| R07 | PGID reuse after reap | observation only; zero signal |
| R08 | short/changed birth, UID, PGID or SID | zero stdin and zero group signal |
| R09 | waitid no-event, wrong PID/code, prefilled buffer and EINTR | only exact SIGCHLD terminal codes become exit |
| R10 | `ECHILD` from reap | unresolved, never a proof |
| R11 | insufficient work/finalization window | zero spawn |
| R12 | detach at admission cutoff and cutoff plus one tick | exact cutoff admitted; later time rejected |
| R13 | absence at admission cutoff and cutoff plus one tick | exact cutoff admitted; later time rejected |
| R14 | normal work at cutoff | compensation windows retain their original absolute bounds |
| R15 | terminal pre-observation for every ordinary command including normal detach | zero spawn regardless of stdin |
| R16 | terminal event during compile/info | immediate bounded cancellation; no workflow continuation |
| R17 | caller-supplied arbitrary argv | cannot obtain a safety permit |
| R18 | wrong/stale/replayed detach permit | zero spawn; exact first permit consumed once |
| R19 | two permits requested for one mount receipt | second issuance rejected before spawn |
| R20 | absence permit before versus after exact detach | only exact settled detach emits one permit |
| R21 | exact post-terminal disposition | direct `hdiutil detach <receipt-device>`, one `hdiutil info -plist`, then descriptor rename |
| R22 | unknown mapping after terminal | preserve without info, inspect, delete or quarantine |
| R23 | terminal path across all artifact states | no Keychain inspect/delete |
| R24 | all terminal/cleanup event orderings | SecurityAgent priority, otherwise observer-unavailable priority |
| R25 | complete nonzero create/mount response plus terminal event | UUID/device recorded before terminal propagation |
| R26 | short foreign-UID child of exact owned parent | permanent lineage uncertainty and cleanup false |
| R27 | partial bridge to exact grandchild | grandchild not signalled; cleanup false |
| R28 | zero/full-reread/live | partial identity, not vanished; cleanup false |
| R29 | zero/full-reread/`ESRCH` | exact vanished result |
| R30 | late child after adoption closes | no adoption/signal; cleanup never recovers |
| R31 | reused parent birth identity | no adoption/signal; cleanup never recovers |
| R32 | changed group membership after permit | stale permit rejected before syscall |
| R33 | identity changes between TERM and KILL | zero KILL; unresolved |
| R34 | state already issued KILL | zero later TERM or KILL |
| R35 | invalid identity for suspended child | bounded direct-child abort and exact reap; zero group signal |
| R36 | observer init, scan, cap, timeout, termination and every pipe-close exception | normalized terminal result plus every bounded cleanup/close attempt |
| R37 | valid output plus unclear process cleanup | never returns success or a compensation permit |
| R38 | clock jumps before/after poll/read/write/append/close/reap/scan | no action beyond the one hard deadline |
| R39 | create master and per-invocation wire secret | wire zeroized at child outcome; master remains through Keychain add then zeroizes |
| R40 | Python cancellation while fixture child is active | `0x01`; witness EOF and helper `0x13` precede helper exit/reap and outer deadline |
| R41 | production/testing builds and invalid testing FDs | production routes absent; invalid FDs exit 64 with zero spawn/write |
| R42 | default-test manifest under Python 3.11 and 3.14 | exact same IDs; every non-live class once; live class absent |
| R43 | deadline/cancel real probes repeated twenty times each | 40/40 within external bounds, matching nonce, EOF and no nonce survivor |
| R44 | structural source scan | no old numeric receipts/helpers, unique proof factories and signal sites only |
| R45 | missing-authorization CLI matrix in an environment allowlist | four exit-64 empty-output refusals and zero live-runner construction |

## Local proof gates

The checkpoint can be approved locally only when all of the following are
fresh:

- focused RED evidence exists before implementation changes for every R01–R45
  regression, including sensitivity traces for a false cleanup, stale permit,
  raw numeric signal and omitted reap;
- exhaustive process/effect traces through depth five run without state
  deduplication and pass against a separate reference predicate;
- `DEFAULT_TEST_CASES` is a closed ordered tuple; a meta-test proves every
  non-live `TestCase` and every `test_*` ID is selected exactly once, and the
  live class is absent;
- the exact default test-ID list is byte-identical under equipped Python 3.11
  and 3.14;
- the complete default Task 3 suite passes with zero skip in an `env -i`
  allowlist containing only fixed `PATH`, `LANG=C`, `LC_ALL=C` and
  `PYTHONHASHSEED=0`;
- the real guardian/witness deadline and cancellation probes pass once in-suite
  and twenty times as a flake gate;
- Swift production helper and extracted observer sources typecheck without
  execution;
- integration-only, effects-only, combined-effects and cleanup-only invocations
  each run in that same `env -i` allowlist, exit `64` with empty stdout/stderr,
  and construct neither live observer nor live effects. The only positive
  triple-gate test injects a recording `live_runner`; it never executes the live
  suite;
- the real authorization key remains exactly
  `CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION`; no similarly named substitute is
  accepted;
- Python compiles in memory; AST gates prove every subprocess/wait/scan has a
  bounded deadline and every `Popen` creates a new session;
- no Python group signal exists outside the private anchored
  `DarwinOwnedProcessAdapter.signal_owned_group`; no numeric PID/PGID receipt,
  `child_pid`, generic `safety_only`, `disposition_active`, or forgeable
  process-success boolean remains;
- the default suite proves the private Python group-signal adapter is never
  invoked;
- the only negative-PGID signal in Swift is private to the anchored Darwin
  kernel adapter;
- production compilation excludes all scripted-kernel, deadline-witness and
  cancellation-witness routes; invoking those routes returns exit 64 with
  empty output and zero spawn;
- testing builds reject identical, reversed, closed, stdio, regular-file and
  unlisted guardian/witness/control descriptors before child spawn or witness
  write;
- `git diff --check` and both Gitleaks history/worktree scans pass;
- the implementation diff from the separately recorded reviewed-plan base
  contains only the three files in this design;
- an independent reviewer reports `P0=0`, `P1=0`, `P2=0` and `PASS`.

No live integration result can be inferred from these gates. A later live
spike still requires a separate action-time authorization and must report
`PASS`, `FAIL` or `UNCLEAR` from actual evidence.

## Compatibility and rollout

- Keep the public six-key helper response and existing stable error codes.
- Keep the exact Keychain item attributes, 43-byte secret format, no-UI query
  policy, strict request schema and secret zeroization contract.
- Keep all live entry points behind the existing double gate and cleanup behind
  its separate approval.
- Layer the architectural commit after `2b85e504`; do not rewrite or hide the
  failed-review history.
- Mark S3 complete only after the local gates and independent review pass.
- Rebaseline and independently re-review S4 after S3. Its source-manifest shape
  remains single-source, but `run_attested_helper` must accept one absolute
  deadline, create/validate the helper control socket internally for
  `disk-image-keychain`, pass only the approved descriptor, and preserve the
  cancellation acknowledgement contract before process escalation.

## Residual limits

- Darwin has no public pidfd equivalent. The unreaped session anchor prevents
  reuse of the owned session leader while signals are possible, but it is not a
  general atomic identity-and-signal primitive.
- A deliberately hostile descendant can change session, close inherited pipes
  or block in the kernel. Such evidence is `UNCLEAR`; it is never converted to
  successful cleanup.
- `proc_pidinfo`, Security.framework and the scheduler are synchronous and not
  mathematically preemptible. Deadlines are operational bounds with
  fail-closed overrun handling.
- Killing `hdiutil` does not prove that no partial disk-image effect occurred.
  Only a settled invocation plus exact detach and absence proof permits
  compensation success.
- If the helper control channel cannot return a terminal frame after its inner
  deadline, Python cannot prove the isolated child session gone. Direct-helper
  escalation is permitted only with `UNCLEAR descendant_potentially_surviving`
  and no compensation success.
- Fake/model tests cannot prove actual Keychain UI absence, DiskImages behavior
  or observer completeness. Those claims remain unavailable until an expressly
  authorized live spike.
- The previously documented malicious same-UID filesystem replacement race
  remains outside the frozen threat model and is not broadened by this design.
