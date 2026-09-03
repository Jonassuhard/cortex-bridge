# S3 Owned-Process Supervision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace S3's forgeable process-cleanup and terminal-effect boundaries with exact unreaped-session ownership, typed process/effect receipts, disjoint deadlines, and harmless reproducible tests.

**Architecture:** The Swift helper owns an isolated suspended Darwin session and can issue group signals only through a validated unreaped anchor; only a settled invocation can produce a quiescence proof or mount-compensation permit. The Python live harness uses a monotone effect state with fixed command specifications and receipt-derived safety permits. Descendant races are tested through a pure deterministic model; the only real default process probe uses one self-expiring direct child with guardian and witness pipes.

**Tech Stack:** Swift 6/Darwin `posix_spawn`, `proc_pidinfo`, `waitid` and Security.framework; Python 3.11+ standard library `unittest`, `ctypes`, `subprocess` and deterministic state exploration; Git/Gitleaks.

**Spec:** `docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md`

## Global Constraints

- Work only in `/Users/asterion/Desktop/cortex-bridge/.worktrees/codex-v054-storage-consolidation` on branch `codex/v054-storage-consolidation`.
- Implementation base is the approved design commit `0240377`; preserve the failed-review history through `2b85e504` and do not rewrite it.
- Do not edit, stage or commit the pre-existing `primer.md` change.
- Only these implementation files are in scope: `native/macos/disk_image_keychain.swift`, `tests/disk_image_keychain_harness.py`, and `tests/test_disk_image_keychain_helper.py`.
- No S4 file may change until this plan is complete and independently approved.
- Run no live Keychain, DiskImages, `hdiutil`, mount, detach, quarantine, SecurityAgent, Chrome or Cortex runtime effect.
- Never define the action-time authorization environment while implementing this plan.
- Keep the public six-key helper response, existing stable error codes, strict ten-key request, exact Keychain item schema, 43-character Base64URL secret, no-UI policy and secret-zeroization contract unchanged.
- Every subprocess, pipe operation, process scan, wait and cleanup consumes one finite absolute monotonic deadline; a retry never creates new time.
- No caller may obtain a raw signalable PID or PGID. The only production negative-PGID signal is private to the anchored kernel adapter.
- Any incomplete identity, process lineage, output, deadline, detach, absence or cleanup evidence fails closed.
- Default tests may execute only fakes/models and the one guardian/witness direct-child probe. Authorized live tests remain selected separately and unexecuted.
- Use `.venv/py311/bin/python` for the Python 3.11 gate and the existing repository venv for the Python 3.14 compatibility gate.
- Each task has one writer, ends in a dedicated commit, and receives fresh spec-compliance plus code-quality review before the next task begins.
- No push, merge, tag, release or cleanup is part of this plan.

---

### Task 1: Replace unsafe numeric process-tree tests with a pure owned-process model

**Files:**
- Create: `tests/disk_image_keychain_harness.py`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Produces `ExactProcessIdentity`, `PartialProcessIdentity`, `ProcessSnapshot`, `ProcessTracker`, `OwnedSessionAnchor`, `OwnedGroupSignalPermit`, `ScriptedProcessAdapter`, and `explore_process_traces`.
- Preserves the existing `build_selected_suite` default/live selection contract.
- Removes the real `ignore-term-grandchild`/numeric receipt cleanup path before any complete default suite is run again.
- Does not modify production Swift or claim a product behavior fix.

- [ ] **Step 1: Add a static RED that identifies the unsafe default path**

Add `DiskImageKeychainHarnessSafetyTests` and require the old helpers and receipt fields to be absent from the default test source:

```python
class DiskImageKeychainHarnessSafetyTests(unittest.TestCase):
    def test_default_suite_has_no_numeric_process_tree_cleanup(self):
        source = Path(__file__).read_text(encoding="utf-8")
        for forbidden in (
            "_harmless_process_tree_command",
            "_assert_tree_gone_and_cleanup_if_needed",
            'receipt["pgids"]',
            'receipt["pids"]',
            "os.killpg(pgid, signal.SIGKILL)",
        ):
            self.assertNotIn(forbidden, source)

    def test_process_identity_contract_includes_uid_and_birth(self):
        harness = importlib.import_module("tests.disk_image_keychain_harness")
        fields = {
            field.name
            for field in dataclasses.fields(harness.ExactProcessIdentity)
        }
        self.assertEqual(fields, {
            "pid", "ppid", "pgid", "uid", "start_seconds",
            "start_microseconds", "session_id",
        })
```

- [ ] **Step 2: Run only the new static tests and confirm RED for the intended reason**

Run:

```bash
PYTHON=.venv/py311/bin/python
"$PYTHON" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainHarnessSafetyTests -v
```

