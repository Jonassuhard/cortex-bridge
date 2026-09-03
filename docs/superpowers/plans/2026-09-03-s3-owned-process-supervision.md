# S3 Owned-Process Supervision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task by task. Track every step with its checkbox and stop
> at the first failed gate.

**Goal:** Replace S3's forgeable process and effect authority with two exact
unreaped anchor states, narrow native settlement, absolute deadline/control
propagation, sealed command capabilities and closed harmless tests.

**Architecture:** The Swift helper owns a suspended `/usr/bin/hdiutil` session,
transforms a running anchor into an exited-unreaped anchor through exact
`waitid(WNOWAIT)`, and consumes the latter only through exact `waitpid`.
Python creates one outer deadline and one transmitted Swift deadline, owns the
helper control socket, and exposes only typed requests through a sealed live
capability. Process and effect traces use independent reducers and independent
raw-prefix predicates; the sole real fixture is one self-expiring direct child.

**Tech Stack:** Swift 6, Darwin `posix_spawn`/`proc_pidinfo`/`waitid`/
`waitpid`/`poll`, Security.framework, Python 3.11 and Python 3.14 standard library
`unittest`/`ctypes`/`subprocess`/`selectors`, Git and Gitleaks.

**Spec:** `docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md`

## Global constraints

- Work only in
  `/Users/asterion/Desktop/cortex-bridge/.worktrees/codex-v054-storage-consolidation`
  on `codex/v054-storage-consolidation`.
- Implementation cannot start until the exact revision-3 spec and plan receive
  three fresh blind read-only reviews with `P0=0`, `P1=0`, `P2=0` and
  `PASS`.
- Do not edit, stage or commit the pre-existing `primer.md` change.
- Between `IMPLEMENTATION_BASE` and `S3_FINAL` modify only:
  `native/macos/disk_image_keychain.swift`,
  `tests/disk_image_keychain_harness.py` and
  `tests/test_disk_image_keychain_helper.py`.
- Run no live Keychain, DiskImages, `hdiutil`, mount, detach, quarantine,
  SecurityAgent, Chrome, runtime, push, merge, tag or release action.
- Never define the action-time authorization environment during normal
  implementation gates. The exact key is
  `CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION` and the exact value is
  `YES_DISPOSABLE_64_MIB_ONLY`.
- Keep the public six-key response, strict ten-key request, existing stable
  error codes, Keychain attributes, 43-character Base64URL secret and no-UI
  query policy unchanged.
- Production execution is fixed to `/usr/bin/hdiutil`. Native settlement
  proves only exact leader reap, successful supervised-pipe closure and one
  absent original-group observation after reap.
- A raw PID or PGID may exist transiently in a process snapshot. It is never
  signal authority or a durable receipt.
- Every retry and every I/O, scan, wait, signal, close and subprocess action
  consumes a finite part of one absolute monotonic deadline.
- Every task has one writer, one dedicated commit and a fresh read-only
  spec-compliance plus code-quality review before the next task.
- No S4 implementation file changes during S3.

## Mandatory pre-implementation review gate

- [ ] Freeze the documentation candidate commit and compute both SHA-256
  values from that commit.
- [ ] Give three reviewers the same spec bytes, plan bytes, consolidated
  rereview findings and baseline `2b407be00c9ff95ee64d62b52e7634576f12e051`.
  Do not provide one reviewer's verdict to another reviewer.
- [ ] Require each reviewer to return counts for P0, P1 and P2 plus a
  `PASS`/`FAIL` verdict. Any P0-P2 finding or non-PASS verdict keeps Task 1
  frozen.
- [ ] Record the three review receipts in the ignored directory
  `.superpowers/sdd/2026-09-03-s3-owned-process-supervision/`.

## Checkpoint and individual RED protocol

Before Task 1, run these read-only commands and write their exact outputs to
the ignored implementation ledger:

~~~bash
git symbolic-ref --short HEAD
IMPLEMENTATION_BASE=$(git rev-parse HEAD)
SPEC_SHA256=$(shasum -a 256 docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md | awk '{print $1}')
PLAN_SHA256=$(shasum -a 256 docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md | awk '{print $1}')
PRIMER_DIFF_SHA256=$(git diff --binary -- primer.md | shasum -a 256 | awk '{print $1}')
git status --short
~~~

The status must contain only the pre-existing `primer.md` modification.
`IMPLEMENTATION_BASE` must contain the reviewed documentation bytes.

At the beginning of every task:

~~~bash
TASK_N_BASE=$(git rev-parse HEAD)
git diff --binary -- primer.md | shasum -a 256
git status --short
~~~

Immediately before that task's commit:

~~~bash
git diff --name-only
git diff --check
~~~

Immediately after that task's commit:

~~~bash
TASK_N_HEAD=$(git rev-parse HEAD)
git diff --name-only "$TASK_N_BASE..$TASK_N_HEAD"
git diff --name-only "$IMPLEMENTATION_BASE..$TASK_N_HEAD"
git diff --binary -- primer.md | shasum -a 256
~~~

The primer hash must equal `PRIMER_DIFF_SHA256`. The task diff may contain
only that task's declared files; the cumulative diff may contain only the three
S3 implementation files. Each reviewer receives both
`TASK_N_BASE..TASK_N_HEAD` and `IMPLEMENTATION_BASE..TASK_N_HEAD` plus the
task's test receipt.

Task 1 installs the final `REGRESSION_TEST_IDS` and
`REGRESSION_MUTANTS` dictionaries. Before changing non-test behavior in a
task, run every ID owned by that task separately under Python 3.11:

~~~bash
PYTHON311="$PWD/.venv/py311/bin/python"
TEST_SOURCE_SHA256=$(shasum -a 256 tests/test_disk_image_keychain_helper.py | awk '{print $1}')
RID=R01
TEST_ID=$("$PYTHON311" -c 'import sys; from tests.test_disk_image_keychain_helper import REGRESSION_TEST_IDS; print(REGRESSION_TEST_IDS[sys.argv[1]])' "$RID")
set +e
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" -m unittest "$TEST_ID" -v
RED_EXIT=$?
set -e
~~~

Record `RID`, `TEST_ID`, `TEST_SOURCE_SHA256`, interpreter path/version,
`RED_EXIT`, failing assertion and expected cause. If `RED_EXIT` is zero,
enable the exact closed mutant named for that ID and require the same test to
fail:

~~~bash
set +e
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" CORTEX_STORAGE_TEST_MUTANT="$RID" \
  "$PYTHON311" -m unittest "$TEST_ID" -v
MUTANT_EXIT=$?
set -e
test "$MUTANT_EXIT" -ne 0
~~~

The failure must name the `RED_Rxx` assertion declared for that ID. An import
failure, syntax failure, unrelated exception or different assertion is not a
valid RED receipt. Repeat the commands with each mapped ID; a loop may
mechanize the repetition but may not combine IDs into one unittest process.

---

### Task 1: Install closed regressions and replace every legacy real-process probe

**Files:**

- Create: `tests/disk_image_keychain_harness.py`
- Modify: `tests/test_disk_image_keychain_helper.py`
- Modify: `native/macos/disk_image_keychain.swift`

**Interfaces:**

- Produces immutable process/effect model values, independent reducers,
  zero-based action indices and private model permit registries.
- Produces the final `DEFAULT_TEST_CASES`,
  `REGRESSION_TEST_IDS` and `REGRESSION_MUTANTS` structures before production
  behavior changes.
- Removes six obsolete route tokens, their Swift handlers/call graph and their
  Python tests before any default suite is executed.
- Retains `DiskImageKeychainLiveIntegrationTests` as the only excluded
  `TestCase`.

- [ ] **Step 1: Write all final regression methods and executable maps**

Add the classes named in the normative map at the end of this plan. Every
method must contain its final assertions before its owning implementation task
starts. Imports of not-yet-created product types occur inside the method or
through a test fixture that reports the exact `RED_Rxx` assertion instead of
preventing module import.

Define `REGRESSION_TEST_IDS` and `REGRESSION_MUTANTS` exactly as shown in the
normative section. In `setUp`, read
`CORTEX_STORAGE_TEST_MUTANT`, validate it against the closed dictionary and
inject only that method's scripted adapter mutation. The variable is
test-module-only and never read by Swift or live production code.

- [ ] **Step 2: Add dynamic inventory before selecting a default suite**

Use this final tuple:

~~~python
DEFAULT_TEST_CASES = (
    DiskImageKeychainHelperTests,
    DiskImageKeychainIntegrationOrchestrationTests,
    DiskImageKeychainHarnessSafetyTests,
    DiskImageKeychainProcessModelTests,
    DiskImageKeychainEffectModelTests,
    DiskImageKeychainSwiftSupervisorTests,
    DiskImageKeychainMountCompensationTests,
    DiskImageKeychainTerminalEffectTests,
    DiskImageKeychainContainedProcessProbeTests,
    DiskImageKeychainBuildBoundaryTests,
    DiskImageKeychainManifestAndGateTests,
)
~~~

The meta-test discovers module-owned `unittest.TestCase` identities at runtime:

~~~python
def module_test_case_inventory(module):
    return tuple(
        value
        for value in vars(module).values()
        if isinstance(value, type)
        and issubclass(value, unittest.TestCase)
        and value.__module__ == module.__name__
    )

discovered = set(module_test_case_inventory(sys.modules[__name__]))
expected = set(DEFAULT_TEST_CASES)
excluded = {DiskImageKeychainLiveIntegrationTests}
self.assertEqual(discovered - excluded, expected)
self.assertEqual(discovered - expected, excluded)
self.assertEqual(len(DEFAULT_TEST_CASES), len(expected))
~~~

Flatten the selected suite, count every `test.id()`, require each count to be
one, require the 45 regression values to be unique, and require every
regression value count to be one. Add an AST assertion that every
`unittest.TestCase` class is top-level so the runtime inventory cannot miss a
nested class. Expose `build_default_suite(loader)` and non-executing
`default_test_ids()` helpers; neither selects the live class.

- [ ] **Step 3: Write independent process and effect model reducers**

In `tests/disk_image_keychain_harness.py` define:

~~~python
@dataclass(frozen=True, slots=True)
class ModelAction:
    transition_index: int
    kind: str
    authority_id: str | None
    command: str | None
    result: str | None

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

`ProcessModelReducer` and `EffectModelReducer` have different state classes,
different issuance dictionaries and different consume methods. A permit
contains an opaque string identifier registered by its reducer; equality of
fields cannot forge registration.

Each explorer is the direct product without state deduplication:

~~~python
def every_trace(events, max_depth=5):
    for depth in range(max_depth + 1):
        for trace in itertools.product(events, repeat=depth):
            yield trace
~~~

Require exactly 271,453 process traces and 111,111 effect traces. Every action
stores the index of the event that produced it.

- [ ] **Step 4: Write reference predicates in the test module**

The two reference predicates accept only immutable tuples of strings and
immutable tuples of `ModelAction` values. They do not import reducer
state, reducer classes, reducer permit classes or registry contents. For each
action they replay `trace[: action.transition_index + 1]` into local primitive
sets and booleans.

The process predicate independently rejects:

- a numeric `authority_id`;
- signal without an issued fresh anchor;
- signal after exact reap;
- signal after partial, foreign, UID, SID, group, scan, late-child or reuse
  uncertainty;
- cleanup true without exact reap and a complete final absence observation.

The effect predicate independently rejects:

- an unissued, stale or already consumed permit;
- a second detach issuance for one mount receipt;
- absence before the exact detach transition;
- ordinary spawn, inspect or delete at or after terminal;
- cleanup success after an unresolved transition.

Add direct sensitivity tests with fresh forged permits, copied replay, stale
permit, raw numeric signal, signal after reap, signal after uncertainty,
omitted reap, false cleanup, and terminal ordinary/inspect/delete actions.
Each deliberately bad action tuple must make the independent predicate raise.

- [ ] **Step 5: Record Task 1 individual RED evidence**

Run R26 through R32 individually with the checkpoint protocol. At this point
they fail on the absent exact/partial snapshot and process adapter behavior.
If an assertion already passes through old code, use its closed mutant and
record the `RED_Rxx` failure. Do not run the default suite.

- [ ] **Step 6: Remove all legacy real-process routes and tests**

Delete the complete Swift handler call graph and Python assertions for:

~~~text
--spawn-probe
--fd-child
--deadline-drain-probe
--process-policy
--process-scenario
--process-child
~~~

Delete the corresponding Swift symbols
`runSpawnProbe`, `runFileDescriptorChild`, `runDeadlineDrainProbe`,
`runProcessPolicy`, `runProcessScenario` and `runProcessChild`. Remove every
test that launches or cleans those processes, including numeric PID/PGID
receipts and emergency `killpg` cleanup.

Keep `--test-scenario` under the testing conditional. Transfer its wire and
CLOEXEC assertions to scripted observations that create no real child. Do not
add the guardian/witness route until Task 5.

- [ ] **Step 7: Make the pure models and route-removal gates GREEN**

Implement `ExactProcessIdentity`, `PartialProcessIdentity` and deeply immutable
`ProcessSnapshot` exactly as the spec defines. Add a source AST gate requiring
zero obsolete token/handler occurrences and zero `killpg` use.

Run only:

~~~bash
PYTHON311="$PWD/.venv/py311/bin/python"
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainHarnessSafetyTests \
  tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests \
  tests.test_disk_image_keychain_helper.DiskImageKeychainEffectModelTests -v
"$PYTHON311" -c 'from pathlib import Path; compile(Path("tests/disk_image_keychain_harness.py").read_text(), "tests/disk_image_keychain_harness.py", "exec"); compile(Path("tests/test_disk_image_keychain_helper.py").read_text(), "tests/test_disk_image_keychain_helper.py", "exec")'
git diff --check
~~~

Expected: model and source-safety tests pass, process count is 271,453, effect
count is 111,111, sensitivity mutants are rejected, no subprocess is spawned
by either exhaustive model, and all obsolete routes are absent.

- [ ] **Step 8: Commit and review Task 1**

~~~bash
git add native/macos/disk_image_keychain.swift tests/disk_image_keychain_harness.py tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "test(storage): replace unsafe process probes and models"
~~~

The staged names must be exactly the three listed files. Record
`TASK_1_BASE`/`TASK_1_HEAD` and the unchanged primer diff hash. A fresh
read-only reviewer checks both task and cumulative diffs, dynamic inventory,
model independence, raw-prefix replay and total removal of old routes. Require
zero P0/P1/P2 and `PASS`.

---

### Task 2: Implement two-anchor Swift supervision, control parsing and secret erasure

**Files:**

- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**

- Produces private `RunningSessionAnchor`,
  `ExitedUnreapedSessionAnchor`, `ReapedGroupObservationToken` and
  `NativeSettlementProof`.
- Produces the exhaustive kernel/I/O result enums and
  `OwnedProcessSupervisor.InvocationOutcome`.
- Produces `BoundedRequestReader`, `HelperControlChannel`,
  `MasterSecret` and `WireSecret`.
- Accepts exactly `--control-fd` and `--swift-hard-deadline-ns` in production.
- Does not yet change mount compensation policy; Task 3 consumes the new
  outcomes.

- [ ] **Step 1: Freeze Task 2 fixtures and record individual RED**

Complete the scripted matrices for R06 through R10, R33 through R35 and R39.
Also add non-regression methods for every closed result branch, request
cap/EOF cases, simultaneous stdin/control, cancel-before-parse, invalid
control grammar, delayed parse/spawn, late `0x10`, too-close deadline and
missing ACK, including Swift clock jumps at every boundary.

R39 iterates both `create` and `mount` across this exact terminal matrix:

~~~python
SECRET_TERMINAL_CASES = (
    "not_spawned",
    "spawn_failure",
    "invalid_suspended_identity",
    "partial_write",
    "epipe",
    "output_cap",
    "timeout",
    "term",
    "kill",
    "cancel_settled_0x13",
    "cancel_unresolved_0x14",
    "stdin_close_failure",
    "stdout_close_failure",
    "stderr_close_failure",
    "control_close_failure",
)
~~~

Every subcase asserts distinct allocation ranges, Wire all-zero before the
outcome/frame, and Master lifetime appropriate to the operation. Create also
asserts Master readable during the exact `SecItemAdd` callback and all-zero on
every return/throw afterward.

Run each owned R ID in its own unittest process and record natural RED or the
exact mutant rejection before changing Swift behavior.

- [ ] **Step 2: Replace the old runner with closed result types**

Implement these exact enum cases:

~~~swift
enum ResumeResult {
    case resumed
    case childGone
    case identityChanged
    case deadlineExpired
    case interruptedAtDeadline
    case failed(POSIXFailure)
}

enum SignalResult {
    case delivered
    case alreadyAbsent
    case identityChanged
    case notWaitable
    case permissionDenied
    case deadlineExpired
    case interruptedAtDeadline
    case failed(POSIXFailure)
}

