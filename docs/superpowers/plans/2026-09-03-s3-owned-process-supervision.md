# S3 Owned-Process Supervision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace S3's forgeable process-cleanup and terminal-effect boundaries with exact unreaped-session ownership, typed process/effect receipts, disjoint deadlines, and harmless reproducible tests.

**Architecture:** The Swift helper owns an isolated suspended Darwin session and can issue group signals only through a validated unreaped anchor; only a settled invocation can produce a quiescence proof or mount-compensation permit. The Python live harness uses a monotone effect state with fixed command specifications and receipt-derived safety permits. Descendant races are tested through a pure deterministic model; the only real default process probe uses one self-expiring direct child with guardian and witness pipes.

**Tech Stack:** Swift 6/Darwin `posix_spawn`, `proc_pidinfo`, `waitid` and Security.framework; Python 3.11+ standard library `unittest`, `ctypes`, `subprocess` and deterministic state exploration; Git/Gitleaks.

**Spec:** `docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md`

## Global Constraints

- Work only in `/Users/asterion/Desktop/cortex-bridge/.worktrees/codex-v054-storage-consolidation` on branch `codex/v054-storage-consolidation`.
- Immediately before Task 1, freeze `IMPLEMENTATION_BASE=$(git rev-parse HEAD)` plus the reviewed spec/plan SHA-256 values in the ignored SDD ledger. The base must be the commit containing the final reviewed plan bytes; final code review uses `IMPLEMENTATION_BASE..HEAD` and receives spec/plan as separate inputs. Preserve failed-review history through `2b85e504` and do not rewrite it.
- Do not edit, stage or commit the pre-existing `primer.md` change.
- Only these implementation files are in scope: `native/macos/disk_image_keychain.swift`, `tests/disk_image_keychain_harness.py`, and `tests/test_disk_image_keychain_helper.py`.
- No S4 implementation file may change until this plan is complete and independently approved. A documentation-only S4 rebaseline is mandatory afterward and precedes all S4 code.
- Run no live Keychain, DiskImages, `hdiutil`, mount, detach, quarantine, SecurityAgent, Chrome or Cortex runtime effect.
- Never define the action-time authorization environment while implementing this plan. No-effect subprocess gates use `env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0`; the real key is `CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION` and must be absent.
- Keep the public six-key helper response, existing stable error codes, strict ten-key request, exact Keychain item schema, 43-character Base64URL secret, no-UI policy and secret-zeroization contract unchanged.
- Every subprocess, pipe operation, process scan, wait and cleanup consumes one finite absolute monotonic deadline; a retry never creates new time.
- No caller may obtain a raw signalable PID or PGID. The only production negative-PGID signal is private to the anchored kernel adapter.
- Any incomplete identity, process lineage, output, deadline, detach, absence or cleanup evidence fails closed.
- Default tests may execute only fakes/models and the guardian/witness deadline/cancellation probes. Authorized live tests remain selected separately and unexecuted.
- Set `PYTHON311="$PWD/.venv/py311/bin/python"`. Resolve `PYTHON314` from the main checkout as `$(cd "$(dirname "$(git rev-parse --git-common-dir)")" && pwd)/.venv/bin/python`, then require its reported version to match `3.14.*` before use.
- Each task has one writer, ends in a dedicated commit, and receives fresh spec-compliance plus code-quality review before the next task begins. Every review must report `P0=0`, `P1=0`, `P2=0`; any P0-P2 finding freezes the task.
- No push, merge, tag, release or cleanup is part of this plan.

---

### Task 1: Replace unsafe numeric process-tree tests with a pure owned-process model

**Files:**
- Create: `tests/disk_image_keychain_harness.py`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Produces `ExactProcessIdentity`, `PartialProcessIdentity`, deeply immutable `ProcessSnapshot`, `ProcessTracker`, opaque `ModelOwnedSessionAnchor`, `OwnedGroupSignalPermit`, `ActionRecord`, `ScriptedProcessAdapter`, `reference_process_invariants`, `explore_process_traces`, and the closed `DEFAULT_TEST_CASES` selector.
- Replaces the current hard-coded `build_selected_suite` default classes with the closed manifest while preserving the separate live selection contract.
- Removes the real `ignore-term-grandchild`/numeric receipt cleanup path before any complete default suite is run again.
- Does not modify production Swift or claim a product behavior fix.

- [ ] **Step 1: Write the static and behavioral RED tests before the model**

Add `DiskImageKeychainHarnessSafetyTests` and `DiskImageKeychainProcessModelTests`. The static oracle parses syntax; its forbidden strings therefore cannot match themselves:

```python
class DiskImageKeychainHarnessSafetyTests(unittest.TestCase):
    def test_source_ast_has_no_unsafe_numeric_process_tree_cleanup(self):
        forbidden_defs = {
            "_harmless_process_tree_command",
            "_assert_tree_gone_and_cleanup_if_needed",
        }
        violations = []
        paths = [Path(__file__), Path("tests/disk_image_keychain_harness.py")]
        for path in paths:
            if not path.exists():
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            allowed_signal_calls = set()
            for owner in tree.body:
                if isinstance(owner, ast.ClassDef) and owner.name == "DarwinOwnedProcessAdapter":
                    for method in owner.body:
                        if isinstance(method, ast.FunctionDef) and method.name == "signal_owned_group":
                            allowed_signal_calls.update(
                                id(item) for item in ast.walk(method)
                                if isinstance(item, ast.Call)
                            )
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name in forbidden_defs:
                        violations.append((str(path), node.lineno, node.name))
                if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                    if node.slice.value in {"pids", "pgids"}:
                        violations.append((str(path), node.lineno, node.slice.value))
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    if (id(node) not in allowed_signal_calls
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                            and node.func.attr == "killpg"):
                        violations.append((str(path), node.lineno, "os.killpg"))
                    if (id(node) not in allowed_signal_calls
                            and isinstance(node.func.value, ast.Name)
                            and node.func.value.id == "os"
                            and node.func.attr == "kill"
                            and node.args
                            and isinstance(node.args[0], ast.UnaryOp)
                            and isinstance(node.args[0].op, ast.USub)):
                        violations.append((str(path), node.lineno, "os.kill-negative"))
        self.assertEqual(violations, [])

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

Write these behavior tests now, before creating the module:

| Test | Scripted input | Required oracle |
| --- | --- | --- |
| `test_partial_or_foreign_related_identity_permanently_blocks_cleanup` | exact root plus partial child or foreign-UID child whose PPID is root | permanent lineage uncertainty, no permit, cleanup false |
| `test_partial_bridge_to_exact_grandchild_blocks_cleanup` | root → partial child → exact grandchild | grandchild not signalled; cleanup false |
| `test_zero_then_live_is_not_vanished` | two zero full reads, liveness success, short record | partial, not vanished; cleanup false |
| `test_zero_then_esrch_is_the_only_vanished_case` | two zero full reads and `ESRCH` | PID appears once in vanished set |
| `test_late_child_after_adoption_close_never_recovers_cleanup` | root disappears, then new child of tracked member | no adoption; permanent uncertainty |
| `test_reused_parent_cannot_adopt_child` | same PID with changed birth before child | no adoption or signal |
| `test_changed_group_membership_invalidates_signal_permit` | permit generation 3, changed member at generation 4 | stale permit rejected before adapter call |
| `test_process_state_model_never_emits_raw_numeric_signal_target` | every trace through depth five | every action carries opaque permit, never integer |
| `test_exhaustive_short_traces_preserve_fail_closed_invariants` | all 111,111 traces of zero to five events | independent reference predicate accepts every produced action log |
| `test_reference_oracle_rejects_unsafe_mutants` | false cleanup after partial, accepted stale permit, raw integer signal | each mutant raises the reference invariant assertion |

- [ ] **Step 2: Run every new test and record the RED reasons**

Run:

```bash
PYTHON=.venv/py311/bin/python
"$PYTHON" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainHarnessSafetyTests -v
"$PYTHON" -m unittest \
  tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests -v