Expected: failure because the numeric process-tree helpers/receipts are still present and `ExactProcessIdentity` does not yet exist. Do not run the current complete default suite.

- [ ] **Step 3: Create the pure immutable snapshot and tracker types**

Implement in `tests/disk_image_keychain_harness.py`:

```python
@dataclass(frozen=True)
class ExactProcessIdentity:
    pid: int
    ppid: int
    pgid: int
    uid: int
    start_seconds: int
    start_microseconds: int
    session_id: int

@dataclass(frozen=True)
class PartialProcessIdentity:
    pid: int
    ppid: int
    pgid: int
    uid: int
    missing: frozenset[str]

@dataclass(frozen=True)
class ProcessSnapshot:
    exact_identities: Sequence[ExactProcessIdentity]
    partial_identities: Sequence[PartialProcessIdentity]
    vanished_pids: frozenset[int]
    enumeration_complete: bool
    tree_complete: bool
    uncertainty_reasons: Sequence[str]

@dataclass(frozen=True)
class OwnedSessionAnchor:
    identity: ExactProcessIdentity
    generation: object

@dataclass(frozen=True)
class OwnedGroupSignalPermit:
    anchor: OwnedSessionAnchor
    observed_members: Sequence[ExactProcessIdentity]
    snapshot_generation: int
```

`ProcessTracker.reduce(snapshot)` must collect lineage before UID filtering. A related partial/foreign-UID identity, a late child, a reused identity, a short read followed by liveness, or an incomplete scan permanently sets `lineage_uncertain`. `cleanup_verified` is true only after exact root reap and a complete empty final owned tree.

- [ ] **Step 4: Replace each real tree scenario with a scripted state trace**

Implement a `ScriptedProcessAdapter` whose methods accept absolute deadlines and return only typed snapshots/observations. Add a breadth-first trace explorer with deterministic event ordering:

```python
PROCESS_EVENTS = (
    "exact_child", "partial_child", "foreign_uid_child", "parent_reused",
    "late_child", "root_exit", "scan_incomplete", "zero_then_live",
    "zero_then_esrch", "group_membership_changed",
)

def explore_process_traces(initial, *, max_depth=5):
    queue = collections.deque([(initial, ())])
    seen = set()
    while queue:
        state, trace = queue.popleft()
        key = state.canonical_key()
        if key in seen:
            continue
        seen.add(key)
        yield state, trace
        if len(trace) < max_depth:
            for event in PROCESS_EVENTS:
                queue.append((state.apply(event), trace + (event,)))
```

Replace the current default integration-orchestration process-tree tests with model cases. Keep the authorized live suite definitions but make them unreachable without the existing exact gates.

- [ ] **Step 5: Add adversarial model GREEN assertions**

Cover this exact matrix:

| Test | Scripted input | Required oracle |
| --- | --- | --- |
| `test_partial_or_foreign_related_identity_permanently_blocks_cleanup` | exact root plus partial child or foreign-UID child whose PPID is the root | `lineage_uncertain is True`, no signal permit, cleanup false after every later snapshot |
| `test_zero_then_live_is_not_vanished` | full read returns zero, immediate reread returns zero, liveness succeeds and short record exists | PID is partial, not vanished; cleanup false |
| `test_zero_then_esrch_is_the_only_vanished_case` | both full reads return zero and liveness returns `ESRCH` | PID appears once in `vanished_pids` |
| `test_late_child_after_adoption_close_never_recovers_cleanup` | root disappears, then a new child of an exact tracked member appears | child is not adopted; permanent lineage uncertainty |
| `test_reused_parent_cannot_adopt_child` | parent PID retains number but changes birth timestamp before child appears | child is not adopted or signalled |
| `test_signal_permit_expires_on_snapshot_change` | issue permit at generation 3, reduce generation 4, attempt signal | adapter rejects stale permit before syscall |
| `test_process_state_model_never_emits_raw_numeric_signal_target` | explore every event through depth 5 | all signal actions carry `OwnedGroupSignalPermit`, never `int` |
| `test_exhaustive_short_traces_preserve_fail_closed_invariants` | breadth-first event exploration through depth 5 | any incomplete/foreign/reused/late trace keeps cleanup false |

Run only `DiskImageKeychainHarnessSafetyTests` and the new pure-model class. Expected: PASS with no subprocess spawn.

- [ ] **Step 6: Prove the default selector cannot execute a real group signal**

Patch both `os.killpg` and direct negative-PID `os.kill` to raise, then execute the default suite selector through a recording result. Assert that neither patch was called. This step may run only after all old numeric real-tree scenarios have been removed. Task 4 will add the private anchored live adapter and repeat the same default-suite proof against that exact method.

- [ ] **Step 7: Run Task 1 gates and commit**

Run:

```bash
PYTHON=.venv/py311/bin/python
PYTHONHASHSEED=0 LANG=C LC_ALL=C \
  "$PYTHON" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainHarnessSafetyTests \
  tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests -v
"$PYTHON" - <<'PY'
from pathlib import Path
compile(Path("tests/disk_image_keychain_harness.py").read_text(),
        "tests/disk_image_keychain_harness.py", "exec")
compile(Path("tests/test_disk_image_keychain_helper.py").read_text(),
        "tests/test_disk_image_keychain_helper.py", "exec")
PY
git diff --check
```

Expected: all selected tests pass, no skip, no subprocess effect, and the static scan finds no old PID/PGID receipt cleanup.

Commit only the two Task 1 files:

```bash
git add tests/disk_image_keychain_harness.py tests/test_disk_image_keychain_helper.py
git commit -m "test(storage): replace unsafe process tree probes"
```

- [ ] **Step 8: Independent checkpoint review**

Give a fresh read-only reviewer the spec, this Task 1 section, exact base/HEAD diff and test receipt. Require explicit confirmation that default tests cannot call numeric group cleanup and that model success cannot be forged from a tuple or boolean. Any Critical or Important finding blocks Task 2.

---

### Task 2: Replace the Swift child runner with an anchored session supervisor

**Files:**
- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Consumes the unchanged strict helper request and secret buffer contracts.
- Produces `ProcessBirthIdentity`, `SpawnRequest`, `ProcessKernel`, `DarwinProcessKernel`, `UnreapedSessionAnchor`, `ReapedOwnedGroup`, `ProcessQuiescenceProof`, `InvocationCause`, `ExitStatus`, `CompleteCapturedOutput`, `SpawnRefusal`, `UnresolvedInvocation`, `InvocationOutcome`, `SettledInvocation`, `InvocationWindow`, and `HdiutilInvoking.invoke`.
- The public helper response remains the same six keys and no test-only raw PID/PGID enters it.

- [ ] **Step 1: Write RED scenario tests for ownership and terminal proof**

Compile the helper with `-D CORTEX_STORAGE_HELPER_TESTING` and invoke a no-effect scripted-kernel route `--test-supervisor-scenario NAME`. Add this exact matrix:

| Test | Scenario | Required trace/result |
| --- | --- | --- |
| `test_valid_receipt_with_unreaped_child_is_unresolved` | `receipt-unreaped` | `unresolved`, zero compensation permit |
| `test_valid_receipt_with_group_present_is_unresolved` | `receipt-group-present` | exact reap followed by group present, therefore `unresolved` |
| `test_truncated_output_never_yields_settled_receipt` | `output-truncated` | output marked incomplete, zero parsed device |
| `test_exit_observed_keeps_anchor_until_last_signal_then_reaps` | `exit-pipe-held` | `waitid_wnowait`, TERM, KILL, exact waitpid, absence observation in this order |
| `test_pgid_reuse_after_reap_never_emits_signal` | `group-reused-after-reap` | no signal after `waitpid`; `unresolved` |
| `test_short_or_changed_birth_uid_pgid_sid_writes_zero_stdin` | subtests `identity-short`, `birth-changed`, `uid-changed`, `pgid-changed`, `sid-changed` | stdin byte count zero and no group signal for each |
| `test_echild_is_not_a_reap_proof` | `waitpid-echild` | `unresolved`, no quiescence proof |
| `test_signal_trace_contains_no_signal_after_reap` | every scripted supervisor scenario | last TERM/KILL index is lower than exact-reap index |

The scenario output is test-only structured JSON containing lifecycle states,
stdin byte count and symbolic signal events. It must not contain a PID, PGID or
caller-provided `reaped/gone` success boolean.

- [ ] **Step 2: Run the supervisor tests and confirm RED**

Run the new `DiskImageKeychainSwiftSupervisorTests` only. Expected: failures because the current runner reaps before its last group checks and exposes forgeable cleanup booleans.

- [ ] **Step 3: Introduce closed process outcomes and the kernel protocol**

Replace `ProcessInvocationFailure` with:

```swift
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
```

Keep `ProcessQuiescenceProof`, `UnreapedSessionAnchor`, `ReapedOwnedGroup` and raw process numbers `fileprivate`. `ScriptedProcessKernel` supplies kernel events, not outcome proofs.

- [ ] **Step 4: Implement suspended isolated spawn and identity capture**

In `DarwinProcessKernel`, configure:

```swift
POSIX_SPAWN_CLOEXEC_DEFAULT
POSIX_SPAWN_SETSID
POSIX_SPAWN_START_SUSPENDED
```

Before SIGCONT or stdin, require full birth timestamp, effective UID, `pgid == pid`, and `sid == pid`. On incomplete identity, terminate/reap only the still-suspended direct child while it remains waitable and return `unresolved`; issue no group signal.

- [ ] **Step 5: Implement non-reaping observation, bounded drain and anchored finalization**

