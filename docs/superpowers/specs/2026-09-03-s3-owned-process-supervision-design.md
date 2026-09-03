# Cortex Bridge S3 Owned-Process Supervision Design

**Status:** Architecture A approved by the owner; written specification pending review
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
3. a safe test architecture that models process trees in memory and uses only
   one self-expiring direct child for the real deadline probe.

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
  transport or user interface.
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
with closed outcomes:

```swift
struct ProcessBirthIdentity {
    let pid: pid_t
    let startSeconds: UInt64
    let startMicroseconds: UInt64
    let effectiveUID: uid_t
    let processGroupID: pid_t
    let sessionID: pid_t
}

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
    fileprivate let quiescence: ProcessQuiescenceProof
}

struct CompensableAttach {
    let device: String
    fileprivate let quiescence: ProcessQuiescenceProof
}
```

`ProcessQuiescenceProof`, `UnreapedSessionAnchor` and the raw numeric process
identifiers have `fileprivate` construction. Scripted tests drive a kernel
adapter; they cannot instantiate a successful process proof themselves.

`UnresolvedInvocation` may expose a stable reason, captured byte counts and
truncation flags. It never exposes captured stdout as a source of a device or
Keychain receipt.

### Kernel boundary

The supervisor is the only consumer of this protocol:

```swift
protocol ProcessKernel {
    func spawnSuspendedSession(_ request: SpawnRequest) throws -> SpawnedPID
    func exactIdentity(of child: SpawnedPID) -> IdentityObservation
    func observeExitWithoutReaping(
        _ anchor: UnreapedSessionAnchor
    ) -> ExitObservation?
    func signalOwnedGroup(
        _ signal: Int32,
        anchoredBy anchor: UnreapedSessionAnchor
    ) -> SignalResult
    func reapObservedChild(
        _ anchor: UnreapedSessionAnchor
    ) -> ReapResult
    func observeGroupAfterReap(_ group: ReapedOwnedGroup) -> GroupPresence
}
```

The Darwin adapter uses `POSIX_SPAWN_CLOEXEC_DEFAULT`,
`POSIX_SPAWN_SETSID` and `POSIX_SPAWN_START_SUSPENDED`. Before SIGCONT or one
stdin byte, it requires a complete `proc_bsdinfo` identity with:

- the spawned PID;
- the captured birth timestamp;
- the current effective UID;
- `processGroupID == pid`;
- `sessionID == pid`.

Any short, missing or contradictory identity kills only the still-suspended
direct child while it remains waitable, reaps that exact child, and returns
`unresolved`. It never signals a group from that incomplete state.

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
3. Capture and validate the exact session anchor before SIGCONT/stdin.
4. Drain stdout and stderr fairly. Check the absolute work and hard deadlines
   before and after every read and append. Enforce an independent 1 MiB limit
   per stream in production.
5. Observe exit with `waitid(P_PID, ..., WEXITED | WNOHANG | WNOWAIT)`.
   Never reap in the drain loop.
6. During finalization, revalidate the unreaped anchor immediately before each
   permitted TERM or KILL. The adapter accepts the anchor token, never a raw
   integer.
7. Once KILL has been attempted, issue no further group signal.
8. Reap only after an exact exit observation. Only `waitpid == exact pid`
   proves reap; `ECHILD`, zero, identity mismatch or timeout is unresolved.
9. After reap, perform only a no-signal group absence observation. `ESRCH` is
   absent; success, `EPERM` or another error is unresolved.
10. Close every pipe independently, zeroize the secret and remain inside the
    hard deadline. Only then can the supervisor create
    `ProcessQuiescenceProof` and return `settled`.

The adapter's one internal negative-PGID signal site is allowed only inside
`signalOwnedGroup`, after exact unreaped-anchor validation. No other Swift or
Python code can call it or recover the raw PGID.

### Invocation and compensation outcomes

`HdiutilRunning` changes from a throwing `Data` API to:

```swift
protocol HdiutilInvoking {
    func invoke(
        _ command: HdiutilCommand,
        secret: SecretBuffer?,
        window: InvocationWindow
    ) -> InvocationOutcome
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

## Deadline policy

All deadlines are absolute monotonic timestamps. A retry never receives a new
request budget.

Production mount request:

```text
request hard deadline: 70 s
[ 0 s, 40 s) normal attach and validation
[40 s, 54 s) exact detach compensation
[54 s, 66 s) exact absence verification
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
- detach has at least eight seconds of work plus six seconds of finalization;
- absence verification has at least six seconds of work plus six seconds of
  finalization;
- no compensation phase borrows from its successor.

The Python outer deadline is 85 seconds:

```text
1 s pre-observation
+ 70 s complete Swift request
+ 1 s post-observation
+ 6 s Python finalization
+ 5 s scheduler/process margin
= 83 s required; 85 s configured
```

These values are operational bounds, not real-time guarantees. A syscall that
does not return before a deadline produces an unclear/fail-closed result; the
deadline is not described as preemption.

## Python terminal effect session

### Monotone state