```

Expected: static failure on the existing helper definitions/numeric cleanup and import/behavior failures because the pure model does not exist. Record each test ID and failure reason. Do not run the current complete default suite.

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

@dataclass(frozen=True)
class ModelOwnedSessionAnchor:
    opaque_id: object

@dataclass(frozen=True)
class OwnedGroupSignalPermit:
    anchor: ModelOwnedSessionAnchor
    snapshot_generation: int
    member_digest: str

@dataclass(frozen=True)
class ActionRecord:
    kind: str
    authority: object | None
    value: object | None
```

`OwnedGroupSignalPermit.__post_init__` validates a 64-character lowercase hexadecimal member digest. Exact member identities remain only in the tracker's private issuance registry; the permit and its representation expose no PID/PGID target. The live `PythonOwnedSessionAnchor` is a different private type introduced only in Task 4.

`ProcessTracker.reduce(snapshot)` must collect lineage before UID filtering. A related partial/foreign-UID identity, a late child, a reused identity, a short read followed by liveness, or an incomplete scan permanently sets `lineage_uncertain`. `cleanup_verified` is true only after exact root reap and a complete empty final owned tree.

- [ ] **Step 4: Replace each real tree scenario with a scripted state trace**

Implement a `ScriptedProcessAdapter` whose methods accept absolute deadlines and return only typed snapshots/observations. Add an exhaustive trace explorer without state deduplication and a separate reference predicate that derives allowed actions from the raw trace:

```python
PROCESS_EVENTS = (
    "exact_child", "partial_child", "foreign_uid_child", "parent_reused",
    "late_child", "root_exit", "scan_incomplete", "zero_then_live",
    "zero_then_esrch", "group_membership_changed",
)

def explore_process_traces(initial, *, max_depth=5):
    for depth in range(max_depth + 1):
        for trace in itertools.product(PROCESS_EVENTS, repeat=depth):
            yield reduce_trace(initial, trace), trace

def reference_process_invariants(trace, action_log):
    uncertain = {
        "partial_child", "foreign_uid_child", "parent_reused",
        "late_child", "scan_incomplete", "zero_then_live",
        "group_membership_changed",
    }
    has_uncertainty = any(event in uncertain for event in trace)
    latest_generation = len(trace)
    for action in action_log:
        if action.kind == "signal":
            assert isinstance(action.authority, OwnedGroupSignalPermit)
            assert action.authority.snapshot_generation == latest_generation
        if action.kind == "cleanup_verified":
            assert action.value is False or not has_uncertainty
```

`reference_process_invariants` consumes only the raw trace and immutable
`ActionRecord` values; importing or calling `ProcessTracker` from it is a static
test failure.

Replace the current default integration-orchestration process-tree tests with model cases. Keep the authorized live suite definitions but make them unreachable without the existing exact gates.

- [ ] **Step 5: Make the prewritten model tests GREEN and prove oracle sensitivity**

Implement only enough reducer/reference behavior to satisfy the Step 1 matrix. Feed the reference predicate three deliberately bad action logs: cleanup true after a partial identity, a stale permit accepted after epoch advance, and a raw integer signal. Each must fail the independent predicate. Run the two classes and require PASS with no subprocess spawn.

- [ ] **Step 6: Install and prove the closed default-test manifest**

Define `DEFAULT_TEST_CASES` as the exact ordered tuple of the two existing safe classes plus the new safety/model classes. Remove the old real tree and deadline-probe methods before adding their owning classes to the manifest. Add a non-recursive meta-test that compares the manifest's class-name set to an explicit literal, flattens every selected test ID, proves each appears exactly once, and proves `DiskImageKeychainLiveIntegrationTests` is absent. Statically reject `--deadline-drain-probe` and real tree helpers from methods belonging to a default class.

As an external gate, wrap `os.killpg` and negative-PID `os.kill` with raising spies, execute the default suite once, and require zero calls. This observes Python only; Task 2 separately proves that every default Swift scenario uses `ScriptedProcessKernel` and refuses `DarwinProcessKernel` construction.

- [ ] **Step 7: Run Task 1 gates and commit**

Run:

```bash
PYTHON="$PWD/.venv/py311/bin/python"
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
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

Give a fresh read-only reviewer the spec, this Task 1 section, exact base/HEAD diff and test receipt. Require explicit confirmation that default tests cannot call numeric group cleanup, that the closed manifest selects every safe test exactly once, and that the independent reference predicate rejects the three unsafe mutants. Require `P0=0`, `P1=0`, `P2=0`; otherwise Task 1 freezes.

---

### Task 2: Replace the Swift child runner with an anchored session supervisor

**Files:**
- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Consumes the unchanged strict helper JSON request and exact Keychain schema.
- Produces nested/private `OwnedProcessSupervisor.InvocationOutcome`, `SettledInvocation`, `ProcessQuiescenceProof`, `CompensableAttach`, `ProcessBirthIdentity`, `SpawnRequest`, `SuspendedChild`, `ProcessKernel`, `ProcessIO`, `DarwinProcessKernel`, `UnreapedSessionAnchor`, `ReapedOwnedGroup`, `TerminationSignal`, `ExitObservation`, `InvocationCause`, `ExitStatus`, `CompleteCapturedOutput`, `SpawnRefusal`, `UnresolvedInvocation`, `InvocationWindow`, `MasterSecret`, `WireSecret`, `HelperControlChannel`, and `HdiutilInvoking.invoke`.
- Adds the non-secret `--control-fd <decimal-fd>` production boundary with the exact one-byte protocol from the spec.
- The public helper response remains the same six keys and no test-only raw PID/PGID enters it.

- [ ] **Step 1: Write RED scenario tests for ownership and terminal proof**

Compile the helper with `-D CORTEX_STORAGE_HELPER_TESTING` and invoke a no-effect scripted-kernel route `--test-supervisor-scenario NAME`. Add this exact matrix:

| Test | Scenario | Required trace/result |
| --- | --- | --- |
| `test_valid_receipt_with_unreaped_child_is_unresolved` | `receipt-unreaped` | `unresolved`, zero compensation permit |
| `test_valid_receipt_with_group_present_is_unresolved` | `receipt-group-present` | exact reap followed by group present, therefore `unresolved` |
| `test_truncated_output_never_yields_settled_receipt` | `output-truncated` | output marked incomplete, zero parsed device |
| `test_capped_output_never_yields_settled_receipt` | `output-capped` | cap reason, zero parsed device |
| `test_exit_observed_keeps_anchor_until_last_signal_then_reaps` | `exit-pipe-held` | `waitid_wnowait`, TERM, KILL, exact waitpid, absence observation in this order |
| `test_pgid_reuse_after_reap_never_emits_signal` | `group-reused-after-reap` | no signal after `waitpid`; `unresolved` |
| `test_short_or_changed_birth_uid_pgid_sid_writes_zero_stdin` | subtests `identity-short`, `birth-changed`, `uid-changed`, `pgid-changed`, `sid-changed` | stdin byte count zero and no group signal for each |
| `test_waitid_exact_exit_matrix` | no-event, wrong PID, wrong code, prefilled buffer, EINTR then exact exit | only exact child SIGCHLD terminal code becomes exit; EINTR keeps same deadline |
| `test_echild_is_not_a_reap_proof` | `waitpid-echild` | `unresolved`, no quiescence proof |
| `test_identity_change_between_term_and_kill_blocks_kill` | birth/UID/group change after TERM | zero KILL; unresolved |
| `test_no_term_or_kill_after_kill_state` | state already recorded KILL | no later signal event |
| `test_invalid_suspended_identity_aborts_direct_child_only` | invalid initial identity | direct abort, `waitpid == exact pid`, zero group signal |
| `test_scripted_routes_refuse_darwin_kernel` | every `--test-supervisor-scenario` | Darwin-kernel factory raises before spawn; scripted factory called once |
| `test_valid_output_with_unclear_cleanup_never_settles` | complete parseable output plus reap/group uncertainty | unresolved, no success/compensation proof |
| `test_clock_jump_matrix_checks_every_io_and_cleanup_boundary` | jump before/after poll/read/write/append/close/reap/scan | no action after hard deadline; unresolved |
| `test_master_and_wire_secret_lifetimes_are_separate` | create success/failure around Keychain add | wire zeroized at each child outcome; master alive for add then zeroized |
| `test_signal_trace_contains_no_signal_after_reap` | every scripted supervisor scenario | last TERM/KILL index is lower than exact-reap index |

The scenario output is test-only structured JSON containing lifecycle states,
stdin byte count and symbolic signal events. It must not contain a PID, PGID or
caller-provided `reaped/gone` success boolean.

- [ ] **Step 2: Run the supervisor tests and confirm RED**

Run the new `DiskImageKeychainSwiftSupervisorTests` only. Expected: failures because the current runner reaps before its last group checks and exposes forgeable cleanup booleans.

- [ ] **Step 3: Introduce closed process outcomes and the kernel protocol**

Nest the outcomes and their factories inside `OwnedProcessSupervisor`:

```swift
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
        private let proof: ProcessQuiescenceProof
    }
    private struct ProcessQuiescenceProof {
        let terminalGeneration: UInt64
    }
}
```

Give every proof/outcome/anchor initializer nested `private` visibility and construct them only in named reducer methods. Add a syntax gate that asserts the unique constructor sites. `ScriptedProcessKernel` supplies kernel/I/O/clock events, not outcome proofs.

- [ ] **Step 4: Implement suspended isolated spawn and identity capture**

In `DarwinProcessKernel`, configure:

```swift
POSIX_SPAWN_CLOEXEC_DEFAULT
POSIX_SPAWN_SETSID
POSIX_SPAWN_START_SUSPENDED
```

Before SIGCONT or stdin, require full birth timestamp, effective UID, `pgid == pid`, and `sid == pid`. On incomplete identity, terminate/reap only the still-suspended direct child while it remains waitable and return `unresolved`; issue no group signal.

Read full `proc_bsdinfo`, call `getsid(pid)`, then reread full `proc_bsdinfo`; both identities and SID must agree. Add typed kernel operations `resumeSuspended(anchor, deadline)` and `abortAndReapSuspended(child, deadline)`. Replace raw signal integers with `TerminationSignal.term` and `.kill`. Remove `POSIX_SPAWN_SETPGROUP` and `posix_spawnattr_setpgroup`.

- [ ] **Step 5: Implement non-reaping observation, bounded drain and anchored finalization**

Inject `ProcessIO` and the monotonic clock so scripted scenarios control poll/read/write/close and time. Zero `siginfo_t`, use `waitid(P_PID, childPID, WEXITED | WNOHANG | WNOWAIT)`, and recognize exit only for exact PID/SIGCHLD/terminal `si_code`; `si_pid == 0` remains running. Check the one hard deadline before and after each poll/read/write/append/close/reap/scan. Finalize in this order:

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
zeroize per-invocation wire secret
create ProcessQuiescenceProof
```

`ECHILD`, deadline expiry, identity mismatch, `EPERM`, incomplete drain or non-ESRCH final group observation returns `unresolved`.