Use `waitid(P_PID, childPID, WEXITED | WNOHANG | WNOWAIT)` during execution. Check work/hard deadlines before and after each nonblocking read/append. Finalize in this order:

```text
close stdin
revalidate unreaped anchor
TERM through anchor if required
continue bounded drain/exit observation
revalidate same unreaped anchor
KILL through anchor if required
observe exact exit
waitpid == exact pid
no-signal group absence observation == ESRCH
close each pipe independently
zeroize secret
create ProcessQuiescenceProof
```

`ECHILD`, deadline expiry, identity mismatch, `EPERM`, incomplete drain or non-ESRCH final group observation returns `unresolved`.

- [ ] **Step 6: Adapt `HdiutilInvoking` and existing fake scenarios**

Use:

```swift
protocol HdiutilInvoking {
    func invoke(
        _ command: HdiutilCommand,
        secret: SecretBuffer?,
        window: InvocationWindow
    ) -> InvocationOutcome
}
```

Existing Keychain/create/detach logic may parse output only from `settled`. Update all scripted helper scenarios to drive `ScriptedProcessKernel`; remove any direct construction of a quiescence success proof.

- [ ] **Step 7: Run Task 2 GREEN/typecheck gates and commit**

Run:

```bash
PYTHON=.venv/py311/bin/python
"$PYTHON" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests -v
xcrun swiftc -typecheck native/macos/disk_image_keychain.swift -framework Security
git diff --check
```

Expected: all supervisor scenarios pass, no live executable is invoked, Swift typecheck exits zero with only the already documented deprecation warning.

Commit:

```bash
git add native/macos/disk_image_keychain.swift tests/test_disk_image_keychain_helper.py
git commit -m "refactor(storage): anchor native process supervision"
```

- [ ] **Step 8: Independent checkpoint review**

Require a fresh reviewer to trace every signal site, prove the leader remains unreaped while signals are possible, prove no caller constructs `ProcessQuiescenceProof`, and confirm `ECHILD` is not accepted as reap. Any Critical or Important finding blocks Task 3.

---

### Task 3: Make mount compensation receipt-driven with disjoint deadlines

**Files:**
- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Consumes Task 2 `InvocationOutcome` and `ProcessQuiescenceProof`.
- Produces `MountDeadlinePolicy`, `CompensableAttach`, the monotone mount-compensation states, and unchanged public `MOUNT_CLEANUP_UNCLEAR` behavior.

- [ ] **Step 1: Add RED tests for settled compensation and phase isolation**

Add `DiskImageKeychainMountCompensationTests` with this matrix:

| Test | Scripted outcomes | Required oracle |
| --- | --- | --- |
| `test_unresolved_attach_with_device_text_spawns_zero_detach` | attach `unresolved` with `/dev/disk99` bytes | call log contains attach only; public code `MOUNT_CLEANUP_UNCLEAR` |
| `test_settled_nonzero_attach_with_exact_device_detaches_once` | settled nonzero attach with complete one-device plist, settled detach, settled empty info | call log is attach/detach/info exactly once each; cleanup proven |
| `test_detach_requires_complete_quiescence_proof` | complete receipt object without supervisor proof | construction or consumption is rejected before detach spawn |
| `test_detach_nonzero_or_unresolved_skips_absence_probe` | detach settled nonzero, then detach unresolved | each subtest ends `MOUNT_CLEANUP_UNCLEAR` with no later info call |
| `test_absence_requires_settled_complete_zero_mapping` | info unresolved, truncated, one device, or one image entry | every subtest remains cleanup unclear |
| `test_insufficient_phase_budget_spawns_zero_child` | clock at each phase's work cutoff | zero adapter spawn |
| `test_detach_using_its_full_window_cannot_borrow_absence_time` | detach settles exactly at +54 s | absence phase starts with its original +54/+66 bounds or does not spawn; no extended deadline |
| `test_normal_work_at_cutoff_leaves_compensation_windows_intact` | attach failure at +40 s with settled receipt | detach/absence retain +40/+54 and +54/+66 bounds |
| `test_public_response_schema_and_error_codes_are_unchanged` | all public success/failure scenarios | six exact keys and existing stable codes only |

- [ ] **Step 2: Run the compensation class and confirm RED**

Expected failures: current code accepts device text from a failure without a quiescence proof and current 12-second reserve cannot contain two six-second teardowns plus work.

- [ ] **Step 3: Implement the exact production deadline policy**

Add a validating policy with one 70-second hard deadline:

```swift
struct MountDeadlinePolicy {
    let normal: InvocationWindow       // request start through +40 s
    let detach: InvocationWindow       // +40 s through +54 s
    let absence: InvocationWindow      // +54 s through +66 s
    let epilogueDeadline: Double       // +70 s
}
```