enum ReapResult {
    case exactlyReaped(ReapedGroupObservationToken)
    case stillRunning
    case noChild
    case wrongPID
    case deadlineExpired
    case interruptedAtDeadline
    case failed(POSIXFailure)
}

enum GroupPresence {
    case absentESRCH
    case present
    case permissionDenied
    case deadlineExpired
    case interruptedAtDeadline
    case failed(POSIXFailure)
}

enum PollResult {
    case ready(ReadySet)
    case timedOut
    case interrupted
    case deadlineExpired
    case failed(POSIXFailure)
}

enum IOResult {
    case bytes(Int)
    case endOfFile
    case wouldBlock
    case interrupted
    case brokenPipe
    case deadlineExpired
    case failed(POSIXFailure)
}

enum CloseResult {
    case closed
    case alreadyClosed
    case interruptedStateUnknown
    case deadlineExpired
    case failed(POSIXFailure)
}
~~~

Also implement the exact `SpawnResult`, `IdentityResult`,
`ExitObservation` and `SuspendedAbortResult` cases from the spec. Remove
`ProcessInvocationFailure`, `directChildReaped` and `processGroupGone`.
Every non-success branch latches unresolved; no later result clears it.

Nest `InvocationOutcome`, `SettledInvocation` and
`UnresolvedInvocation` exactly as the spec. Give `SettledInvocation`,
`CompleteCapturedOutput` and `NativeSettlementProof` private validating
initializers. `UnresolvedInvocation` exposes only a closed reason, byte counts
and truncation flags; it exposes no bytes, command context or receipt source.

- [ ] **Step 3: Implement consumable running and exited anchor registries**

Keep PID, PGID, UID, SID and birth timestamps only in a private registry keyed
by `issuanceID`. No public description or test JSON includes them.

Implement the state transitions:

~~~text
exact suspended identity -> RunningSessionAnchor
exact WNOWAIT terminal observation -> ExitedUnreapedSessionAnchor
exact waitpid equality -> ReapedGroupObservationToken
absentESRCH plus all successful closes -> NativeSettlementProof
~~~

Running validation performs complete
`proc_bsdinfo -> getsid -> proc_bsdinfo`. Exited validation zeroes
`siginfo_t` and repeats exact `waitid(WNOWAIT)`; it never calls `getsid`.
Consume the running issuance when issuing exited, and consume exited when
exact reap succeeds. Registry rejection happens before syscall.

- [ ] **Step 4: Restrict negative-PGID syscalls**

Inside `DarwinProcessKernel` implement exactly:

~~~swift
func signalOwnedGroup(
    _ signal: TerminationSignal,
    anchoredBy anchor: SignalAnchor,
    deadline: MonotonicInstant
) -> SignalResult

func observeGroupAfterReap(
    _ token: ReapedGroupObservationToken,
    deadline: MonotonicInstant
) -> GroupPresence
~~~

The first contains the sole Swift negative target for TERM/KILL. The second
contains the sole Swift negative target for signal zero. Remove every other
negative `Darwin.kill` and all `killpg`. Consume the reap token in the
registry before the one signal-zero syscall; replay produces zero syscall.
Invalid suspended identity may use only a positive-PID KILL and exact waitpid through
`abortAndReapSuspendedDirectChild`.

- [ ] **Step 5: Implement bounded request and inherited control validation**

Replace `readDataToEndOfFile()` with a 65,536-byte
`BoundedRequestReader` polling stdin and control under the transmitted
deadline. Control is inspected first when both descriptors are ready. Require
stdin EOF before JSON parsing.

Parse the production argv as exactly:

~~~text
--control-fd DECIMAL_FD --swift-hard-deadline-ns DECIMAL_NS
~~~

Validate the socket before request bytes: open, non-stdio, unique, connected,
`AF_UNIX` and `SOCK_STREAM`. Immediately set `FD_CLOEXEC | O_NONBLOCK`.
Use a bounded `PROC_PIDLISTFDS` inventory and require exactly
stdin/stdout/stderr/control in production. Reject malformed decimal, duplicate
flags, extra args, closed FD, wrong socket, incomplete FD inventory, extra FD
or expired deadline with zero spawn/write.

Implement the control reducer with `0x01` and `0x10` through `0x14` exactly
as the spec grammar. `0x10` acknowledges the accepted request and already
transmitted deadline; it never creates a time epoch. A cancel before parse or
child creation issues `0x13` from `NoActiveChildProof`. After
`helperCancelLatchedAt`, permit only settlement work, one terminal control
frame and closes.

- [ ] **Step 6: Implement absolute deadline propagation**

Represent `MonotonicInstant` as checked UInt64 nanoseconds. Derive:

~~~swift
let swiftEpochNS = swiftHardDeadlineNS - 70_000_000_000
~~~

Do not add 70 seconds to Swift's current clock. Every request read, poll,
write, append, waitid, anchor validation, signal, waitpid, group observation,
close and response write checks the same hard value before and after the
operation. Delayed parse/spawn/ACK shortens work. Expired or insufficient
windows return not-spawned or unresolved without a replacement deadline.

- [ ] **Step 7: Implement suspended spawn and narrow settlement**

Use `POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSID |
POSIX_SPAWN_START_SUSPENDED`. Remove SETPGROUP flags and calls. Before SIGCONT
or child stdin, validate exact birth, UID, PGID and SID and recheck control.

The finalization order is:

~~~text
close child stdin
revalidate running or exited anchor
TERM when required
observe/revalidate exact exited anchor
KILL when required and not already attempted
observe/revalidate exact exited anchor
exact waitpid
one token-bound signal-zero observation
independent close attempt for every pipe
erase Wire
issue NativeSettlementProof
~~~

No TERM or KILL follows the first KILL attempt. A failed signal, wait, group
observation or close remains unresolved. `NativeSettlementProof` carries no
descendant-absence claim.

- [ ] **Step 8: Split Master and Wire allocations**

Replace `SecretBuffer` with separate final `MasterSecret` and `WireSecret`
classes backed by different `UnsafeMutableRawPointer` ranges. Copy directly
between raw buffers. Ban `String`, `[UInt8]` and non-erasable `Data` as Wire
representations.

Centralize outcome emission so `WireSecret.zeroize()` completes before every
not-spawned, spawn failure, invalid identity, EPIPE, partial write, cap,
timeout, TERM/KILL result, control `0x13`/`0x14`, close failure or invocation
return. Create keeps Master live through `SecItemAdd` and erases it on every
return/throw after that call. Mount erases its Keychain-derived Master after
the attach outcome.

- [ ] **Step 9: Run focused GREEN and typecheck gates**

~~~bash
PYTHON311="$PWD/.venv/py311/bin/python"
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests -v
xcrun swiftc -typecheck native/macos/disk_image_keychain.swift -framework Security
rg -n 'ProcessInvocationFailure|directChildReaped|processGroupGone|readDataToEndOfFile|POSIX_SPAWN_SETPGROUP|posix_spawnattr_setpgroup|killpg' native/macos/disk_image_keychain.swift
git diff --check
~~~

Expected: the class passes with zero skip and no real child; typecheck exits
zero; the source search returns no matches. The result matrix covers every
enum value and every descriptor position. R06 and R33 explicitly prove
`getsid == ESRCH` after WNOWAIT does not invalidate an exact exited anchor.

- [ ] **Step 10: Commit and review Task 2**

~~~bash
git add native/macos/disk_image_keychain.swift tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "refactor(storage): anchor native process supervision"
~~~

Record `TASK_2_BASE`/`TASK_2_HEAD` and the primer hash. The reviewer traces
both anchor registries, every result branch, both negative-PGID syscall
categories, control precedence, transmitted deadline, close fan-out and every
secret return. Require zero P0/P1/P2 and `PASS`.

---

### Task 3: Bind Swift settlement and mount compensation to exact command provenance

**Files:**

- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**

- Consumes Task 2 `InvocationOutcome` and `NativeSettlementProof`.
- Produces closed `HdiutilCommand`/`ExactCommandContext` values,
  `AttachCompensationPermit` and `AbsenceQueryPermit`.
- Produces the fixed 70-second `MountDeadlinePolicy` without extending the
  transmitted hard deadline.
- Preserves the exact public helper response and
  `MOUNT_CLEANUP_UNCLEAR` priority.

- [ ] **Step 1: Freeze Task 3 fixtures and record individual RED**

Complete R01 through R05, R11 through R14 and R37. Every scripted invocation
passes through the real compensation reducer rather than calling a parser or
permit factory directly.