- [ ] **Step 6: Adapt `HdiutilInvoking` and existing fake scenarios**

Use:

```swift
protocol HdiutilInvoking {
    func invoke(
        _ command: HdiutilCommand,
        secret: WireSecret?,
        window: InvocationWindow
    ) -> OwnedProcessSupervisor.InvocationOutcome
}
```

Existing Keychain/create/detach logic may parse output only from `settled`. Update all scripted helper scenarios to drive `ScriptedProcessKernel`; remove any direct construction of a quiescence success proof.

For create, retain one `MasterSecret` through the exact `SecItemAdd`, create a fresh `WireSecret` copy per child invocation, zeroize each wire copy inside the supervisor, then zeroize the master in the enclosing create `defer`.

- [ ] **Step 7: Add and test the helper control channel**

Validate `--control-fd` as one inherited non-stdio Unix stream socket before an effectful request. Implement the exact bytes `0x01`, `0x10`–`0x14`. Include the descriptor in the supervisor poll loop; never inherit it into `hdiutil`. Script cancellation while no child, while a child is active, after quiescence, and when cleanup is unresolved. `0x13` requires a quiescence proof; `0x14` authorizes no later invocation.

- [ ] **Step 8: Run Task 2 GREEN/typecheck gates and commit**

Add `DiskImageKeychainSwiftSupervisorTests` to `DEFAULT_TEST_CASES` and update the explicit class-name/ID manifest before running the class.

Run:

```bash
PYTHON="$PWD/.venv/py311/bin/python"
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0 \
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

- [ ] **Step 9: Independent checkpoint review**

Require a fresh reviewer to trace every signal/control/secret site, prove the leader remains unreaped while signals are possible, prove no caller constructs `ProcessQuiescenceProof`, confirm exact `waitid`/`waitpid` semantics, and confirm cancellation retains helper ownership of the isolated child. Require `P0=0`, `P1=0`, `P2=0`; otherwise Task 2 freezes.

---

### Task 3: Make mount compensation receipt-driven with disjoint deadlines

**Files:**
- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Consumes Task 2 `OwnedProcessSupervisor.InvocationOutcome`; the private proof never crosses this boundary.
- Produces `MountDeadlinePolicy`, `OwnedProcessSupervisor.compensableAttach(from:mountPath:)`, supervisor-issued `CompensableAttach`, the monotone mount-compensation states, and unchanged public `MOUNT_CLEANUP_UNCLEAR` behavior.

- [ ] **Step 1: Add RED tests for settled compensation and phase isolation**

Add `DiskImageKeychainMountCompensationTests` with this matrix:

| Test | Scripted outcomes | Required oracle |
| --- | --- | --- |
| `test_unresolved_attach_with_device_text_spawns_zero_detach` | attach `unresolved` with `/dev/disk99` bytes | call log contains attach only; public code `MOUNT_CLEANUP_UNCLEAR` |
| `test_settled_nonzero_attach_with_exact_device_detaches_once` | settled nonzero attach with complete tab-delimited one-device output, settled detach, settled empty info plist | call log is attach/detach/info exactly once each; cleanup proven |
| `test_capped_attach_output_spawns_zero_detach` | attach hits output cap after device-like prefix | no receipt, no detach, cleanup unclear |
| `test_detach_requires_complete_quiescence_proof` | complete receipt object without supervisor proof | construction or consumption is rejected before detach spawn |
| `test_detach_nonzero_or_unresolved_skips_absence_probe` | detach settled nonzero, then detach unresolved | each subtest ends `MOUNT_CLEANUP_UNCLEAR` with no later info call |
| `test_absence_requires_settled_complete_zero_mapping` | info unresolved, truncated, one device, or one image entry | every subtest remains cleanup unclear |
| `test_insufficient_phase_budget_spawns_zero_child` | clock at each phase's work cutoff | zero adapter spawn |
| `test_detach_admission_cutoff_and_epsilon` | request clock at +38 s and one tick later | exact cutoff can spawn inside hard +52 s; later time spawns nothing |
| `test_absence_admission_cutoff_and_epsilon` | request clock at +54 s and one tick later | exact cutoff can spawn inside hard +66 s; later time spawns nothing |
| `test_detach_using_its_full_window_cannot_borrow_absence_time` | detach settles exactly at +52 s | absence transition retains +52/+54 and hard +66 s; no extended deadline |
| `test_normal_work_at_cutoff_leaves_compensation_windows_intact` | attach failure at +36 s with settled receipt | receipt transition retains +36/+38; detach hard +52 and absence hard +66 stay unchanged |
| `test_public_response_schema_and_error_codes_are_unchanged` | all public success/failure scenarios | six exact keys and existing stable codes only |

- [ ] **Step 2: Run the compensation class and confirm RED**

Expected failures: current code accepts device text from a failure without a quiescence proof and current 12-second reserve cannot contain two six-second teardowns plus work.

- [ ] **Step 3: Implement the exact production deadline policy**

Add a validating policy with one 70-second hard deadline:

```swift
struct MountDeadlinePolicy {
    let normal: InvocationWindow       // request start through +36 s
    let detachAdmission: Double        // no later than +38 s
    let detachHard: Double             // +52 s
    let absenceAdmission: Double       // no later than +54 s
    let absenceHard: Double            // +66 s
    let epilogueDeadline: Double       // +70 s
}
```

Every child reserves six seconds within its own phase. Minimum work is eight seconds for create/attach/detach and four seconds for info/isencrypted; absence reserves six seconds of work. The two receipt/permit transitions each reserve two seconds. The constructor rejects overlap, non-finite timestamps, admission after cutoff, or a phase lacking work plus finalization.

- [ ] **Step 4: Implement the monotone compensation state machine**

Use these states:

```text
baselineVerified -> attaching -> attached(CompensableAttach)
-> validating -> compensatingDetach -> verifyingAbsence -> cleanupProven
Any state -> cleanupUnclear
```

Create `CompensableAttach` only through `OwnedProcessSupervisor.compensableAttach(from:mountPath:)`, which parses the settled complete stdout itself and accepts exactly one matching device. `unresolved` prohibits every later invocation. Detach consumes the permit once. Absence proof consumes only its own window and accepts exactly zero devices and zero image entries.

- [ ] **Step 5: Preserve receipts and public failure priority**

A settled nonzero response may preserve an exact device receipt before surfacing failure. An unresolved response may not. Any failed compensation returns `MOUNT_CLEANUP_UNCLEAR`; no path downgrades it to generic `HDIUTIL_FAILED` or claims the image unmounted.

- [ ] **Step 6: Run Task 3 GREEN and compatibility gates**

Add `DiskImageKeychainMountCompensationTests` to `DEFAULT_TEST_CASES` and update the explicit manifest meta-test. Run the compensation class, existing helper contract tests and Swift typecheck. Run each no-authorization CLI gate in the exact `env -i` allowlist; expected exit `64`, zero stdout/stderr and zero live-runner construction.

- [ ] **Step 7: Commit**

```bash
git add native/macos/disk_image_keychain.swift tests/test_disk_image_keychain_helper.py
git commit -m "fix(storage): require settled mount compensation"
```

- [ ] **Step 8: Independent checkpoint review**

Require a fresh reviewer to prove that every compensation command consumes a distinct phase and that output from `unresolved` cannot create a permit. Require `P0=0`, `P1=0`, `P2=0`; otherwise Task 3 freezes.

---

### Task 4: Replace generic Python effect routing with a typed terminal session

**Files:**
- Modify: `tests/disk_image_keychain_harness.py`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Consumes Task 1 exact process model and the existing gated live integration entry point.
- Produces `EffectPhase`, `TerminalEvent`, `EffectSession`, `CommandSpec`, `OrdinaryPermit`, `CleanupGrant`, `MountReceipt`, `DetachPermit`, `AbsencePermit`, `QuarantinePermit`, `ArtifactLedger`, `CommandReceipt`, `ProcessCleanupReceipt`, `DetachReceipt`, `PreTerminalUnmountedProof`, `DetachedUnmountedProof`, `QuarantineReceipt`, `DispositionReceipt`, `FinalVerdict`, `PythonOwnedSessionAnchor`, `DarwinOwnedProcessAdapter`, and `HelperControlClient`.
- Exposes only the closed workflow methods named in the design; no public generic argv runner remains.

- [ ] **Step 1: Add the terminal/effect matrix as RED tests**

Add `DiskImageKeychainTerminalEffectTests` with this matrix:

| Test | Input/state | Required oracle |
| --- | --- | --- |
| `test_terminal_preobservation_blocks_all_ordinary_specs_before_spawn` | terminal event before each compile/create/mount/normal-detach/inspect/delete/encryption/disk/mapping call | adapter spawn count remains zero for every command, with and without stdin |
| `test_terminal_during_no_stdin_command_terminates_before_communication_continues` | observer becomes terminal after spawn of compile or info | bounded cleanup begins immediately; result bytes do not continue the workflow |
| `test_arbitrary_argv_cannot_be_marked_safety_only` | attempt to construct a safety command from `/usr/bin/true` or caller argv | no public constructor/API accepts it |
| `test_detach_permit_is_exact_bound_and_single_use` | wrong session, epoch, UUID, image, mount or device; then replay | every mismatch/replay gives zero spawn; exact first use gives one detach |
| `test_mount_receipt_cannot_issue_two_detach_permits` | request two permits before either is consumed | second issuance rejected; only one registry entry |
| `test_absence_permit_exists_only_after_exact_detach` | missing/nonzero/unresolved detach versus exact settled detach | only exact settled detach yields one absence permit |
| `test_unknown_mapping_after_terminal_preserves_without_probe` | terminal plus mount state unknown | no info/inspect/delete/quarantine call; ledger records preservation |
| `test_terminal_disposition_runs_detach_absence_quarantine_only` | exact mount receipt and image descriptor | exact call order detach/absence/descriptor rename |
| `test_terminal_path_never_calls_inspect_or_delete` | all terminal causes and artifact states | Keychain inspect/delete counts remain zero |
| `test_complete_nonzero_receipt_is_recorded_before_terminal_raise` | complete nonzero create/mount response plus terminal event | UUID/device is in ledger before terminal exception is observed |
| `test_securityagent_has_priority_over_observer_and_cleanup_failures` | every ordering of SecurityAgent, observer unavailable and cleanup error | final verdict is `FAIL securityagent_detected` whenever SecurityAgent exists; otherwise observer verdict remains `UNCLEAR observer_unavailable` |
| `test_every_pipe_close_is_attempted_when_prior_close_raises` | stdin close and stdout close each raise in separate subtests | stdin/stdout/stderr close attempt counters are all one |
| `test_observer_fault_matrix_normalizes_and_cleans_every_boundary` | init, scan, cap, timeout, termination, stdin/stdout/stderr close failures | terminal normalization, bounded cleanup and all close attempts for each case |
| `test_helper_cancel_ack_precedes_escalation` | terminal event while helper reports active child | send `0x01`, wait `0x13`/`0x14` or inner-budget expiry; no earlier helper signal |
| `test_outer_deadline_is_exactly_115_seconds_without_retry_reset` | fake clock advances across pre/Swift/post/detach/absence/quarantine/finalization | all commands share original hard timestamp and no retry extends it |

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
| `authorize_cleanup(approved: bool) -> CleanupGrant` | emits once only for true approved CLI state while `ACTIVE` |
| `record_preterminal_unmounted(receipt: CommandReceipt) -> PreTerminalUnmountedProof` | records an exact complete mapping proof while `ACTIVE` |
| `detach_permit(receipt: MountReceipt) -> DetachPermit` | emits at most once for exact recorded receipt; permit is single-use |
| `absence_permit(receipt: DetachReceipt) -> AbsencePermit` | emits at most once after exact successful detach |
| `quarantine_permit(proof: PreTerminalUnmountedProof | DetachedUnmountedProof) -> QuarantinePermit` | binds exact image descriptor and immutable unmounted proof |
| `begin_disposition() -> None` | only `TERMINAL` to `DISPOSING` |
| `close_success(receipt: CommandReceipt) -> FinalVerdict` | `ACTIVE` to `CLOSED` without terminal event |
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
class PreTerminalUnmountedProof:
    mapping_receipt_id: str
    session_id: str
    epoch: int

@dataclass(frozen=True)
class DetachedUnmountedProof:
    detach_receipt: DetachReceipt
    absence_receipt_id: str
```