Every child reserves six seconds within its own phase. Minimum work is eight seconds for create/attach/detach and four seconds for info/isencrypted; the absence phase reserves six seconds of work. The constructor rejects overlap, an invalid ordering, a phase shorter than work plus finalization, or a non-finite timestamp.

- [ ] **Step 4: Implement the monotone compensation state machine**

Use these states:

```text
baselineVerified -> attaching -> attached(CompensableAttach)
-> validating -> compensatingDetach -> verifyingAbsence -> cleanupProven
Any state -> cleanupUnclear
```

Create `CompensableAttach` only from settled complete stdout with exactly one matching device. `unresolved` prohibits every later invocation. Detach consumes the permit once. Absence proof consumes only its own window and accepts exactly zero devices and zero image entries.

- [ ] **Step 5: Preserve receipts and public failure priority**

A settled nonzero response may preserve an exact device receipt before surfacing failure. An unresolved response may not. Any failed compensation returns `MOUNT_CLEANUP_UNCLEAR`; no path downgrades it to generic `HDIUTIL_FAILED` or claims the image unmounted.

- [ ] **Step 6: Run Task 3 GREEN and compatibility gates**

Run the compensation class, existing helper contract tests, Swift typecheck, and the four no-authorization CLI gates. Expected: all selected tests pass; each unauthorized command exits `64` with zero stdout/stderr; no live branch executes.

- [ ] **Step 7: Commit**

```bash
git add native/macos/disk_image_keychain.swift tests/test_disk_image_keychain_helper.py
git commit -m "fix(storage): require settled mount compensation"
```

- [ ] **Step 8: Independent checkpoint review**

Require a fresh reviewer to prove that every compensation command consumes a distinct phase and that output from `unresolved` cannot create a permit. Any Critical or Important finding blocks Task 4.

---

### Task 4: Replace generic Python effect routing with a typed terminal session

**Files:**
- Modify: `tests/disk_image_keychain_harness.py`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Consumes Task 1 exact process model and the existing gated live integration entry point.
- Produces `EffectPhase`, `TerminalEvent`, `EffectSession`, `CommandSpec`, `OrdinaryPermit`, `CleanupGrant`, `MountReceipt`, `DetachPermit`, `AbsencePermit`, `QuarantinePermit`, `ArtifactLedger`, `CommandReceipt`, `ProcessCleanupReceipt`, `DetachReceipt`, `UnmountedProof`, `QuarantineReceipt`, `DispositionReceipt`, `FinalVerdict`, and `DarwinOwnedProcessAdapter`.
- Exposes only the closed workflow methods named in the design; no public generic argv runner remains.

- [ ] **Step 1: Add the terminal/effect matrix as RED tests**

Add `DiskImageKeychainTerminalEffectTests` with this matrix:

| Test | Input/state | Required oracle |
| --- | --- | --- |
| `test_terminal_preobservation_blocks_all_ordinary_specs_before_spawn` | terminal event before each compile/create/mount/inspect/delete/encryption/disk/mapping call | adapter spawn count remains zero for every command, with and without stdin |
| `test_terminal_during_no_stdin_command_terminates_before_communication_continues` | observer becomes terminal after spawn of compile or info | bounded cleanup begins immediately; result bytes do not continue the workflow |
| `test_arbitrary_argv_cannot_be_marked_safety_only` | attempt to construct a safety command from `/usr/bin/true` or caller argv | no public constructor/API accepts it |
| `test_detach_permit_is_exact_bound_and_single_use` | wrong session, epoch, UUID, image, mount or device; then replay | every mismatch/replay gives zero spawn; exact first use gives one detach |
| `test_absence_permit_exists_only_after_exact_detach` | missing/nonzero/unresolved detach versus exact settled detach | only exact settled detach yields one absence permit |
| `test_unknown_mapping_after_terminal_preserves_without_probe` | terminal plus mount state unknown | no info/inspect/delete/quarantine call; ledger records preservation |
| `test_terminal_disposition_runs_detach_absence_quarantine_only` | exact mount receipt and image descriptor | exact call order detach/absence/descriptor rename |
| `test_terminal_path_never_calls_inspect_or_delete` | all terminal causes and artifact states | Keychain inspect/delete counts remain zero |
| `test_complete_nonzero_receipt_is_recorded_before_terminal_raise` | complete nonzero create/mount response plus terminal event | UUID/device is in ledger before terminal exception is observed |
| `test_securityagent_has_priority_over_observer_and_cleanup_failures` | every ordering of SecurityAgent, observer unavailable and cleanup error | final verdict is `FAIL securityagent_detected` whenever SecurityAgent exists; otherwise observer verdict remains `UNCLEAR observer_unavailable` |
| `test_every_pipe_close_is_attempted_when_prior_close_raises` | stdin close and stdout close each raise in separate subtests | stdin/stdout/stderr close attempt counters are all one |
| `test_outer_deadline_is_exactly_85_seconds_without_retry_reset` | fake clock advances across pre/Swift/post/finalization | all commands share the original hard timestamp and no retry extends it |