R02's scripted attach has complete output plus exact exit/reap, then
`GroupPresence.present`; only the supervisor decides that its outcome is
unresolved. R01, R02, R03 and R04 assert the exact call log:

~~~python
self.assertEqual(call_log, [("attach", image, mount, transaction)])
~~~

They also assert zero detach permit consumption, zero absence permit issuance
and `MOUNT_CLEANUP_UNCLEAR`. R05 asserts:

~~~python
self.assertEqual(
    [entry[0] for entry in call_log],
    ["attach", "detach", "info"],
)
~~~

Run each owned ID separately and record the exact natural RED or mutant
failure before changing compensation code.

- [ ] **Step 2: Add closed command contexts**

Implement:

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

private struct ExactCommandContext: Equatable {
    let command: HdiutilCommand
    let executable: String
    let argv: [String]
    let stdinPolicy: StdinPolicy
    let window: InvocationWindow
    let generation: UInt64
}
~~~

The only context factory maps every enum case to `/usr/bin/hdiutil` and its
fixed argv. It validates image, mount, UUID, device and phase before returning.
Callers cannot supply executable, argv, operation text or cleanup state.

Store `ExactCommandContext` privately inside `SettledInvocation` together with
its `NativeSettlementProof` and complete output. `notSpawned` and
`unresolved` expose only stable non-authoritative diagnostics.

- [ ] **Step 3: Add private single-use Swift permit registries**

Define private token values that contain only an issuance ID. The registry
record for `AttachCompensationPermit` stores:

~~~text
issuance ID
unconsumed state
settled invocation generation
image
mount
transaction
parsed device
~~~

`issueAttachCompensationPermit(from:)` accepts only exact
`.attach(image, mount, transaction)` context, complete uncapped output and
one valid tab-delimited device bound to the same mount. It parses the device
internally. A caller cannot pass it.

Consuming the permit atomically marks the registry record before constructing
`.detach(device, image, mount, transaction)`. A copied, missing, stale,
wrong-context or consumed token returns refusal before invoking
`HdiutilInvoking`.

`issueAbsenceQueryPermit(from:consuming:)` requires the exact settled detach
created by that consumed attach permit. Its registry record fixes
`.info(image, mount, transaction, purpose: .postDetachAbsence)` and is also
single-use. Absence proof requires settled complete plist output with zero
matching devices and zero image entries.

- [ ] **Step 4: Implement the fixed absolute mount policy**

Derive every field from `swiftEpochNS` and the transmitted
`swiftHardDeadlineNS`:

~~~swift
struct MountDeadlinePolicy {
    let normalHard: MonotonicInstant
    let attachReceiptHard: MonotonicInstant
    let detachAdmission: MonotonicInstant
    let detachHard: MonotonicInstant
    let absenceTransitionHard: MonotonicInstant
    let absenceAdmission: MonotonicInstant
    let absenceHard: MonotonicInstant
    let epilogueHard: MonotonicInstant
}
~~~

Set the offsets exactly:

~~~text
normalHard = epoch + 36 seconds
attachReceiptHard = epoch + 38 seconds
detachAdmission = epoch + 38 seconds
detachHard = epoch + 52 seconds
absenceTransitionHard = epoch + 54 seconds
absenceAdmission = epoch + 54 seconds
absenceHard = epoch + 66 seconds
epilogueHard = epoch + 70 seconds = transmitted Swift hard deadline
~~~

Create/attach/detach require 8 seconds work plus 6 seconds finalization.
Info/isencrypted require 4 seconds work plus 6 seconds finalization; the
post-detach absence info requires 6 seconds work plus 6 seconds finalization.
The policy rejects overflow, reversed boundaries, phase overlap and
insufficient fit. Equality at admission is accepted only when the complete
budget fits; one nanosecond later is refused.

- [ ] **Step 5: Replace mount compensation with one monotone reducer**

Use:

~~~text
baselineVerified
-> attaching
-> attachSettled
-> attachPermitIssued
-> detachPermitConsumed
-> detachSettled
-> absencePermitIssued
-> absencePermitConsumed
-> absenceSettled
-> cleanupProven

Any state -> cleanupUnclear
~~~

R01 through R04 reach `cleanupUnclear` directly from the attach result and
therefore retain the attach-only call log. No parser fallback may inspect
unresolved/truncated/capped output. R37 proves that syntactically valid output
without `NativeSettlementProof` cannot reach `attachSettled`.

A settled nonzero attach may reach `attachPermitIssued` only through the exact
factory. Detach nonzero/unresolved and absence nonzero/unresolved/truncated/
capped/nonempty results all end `MOUNT_CLEANUP_UNCLEAR` without another child.
Every `notSpawned` or `unresolved` outcome closes the enclosing request and
forbids another helper invocation. No phase computes a new relative deadline.

- [ ] **Step 6: Preserve public contract and error priority**

For every operation and outcome, assert the response key set is exactly:

~~~python
{
    "schema_version",
    "operation",
    "code",
    "encryption_uuid",
    "device",
    "item_count",
}
~~~

Keep all existing error strings. Any failed or unavailable compensation proof
returns `MOUNT_CLEANUP_UNCLEAR`; it cannot be downgraded to
`HDIUTIL_FAILED`. A device from unresolved output never enters the public
response or an internal permit record.

- [ ] **Step 7: Run Task 3 GREEN and compatibility gates**

~~~bash
PYTHON311="$PWD/.venv/py311/bin/python"
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests -v
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainHelperTests -v
xcrun swiftc -typecheck native/macos/disk_image_keychain.swift -framework Security
git diff --check
~~~

Expected: both classes pass with zero skip and scripted adapters only;
R01-R04 log attach only; R05 logs attach/detach/info; typecheck exits zero.

- [ ] **Step 8: Commit and review Task 3**

~~~bash
git add native/macos/disk_image_keychain.swift tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "fix(storage): seal mount compensation provenance"
~~~

Record `TASK_3_BASE`/`TASK_3_HEAD` and the primer hash. The reviewer traces
the exact command context, both registries, all copied/replayed values, output
binding and every absolute phase. Require zero P0/P1/P2 and `PASS`.

---

### Task 4: Seal Python live authority and terminal process/effect handling

**Files:**

- Modify: `tests/disk_image_keychain_harness.py`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**

- Produces sealed `LiveExecutionCapability` and
  `EffectSession.authorize_cleanup()` with no boolean argument.
- Produces frozen typed request objects and private exact ten-key JSON
  builders.
- Produces distinct `ObserverBaseline`, `SecurityAgentSnapshot` and
  `ProcessSnapshot` types.
- Produces private Python running/exited anchors,
  `DarwinOwnedProcessAdapter` and `HelperControlClient`.
- Produces receipt/permit registries, artifact/disposition ledger and the fixed
  post-terminal command chain.
- Moves all non-`TestCase` live harness implementation out of
  `tests/test_disk_image_keychain_helper.py` into
  `tests/disk_image_keychain_harness.py`; the test module retains assertions,
  fakes, reference predicates, inventory and suite selection.

- [ ] **Step 1: Freeze Task 4 fixtures and record individual RED**

Complete the test-only recording fixtures for R15 through R25, R36 and R38
without changing their Task 1 assertions. Add adapter-parity methods for the R26-R32
process-lineage cases: each drives the scripted surface of
`DarwinOwnedProcessAdapter` and compares primitive action logs to the
already-green independent process predicate.

R36 drives every Swift `CloseResult` through
`--test-supervisor-scenario` and every Python close result through the
scripted adapter. It injects the failure independently at child stdin, child
stdout, child stderr, request stdin, helper control and each parent-side pipe,
then requires one recorded close attempt for every remaining descriptor.

R38 combines the Task 2 Swift clock scenarios with Python jumps immediately
before and after request read, control read/write, poll, pipe read/write,
append, close, waitid, waitpid, process scan and nonce scan. Each subcase
asserts zero new action after its original hard deadline.

Add non-regression matrices for observer/process type cross-use, capability
forgery, request-field immutability, control-frame ordering, Popen FD closure,
delayed helper ACK and all direct-command result branches.

Run every owned ID in its own unittest process and record natural RED or its
closed mutant rejection before changing harness behavior.

- [ ] **Step 2: Mint one sealed live capability from the exact gate**

Move the current execution gate, process scanning, observer, workflow and live
effects implementation into `tests/disk_image_keychain_harness.py` before
replacing their APIs. Update the test module to import that closed surface.
Do not move any `unittest.TestCase`, `REGRESSION_TEST_IDS`,
`REGRESSION_MUTANTS`, reference predicate or suite selector.

Implement a private issuance registry keyed by object identity. The exact
selector validates flags and environment, then registers:

~~~python
@dataclass(frozen=True, slots=True)
class LiveExecutionCapability:
    _issuance_id: str
    _cleanup_approved: bool
~~~

The public test module cannot make a valid capability by copying fields or
constructing the dataclass. `EffectSession.__init__` rejects every value not
present in the private registry before constructing observers, adapters or
ledgers.

The exact accepted flag sets are:

~~~python
frozenset({"--integration", "--allow-effects"})
frozenset({"--integration", "--allow-effects", "--cleanup-approved"})
~~~

Each flag occurs once. The authorization key and value must match exactly.
All other inputs exit 64 with empty stdout/stderr and zero live construction.

Store cleanup approval only in the registry record.
`EffectSession.authorize_cleanup()` takes no parameter, works once in ACTIVE,
and issues no grant if the capability lacks approval.

- [ ] **Step 3: Replace mappings with frozen request objects**

Implement the five request dataclasses exactly as specified in the design.
Validate absolute private paths, lower-case canonical UUID text where
serialized, fixed `64m` size and fixed `APFS`/volume rules at construction.

Private builder methods emit exactly ten keys:

~~~python
def _base_helper_request(
    *,
    operation: str,
    image_path: Path,
    mount_path: Path | None,
    volume_name: str | None,
    size: str | None,
    transaction_id: uuid.UUID,
    expected_encryption_uuid: str | None,
    disposable: bool,
    cleanup_approved: bool,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "operation": operation,
        "image_path": str(image_path),
        "mount_path": None if mount_path is None else str(mount_path),
        "volume_name": volume_name,
        "size": size,
        "transaction_id": str(transaction_id),
        "expected_encryption_uuid": expected_encryption_uuid,
        "disposable": disposable,
        "cleanup_approved": cleanup_approved,
    }
~~~

Keep this function private and call it only from fixed typed workflow methods.
No public method accepts `Mapping[str, object]`, operation text, cleanup
boolean, executable or argv.

- [ ] **Step 4: Separate observer and process types**

Implement frozen `ObserverBaseline` and `SecurityAgentSnapshot` with immutable
process/window observations. Keep `ExactProcessIdentity`,
`PartialProcessIdentity` and `ProcessSnapshot` separate with no inheritance or
converter.

Use exact runtime checks:

~~~python
if type(baseline) is not ObserverBaseline or not baseline.complete:
    raise ObservationUnavailable
if baseline.processes or baseline.windows:
    raise SecurityAgentBaselineNonempty

if type(snapshot) is not SecurityAgentSnapshot:
    raise ObservationUnavailable

if type(process_snapshot) is not ProcessSnapshot:
    raise ProcessObservationUnavailable
~~~

Define `SecurityAgentBaselineNonempty` as a closed pre-effect outcome normalized
to `UNCLEAR securityagent_baseline_nonempty`. It is distinct from
`ObservationUnavailable` and neither path issues an ordinary permit.

Every rejection occurs before ordinary permit issuance or spawn. Add
`__post_init__` tuple/frozenset copies so caller mutation cannot alter stored
evidence.

- [ ] **Step 5: Implement monotone EffectSession and private registries**

Use:

~~~python
class EffectPhase(enum.Enum):
    PREPARING = "preparing"
    ACTIVE = "active"
    TERMINAL = "terminal"
    DISPOSING = "disposing"
    CLOSED = "closed"

@dataclass(frozen=True, slots=True)
class TerminalEvent:
    cause: str
    command_id: str
    stage: str
    observed_at_ns: int
~~~

`activate(ObserverBaseline)` issues ordinary authority once.
`latch_terminal(TerminalEvent)` sets `observerTerminalLatchedAt` once,
increments the epoch and permanently revokes ordinary authority. Later events
append evidence but do not change the first timestamp.

The private registry records each `DetachPermit` with session, origin ACTIVE
epoch, current disposition epoch, transaction, image, mount, encryption UUID,
device and mount-receipt ID. After `begin_disposition`, issue it at most once
from an exact mount receipt recorded in the immediately preceding ACTIVE
epoch. Consumption allows only that receipt-device detach. Exact settled
detach issues one `AbsencePermit` in the same disposition epoch for one fixed
info query; exact absence issues one descriptor-bound `QuarantinePermit`. All
issuance and consumption changes are atomic before spawn.

Forged, copied replay, second issuance, stale/wrong session, wrong epoch,
wrong image/mount/UUID/device and raw mappings produce zero spawn.

- [ ] **Step 6: Implement the fixed method catalogue**

Expose only:

~~~text
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
~~~

Every ordinary method checks phase/epoch immediately before adapter spawn and
again before the first child write. No `safety_only`,
`disposition_active`, generic plist command or public argv runner remains.

After `observerTerminalLatchedAt`:

- compile, create, mount, normal detach, inspect, delete and all ordinary probes
  refuse before spawn;
- an already running command begins bounded cancellation regardless of stdin;
- only the exact receipt-derived detach, one info query and descriptor-relative
  rename can occur;
- unknown mapping preserves the image and item without query or mutation;
- Keychain inspect/delete is always forbidden.

- [ ] **Step 7: Implement Python running/exited anchors and lineage**

Keep raw PID/PGID only in private snapshot/registry records. Define opaque
`PythonRunningSessionAnchor`, `PythonExitedUnreapedSessionAnchor` and
`PythonReapedGroupObservationToken` issuance IDs.

Running revalidation reads full `proc_bsdinfo`, calls `getsid` and rereads full
`proc_bsdinfo`. Exact WNOWAIT exit consumes running authority and issues exited
authority. Exited revalidation repeats exact waitid and does not call getsid.
Exact waitpid consumes exited authority and issues the post-reap observation
token.

Inside `DarwinOwnedProcessAdapter`, allow one negative target TERM/KILL site in
`signal_owned_group` and one negative target signal-zero site in
`observe_group_after_reap`. Ban `os.killpg` and every other negative target.
Consume `PythonReapedGroupObservationToken` before the sole signal-zero
syscall; a copy or replay causes zero syscall. Do not use
`Popen.communicate()` as terminal proof.

Collect all records before UID filtering. Preserve PID, PPID, PGID and UID in
partial records. Latch uncertainty for related partial/foreign identity,
tracked UID/SID/group change, late child, reused parent, incomplete scan and
zero/full-reread/live. Only zero/full-reread/ESRCH records vanished.

- [ ] **Step 8: Create the production helper socket and deadlines once**

For each helper invocation:

~~~python
outer_started_ns = time.monotonic_ns()
outer_hard_ns = outer_started_ns + 115_000_000_000
pre_observation_hard_ns = outer_started_ns + 1_000_000_000
swift_hard_ns = min(
    time.monotonic_ns() + 70_000_000_000,
    outer_hard_ns - 44_000_000_000,
)
~~~

Create `swift_hard_ns` once after the accepted baseline. Pass it as decimal
argv and never replace it. Create a CLOEXEC Unix stream socketpair. Production
`Popen` sets `close_fds=True`, exact `pass_fds=(control_fd,)` and
`start_new_session=True`. Close the child end immediately in the parent; on
spawn failure close both ends and every pipe independently.

`HelperControlClient` validates `0x10`, repeated `0x11 -> 0x12` pairs and one
terminal `0x13`/`0x14`. When the observer latches terminal, send `0x01` once.
Do not signal/reap a running helper before the transmitted Swift deadline
unless it exits or returns a terminal frame. Invalid order, EOF, socket error,
helper exit without terminal ACK after cancel, `0x14` or missing ACK returns
`UNCLEAR descendant_potentially_surviving`.

- [ ] **Step 9: Implement ledger and terminal verdict priority**

Track immutable image, mount and Keychain states from the design. Record
complete non-secret UUID/device receipts before raising nonzero or terminal
results. Output from unresolved native settlement is not recordable receipt
authority.

`close` freezes the ledger once. If any SecurityAgent event exists, return
`FAIL securityagent_detected`. Otherwise, if observer unavailable exists,
return `UNCLEAR observer_unavailable`. Cleanup failures append secondary
evidence and never overwrite either terminal cause.

- [ ] **Step 10: Run Task 4 GREEN and structural gates**

~~~bash
PYTHON311="$PWD/.venv/py311/bin/python"
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests \
  tests.test_disk_image_keychain_helper.DiskImageKeychainEffectModelTests \
  tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests \
  tests.test_disk_image_keychain_helper.DiskImageKeychainIntegrationOrchestrationTests -v