All collections are converted to tuples in `__post_init__`. `CleanupGrant`, `DetachPermit`, `AbsencePermit` and `QuarantinePermit` include a closure-local token, session/epoch binding and private issuance/consumption registry. They may be constructed only by `EffectSession` from recorded receipts. This prevents accidental forging/replay inside the trusted harness; it does not claim resistance to hostile Python introspection.

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
| `detach_for_disposition(permit: DetachPermit)` | exactly `/usr/bin/hdiutil detach <receipt-device>` | `DetachReceipt` |
| `prove_absence_for_disposition(permit: AbsencePermit)` | exactly `/usr/bin/hdiutil info -plist` once | `DetachedUnmountedProof` |
| `quarantine_for_disposition(permit: QuarantinePermit)` | descriptor-relative rename only | `QuarantineReceipt` |

Each method constructs its fixed executable/argv or helper request internally. A terminal event blocks every ordinary method before spawn. During an already running direct command, terminal observation starts bounded anchored cleanup independently of stdin. During a helper command, it starts the control-channel cancellation protocol instead of killing the helper owner.

- [ ] **Step 5: Implement exact Python process snapshots and anchored live cleanup**

The Darwin reader must retain PID, PPID, PGID and UID from short records. Determine lineage before UID filtering. Only the private `DarwinOwnedProcessAdapter.signal_owned_group(anchor, signal, deadline)` may translate a fresh exact unreaped anchor into a group signal; it revalidates the root/session and complete membership immediately before the signal. It never accepts a numeric receipt.

Do not use `Popen.communicate()` as terminal proof. Observe exit without reap, perform permitted signals, reap the exact child, then make a no-signal group absence observation. Close stdin/stdout/stderr in independent `try` blocks.

For the helper path, create a private Unix stream socketpair, pass only the validated child descriptor through `--control-fd`, and consume the exact one-byte state protocol. On terminal, send `0x01` once. Do not signal or reap the helper before `0x13`, `0x14`, helper exit, or expiry of its complete 70-second inner bound. Escalation after expiry targets only the exact unreaped helper and permanently records `descendant_potentially_surviving`.

- [ ] **Step 6: Implement artifact ledger and exact terminal disposition**

Track:

```python
image = "absent" | "exact" | "quarantined" | "deleted" | "unknown"
mount = "proven_unmounted" | "exact_mounted" | "unknown"
keychain = "absent" | "exact_present" | "deleted" | "unknown"
```

After terminal, allow only exact detach, one bound absence proof and descriptor-relative quarantine. Missing evidence preserves artifacts. Never run compile, generic plist reconciliation, Keychain inspect or delete. Parse complete helper output and update non-secret receipts before deriving the final terminal verdict.

- [ ] **Step 7: Run Task 4 GREEN and negative gates**

Add `DiskImageKeychainTerminalEffectTests` to `DEFAULT_TEST_CASES` and update the explicit manifest meta-test. Run the pure model class, terminal-effect class and existing gate tests in the exact `env -i` allowlist. Inspect call logs and assert neither the live helper runner nor Python group-signal adapter runs in the default suite. Expected: PASS, zero skip, no live effect.

- [ ] **Step 8: Commit**

```bash
git add tests/disk_image_keychain_harness.py tests/test_disk_image_keychain_helper.py
git commit -m "refactor(storage): type terminal integration effects"
```

- [ ] **Step 9: Independent checkpoint review**

Require a fresh reviewer to enumerate every post-terminal callable method and confirm that only receipt-bound direct detach/absence/quarantine survive. Require explicit review of foreign-UID lineage, root/session revalidation, cancellation-channel ownership and all permit producers. Require `P0=0`, `P1=0`, `P2=0`; otherwise Task 4 freezes.

---

### Task 5: Add contained deadline/cancellation witnesses and close S3

**Files:**
- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Interfaces:**
- Consumes Task 2's anchored supervisor/control protocol, Task 4's `HelperControlClient`, and Task 1's closed default selector.
- Produces test-only `--deadline-witness-probe`, `--cancellation-witness-probe`, and `--deadline-witness-child` routes under `CORTEX_STORAGE_HELPER_TESTING`.
- Returns no PID, PGID, secret, path, test-owned budget or cleanup-success assertion.

- [ ] **Step 1: Write all probe/build-boundary RED tests**

Add `DiskImageKeychainContainedDeadlineProbeTests`, `DiskImageKeychainCancellationChannelTests`, and `DiskImageKeychainBuildBoundaryTests` with this matrix:

| Test | Required oracle |
| --- | --- |
| `test_deadline_probe_records_start_and_witness_eof_inside_external_window` | exact nonce; `0.50 <= witnessEOFAt-started <= 0.65`; helper exit/reap before absolute 1.20 s |
| `test_cancellation_probe_acknowledges_quiescence_before_helper_reap` | receive child-active `0x11`, send `0x01`, observe witness EOF and `0x13` in either poll order, then helper exit/exact reap |
| `test_probe_uses_one_absolute_outer_deadline` | every select/wait/kill/reap timeout equals remaining time; no relative timeout after expiry |
| `test_probe_nonce_has_no_survivor_after_eof` | bounded `ps` snapshot succeeds and contains zero nonce match; output not logged |
| `test_fixture_child_route_has_no_spawn_or_fork` | syntax tree of child route contains no spawn/fork/process constructor |
| `test_production_build_rejects_every_test_route` | each test-only route exits 64 with empty output and zero child witness |
| `test_testing_fd_validation_rejects_invalid_matrix_before_spawn` | identical, reversed, closed, stdio, regular-file and unlisted extra FDs yield exit 64, empty witness and zero spawn |
| `test_testing_spawn_inherits_only_guardian_and_witness` | scripted file-action log has exactly the two fixture `addinherit_np` descriptors; helper control socket is not inherited by the child |
| `test_production_and_testing_build_fd_boundary_matrix` | aggregates both build modes and all FD subcases; no case reaches a child spawn on invalid input |
| `test_default_manifest_selects_every_safe_test_id_once_on_both_pythons` | exact sorted ID list is equal under 3.11/3.14 and excludes live class |
| `test_deadline_and_cancellation_probes_pass_twenty_fresh_runs` | launches only the two focused probe IDs in 20 fresh subprocesses each; 40 zero exits and external bounds |
| `test_final_source_structure_has_only_anchored_signal_and_proof_sites` | structural scan matches the exact allowlist of signal/proof constructors |
| `test_missing_authorization_allowlist_refuses_every_cli_shape` | four CLI shapes under `env -i`; exit 64, empty streams, zero live construction |