- [ ] **Step 2: Run the terminal class and confirm RED**

Expected: failure because current effect classification uses `input_text`, `safety_only` and `disposition_active`, and generic `_plist_command` remains callable after terminal observation.

- [ ] **Step 3: Implement the monotone effect session and sealed permits**

Implement these exact state and event types:

```python
class EffectPhase(enum.Enum):
    PREPARING = "preparing"
    ACTIVE = "active"
    TERMINAL = "terminal"
    DISPOSING = "disposing"
    CLOSED = "closed"

@dataclass(frozen=True)
class TerminalEvent:
    cause: str
    command_id: str
    stage: str
    observed_at: float
```

`EffectSession` exposes these signatures and no generic transition method:

| Method | Exact result/constraint |
| --- | --- |
| `activate(complete_baseline: ProcessSnapshot) -> OrdinaryPermit` | succeeds once from `PREPARING` only when the baseline is complete |
| `latch_terminal(event: TerminalEvent) -> None` | appends immutable event and irreversibly revokes ordinary permit |
| `ordinary_permit() -> OrdinaryPermit` | only in `ACTIVE`, bound to current session and epoch |
| `detach_permit(receipt: MountReceipt) -> DetachPermit` | only for the exact recorded receipt; permit is single-use |
| `begin_disposition() -> None` | only `TERMINAL` to `DISPOSING` |
| `close(receipt: DispositionReceipt) -> FinalVerdict` | freezes ledger and derives terminal-priority verdict |

Use private module seals plus session/epoch/receipt equality to reject forged, stale or replayed permits. Terminal transition is irreversible.

Freeze the receipt/permit bindings as:

```python
@dataclass(frozen=True)
class MountReceipt:
    session_id: str
    epoch: int
    transaction_id: str
    image_name: str
    mount_name: str
    encryption_uuid: str
    device: str

@dataclass(frozen=True)
class DetachReceipt:
    mount_receipt: MountReceipt
    command_receipt_id: str

@dataclass(frozen=True)
class UnmountedProof:
    detach_receipt: DetachReceipt
    absence_receipt_id: str
```

`CleanupGrant`, `DetachPermit`, `AbsencePermit` and `QuarantinePermit` include a private module seal and may be constructed only by `EffectSession` from these recorded receipts.

- [ ] **Step 4: Replace the generic runner with fixed command specifications**

Expose only this closed catalogue:

| Method | Input | Result |
| --- | --- | --- |
| `compile_helper(source: Path, target: Path)` | ordinary permit derived internally | `CommandReceipt` |
| `create_image(request: Mapping[str, object])` | fixed helper request | `CommandReceipt` plus optional image receipt |
| `mount_image(request: Mapping[str, object])` | fixed helper request | `CommandReceipt` plus optional mount receipt |
| `detach_normal(request: Mapping[str, object])` | active-session detach | `CommandReceipt` |
| `inspect_item(request: Mapping[str, object])` | active-session exact selector | `CommandReceipt` |
| `delete_item(request: Mapping[str, object], grant: CleanupGrant)` | active-session exact selector and cleanup grant | `CommandReceipt` |
| `probe_encryption(image: Path)` | fixed `hdiutil isencrypted -plist` | parsed `CommandReceipt` |
| `probe_disk(device: str)` | fixed `diskutil info -plist` | parsed `CommandReceipt` |
| `probe_mapping(image: Path, mount: Path)` | fixed `hdiutil info -plist` | parsed `CommandReceipt` |
| `detach_for_disposition(permit: DetachPermit)` | no caller argv | `DetachReceipt` |
| `prove_absence_for_disposition(permit: AbsencePermit)` | no caller argv | `UnmountedProof` |
| `quarantine_for_disposition(permit: QuarantinePermit)` | descriptor-relative rename only | `QuarantineReceipt` |

Each method constructs its fixed executable/argv or helper request internally. A terminal event blocks every ordinary method before spawn. During an already running command, terminal observation starts bounded cleanup independently of stdin.

- [ ] **Step 5: Implement exact Python process snapshots and anchored live cleanup**

The Darwin reader must retain PID, PPID, PGID and UID from short records. Determine lineage before UID filtering. Only the private `DarwinOwnedProcessAdapter.signal_owned_group(anchor, signal, deadline)` may translate a fresh exact unreaped anchor into a group signal; it revalidates the root/session and complete membership immediately before the signal. It never accepts a numeric receipt.

Do not use `Popen.communicate()` as terminal proof. Observe exit without reap, perform permitted signals, reap the exact child, then make a no-signal group absence observation. Close stdin/stdout/stderr in independent `try` blocks.