rg -n 'safety_only|disposition_active|os\\.killpg|authorize_cleanup\\([^)]|Mapping\\[str, object\\].*request|input_text.*effect' tests/disk_image_keychain_harness.py tests/test_disk_image_keychain_helper.py
git diff --check
~~~

Expected: all four classes pass with zero skip and scripted subprocesses only;
the source search returns no matches. The process and effect trace counts stay
exact, all cross-type uses refuse, and default tests call neither Python
negative-PGID site.

- [ ] **Step 11: Commit and review Task 4**

~~~bash
git add tests/disk_image_keychain_harness.py tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "refactor(storage): seal terminal integration effects"
~~~

Record `TASK_4_BASE`/`TASK_4_HEAD` and the primer hash. The reviewer enumerates
every public method, capability/permit producer, post-terminal spawn,
observer/process type boundary, process authority transition, deadline and
socket close. Require zero P0/P1/P2 and `PASS`.

---

### Task 5: Add the sole guardian/witness fixture and close S3

**Files:**

- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**

- Consumes Task 2's supervisor/control protocol, Task 4's Python launcher and
  Task 1's inventory.
- Produces testing-only `--guardian-witness-probe` and
  `--guardian-witness-child` while retaining scripted `--test-scenario` and
  `--test-supervisor-scenario`.
- Produces one real self-expiring direct fixture child and no other real child
  route.
- Produces final Python 3.11/3.14, route, FD, flake, source, secret and diff
  evidence.

- [ ] **Step 1: Freeze Task 5 fixtures and record individual RED**

Complete R40 through R45. Add non-regression assertions for reversed control/
witness ordering, persistent EAGAIN, terminal socket close, production binary
symbol absence, exact fixture call graph and the 45-entry map.

Run each of R40-R45 in its own Python 3.11 unittest process. Record natural RED
or the exact closed mutant failure before adding a new Swift route or changing
the selector.

- [ ] **Step 2: Add one closed testing route grammar**

The complete testing-only route tokens are:

~~~python
TESTING_ONLY_SWIFT_ROUTES = (
    "--test-scenario",
    "--test-supervisor-scenario",
    "--guardian-witness-probe",
    "--guardian-witness-child",
)
~~~

Keep all dispatch branches and handler definitions inside
`#if CORTEX_STORAGE_HELPER_TESTING`. Production dispatch has only the generic
strict argv parser, so it rejects those strings without embedding them.

Use these exact test forms:

~~~text
--test-scenario SCENARIO
--test-supervisor-scenario SCENARIO
--guardian-witness-probe MODE --guardian-fd FD --witness-fd FD --control-fd FD --nonce HEX32 --swift-hard-deadline-ns NS
--guardian-witness-child --guardian-fd FD --witness-fd FD --nonce HEX32 --self-expire-ns NS
~~~

`MODE` is exactly `deadline` or `cancel`. Reject duplicate, missing, reordered
or extra arguments, invalid decimals, a nonce outside 32 lower-case hex
characters, and an expiry not later than the current monotonic clock.

The testing route constructs a testing-only `FixtureSpawnRequest` under the
compile conditional. It does not add an executable case to `HdiutilCommand`
and cannot widen the production `/usr/bin/hdiutil` catalogue.

- [ ] **Step 3: Validate the test-only descriptor boundary before spawn**

For `--guardian-witness-probe` require guardian-read, witness-write and
control-socket descriptors to be distinct, non-stdio, open and listed exactly
once. Validate guardian/witness pipe direction and control
`AF_UNIX/SOCK_STREAM` type.

Reject this complete matrix before child spawn or witness write:

~~~text
guardian equals witness
guardian equals control
witness equals control
guardian/witness order reversed
each descriptor closed
each descriptor in 0, 1, 2
guardian as regular file
witness as regular file
control as regular file
control as non-Unix socket
one unlisted inherited descriptor
one missing descriptor
~~~

The helper immediately sets CLOEXEC/nonblocking on control. Fixture spawn uses
`posix_spawn_file_actions_addinherit_np` only for guardian-read and
witness-write. The control socket never enters fixture file actions.

- [ ] **Step 4: Implement the single self-expiring child**

Before START, the child validates its exact args and arms the absolute
`self-expire-ns = start + 900_000_000` bound. It writes
`START:HEX32`, emits paced bytes below 64 KiB, polls guardian EOF and closes
witness on every exit.

Keep its transitive reachable call set to:

~~~text
argument parsers
clock_gettime
poll
read
write
memset
memcpy
nanosleep
close
_exit
~~~

The structural test constructs the route's local call graph and fails if a
reachable node calls `posix_spawn`, `fork`, `vfork`, an exec-family symbol,
`system`, `popen`, Foundation `Process`, `NSTask`, `dlopen` or
`dlsym`. A scan of the route body alone is insufficient.

- [ ] **Step 5: Implement one absolute probe timeline**

The Python launcher creates exactly:

~~~python
start_ns = time.monotonic_ns()
work_cutoff_ns = start_ns + 500_000_000
supervisor_hard_ns = start_ns + 650_000_000
outer_hard_ns = start_ns + 1_200_000_000
~~~

It passes `supervisor_hard_ns` to Swift. The supervisor derives the test work
cutoff and issues no I/O or signal after 0.65 seconds. One selector monitors
helper stdout/stderr, witness and control. Every timeout equals
`max(0, hard_ns - time.monotonic_ns()) / 1_000_000_000`; no wait adds a new
relative budget.

The deadline mode requires matching START and witness EOF with:

~~~python
500_000_000 <= witness_eof_ns - start_ns <= 650_000_000
~~~

The cancel mode waits for `0x11`, sends one `0x01`, accepts witness EOF and
`0x13` in either selector order, and requires both before helper exit/exact
helper reap. `0x14`, unknown/duplicate/out-of-order frame, missing event or
deadline overrun fails.

At `supervisor_hard_ns`, if the helper remains alive, close guardian/control,
kill only the exact still-unreaped helper and reap it with the time remaining
before `outer_hard_ns`. This direct helper containment is not a group signal
and cannot yield a settlement claim.

After helper reap, run one bounded `/bin/ps -axo command=` scan with the
remaining outer deadline. Filter the nonce in memory, discard stdout and never
include command lines in assertion text, logs or receipts. Scan failure,
timeout or a match fails. Finish before `outer_hard_ns`.

- [ ] **Step 6: Prove test and production build boundaries**

Compile one testing binary and one production binary to a test-owned temporary
directory. Run every route token against production; each returns exit 64,
empty stdout/stderr and no witness. Use `strings` to require every route token
and handler symbol absent from the production binary.

Run every invalid FD case against the testing binary and require exit 64,
empty output, empty witness and zero scripted spawn. The one valid scripted
spawn log contains only guardian and witness in `addinherit_np` and excludes
control.

- [ ] **Step 7: Run the real probes once and the flake gate**

Run the two exact regression IDs once in the normal class. Then R43 launches
each exact probe ID in twenty fresh child interpreters using
`sys.executable`:

~~~python
probe_ids = (
    "tests.test_disk_image_keychain_helper."
    "DiskImageKeychainContainedProcessProbeTests."
    "test_deadline_probe_uses_external_witness_and_nonce_bounds",
    "tests.test_disk_image_keychain_helper."
    "DiskImageKeychainContainedProcessProbeTests."
    "test_cancellation_probe_orders_cancel_settlement_eof_and_helper_reap",
)
for probe_id in probe_ids:
    for iteration in range(20):
        run_one_probe(sys.executable, probe_id, iteration)
~~~

`run_one_probe` consumes the child-reported `outer_hard_ns`, creates no later
relative timeout, records only return code and START/EOF/control/helper
timestamps, and fails on stderr, timeout or nonzero exit. Require 40/40. No
test claims direct observation of fixture-child waitpid.

- [ ] **Step 8: Run the complete suite independently on Python 3.11 and 3.14**

Resolve and validate:

~~~bash
PYTHON311="$PWD/.venv/py311/bin/python"
GIT_COMMON_DIR=$(git rev-parse --git-common-dir)
MAIN_CHECKOUT=$(cd "$(dirname "$GIT_COMMON_DIR")" && pwd)
PYTHON314="$MAIN_CHECKOUT/.venv/bin/python"
"$PYTHON311" -c 'import sys; assert sys.version_info[:2] == (3, 11)'
"$PYTHON314" -c 'import sys; assert sys.version_info[:2] == (3, 14)'
~~~

R42 invokes each interpreter with `-c`, imports the module, calls only
`default_test_ids()` and compares the emitted JSON arrays. It never executes a
suite and therefore cannot recursively invoke itself.