Run the three classes only. Expected RED: the routes, simultaneous event collector, production-build rejection and FD contracts do not exist.

- [ ] **Step 2: Implement the test-only child and strict descriptor boundary**

Under `CORTEX_STORAGE_HELPER_TESTING`, validate distinct guardian-read, witness-write and helper control-socket descriptors plus a 32-hex nonce. Reject stdio, closed, wrong type/direction and any unlisted inherited descriptor before spawn. Use `posix_spawn_file_actions_addinherit_np` only for guardian-read and witness-write; the control socket remains helper-owned and is never inherited by the fixture. The child arms a 0.90-second monotonic death timer before START, writes `START:<nonce>`, produces paced output, watches guardian EOF, creates no descendant and returns no process identifier.

Without the testing macro, all three routes must be absent from dispatch and rejected before any descriptor open or spawn.

- [ ] **Step 3: Implement the single-deadline Python event collector**

For both real probes:

```text
started = monotonic()
outer_deadline = started + 1.20
forced_helper_stop_at = outer_deadline - 0.15
```

Use one selector to monitor helper stdout/stderr, witness and control socket. Timestamp START, witness EOF, control terminal frame and helper exit as they are observed. Every wait uses `max(0, deadline - monotonic())`. At `forced_helper_stop_at`, close guardian/control and kill only the exact unreaped helper if it is still alive; reap it before `outer_deadline`. No later timeout is created.

The deadline case requires witness EOF between 0.50 and 0.65 seconds and stable `PROCESS_TIMEOUT`. The cancellation case waits for child-active `0x11`, sends one `0x01`, and requires both witness EOF and `0x13` before helper exit/exact reap; EOF and ACK may be observed in either polling order. `0x14`, a missing event or outer overrun fails.

After EOF/reap, run `/bin/ps -axo command=` with the same allowlist and remaining outer deadline, count nonce matches in memory, discard stdout, and require zero. A scan error or timeout fails; no numeric PID is retained or signalled.

- [ ] **Step 4: Make the prewritten probes GREEN and run the 20-run flake gate**

Freeze the final selector as:

```python
DEFAULT_TEST_CASES = (
    DiskImageKeychainHelperTests,
    DiskImageKeychainIntegrationOrchestrationTests,
    DiskImageKeychainHarnessSafetyTests,
    DiskImageKeychainProcessModelTests,
    DiskImageKeychainSwiftSupervisorTests,
    DiskImageKeychainMountCompensationTests,
    DiskImageKeychainTerminalEffectTests,
    DiskImageKeychainContainedDeadlineProbeTests,
    DiskImageKeychainCancellationChannelTests,
    DiskImageKeychainBuildBoundaryTests,
)
```

Update the explicit class-name/ID manifest. Run both real probe tests once, then each in twenty fresh processes. Record only return code, START/EOF/control/helper timestamps and elapsed bounds. Expected: 40/40 PASS, zero nonce survivor, empty stderr, no group signal, and no exact fixture-child-reap claim beyond the scripted kernel oracle.

- [ ] **Step 5: Run the complete default suite and exact authorization gates**

Set:

```bash
PYTHON311="$PWD/.venv/py311/bin/python"
NO_EFFECT_ENV=(env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C PYTHONHASHSEED=0)
```

Run `${NO_EFFECT_ENV[@]} "$PYTHON311" tests/test_disk_image_keychain_helper.py`. Require every manifest test ID exactly once, zero skip, live class absent, live observer/effects constructors at zero, and the Python group-signal adapter call count at zero.

Run these argv separately under the same environment:

```text
--integration
--allow-effects
--integration --allow-effects
--cleanup-approved
```

Each must exit 64 with zero stdout/stderr. The selector key remains exactly `CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION`, which is absent because the environment is built from scratch. Test the positive triple gate only by calling `dispatch_execution_mode` with an injected recording `live_runner`; never execute `build_selected_suite(live)`.

- [ ] **Step 6: Run production/test build, AST and Python-version gates**

Compile/typecheck the production helper, compile one production binary without the macro, and verify every test-only route returns 64/empty without spawn. Compile the testing binary separately and run the FD negative matrix. Extract/typecheck the observer Swift source without execution.

Resolve and validate interpreters:

```bash
PYTHON311="$PWD/.venv/py311/bin/python"
PYTHON314="$(cd "$(dirname "$(git rev-parse --git-common-dir)")" && pwd)/.venv/bin/python"
"$PYTHON311" -c 'import sys; assert sys.version_info[:2] == (3, 11)'
"$PYTHON314" -c 'import sys; assert sys.version_info[:2] == (3, 14)'
```

Compile both Python files in memory. Run an AST gate proving every subprocess, wait, poll, pipe communication, control frame and process scan consumes one finite remaining deadline; every `Popen` creates a new session. Emit sorted default test IDs under both interpreters and require byte-identical lists and verdicts, not merely equal counts.

- [ ] **Step 7: Run final structural, diff and secret gates**

Require this exact structural result:

```text
old real tree/probe helper definitions = 0
numeric PID/PGID or child_pid receipts = 0
generic safety_only/disposition_active = 0
proof/settled/compensable constructors outside supervisor reducers = 0
Python group-signal sites outside DarwinOwnedProcessAdapter.signal_owned_group = 0
Swift negative-PGID signal sites outside DarwinProcessKernel.signalOwnedGroup = 0
SETPGROUP/setpgroup production uses = 0
testing routes reachable in production build = 0
default live-class selections = 0
```

Run:

```bash
git diff --check "$IMPLEMENTATION_BASE"..HEAD
gitleaks detect --source . --no-banner --redact --log-opts="--all"
gitleaks detect --source . --no-banner --redact --no-git
```

Confirm `IMPLEMENTATION_BASE..HEAD` contains only the three implementation files and `primer.md` remains excluded.

- [ ] **Step 8: Commit the contained witnesses**

```bash
git add native/macos/disk_image_keychain.swift tests/test_disk_image_keychain_helper.py
git commit -m "test(storage): add contained process witnesses"
```

- [ ] **Step 9: Final independent S3 review**

Build a clean package over `IMPLEMENTATION_BASE..HEAD`; attach the reviewed spec, plan and fresh evidence separately, without prior reviewer verdicts. A fresh read-only reviewer must return:

```text
P0 = 0
P1 = 0
P2 = 0
Verdict = PASS
```