- [ ] **Step 6: Implement artifact ledger and exact terminal disposition**

Track:

```python
image = "absent" | "exact" | "quarantined" | "deleted" | "unknown"
mount = "proven_unmounted" | "exact_mounted" | "unknown"
keychain = "absent" | "exact_present" | "deleted" | "unknown"
```

After terminal, allow only exact detach, one bound absence proof and descriptor-relative quarantine. Missing evidence preserves artifacts. Never run compile, generic plist reconciliation, Keychain inspect or delete. Parse complete helper output and update non-secret receipts before deriving the final terminal verdict.

- [ ] **Step 7: Run Task 4 GREEN and negative gates**

Run the pure model class, terminal-effect class and existing live-gate tests with authorization absent. Also inspect call logs and assert no group signal adapter call occurs in the default suite. Expected: PASS, zero skip, no live effect.

- [ ] **Step 8: Commit**

```bash
git add tests/disk_image_keychain_harness.py tests/test_disk_image_keychain_helper.py
git commit -m "refactor(storage): type terminal integration effects"
```

- [ ] **Step 9: Independent checkpoint review**

Require a fresh reviewer to enumerate every post-terminal callable method and confirm that only receipt-bound detach/absence/quarantine survive. Require explicit review of foreign-UID lineage and root/session revalidation. Any Critical or Important finding blocks Task 5.

---

### Task 5: Add the contained real deadline witness and close S3

**Files:**
- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Consumes Task 2's real anchored supervisor and Task 1's safe default selector.
- Produces test-only `--deadline-witness-probe` and `--deadline-witness-child` routes under `CORTEX_STORAGE_HELPER_TESTING`.
- Returns no PID, PGID, secret, path, test-owned budget or cleanup-success assertion.

- [ ] **Step 1: Add the guardian/witness probe as RED**

Create `DiskImageKeychainContainedDeadlineProbeTests` that:

```python
def test_real_probe_uses_test_owned_deadline_and_witness_eof(self):
    guardian_read, guardian_write = os.pipe()
    witness_read, witness_write = os.pipe()
    nonce = secrets.token_hex(16)
    started = time.monotonic()
    process = subprocess.Popen(
        [str(self.helper), "--deadline-witness-probe",
         "--guardian-fd", str(guardian_read),
         "--witness-fd", str(witness_write),
         "--nonce", nonce],
        pass_fds=(guardian_read, witness_write),
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    os.close(guardian_read)
    os.close(witness_write)
    try:
        try:
            stdout, stderr = process.communicate(timeout=1.20)
        except subprocess.TimeoutExpired:
            os.close(guardian_write)
            guardian_write = -1
            try:
                process.wait(timeout=0.20)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.20)
            self.fail("deadline witness helper exceeded outer containment")
        elapsed = time.monotonic() - started
        witness = bytearray()
        while True:
            remaining = started + 1.20 - time.monotonic()
            self.assertGreater(remaining, 0, "witness EOF exceeded containment")
            readable, _, _ = select.select([witness_read], [], [], remaining)
            self.assertEqual(readable, [witness_read], "witness EOF not observed")
            chunk = os.read(witness_read, 4096)
            if not chunk:
                break
            witness.extend(chunk)
    finally:
        if guardian_write >= 0:
            os.close(guardian_write)
        os.close(witness_read)
    self.assertEqual(process.returncode, 0)
    self.assertEqual(stderr, "")
    self.assertLessEqual(elapsed, 0.65)
    self.assertEqual(witness.decode("ascii"), f"START:{nonce}\n")
    self.assertEqual(json.loads(stdout)["code"], "PROCESS_TIMEOUT")
```

The test owns: hard deadline `0.50 s`, tolerance `0.15 s`, output cap `64 KiB`, child TTL `0.90 s`, and outer containment `1.20 s`. Expected RED: the new routes and witness protocol do not exist.

- [ ] **Step 2: Implement the test-only direct child**

Under `CORTEX_STORAGE_HELPER_TESTING`, the child:

- validates the two inherited descriptors and 32-hex nonce;
- writes `START:<nonce>` to the witness;
- emits bounded continuous output slowly enough to reach the deadline before the cap;
- watches guardian EOF;
- self-exits at its independent 0.90-second monotonic TTL;
- creates no descendant and returns no process identifier.

- [ ] **Step 3: Route the probe through the real Task 2 supervisor**

The probe parent invokes its child with the production supervisor using testing grace constants and an allowed-inherited-FD set available only in the testing build. Python closes the guardian in `finally`, requires witness EOF, and reaps only its exact direct `Popen` child. If outer containment fails, direct `Popen.kill()` is allowed only before that child is reaped. No group signal or numeric process receipt appears in the Python probe.

- [ ] **Step 4: Run focused GREEN and the 20-run flake gate**