For the final gate, run the complete default suite once per interpreter in the
exact clean environment. Use this recording result shape with
`build_default_suite(unittest.defaultTestLoader)`; write test diagnostics to
stderr and the ordered ID stream to stdout:

~~~bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" -c 'import sys, unittest
import tests.test_disk_image_keychain_helper as module
class RecordingResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.started_ids = []
    def startTest(self, test):
        self.started_ids.append(test.id())
        super().startTest(test)
runner = unittest.TextTestRunner(stream=sys.stderr, verbosity=2, resultclass=RecordingResult)
result = runner.run(module.build_default_suite(unittest.defaultTestLoader))
print("\n".join(result.started_ids))
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)' \
  > .superpowers/sdd/2026-09-03-s3-owned-process-supervision/default-ids-py311.txt
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON314" -c 'import sys, unittest
import tests.test_disk_image_keychain_helper as module
class RecordingResult(unittest.TextTestResult):
    def __init__(self, stream, descriptions, verbosity):
        super().__init__(stream, descriptions, verbosity)
        self.started_ids = []
    def startTest(self, test):
        self.started_ids.append(test.id())
        super().startTest(test)
runner = unittest.TextTestRunner(stream=sys.stderr, verbosity=2, resultclass=RecordingResult)
result = runner.run(module.build_default_suite(unittest.defaultTestLoader))
print("\n".join(result.started_ids))
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)' \
  > .superpowers/sdd/2026-09-03-s3-owned-process-supervision/default-ids-py314.txt
cmp .superpowers/sdd/2026-09-03-s3-owned-process-supervision/default-ids-py311.txt \
  .superpowers/sdd/2026-09-03-s3-owned-process-supervision/default-ids-py314.txt
~~~

Require both exit zero, zero skip, every dynamically discovered non-live
class once, every method once, live class absent, every regression value once,
and byte-identical ordered started-test streams.

- [ ] **Step 9: Run authorization and factory-construction gates**

Run these four shapes independently in the clean environment:

~~~bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" tests/test_disk_image_keychain_helper.py --integration
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" tests/test_disk_image_keychain_helper.py --allow-effects
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" tests/test_disk_image_keychain_helper.py --integration --allow-effects
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
  PYTHONPATH="$PWD" "$PYTHON311" tests/test_disk_image_keychain_helper.py --cleanup-approved
~~~

Each must exit 64 with empty stdout/stderr and zero capability, observer,
effect session or live runner construction.

R45 generates every subset of the three known flags, duplicate occurrences,
an unknown flag and the two accepted flag sets against each bad key:

~~~text
CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATIO
CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION_
cortex_keychain_test_effect_authorization
CORTEX_KEYCHAIN_EFFECT_AUTHORIZATION
~~~

It also tests the exact key with missing, empty, wrong-case, prefixed and
suffixed values. Every case refuses before a live factory. The positive exact
triple gate is tested only with injected recording factories; it never loads
or runs the live `TestCase`.

- [ ] **Step 10: Run final source, deadline, secret and diff gates**

Compile both Python files in memory under both interpreters. Typecheck the
production Swift source and extracted observer source without execution. Run
AST/source gates proving:

~~~text
obsolete route tokens and handler symbols = 0
real child routes other than guardian-witness-child = 0
numeric signal receipts = 0
process success booleans = 0
safety_only/disposition_active = 0
readDataToEndOfFile = 0
generic caller request mappings/argv = 0
unregistered proof/permit factories = 0
Swift negative TERM/KILL sites outside signalOwnedGroup = 0
Swift negative signal-zero sites outside observeGroupAfterReap = 0
Python negative TERM/KILL sites outside signal_owned_group = 0
Python negative signal-zero sites outside observe_group_after_reap = 0
killpg sites = 0
production test-route symbols = 0
default live-class selections = 0
hard-coded nested python3.11 relaunches = 0
~~~

The Python AST additionally proves every `Popen` has
`start_new_session=True`, every production helper `Popen` has
`close_fds=True` and exactly one `pass_fds=(control_fd,)`, and every wait,
poll, scan, frame and cleanup receives a remaining value derived from an
absolute deadline.

Run:

~~~bash
xcrun swiftc -typecheck native/macos/disk_image_keychain.swift -framework Security
git diff --check "$IMPLEMENTATION_BASE..HEAD"
gitleaks detect --source . --no-banner --redact --log-opts="--all"
gitleaks detect --source . --no-banner --redact --no-git
git diff --name-only "$IMPLEMENTATION_BASE..HEAD"
git diff --binary -- primer.md | shasum -a 256
~~~

Expected: typecheck and all gates exit zero; only the three S3 implementation
paths appear; the primer hash equals `PRIMER_DIFF_SHA256`.

- [ ] **Step 11: Commit the contained fixture**

~~~bash
git add native/macos/disk_image_keychain.swift tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "test(storage): add contained guardian witness"
~~~

Record `TASK_5_BASE`/`TASK_5_HEAD` and unchanged primer hash.

- [ ] **Step 12: Freeze and independently review S3**

Set `S3_FINAL=$(git rev-parse HEAD)` before any later documentation change.
Build a clean review package containing the spec, plan, test receipts,
`IMPLEMENTATION_BASE..S3_FINAL` and each task diff. Do not include prior
reviewer verdicts.

Three fresh blind read-only reviewers must each return:

~~~text
P0 = 0
P1 = 0
P2 = 0
Verdict = PASS
~~~

Any finding freezes S3. It does not authorize an incremental exception or S4.

## Post-S3 documentation-only S4 rebaseline

This action occurs only after `S3_FINAL` and the three final PASS reviews. It
is outside `IMPLEMENTATION_BASE..S3_FINAL` and uses a separate commit.

Modify exactly:

- `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md`
- `docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md`
- `docs/superpowers/plans/2026-09-02-v054-completion-program.md`

Update `run_attested_helper` so S4 creates and validates the Unix control
socket internally, creates one absolute outer/Swift deadline pair, passes only
the control child FD, requires the cancellation acknowledgement contract
before helper escalation, and retains the single-source helper manifest.

Commit those three documentation files alone with a distinct S4 rebaseline
message, compute all three SHA-256 values and obtain independent review before
any S4 code. Do not amend an S3 commit.

## Normative regression map

The implementation defines this dictionary verbatim. Keys and values are
unique; values are fully qualified unittest IDs:

~~~python
REGRESSION_TEST_IDS = {
    "R01": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_unresolved_attach_with_device_text_logs_attach_only",
    "R02": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_attach_exact_reap_with_group_present_logs_attach_only",
    "R03": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_truncated_attach_output_logs_attach_only",
    "R04": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_capped_attach_output_logs_attach_only",
    "R05": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_exact_settled_attach_consumes_detach_then_absence_once",
    "R06": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_exited_anchor_signals_before_exact_reap_with_getsid_esrch",
    "R07": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_reaped_group_observation_never_signals_reused_pgid",
    "R08": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_running_anchor_identity_matrix_blocks_resume_stdin_and_group_signal",
    "R09": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_waitid_matrix_issues_exited_anchor_only_for_exact_terminal_child",
    "R10": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_reap_echild_is_unresolved_and_issues_no_proof",
    "R11": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_insufficient_command_window_spawns_nothing",
    "R12": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_detach_cutoff_accepts_exact_and_rejects_next_tick",
    "R13": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_absence_cutoff_accepts_exact_and_rejects_next_tick",
    "R14": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_normal_cutoff_preserves_fixed_compensation_windows",
    "R15": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_terminal_preobservation_blocks_every_ordinary_request",
    "R16": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_terminal_during_compile_and_info_cancels_without_continuation",
    "R17": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_caller_cannot_supply_operation_cleanup_or_arbitrary_argv",
    "R18": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_detach_permit_wrong_stale_forged_and_replay_matrix_spawns_nothing",
    "R19": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_mount_receipt_issues_exactly_one_detach_permit",
    "R20": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_absence_permit_requires_exact_preceding_detach",
    "R21": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_terminal_disposition_is_exact_detach_info_rename_chain",
    "R22": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_unknown_mapping_preserves_without_query_or_mutation",
    "R23": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_terminal_artifact_matrix_never_inspects_or_deletes_keychain",
    "R24": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_terminal_event_ordering_keeps_securityagent_priority",
    "R25": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_complete_nonzero_receipts_precede_terminal_propagation",
    "R26": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_related_partial_or_foreign_uid_makes_lineage_permanently_uncertain",
    "R27": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_partial_bridge_never_authorizes_grandchild_signal",
    "R28": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_zero_reread_live_is_partial_not_vanished",
    "R29": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_zero_reread_esrch_is_exactly_vanished",
    "R30": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_late_child_after_adoption_close_never_recovers",
    "R31": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_reused_parent_birth_never_authorizes_adoption",
    "R32": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_tracked_uid_sid_or_group_change_expires_signal_permit",
    "R33": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_exited_anchor_change_matrix_blocks_kill_except_getsid_esrch",
    "R34": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_kill_latch_blocks_every_later_group_signal",
    "R35": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_invalid_suspended_identity_aborts_and_reaps_direct_child_only",
    "R36": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_fault_and_close_result_matrix_attempts_every_close",
    "R37": "tests.test_disk_image_keychain_helper.DiskImageKeychainMountCompensationTests.test_valid_output_with_unresolved_native_settlement_never_succeeds",
    "R38": "tests.test_disk_image_keychain_helper.DiskImageKeychainTerminalEffectTests.test_clock_jump_matrix_stops_all_post_deadline_actions",
    "R39": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_master_wire_lifetime_matrix_covers_every_terminal_path",
    "R40": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_cancellation_probe_orders_cancel_settlement_eof_and_helper_reap",
    "R41": "tests.test_disk_image_keychain_helper.DiskImageKeychainBuildBoundaryTests.test_production_testing_route_and_fd_boundary_matrix",
    "R42": "tests.test_disk_image_keychain_helper.DiskImageKeychainManifestAndGateTests.test_dynamic_default_inventory_matches_on_python_311_and_314",
    "R43": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_deadline_and_cancel_probes_pass_twenty_fresh_runs_each",
    "R44": "tests.test_disk_image_keychain_helper.DiskImageKeychainBuildBoundaryTests.test_final_source_has_only_sealed_factories_and_anchored_signal_sites",
    "R45": "tests.test_disk_image_keychain_helper.DiskImageKeychainManifestAndGateTests.test_authorization_key_near_miss_and_flag_matrix_constructs_zero_live_objects",
}
~~~