The live harness uses one session state:

```text
PREPARING -> ACTIVE -> TERMINAL -> DISPOSING -> CLOSED
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
- `CleanupGrant` can authorize exact disposable Keychain deletion only while
  the session remains `ACTIVE`; it never bypasses a terminal event.
- `DetachPermit` is created only from a parsed, recorded mount receipt and is
  bound to session, transaction, image, mount, UUID, device and epoch. It is
  single-use.
- `AbsencePermit` is created only by a successful exact detach and authorizes
  one fixed `hdiutil info -plist` absence query.
- `QuarantinePermit` requires the descriptor-bound image identity plus an
  unmounted proof from before the terminal event or from the exact
  detach/absence chain.

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
the runner begins bounded termination immediately whether or not the command
has stdin. Complete output may be parsed only to retain a non-secret artifact
receipt; it cannot authorize another ordinary command.

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

The process adapter returns:

```python
ProcessSnapshot(
    exact_identities=...,
    partial_identities=...,
    vanished_pids=...,
    enumeration_complete=...,
    tree_complete=...,
    uncertainty_reasons=...,
)
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

### One real harmless probe

The only default real-process test launches one direct child compiled into the
testing build. It creates no grandchild and exposes no PID or PGID receipt.

- Python owns a guardian pipe and a witness pipe plus a random nonce.
- The child emits `START:<nonce>`, produces bounded continuous output, watches
  guardian EOF and has an independent 0.90-second monotonic TTL.
- The test closes the guardian in `finally`, requires matching START and
  witness EOF, and reaps only its own still-unreaped direct `Popen` child.
- If containment fails, direct `Popen.kill()` is permitted only while that
  exact child remains unreaped; no group signal is used.
- Test-owned limits are hard `0.50 s`, scheduler tolerance `0.15 s`, output cap
  `64 KiB` and outer containment `1.20 s`.
- Wall time and witness EOF are external oracles. The test does not accept a
  budget, tolerance, PID, PGID or cleanup-success claim returned by the binary
  as its proof.

The real `ignore-term-grandchild` and numeric process-tree cleanup probes are
removed before the default suite can run again.

## Required regressions

The implementation plan must introduce RED tests for all of these boundaries:

1. settled receipt plus unreaped child: zero detach;
2. settled receipt plus non-absent group: zero detach;
3. truncated/capped attach output: zero detach;
4. exact settled attach: one detach, then one absence proof;
5. leader exit while a pipe remains open: signals occur only before exact reap;
6. PGID reuse after reap: observation only, no signal;
7. short or changed birth/UID/PGID/SID identity: zero stdin and zero group signal;
8. `ECHILD`: never a successful reap proof;
9. insufficient work/finalization window: zero spawn;
10. detach consuming its window: absence query is not spawned late;
11. terminal pre-observation blocks compile, plist commands and all helper
    operations independently of stdin;
12. arbitrary argv cannot acquire a safety permit;
13. terminal disposition accepts only a matching, single-use mount receipt;
14. missing mapping proof after terminal preserves without reconciliation;
15. terminal cause survives all success/nonzero/cleanup orderings;
16. short foreign-UID child of an exact owned parent blocks cleanup;
17. partial bridge to an exact grandchild blocks cleanup;
18. zero/full-reread/live differs from zero/full-reread/`ESRCH`;
19. late child, reused parent and changed group membership never regain cleanup
    success;
20. observer initialization, scan, cap, timeout, termination and pipe-close
    exceptions all produce bounded cleanup attempts and terminal normalization;
21. the process state model never emits a raw numeric signal target;
22. the real guardian/witness probe produces matching nonce, independent wall
    deadline, witness EOF and exact direct-child reap;
23. twenty consecutive real-probe runs complete without survivor or timeout;
24. static rejection of the previous numeric PID/PGID receipts and Python
    `os.killpg` cleanup.

## Local proof gates

The checkpoint can be approved locally only when all of the following are
fresh:

- focused RED evidence exists before production changes for every listed
  regression;
- exhaustive process/effect model passes with `PYTHONHASHSEED=0`, `LANG=C` and
  `LC_ALL=C`;
- the complete default Task 3 suite passes with zero skip and no authorization
  environment;
- the real guardian/witness probe passes once in-suite and twenty times as a
  flake gate;
- Swift production helper and extracted observer sources typecheck without
  execution;
- integration, effects-only, combined-effects and cleanup-only invocations all
  exit `64` with empty stdout/stderr when authorization is absent;
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
- `git diff --check` and secret scanning pass;
- the diff contains only the three files in this design;
- an independent reviewer reports zero Critical and zero Important finding.

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
- Rebaseline S4 from the approved S3 commit; S4 may then install and attest the
  same single Swift source without changing its planned source-manifest shape.

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
- Fake/model tests cannot prove actual Keychain UI absence, DiskImages behavior
  or observer completeness. Those claims remain unavailable until an expressly
  authorized live spike.
- The previously documented malicious same-UID filesystem replacement race
  remains outside the frozen threat model and is not broadened by this design.