Run the contained-probe class once, then the same exact test twenty times in fresh processes. Record each return code and elapsed time. Expected: 20/20 PASS, every elapsed time within 0.65 seconds, matching nonce, witness EOF, exact helper reap and empty stderr. The fixture-child route is statically checked to contain no spawn/fork, and the scripted-kernel tests—not a self-reported real-probe field—prove the 64 KiB cap.

- [ ] **Step 5: Run the complete no-effect Task 3 matrix**

Run:

```bash
PYTHON=.venv/py311/bin/python
env -u CORTEX_KEYCHAIN_INTEGRATION_AUTHORIZATION \
  PYTHONHASHSEED=0 LANG=C LC_ALL=C \
  "$PYTHON" tests/test_disk_image_keychain_helper.py
```

Expected: every default fake/model/probe test passes, zero skip, and the gated live class is not constructed.

Run the four missing-authorization commands separately. For integration-only, effects-only, both effect flags, and cleanup-only, require exit `64`, zero stdout bytes and zero stderr bytes.

- [ ] **Step 6: Run compile, AST and compatibility gates**

Run:

```bash
xcrun swiftc -typecheck native/macos/disk_image_keychain.swift -framework Security
.venv/py311/bin/python - <<'PY'
from pathlib import Path
for name in ("tests/disk_image_keychain_harness.py",
             "tests/test_disk_image_keychain_helper.py"):
    compile(Path(name).read_text(), name, "exec")
PY
```

Extract and typecheck the embedded observer Swift source without executing it. Run an AST gate proving every subprocess run, wait, pipe communication and process scan receives a finite remaining deadline; every `Popen` creates a new session.

Run the full Task 3 test file under the repository Python 3.14 venv as a compatibility check. Expected: same test count and verdict as Python 3.11.

- [ ] **Step 7: Run final forbidden-pattern, diff and secret gates**

Require:

```text
no _harmless_process_tree_command
no _assert_tree_gone_and_cleanup_if_needed
no numeric PID/PGID receipt or child_pid output
no generic safety_only or disposition_active
no direct construction of ProcessQuiescenceProof outside the supervisor
no Python group signal outside DarwinOwnedProcessAdapter.signal_owned_group
only one Swift negative-PGID signal site, inside DarwinProcessKernel.signalOwnedGroup
default suite call count for the Python group-signal adapter == 0
```

Run `git diff --check`, staged diff inspection and Gitleaks. Confirm only the three implementation files changed across the full rearchitecture and `primer.md` remains excluded.

- [ ] **Step 8: Commit the contained probe**

```bash
git add native/macos/disk_image_keychain.swift tests/test_disk_image_keychain_helper.py
git commit -m "test(storage): add contained deadline witness"
```

- [ ] **Step 9: Final independent S3 review**

Build a clean review package from `0240377` to final HEAD containing the approved spec, this plan, exact diff and fresh evidence but no prior reviewer verdict. A fresh read-only reviewer must inspect both spec compliance and code quality. S3 becomes complete only with:

```text
Critical = 0
Important = 0
Task quality = Approved
```

Any Critical or Important finding freezes S3 again and requires an explicit architectural decision; it does not authorize another incremental loop.

- [ ] **Step 10: Rebaseline Phase S without starting S4**

After approval, update the ignored SDD ledger with the final S3 commit, test counts, probe flake receipt, typecheck/gate results, residual limits and review verdict. Generate a new Phase S plan hash only if the S4 dependency/interface text must change; otherwise record that S4 retains its reviewed single-source helper contract. Stop before S4 implementation and verify Git status.

## Plan self-review record

| Approved design section | Implemented and proved by |
| --- | --- |
| Swift closed process types, suspended session, unreaped anchor and no post-reap signal | Task 2 |
| Settled-only receipts, mount compensation and non-overlapping 70-second policy | Task 3 |
| Python monotone terminal state, fixed command catalogue and receipt-bound safety actions | Task 4 |
| Exact/partial UID-aware snapshots and permanent lineage uncertainty | Tasks 1 and 4 |
| Removal of unsafe numeric process-tree tests | Task 1 |
| Guardian/witness real probe with external timing/EOF oracles | Task 5 |
| All 24 required regressions | Tasks 1 through 5 matrices |
| Public protocol, Keychain/secret contracts and missing-authorization gates | Tasks 2, 3 and 5 |
| Python 3.11/3.14, Swift typecheck, AST, diff and secret proof gates | Task 5 |
| Independent zero-Critical/zero-Important completion review and S4 rebaseline | Task 5 |

Self-review found no uncovered approved requirement, unresolved type name or placeholder. The one real probe deliberately proves only the fixed direct fixture child, wall deadline and witness EOF; descendant/session races remain model evidence and are not mislabeled as live DiskImages proof.