The test module also defines this closed sensitivity map verbatim:

~~~python
REGRESSION_MUTANTS = {
    "R01": "allow_unresolved_attach_receipt",
    "R02": "treat_present_group_as_settled",
    "R03": "parse_truncated_attach",
    "R04": "parse_capped_attach",
    "R05": "skip_absence_query",
    "R06": "reap_before_last_signal",
    "R07": "signal_reused_group_after_reap",
    "R08": "resume_on_identity_mismatch",
    "R09": "accept_inexact_waitid",
    "R10": "treat_echild_as_reap",
    "R11": "spawn_without_full_window",
    "R12": "admit_detach_after_cutoff",
    "R13": "admit_absence_after_cutoff",
    "R14": "reset_compensation_deadline",
    "R15": "allow_ordinary_after_terminal",
    "R16": "continue_after_terminal_cancel",
    "R17": "accept_caller_effect_mapping",
    "R18": "accept_forged_or_replayed_detach",
    "R19": "issue_second_detach_permit",
    "R20": "issue_absence_without_exact_detach",
    "R21": "insert_extra_terminal_query",
    "R22": "query_unknown_mapping",
    "R23": "inspect_or_delete_after_terminal",
    "R24": "let_cleanup_override_terminal",
    "R25": "drop_receipt_before_terminal",
    "R26": "clear_related_identity_uncertainty",
    "R27": "adopt_through_partial_bridge",
    "R28": "treat_live_zero_read_as_vanished",
    "R29": "refuse_exact_esrch_vanish",
    "R30": "adopt_late_child",
    "R31": "adopt_from_reused_parent",
    "R32": "reuse_stale_signal_permit",
    "R33": "kill_after_exited_anchor_change",
    "R34": "signal_after_kill",
    "R35": "group_signal_invalid_suspended",
    "R36": "short_circuit_close_attempts",
    "R37": "settle_unresolved_output",
    "R38": "act_after_hard_deadline",
    "R39": "alias_or_leave_wire_live",
    "R40": "ack_before_native_settlement",
    "R41": "expose_test_route_or_bad_fd",
    "R42": "omit_dynamic_testcase",
    "R43": "skip_one_probe_iteration",
    "R44": "allow_unsealed_factory_or_signal",
    "R45": "accept_near_miss_authorization",
}
~~~

When a normal regression is already green, mutant mode changes exactly the
named reducer/adapter branch and nothing else. The mapped method must fail with
this exact assertion label:

~~~python
expected_red_label = f"RED_{rid}_{REGRESSION_MUTANTS[rid]}"
~~~

R45's mutant accepts
`CORTEX_KEYCHAIN_EFFECT_AUTHORIZATION` with both effect flags and attempts to
construct `LiveExecutionCapability`. The mapped method must fail before the
recording factory count can become one.

## Task ownership of normative IDs

| Task | IDs made GREEN | Required boundary |
| --- | --- | --- |
| Task 1 | R26-R32 | Test inventory, independent model oracles, process snapshots and total old-route removal. |
| Task 2 | R06-R10, R33-R35, R39 | Swift anchors, exact wait/reap, result branches, absolute deadline and secret lifetime. |
| Task 3 | R01-R05, R11-R14, R37 | Swift command provenance, compensation reducer and disjoint phase cutoffs. |
| Task 4 | R15-R25, R36, R38 | Python capability, requests, terminal effects, live-adapter parity, process authority, deadlines and close fan-out. |
| Task 5 | R40-R45 | Real fixture, production/test boundary, cross-version manifest, flake, structure and authorization. |

## Final self-review checklist

Before claiming the implementation plan complete, read the design again and
prove each item:

- [ ] Two private anchor states exist in both native and direct-Python process
  adapters; exact WNOWAIT changes running to exited and exact waitpid consumes
  exited.
- [ ] Running revalidation uses the full proc/getsid/proc sandwich; exited
  revalidation uses exact second waitid and tolerates zombie getsid ESRCH by
  never calling getsid.
- [ ] Native settlement makes only the narrow three-part claim and byte 0x13
  never claims hostile-descendant absence.
- [ ] All closed Resume/Signal/Reap/Group/Poll/I/O/Close values have explicit
  test branches; failures remain unresolved and every pipe receives its own
  close attempt.
- [ ] Control wins simultaneous readiness; partial request, EOF, EAGAIN,
  unknown/duplicate/out-of-order frames, close, helper exit and missing ACK all
  have exact fail-closed or UNCLEAR outcomes.
- [ ] Python creates and transmits the absolute Swift nanosecond deadline;
  Swift never creates a new 70-second epoch.
- [ ] Production Popen uses close_fds true, one passed control FD and immediate
  unused-end closure; Swift restores CLOEXEC/nonblocking before request parse.
- [ ] Swift settled values and attach/absence permits carry exact command
  context and private single-use registry provenance.
- [ ] LiveExecutionCapability is minted only by the exact triple gate;
  authorize_cleanup has no boolean; callers cannot supply operation,
  cleanup approval, mappings or argv.
- [ ] ObserverBaseline/SecurityAgentSnapshot cannot cross into
  ProcessSnapshot consumers or the reverse.
- [ ] Process and effect models are independent, record transition indices,
  replay raw prefixes in external predicates and enumerate every trace through
  depth five without deduplication.
- [ ] Forged/stale/replayed permits, numeric signal, post-reap signal, omitted
  reap, false cleanup and post-terminal ordinary/inspect/delete mutants are
  rejected.
- [ ] The old six process routes and all their tests are removed before any
  default suite; the sole real child route has a transitive no-spawn call
  graph.
- [ ] Work cutoff, supervisor hard deadline and outer hard deadline are exactly
  0.50, 0.65 and 1.20 seconds from one start; no supervisor action occurs
  after 0.65 and containment/scan finish before 1.20.
- [ ] Master and Wire never alias; Wire erases before every outcome/frame;
  create Master survives exactly through SecItemAdd and then erases.
- [ ] Dynamic inventory includes every module-owned non-live TestCase exactly
  once; the 45 map keys and values are unique; Python 3.11/3.14 started-test
  streams match byte for byte with zero skip.
- [ ] Every retained testing route is conditional, rejected by production and
  absent as token/symbol from the production binary.
- [ ] Every mapped test has an individual RED or exact unsafe-mutant receipt,
  including R45.
- [ ] Every checkpoint records task base/head, exact paths, test receipt,
  cumulative diff and unchanged primer-diff SHA.
- [ ] S3_FINAL is frozen before the separate three-document S4 rebaseline.

The only acceptable self-review conclusion is no uncovered design requirement,
no unresolved signature mismatch and no unbound authority. A failed item
freezes implementation or the next task.