Any P0-P2 finding freezes S3 and requires an explicit architectural decision; it does not authorize another incremental loop.

- [ ] **Step 10: Rebaseline Phase S and S4 without starting S4 code**

After approval, update the ignored SDD ledger with final S3 commit, exact test IDs/count, 40-run probe receipt, build/typecheck/gate results, residual limits and verdict. Create a separate documentation-only S4 rebaseline that keeps the single-source helper manifest but changes `run_attested_helper` to require an absolute deadline and internally own the validated control socket/cancellation acknowledgement for `disk-image-keychain`. Independently review and hash that S4 plan before any S4 implementation. Verify Git status and stop before S4 code.

## Normative regression-to-test map

Every row below must appear exactly once in `DEFAULT_TEST_CASES` by its fully
qualified unittest ID. Subtests listed in an oracle remain one test ID.

| ID | Exact test method | Task |
| --- | --- | --- |
| R01 | `test_unresolved_attach_with_device_text_spawns_zero_detach` | 3 |
| R02 | `test_valid_receipt_with_group_present_is_unresolved` | 2 |
| R03 | `test_truncated_output_never_yields_settled_receipt` | 2 |
| R04 | `test_capped_attach_output_spawns_zero_detach` | 3 |
| R05 | `test_settled_nonzero_attach_with_exact_device_detaches_once` | 3 |
| R06 | `test_exit_observed_keeps_anchor_until_last_signal_then_reaps` | 2 |
| R07 | `test_pgid_reuse_after_reap_never_emits_signal` | 2 |
| R08 | `test_short_or_changed_birth_uid_pgid_sid_writes_zero_stdin` | 2 |
| R09 | `test_waitid_exact_exit_matrix` | 2 |
| R10 | `test_echild_is_not_a_reap_proof` | 2 |
| R11 | `test_insufficient_phase_budget_spawns_zero_child` | 3 |
| R12 | `test_detach_admission_cutoff_and_epsilon` | 3 |
| R13 | `test_absence_admission_cutoff_and_epsilon` | 3 |
| R14 | `test_normal_work_at_cutoff_leaves_compensation_windows_intact` | 3 |
| R15 | `test_terminal_preobservation_blocks_all_ordinary_specs_before_spawn` | 4 |
| R16 | `test_terminal_during_no_stdin_command_terminates_before_communication_continues` | 4 |
| R17 | `test_arbitrary_argv_cannot_be_marked_safety_only` | 4 |
| R18 | `test_detach_permit_is_exact_bound_and_single_use` | 4 |
| R19 | `test_mount_receipt_cannot_issue_two_detach_permits` | 4 |
| R20 | `test_absence_permit_exists_only_after_exact_detach` | 4 |
| R21 | `test_terminal_disposition_runs_detach_absence_quarantine_only` | 4 |
| R22 | `test_unknown_mapping_after_terminal_preserves_without_probe` | 4 |
| R23 | `test_terminal_path_never_calls_inspect_or_delete` | 4 |
| R24 | `test_securityagent_has_priority_over_observer_and_cleanup_failures` | 4 |
| R25 | `test_complete_nonzero_receipt_is_recorded_before_terminal_raise` | 4 |
| R26 | `test_partial_or_foreign_related_identity_permanently_blocks_cleanup` | 1 |
| R27 | `test_partial_bridge_to_exact_grandchild_blocks_cleanup` | 1 |
| R28 | `test_zero_then_live_is_not_vanished` | 1 |
| R29 | `test_zero_then_esrch_is_the_only_vanished_case` | 1 |
| R30 | `test_late_child_after_adoption_close_never_recovers_cleanup` | 1 |
| R31 | `test_reused_parent_cannot_adopt_child` | 1 |
| R32 | `test_changed_group_membership_invalidates_signal_permit` | 1 |
| R33 | `test_identity_change_between_term_and_kill_blocks_kill` | 2 |
| R34 | `test_no_term_or_kill_after_kill_state` | 2 |
| R35 | `test_invalid_suspended_identity_aborts_direct_child_only` | 2 |
| R36 | `test_observer_fault_matrix_normalizes_and_cleans_every_boundary` | 4 |
| R37 | `test_valid_output_with_unclear_cleanup_never_settles` | 2 |
| R38 | `test_clock_jump_matrix_checks_every_io_and_cleanup_boundary` | 2 |
| R39 | `test_master_and_wire_secret_lifetimes_are_separate` | 2 |
| R40 | `test_cancellation_probe_acknowledges_quiescence_before_helper_reap` | 5 |
| R41 | `test_production_and_testing_build_fd_boundary_matrix` | 5 |
| R42 | `test_default_manifest_selects_every_safe_test_id_once_on_both_pythons` | 5 |
| R43 | `test_deadline_and_cancellation_probes_pass_twenty_fresh_runs` | 5 |
| R44 | `test_final_source_structure_has_only_anchored_signal_and_proof_sites` | 5 |
| R45 | `test_missing_authorization_allowlist_refuses_every_cli_shape` | 5 |

## Plan self-review record

| Approved design section | Implemented and proved by |
| --- | --- |
| Swift closed process types, suspended session, unreaped anchor and no post-reap signal | Task 2 |
| Settled-only receipts, mount compensation and non-overlapping 70-second policy | Task 3 |
| Python monotone terminal state, fixed command catalogue, 115-second bound, helper cancellation and receipt-bound safety actions | Task 4 |
| Exact/partial UID-aware snapshots and permanent lineage uncertainty | Tasks 1 and 4 |
| Removal of unsafe numeric process-tree tests | Task 1 |
| Guardian/witness deadline and cancellation probes with external timing/ACK/EOF oracles | Task 5 |
| All normative regressions | R01–R45 map, Tasks 1 through 5 |
| Public protocol, Keychain/secret contracts and missing-authorization gates | Tasks 2, 3 and 5 |
| Python 3.11/3.14, Swift typecheck, AST, diff and secret proof gates | Task 5 |
| Independent zero-P0/zero-P1/zero-P2 completion review and mandatory S4 rebaseline | Task 5 |

Self-review found no uncovered approved requirement, unresolved type name or placeholder. The real probes deliberately prove only the fixed direct fixture child, external wall/ACK/EOF containment and nonce absence; exact fixture `waitpid` and descendant/session races remain scripted-kernel/model evidence and are not mislabeled as live DiskImages proof.
