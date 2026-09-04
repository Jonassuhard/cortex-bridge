# S3 Owned-Process Supervision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Preserve
> every checkbox and stop at the first failed gate.
>
> Execute sequentially. Each task starts with its own failing tests, ends with
> exact GREEN and mutant receipts, and receives read-only review before the
> next task changes behavior.

**Goal:** Replace forgeable process/effect authority with monotone native
obligations, a retained suspended-cleanup anchor, one current-mapping
detach-plus-absence continuation, an exact two-cycle artifact cursor and closed
harmless evidence.

**Architecture:** Production Swift starts only fixed `/usr/bin/hdiutil`
children suspended in new sessions and retains one private `NativeObligation`
through suspended cleanup, exact reap, group absence, descriptor closes and
settlement-frame publication. Python first compiles and runs the fixed observer,
then compiles the helper under observation, owns one `ArtifactCursor` through
two full mount/detach cycles, and serializes every observation/effect. Mounted
disposition may consume one Python-authorized 26-second helper that resolves the
current mapping, detaches and proves absence in one process; no Swift capability
crosses processes. R43 uses report-GO-exec so the reviewed helper keeps the
direct `Popen.pid`, with exact FD inventories and in-process libproc cleanup.

**Tech stack:** Swift 6; Darwin `posix_spawn`, `proc_pidinfo`, `waitid`,
`waitpid`, `poll`, `clock_gettime` and libproc; Security.framework; Python 3.11
and 3.14 standard library `unittest`, `ctypes`, `subprocess`, `selectors` and
`time.clock_gettime_ns`; Git and Gitleaks.

**Spec:** `docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md`

## Global constraints

- Work only in
  `/Users/asterion/Desktop/cortex-bridge/.worktrees/codex-v054-storage-consolidation`
  on branch `codex/v054-storage-consolidation`.
- Implementation starts only after the exact revision-5 spec/plan bytes pass
  three fresh blind read-only reviews with zero P0/P1/P2 and `PASS`.
- Never edit, stage or commit the pre-existing `primer.md` change.
- Between `IMPLEMENTATION_BASE` and `S3_FINAL`, change only:
  `native/macos/disk_image_keychain.swift`,
  `tests/disk_image_keychain_harness.py`, and
  `tests/test_disk_image_keychain_helper.py`.
- During normal implementation gates, run no live Keychain, DiskImages,
  `hdiutil`, mount, detach, quarantine, SecurityAgent, Chrome, runtime, push,
  merge, tag or release action.
- Never define live authorization during default gates. Its exact environment
  key is `CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION`; its exact value is
  `YES_DISPOSABLE_64_MIB_ONLY`.
- Preserve the public six-key response, strict ten-key request, stable errors,
  Keychain attributes, 43-character Base64URL secret and no-UI queries.
- Production child execution is fixed to `/usr/bin/hdiutil`.
- Raw PID/PGID facts may be transient observation data only, never authority or
  a durable receipt.
- Every retry, read, write, poll, scan, wait, signal, close and subprocess uses
  remaining time from one immutable absolute monotonic deadline.
- Every deadline transmitted to or compared with Swift is integer nanoseconds
  in `CLOCK_MONOTONIC`: Python uses only
  `time.clock_gettime_ns(time.CLOCK_MONOTONIC)` and Swift uses only
  `clock_gettime(CLOCK_MONOTONIC)`. Python's convenience monotonic-nanosecond
  API and `CLOCK_UPTIME_RAW` are forbidden for cross-process authority.
- One writer owns a file at a time. Every task has a dedicated commit and fresh
  read-only spec/code review.
- S4 implementation and S4 rebaseline documentation remain outside S3.

## Revision-5 documentation completion gate

This authoring gate executes no project code, test, build, helper, live effect,
Keychain, DiskImages, `hdiutil`, mount, detach, quarantine, SecurityAgent,
Chrome, runtime, push, merge, tag or release action. It changes only this spec
and this plan; `primer.md` remains byte-identical, unstaged and uncommitted.

Before candidate review, record the pre-existing primer diff hash and run only
the static documentary checks:

~~~bash
DOC_PRIMER_DIFF_SHA256=$(git diff --binary -- primer.md | shasum -a 256 | awk '{print $1}')
git diff --check
PLACEHOLDER_PATTERN='T''ODO|T''BD|F''IXME|[.][.][.]'
rg -n "$PLACEHOLDER_PATTERN" \
  docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md \
  docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md
awk '
  /^(~~~|\140\140\140)/ {
    mark = substr($0, 1, 3)
    if (!open) { open = mark; next }
    if (open != mark) { exit 1 }
    open = ""
  }
  END { exit open != "" }
' docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md \
  docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md
git diff --binary -- primer.md | shasum -a 256
git diff --cached --name-only
git status --short --untracked-files=all
~~~

The placeholder search must return no match, fences must be balanced, the
primer hash must equal `DOC_PRIMER_DIFF_SHA256`, no path may be staged, and
status before the explicit candidate stage must contain only the two documents
plus pre-existing `primer.md`.

An import-free static document checker must then prove all of these facts from
the Markdown bytes:

- spec and plan contain the exact R01-R45 set with no orphan or duplicate;
- normative, task-local and characterization test/mutant maps have unique keys
  and unique fully qualified methods, and ownership ranges equal their keys;
- the documented `MUTANT_MANIFEST` domain is the exact union of those maps and
  every record has owner/test/name/kind/target/unique anchor/oracle-closure
  hash/exact label/red policy;
- R44 is `kind=source`; every structural declaration/signature/call-graph
  mutant is source-kind; every other entry names one atomic runtime branch or
  source replacement;
- `PROCESS_EVENTS` has 15 unique entries and Cartesian count 813,616;
  `EFFECT_EVENTS` has 22 unique entries and Cartesian count 5,399,043;
- the cursor states, two cycles, 26-second schedule, helper tuple rows,
  preparation order, R43 offsets, exact Popen/pass-FD inventories, libproc
  outcomes and package allowlists each occur in both documents;
- both documents instead contain exactly one 26-second continuation helper,
  `RENAME_EXCL`, final-only control close, all eight valid effect-flag
  permutations, current-mapping-only authority, same-PID report-GO-exec and a
  capped in-process scan; every superseded R43 offset is absent.

Stage and commit only the two candidate bytes:

~~~bash
test -z "$(git diff --cached --name-only)"
git add -- \
  docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md \
  docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md
git diff --cached --check
git diff --cached --name-only
git diff --cached --quiet -- primer.md
test "$(git diff --cached --name-only)" = "$(printf '%s\\n' \
  docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md \
  docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md)"
test "$(git diff --binary -- primer.md | shasum -a 256 | awk '{print $1}')" = "$DOC_PRIMER_DIFF_SHA256"
git commit -m "docs(storage): close S3 revision 5 review gaps"
test "$(git status --short --untracked-files=all)" = " M primer.md"
~~~

Only after that exact docs-only commit may the blind documentation gate run.

## Blind documentation gate

- [ ] Freeze the candidate commit and compute exact SHA-256 for the spec and
  plan from that commit.
- [ ] Generate from `git show DOC_CANDIDATE:path` using exactly the four-path
  documentation allowlist in the spec; record canonical path/size/SHA-256.
- [ ] Run negative package self-tests for one extra entry, one wrong hash and
  one prior-review path; require generation to fail before output.
- [ ] Give each fresh reviewer only that sealed package and declared
  requirements. The ignored SDD review tree is unreachable to the generator.
- [ ] Keep reviewers mutually blind and read-only.
- [ ] Require each receipt to say `P0=0`, `P1=0`, `P2=0`, `Verdict=PASS`.
- [ ] Store receipts only under the ignored directory
  `.superpowers/sdd/2026-09-03-s3-owned-process-supervision/`.
- [ ] Freeze Task 1 on any finding or non-PASS verdict.

## Checkpoint and task-local TDD protocol

Before Task 1, record exact output in the ignored implementation ledger:

~~~bash
git symbolic-ref --short HEAD
IMPLEMENTATION_BASE=$(git rev-parse HEAD)
SPEC_SHA256=$(shasum -a 256 docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md | awk '{print $1}')
PLAN_SHA256=$(shasum -a 256 docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md | awk '{print $1}')
PRIMER_DIFF_SHA256=$(git diff --binary -- primer.md | shasum -a 256 | awk '{print $1}')
git status --short --untracked-files=all
git diff --cached --name-only
~~~

The branch must match, status must be exactly ` M primer.md`, and staged output
must be empty. `IMPLEMENTATION_BASE` contains the reviewed documentation bytes.

At every task start:

~~~bash
TASK_N_BASE=$(git rev-parse HEAD)
git diff --binary -- primer.md | shasum -a 256
git status --short --untracked-files=all
git diff --cached --name-only
~~~

The primer hash must equal `PRIMER_DIFF_SHA256`. Task 1 first creates an
importable, non-functional harness skeleton defining every referenced symbol;
missing behavior raises a closed assertion result, never `ImportError`, syntax
error or collection failure.

Before the first production change to a boundary, classify its manifest
`red_policy` and apply exactly one protocol:

1. `natural`: add the mapped test/oracle, run it alone under Python 3.11 and
   require an assertion RED caused by the missing behavior;
2. `baseline_characterization`: run the mapped test on
   `IMPLEMENTATION_BASE` and require GREEN, then require the same GREEN after
   the owner task; never manufacture a RED;
3. `synthetic_gate`: run an independently constructed invalid fixture and
   require the new acceptance mechanism to reject it; do not claim a correct
   final repository state was RED.

For every policy record test-source SHA, transitive oracle-closure SHA,
interpreter path/version, command, exit status and exact assertion/result.
After GREEN, all three policies still require the post-GREEN mapped mutant to
fail. If a `natural` test passes before implementation, stop and tighten only
an incomplete oracle. If a characterization is not GREEN on the baseline,
stop instead of reclassifying it.

Use the same individual runner for normative and task-local IDs:

~~~bash
PYTHON311="$PWD/.venv/py311/bin/python"
CASE_KEY=S3T1_01
TEST_ID=$("$PYTHON311" -c 'import sys; from tests.test_disk_image_keychain_helper import ALL_TEST_IDS; print(ALL_TEST_IDS[sys.argv[1]])' "$CASE_KEY")
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
  PYTHONHASHSEED=0 PYTHONPATH="$PWD" \
  "$PYTHON311" -m unittest "$TEST_ID" -v
~~~

`ALL_TEST_IDS` is a read-only merge of `REGRESSION_TEST_IDS`,
`TASK_LOCAL_TEST_IDS` and `BASELINE_CHARACTERIZATION_TEST_IDS`; duplicate keys
or values fail import.

`ALL_MUTANTS` is a read-only merge of `REGRESSION_MUTANTS`,
`TASK_LOCAL_MUTANTS` and `BASELINE_CHARACTERIZATION_MUTANTS`; duplicate keys or
values fail import. For every closed
case key `K` and its mapped mutant `M`, the only valid mutant-sensitivity label
is `MUTANT_K_M` after literal substitution. For example, R01 may be accepted
only with `MUTANT_R01_accept_unresolved_attach_output`. The test source must
assert that exact label; an import error, syntax error, timeout, unrelated
exception or different assertion is invalid evidence.

After the smallest implementation makes a method GREEN:

1. run the same method alone without a mutant and require exit zero;
2. enable its single mapped production-branch mutant;
3. run the same method alone and require the named assertion to fail;
4. disable the mutant and rerun GREEN;
5. record all three receipts.

~~~bash
MUTANT=$(PYTHONPATH="$PWD" "$PYTHON311" -c 'import sys; from tests.test_disk_image_keychain_helper import ALL_MUTANTS; print(ALL_MUTANTS[sys.argv[1]])' "$CASE_KEY")
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
  PYTHONHASHSEED=0 PYTHONPATH="$PWD" \
  CORTEX_STORAGE_TEST_MUTANT="$MUTANT" \
  "$PYTHON311" -m unittest "$TEST_ID" -v
~~~

`MUTANT_MANIFEST` is a typed read-only mapping whose keys equal exactly
`ALL_MUTANTS`. Every record contains case, owner, exact test ID, mutant name,
`kind`, target file, unique anchor, one runtime branch or source replacement,
oracle ID, frozen transitive oracle-closure SHA-256, exact assertion label and
`red_policy`. Its test/name projections must equal the maps, and all values
that must be unique are unique.

Every mutant changes exactly one production/harness branch or one isolated
source anchor. Composite `A_or_B` mutants and test/oracle mutation are
forbidden. Runtime mutants use only their named test-only branch. Source
mutants create one owner-only regular copy with link count one under ignored
SDD storage, require exactly one anchor, apply one typecheckable transformation,
record original/derived/oracle hashes, run the unchanged oracle against that
copy, and delete it with residual-count zero. Tests, oracle helpers, symlinks,
hardlinks, changed oracle hashes and residual copies fail the receipt. R44 and
all structural declaration/signature/call-graph mutants are source-kind. For
Python copies require `py_compile` success; for Swift copies require the same
unchanged `swiftc -typecheck` command/frameworks used by the source oracle. For
each run set
`ASSERTION_LABEL="MUTANT_${CASE_KEY}_${MUTANT}"`, require that exact label in
the mapped method's failure, record it with the branch name, then restore the
branch. After each task GREEN, run every normative, task-local and
characterization mutant owned by that task one at a time, require its exact
mapped method and label to fail, then rerun the complete task-owned set without
mutants.

Before a task commit:

~~~bash
git diff --check
git diff --name-only
git diff --cached --name-only
git diff --binary -- primer.md | shasum -a 256
~~~

Stage with explicit paths only. After commit record:

~~~bash
TASK_N_HEAD=$(git rev-parse HEAD)
git diff --name-only "$TASK_N_BASE..$TASK_N_HEAD"
git diff --name-only "$IMPLEMENTATION_BASE..$TASK_N_HEAD"
git diff --binary -- primer.md | shasum -a 256
~~~

The task diff is limited to declared files; the cumulative diff is limited to
the three S3 implementation files.

---

## Task 1: Install independent models and remove every legacy process route

**Files:**

- Create: `tests/disk_image_keychain_harness.py`
- Modify: `tests/test_disk_image_keychain_helper.py`
- Modify: `native/macos/disk_image_keychain.swift`

**Normative ownership:** process-model IDs 26 through 32 and legacy-removal ID
44.

**Task-local ownership:** `S3T1_01` through `S3T1_07`.

- [ ] **Step 1: Create an importable non-functional harness skeleton**

Create `tests/disk_image_keychain_harness.py` before adding imports from it.
Define exact names for both event alphabets, primitive result records, reducer
entrypoints, typed mutant record shapes and the source-copy runner. Each
unimplemented reducer returns a closed primitive `("boundary_missing",)` state
so later tests fail by assertion. The skeleton must not compile, spawn, signal
or inspect a process. Import it from the test module and prove import succeeds
before recording any RED.

- [ ] **Step 2: Write and individually observe task-local and normative RED**

Add independent reference-machine tests before reducer or route changes. The
RED set proves:

- transition indices are attached by the explorer, outside both reducers;
- full indexed action sequence and full primitive final state are equal to the
  independent reference result;
- positive signal/native-settlement/two-cycle/disposition counters are nonzero;
- long traces cover both indexed cycles, total unresolved ledger and one close;
- the legacy-route structural gate runs before any default-suite selection and
  is naturally RED while all six legacy literals, handlers, launchers and test
  names remain present.

Run R26-R32, R44 and S3T1_01-S3T1_07 individually. Record only assertion
failures tied to these missing boundaries; import/syntax/timeout failures are
invalid.

- [ ] **Step 3: Implement the process model without live process calls**

Replace only the process skeleton with this exact ordered alphabet:

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

`ProcessModelReducer.reduce(event)` returns primitive unstamped actions and
primitive state only. Its internal issuance/consumption registry is inaccessible
to tests. The explorer enumerates every product at depths zero through five,
without visited set/hash/deduplication, and wraps each reducer action with the
external `enumerate(trace)` index. Assert the exact total 813,616.

In the test module, implement a separately written reference machine over raw
events and primitive local variables. It imports no reducer state, registry or
permit type and computes both complete indexed action sequence and final state.
Compare equality for every trace. Include long positive traces through signal,
WNOWAIT exit, exact reap, original-group absence, pipes closed and
settlement-frame publication, followed by replay attempts. Add a suspended
cleanup trace in which repeated non-exact wait results retain the active
obligation before exact reap; make no liveness claim after destruction of the
owning helper.

- [ ] **Step 4: Implement the independent cursor/effect model**

Use exactly:

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

The effect reducer and registry are independent of the process model. Enumerate
all prefixes through depth five and assert 5,399,043. The independent reference
machine compares the full externally indexed action sequence and final
primitive state. The exact 22-symbol alphabet keeps the exact 5,399,043 count.
Long traces cover `noArtifact -> created(0)`, both
mount/verify/detach-absence cycles, `created(2) -> cyclesComplete`, one inspect,
Keychain-first approved deletion, cleanup-not-authorized quarantine, terminal
from every current cursor state, unresolved old/new ledger facts, one
`DispositionReceipt`, one close and every one-shot replay. Positive counters
require complete two-cycle success, approved cleanup, quarantine, unresolved
preservation and close.

- [ ] **Step 5: Delete legacy routes exhaustively**

Remove these literals, Swift handlers/branches, Python launchers, test methods,
comments naming handlers and any selector reference:

~~~text
--spawn-probe
--fd-child
--deadline-drain-probe
--process-policy
--process-scenario
--process-child
~~~

Do not add the guardian route yet. Add one exact empty testing-route-table
source anchor under `#if CORTEX_STORAGE_HELPER_TESTING`. R44's source mutant
inserts at that anchor a real testing-only legacy handler/dispatch entry; the
isolated Swift copy must typecheck and the unchanged pre-default absence oracle
must fail. The gate scans source plus discovered unittest method names before
any default test that can compile or spawn.

- [ ] **Step 6: GREEN and mutate every owned boundary**

Run each owned normative/task-local method individually, then the Task 1 set.
Enable each mapped mutant alone and require only its mapped method to fail.
The long-trace suite must catch replay, omitted cycle and missing disposition
mutants; exact count tests catch alphabet or enumeration changes. R44 records
original/derived/oracle hashes, exact typecheck and exact assertion label, then
proves residual-copy count zero.

- [ ] **Step 7: Commit Task 1**

~~~bash
git add native/macos/disk_image_keychain.swift \
  tests/disk_image_keychain_harness.py \
  tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "test(storage): replace legacy process probes"
~~~

Record Task 1 base/head, receipts and unchanged primer hash. Obtain fresh
read-only spec-compliance and code-quality reviews before Task 2.

---

## Task 2: Implement Swift anchors, total control, deadlines and erasure

**Files:**

- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Normative ownership:** IDs 06 through 10, 33 through 35 and 39.

**Task-local ownership:** `S3T2_01` through `S3T2_12`.

- [ ] **Step 1: Write and individually observe RED**

Before changing the supervisor, add scripted tests for:

- private final supervisor and private final issuance registries;
- forged/stale/replayed/cross-registry suspended/running/exited tokens;
- strongly retained registry identity with allocator-reuse refusal;
- atomic validate-versus-abort interleavings;
- `SuspendedCleanupAnchor` retention and one monotone `NativeObligation`
  through repeated non-exact cleanup results;
- one serial lifecycle executor, exact lock order and cancel polls at every
  spawn/insertion/resume/write boundary;
- every `SpawnResult` member and zero-obligation behavior for non-spawned
  members;
- native proof excluding control;
- complete control DFA including every invalid input/state;
- distinguishable `strictRejected`, `acceptedNoChild` and
  `protocolAbnormal` normal exits;
- exact frame/response/exit/EOF/reap tuples and final-only control closure;
- pre-request maximum-deadline arithmetic;
- Wire erasure before every outcome/frame and app-owned Keychain staging
  erasure.

Run every owned method alone and record natural RED.

- [ ] **Step 2: Create final owners and registry-only anchors**

Make `OwnedProcessSupervisor`, `LifecycleExecutor`, `AnchorRegistry`,
`CommandIssuanceRegistry` and `ControlIssuanceRegistry` private final reference
types. Give each registry an unexported strongly retained `RegistryIdentity`,
lock and monotonic generation. Tokens hold that private identity reference plus
generation, and every validation uses `===` against the issuing registry; no
`ObjectIdentifier` value is used or accepted.

The single serial lifecycle executor is outermost. Its only nested order is
lifecycle, control registry, anchor/command registry; inverse acquisition is a
source-gate failure. No subordinate lock remains held across a blocking syscall.
It is the only control reader and the only lifecycle writer.

Production `spawnSuspendedSession` uses only
`POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSID |
POSIX_SPAWN_START_SUSPENDED`. `SpawnResult.spawned` inserts one private
`NativeObligation(state: suspended)` containing positive PID, birth
seconds/microseconds, effective UID, PGID, SID, descriptors and frame state,
then returns `SuspendedChildAnchor`. `refused`, `deadlineExpired` and `failed`
insert no obligation and expose no PID authority.

Within one executor turn, `validateSuspendedIdentity` may advance the same
obligation to running after the two complete proc records and intermediate
`getsid` agree. The competing `beginSuspendedCleanup` consumes the suspended
anchor into `SuspendedCleanupAnchor` and state `suspendedCleanup` before any
positive-PID cleanup. Every cleanup result except exact `waitpid == pid`
retains the same active record and permits only bounded retry under the same
deadline. Exact reap advances to `reapedAwaitingGroup`; group absence, all
descriptor closes and pending `0x12` publication remain required. No negative
target, SIGCONT or child write exists on cleanup. This design makes no eventual
reap claim after external destruction of the owning helper.

The obligation states are exactly `suspended`, `suspendedCleanup`, `running`,
`exitedUnreaped`, `reapedAwaitingGroup`, `groupAbsentAwaitingCloses` and
`settledPendingFrame`. `NoActiveChildProof` is unavailable until no obligation
exists, including after reap while group/close/frame work remains. Its strong
identity/generation are consumed by exactly one `0x13`; copied, stale or
cross-registry proofs emit no frame and authorize no effect.

- [ ] **Step 3: Implement running and exited anchors**

Revalidate running authority before SIGCONT, TERM and KILL with:

~~~text
complete proc_bsdinfo
getsid(pid)
complete proc_bsdinfo
~~~

Require unchanged PID, birth, effective UID, PGID and SID. Exact WNOWAIT exit
zero-initializes `siginfo_t` and accepts only exact PID, SIGCHLD and
CLD_EXITED/CLD_KILLED/CLD_DUMPED. Consume running authority, advance the same
obligation to `exitedUnreaped` and mint `ExitedUnreapedSessionAnchor`. Do not
call `getsid` on that zombie.

Observe exited authority before each remaining signal and exact reap with
zero-initialized `waitid(WNOWAIT)`; that observation never reaps. Only exact
`waitpid == pid` advances to `reapedAwaitingGroup` and mints one
`ReapedGroupObservationToken`; consume that token before one signal-zero
original-group observation and advance to `groupAbsentAwaitingCloses`. Complete
independent closes advance to `settledPendingFrame`; only successful matching
`0x12` publication removes the obligation. ECHILD, wrong PID/status, EINTR
after deadline, EPERM, present group or any other error leaves the obligation
active and unresolved. Once KILL is attempted, issue no later TERM/KILL.

- [ ] **Step 4: Implement bounded request/deadline admission**

Accept only production argv:

~~~text
--control-fd DECIMAL_FD --swift-hard-deadline-ns DECIMAL_NS
~~~

Validate the exact descriptor inventory, set CLOEXEC/nonblocking, then sample
`now` once with `clock_gettime(CLOCK_MONOTONIC)` and prove before reading
request bytes:

~~~text
now < hard
hard - now <= 70_000_000_000
hard >= 70_000_000_000
epoch = hard - 70_000_000_000
epoch <= now
~~~

All arithmetic is checked. Add cases for 70 seconds plus one nanosecond,
`UInt64.max`, addition/subtraction overflow, future epoch and valid
phase-too-close input. Arithmetic failure performs zero request read/spawn/
write. Too-close passes arithmetic but fails phase fit before spawn.

The production parser knows no short test deadline flag. A two-second value
cannot reach request acceptance or a child effect on this route. The separate
testing-only two-second validator is added with the guardian route in Task 5
and never calls this admission code.

Replace unbounded request reads with a 65,536-byte `BoundedRequestReader`
polling request/control under the same hard deadline and prioritizing control.
Require request EOF before parse. EAGAIN/EINTR retry only while time remains.

- [ ] **Step 5: Implement the total five-state control reducer**

Encode exactly `START`, `IDLE_ACCEPTED`, `ACTIVE`, `TERMINAL`,
`NORMAL_EXIT` and the spec's complete transition table. Strict rejection before
`0x10` exits with no effect/frame. Accepted no-child inspect/delete may normal
exit. Valid cancel in START/IDLE after zero or any settled pair emits `0x13`.
Cancel in ACTIVE emits the child's required `0x12` after narrow native
settlement and then one `0x13`, or terminal `0x14` when unresolved. Native
unresolved without cancel also emits `0x14`.

Cancellation linearizes only when the serial lifecycle executor reads `0x01`.
Poll before spawn; insert the suspended obligation before `0x11`; poll again
immediately after insertion and before SIGCONT and each child-input write. A
queued cancel converts directly to `SuspendedCleanupAnchor`, publishes `0x11`
for the extant obligation and reaches only `0x12,0x13` after complete settlement
or terminal `0x14` while unresolved. No subordinate lock is held across a
blocking syscall and no other reader consumes control.

Cover cancel after first/second pairs, no-child completion, not-spawned,
unresolved without cancel, helper exit in each state, EOF, EAGAIN, unknown,
duplicate/out-of-order bytes and all terminal replays. Recheck the cancel latch
immediately before spawn, SIGCONT, child input and every nonterminal frame.
Keep `NormalExitKind.strictRejected` (exit 64/no frame),
`NormalExitKind.acceptedNoChild` (exit 0/final `0x10`) and
`NormalExitKind.protocolAbnormal` (exit 65) separate through the Python
verdict. The latter, absent/abnormal control EOF, wrong helper exit or a
missing terminal frame is `UNCLEAR`; no accepted no-child verdict may share
that path. Implement the spec's exact exchange rows: pre-accept reject 64,
pre-accept cancel 75, accepted success, accepted operational error 64/70,
settled cancel 75, unresolved active child 74 with stdout-usable/unusable
variants, and protocol abnormality 65. Each accepted row fixes frames, six-key
response presence/value, exit, bounded stdout/stderr closure, control EOF and
exact helper reap.

- [ ] **Step 6: Narrow `NativeSettlementProof`**

Issue its private constructor only after exact leader reap, one post-reap
`absentESRCH`, complete bounded output, no unresolved latch, independent close
success for request input plus child stdin/stdout/stderr, and Wire erasure.
Exclude the helper control socket.

Order the tail exactly:

~~~text
close and validate request/child/output descriptors
erase request buffer and Wire
mint NativeSettlementProof
write matching 0x12 settlement frame
if cancellation is latched, write the sole 0x13 terminal frame
if the operation is final, shutdown and close helper control endpoint
otherwise keep control open for the next declared child
~~~

A successful `0x12` removes only its matching settled-pending-frame obligation;
it never closes control by itself. Control closes only after final normal or
terminal transition. A control close failure has no later frame. It is detected by Python as missing
or abnormal EOF. Python classifies missing/abnormal control EOF, wrong helper
exit or missing terminal frame as `UNCLEAR` even when another fact appears
successful. Attempt every close independently even after another close fails.

- [ ] **Step 7: Constrain app-owned secrets**

Use disjoint erasable allocations for entropy staging, Master, Wire and mutable
Keychain staging. No application-owned String, immutable Data or general byte
array may hold secret bytes. Zero entropy after Master creation, Wire before
every outcome/frame, create Master immediately after `SecItemAdd`, mount Master
after attach outcome, and mutable Keychain staging after its syscall. A late
sync Keychain result after terminal cannot mint success or further authority.

Tests and wording explicitly exclude copies internal to Security.framework,
Keychain, kernel and child from direct zeroization evidence.

- [ ] **Step 8: GREEN, branch matrices and mutants**

Run owned IDs/task-local tests individually. Run scripted Cartesian matrices
for every `SpawnResult`, `IdentityResult`, `ResumeResult`, `ExitObservation`,
`SignalResult`, `ReapResult`, `GroupPresence`, `PollResult`, `IOResult`,
`CloseResult` and `SuspendedAbortResult`; fail each descriptor position
independently. Prove only `SpawnResult.spawned` inserts an obligation. Include
the three `NormalExitKind` classes, every exact helper tuple, retained suspended
cleanup, lifecycle order and final-only control close.

Run every owned mutant alone after GREEN, restore it, and rerun the exact
method.

- [ ] **Step 9: Commit Task 2**

~~~bash
git add native/macos/disk_image_keychain.swift \
  tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "feat(storage): add anchored native supervision"
~~~

Record Task 2 evidence and obtain both fresh read-only reviews.

---

## Task 3: Bind Swift command provenance and compensation

**Files:**

- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Normative ownership:** IDs 01 through 05, 11 through 14 and 37.

**Task-local ownership:** `S3T3_01` and `S3T3_02`.

- [ ] **Step 1: Write and individually observe RED**

Add tests for cross-supervisor/copied/replayed command permits, wrong command,
wrong result, unresolved settlement, wrong image/mount/transaction/device and
absence-query context. Add exact cutoff equality/one-nanosecond-late cases and
unresolved-output cases. Run each owned method alone to natural RED.

- [ ] **Step 2: Implement a closed command catalogue**

Implement private `HdiutilCommand` cases create, attach, detach, info with
purpose, and isEncrypted. `ExactCommandContext` is registry-only and stores
the closed enum, fixed executable, exact argv, stdin policy, absolute phase,
supervisor identity and generation.

Only a settled invocation with `NativeSettlementProof`, complete bounded
output and exact context can mint a command-derived permit. `notSpawned` and
`unresolved` expose no command context or parseable authority and permanently
close that helper request.

- [ ] **Step 3: Implement the exact compensation chain**

`issueAttachCompensationPermit` accepts only exact settled attach output with
one parsed device whose mount equals the registered mount. It stores device in
the private registry; no caller can pass or replace it. Consuming the permit
constructs one exact detach.

`issueAbsenceQueryPermit` accepts only that exact settled detach and constructs
one post-detach info for the same image, mount and transaction. Only complete
settled output with zero matching devices and zero image entries mints absence.
Copied, replayed, stale, cross-supervisor, wrong-generation or mismatched
values fail before spawn.

- [ ] **Step 4: Enforce immutable absolute phase windows**

Derive all windows from transmitted epoch once. Use hard stops 36, 38, 52, 54,
66 and 70 seconds exactly as specified. Equality requires the complete
command/finalization budget to fit; plus one nanosecond refuses. A normal
failure never resets compensation/absence deadlines. These are original live
helper windows only. Task 4 creates a mounted post-terminal continuation as
exactly one fresh sealed helper invocation with one immutable 26-second hard
deadline inside the unchanged outer 115 seconds. That helper performs current
mapping bind, detach and absence itself; there is no second helper, replacement
epoch or cross-process Swift capability.

- [ ] **Step 5: GREEN and mutant sensitivity**

Run every owned method alone, then the Task 3 set. Enable every normative and
task-local mutant independently and require its exact test to fail after
GREEN. Restore and rerun.

- [ ] **Step 6: Commit Task 3**

~~~bash
git add native/macos/disk_image_keychain.swift \
  tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "feat(storage): bind native command provenance"
~~~

Record Task 3 evidence and obtain both fresh read-only reviews.

---

## Task 4: Seal Python preparation, authority, receipts and process parity

**Files:**

- Modify: `tests/disk_image_keychain_harness.py`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Normative ownership:** IDs 15 through 25, 36, 38 and 45.

**Task-local ownership:** `S3T4_01` through `S3T4_24`.

**Baseline-characterization ownership:** `S3C4_01`.

- [ ] **Step 1: Write and individually observe RED**

Before changing the harness, add task-local tests for:

- one-shot preparation with no caller compile/observer paths;
- observer write/hash/typecheck/compile and first empty baseline before helper
  compile, then a second empty baseline before live issuance;
- copied/cross-session/cross-registry receipts, terminal-snapshot consumption
  and atomic active-lineage transfer at the terminal latch;
- executor linearization at every latch/spawn/register/first-write boundary;
- Python waitid/waitpid parity, replay refusal, private post-reap handle state
  and the ban on Popen poll/wait/communicate before and after exact reap;
- exact scripted Python-adapter parity with the independent Task-1 raw
  lineage oracles for every R26-R32 trace;
- exact ten-key values and zero caller operands;
- exact current `ArtifactCursor`, two complete indexed cycles and total
  settled/unresolved effect outcomes;
- one Python-authorized current-mapping detach-plus-absence helper with the
  fixed 26-second split and no cross-process Swift token;
- Keychain inspect/delete/re-query before image deletion, plus total
  cleanup-not-authorized quarantine and exactly one final disposition;
- descriptor-relative
  `renameatx_np(parent_fd, old_leaf, parent_fd, new_leaf, RENAME_EXCL)` and
  collision refusal;
- the complete helper frame/response/exit/EOF/reap tuple matrix;
- separate prefix/suffix/wrong-case/old-alias rejection for each of
  `--integration`, `--allow-effects` and `--cleanup-approved`;
- separate authorization-key alias and authorization-value normalization
  rejection;
- a synchronous Keychain result returning after terminal;
- executable typecheck of the exact reviewed observer source.
- a 20-sample cross-language `CLOCK_MONOTONIC` bracket oracle with 50 ms
  maximum width and wrong-clock rejection.

Add the owned normative tests and run every method alone to natural RED.
Run `S3C4_01` GREEN against `IMPLEMENTATION_BASE`: it accepts both orders of
the required flags and all six orders when cleanup is present. It never claims
a natural RED.

- [ ] **Step 2: Implement registry-minted authority roots**

Define frozen, slotted, `eq=False` shells containing only `_issuance_id:
object` for:

~~~text
PreparationCapability
LiveExecutionCapability
ObserverBinaryReceipt
ObserverBaseline
HelperBinaryReceipt
SecurityAgentSnapshot
TerminalCause
TerminalEventReceipt
ArtifactContext
ArtifactCursor
CreateCommandReceipt
MountCommandReceipt
MountVerificationReceipt
DetachedAndAbsentReceipt
CleanupGrant
KeychainDeletePermit
KeychainAbsentReceipt
ImageDeletePermit
ImageAbsentReceipt
QuarantinePermit
QuarantineReceipt
UnresolvedEffectReceipt
UnresolvedContinuationReceipt
UnresolvedDeletionReceipt
PreservationReceipt
DispositionReceipt
~~~

Private registry classes store every payload and validate issuance by Python
object identity (`is`) under a lock. Each record includes registry/session/
epoch, exact producer command/result/context and consumed state. Reject direct
construction, shallow/deep copy, field-equivalent object, wrong registry,
session, epoch, command, result, device, unresolved state or replay before
effect.

- [ ] **Step 3: Add one-shot fixed preparation**

The exact gate parses `--integration`, `--allow-effects`, optional
`--cleanup-approved`, and the exact authorization key/value. It mints one
`PreparationCapability` whose registry record fixes reviewed helper source/hash,
private helper target, exact reviewed observer source/private target and cleanup
approval.

`REVIEWED_HELPER_SOURCE`, `REVIEWED_HELPER_SOURCE_SHA256`,
`REVIEWED_SECURITY_AGENT_OBSERVER_SOURCE` and its SHA-256 live only in the
harness. Tests import them. Task 5 will update the helper hash when it changes
Swift and will modify all three implementation files in one task.

Expose only:

~~~python
PreparationSession.prepare_observer()
PreparationSession.compile_helper()
PreparationSession.mint_live()
~~~

All take no operands. Use one checked 30-second absolute preparation deadline
and the exact Python process adapter. Execute only this order: write/hash/
typecheck/compile fixed observer; run it and capture one complete empty
baseline; compile fixed helper while that observer remains active; capture a
fresh complete empty baseline; only then mint live roots. Detection or observer
unavailability during compile mints a registry-only preparation terminal cause,
cancels/reaps the compiler and reaches disposition without a live capability.

`mint_live()` consumes preparation authority into one
`LiveExecutionCapability`, one `ArtifactContext`, one
`ArtifactCursor(noArtifact)` and, only when approved, one `CleanupGrant`. Create
the 115-second live absolute deadline afterward with
`time.clock_gettime_ns(time.CLOCK_MONOTONIC)`. Registry
context fixes transaction, generated image/mount names, volume
`CORTEX_BRIDGE_SPIKE`, size `64m`, filesystem APFS and disposable true. It
captures the private parent directory's no-follow descriptor facts
(device/inode/mode/UID) at issuance. Settled create captures the image leaf's
same four facts through that parent descriptor and advances the cursor to
`created(cycle=0)`; the current cursor, never a later string lookup, carries
them to disposition.

- [ ] **Step 4: Serialize every observation and effect**

One FIFO serial lifecycle executor with one worker identity owns every
observation and effect. One logical turn spans terminal-latch check,
deadline/phase check, current-cursor lookup, `Popen`, handle registration and
first-write authorization. Registry locks protect only in-memory transitions
and are never held across a blocking syscall. No competing executor, observer
reader or effect lock exists. Deterministic barriers schedule the terminal
latch immediately before/after each point and prove no spawn or write crosses
it.

If a synchronous Keychain syscall is in flight at terminal, register only its
late diagnostic result. It cannot mint any receipt, authorize a new effect or
change FAIL/UNCLEAR to success.

The fixed observer bridge alone mints a terminal `SecurityAgentSnapshot` from
complete SecurityAgent detection evidence or the closed
`observer_unavailable` result. `latch_terminal(snapshot)` consumes it in that
same executor turn, registry-mints one closed `TerminalCause`, increments the
epoch, revokes ordinary authority and consumes the current `ArtifactCursor`'s
only terminal-transfer slot into `TerminalEventReceipt`. Historical receipts
are never scanned and old cursor shells are never grandfathered. Cause priority
is independent of cursor state: SecurityAgent, observer unavailable,
deadline/unresolved, operational failure, then cleanup not authorized.

- [ ] **Step 5: Implement only the sealed method catalogue**

Implement exact no-free-operand signatures:

~~~python
create_image(cursor: ArtifactCursor) -> CursorOutcome
mount_cycle(cursor: ArtifactCursor) -> CursorOutcome
verify_mount(cursor: ArtifactCursor) -> CursorOutcome
detach_and_prove_absence_normal(cursor: ArtifactCursor) -> CursorOutcome
advance_cycle(cursor: ArtifactCursor) -> ArtifactCursor
inspect_item(cursor: ArtifactCursor) -> CursorOutcome
keychain_delete_permit(
    cursor: ArtifactCursor,
    grant: CleanupGrant,
) -> KeychainDeletePermit
delete_item(
    cursor: ArtifactCursor,
    permit: KeychainDeletePermit,
) -> KeychainOutcome
image_delete_permit(
    cursor: ArtifactCursor,
    absent: KeychainAbsentReceipt,
) -> ImageDeletePermit
delete_image(
    cursor: ArtifactCursor,
    permit: ImageDeletePermit,
) -> ImageDeletionOutcome
quarantine_unapproved(cursor: ArtifactCursor) -> QuarantineOutcome
observe_terminal_snapshot() -> SecurityAgentSnapshot
latch_terminal(snapshot: SecurityAgentSnapshot) -> TerminalEventReceipt
detach_for_disposition(event: TerminalEventReceipt) -> ContinuationOutcome
quarantine_for_disposition(
    predecessor: TerminalEventReceipt | DetachedAndAbsentReceipt,
) -> QuarantineOutcome
preserve_for_disposition(
    event: TerminalEventReceipt,
) -> PreservationReceipt
finalize_disposition(
    outcome: DispositionOutcome,
) -> DispositionReceipt
close(disposition: DispositionReceipt) -> FinalVerdict
~~~

`CursorOutcome`, `KeychainOutcome`, `ImageDeletionOutcome`,
`QuarantineOutcome` and `ContinuationOutcome` are closed discriminated unions:
each contains either its exact settled receipt/new cursor or one
`UnresolvedEffectReceipt` carrying the complete cursor and old/new leaf ledger.
`DispositionOutcome` is the closed union of normal success, unapproved
quarantine, terminal quarantine, image absence, preservation and unresolved
receipts.

There is no public `record_mount`, generic runner, argv, raw path/device
parameter, operation/cleanup request field, safety switch or alternate close.
Each call claims the current cursor's one named transition before any effect;
every predecessor is consumed and only a successor shell is returned.

- [ ] **Step 6: Emit the exact ten-key value matrix**

Builders emit exactly:

~~~text
schema_version
operation
image_path
mount_path
volume_name
size
transaction_id
expected_encryption_uuid
disposable
cleanup_approved
~~~

For every operation, source schema 1, registered image/mount,
`CORTEX_BRIDGE_SPIKE`, `64m`, transaction and disposable true from
`ArtifactContext`. Set operation internally to exact `create`, `mount`,
`detach`, `inspect-item` or `delete-disposable-item`. Set expected UUID null
only for create and the exact registered UUID for all other operations. Set
cleanup false except `delete-disposable-item` with a consumed cleanup grant.
Keep mount/volume/size populated for every operation to preserve current global
validation. Filesystem APFS remains registered for disk-evidence validation but
is not a request key. Tests compare full mapping equality, not selected fields.

- [ ] **Step 7: Implement exact receipt producers and consumers**

Use the spec's cursor/receipt table literally. The registry owns one current
cursor and permits only this path:

~~~text
noArtifact -> created(0)
-> mounted(0) -> mountVerified(0) -> unmounted(0) -> created(1)
-> mounted(1) -> mountVerified(1) -> unmounted(1) -> created(2)
-> cyclesComplete -> keychainInspected
-> keychainAbsent -> imageQuarantined -> imageAbsent
every state -> unresolved(ledger)
~~~

Each mount cycle requires a fresh helper exact tuple, exact UUID, diskutil
device/mount/APFS proof, exact current hdiutil mapping, one self-contained
detach/absence helper, returned-device consistency and empty mount directory.
Inspect is callable once from `cyclesComplete` only. Advancing consumes the
old cursor, so historical evidence cannot win a precedence scan.

At terminal, consume only the current cursor's transfer slot into one event.
Callers cannot construct `TerminalCause`; registries mint SecurityAgent,
observer-unavailable, deadline/unresolved, operational-failure and
cleanup-not-authorized causes with that fixed verdict priority independent of
artifact state.

A mounted terminal event may consume exactly one Python registry slot to start
one fresh helper with the existing ten-key `operation=detach` request. Use
`shared_clock_ns()` and admit only checked `now + 26_000_000_000 <=
outer_hard_ns`. Inside that one helper: bind/Keychain/encryption/current info
stops at +8 s and finalizes failures by +14 s; detach stops at +14 s and
finalizes by +20 s; absence/response stops at +26 s. It returns one complete
tuple and either `DetachedAndAbsentReceipt` or
`UnresolvedContinuationReceipt`. It resolves current image/mount/UUID mapping;
historical device equality is post-effect consistency only. No second helper,
deadline reset or Swift capability crossing exists.

After exact one-item inspect, approved preparation consumes `CleanupGrant`
into `KeychainDeletePermit`; exact delete plus zero-count re-query yields
`KeychainAbsentReceipt`, which alone issues `ImageDeletePermit`. Approved image
deletion performs exclusive tombstone move, fd-relative removal, old/tombstone
absence checks and independent closes. Unapproved cleanup exclusively
quarantines and records `keychainStillPresent=true`. A terminal cause after
Keychain deletion performs no later Keychain call. Every effect returns a
closed settled/unresolved outcome retaining its ledger.

Normal approved success, unapproved quarantine and every failure/terminal
branch each mint exactly one `DispositionReceipt`; `close` consumes only that
type once. There is no alternate return, boolean cleanup or exception-only
branch.

Write the receipt forgery matrix test-by-test, not as a pooled assertion:

| Normative ID | Exact forged/copy/session/result oracle |
| --- | --- |
| R18 | forged, copied, stale and replayed mounted cursor slots cause zero second continuation spawn |
| R19 | copied/inter-session/inter-registry/wrong-epoch indexed mount cursor cannot issue a second normal detach/absence or terminal transfer |
| R20 | any attempted split helper, cross-process Swift token, wrong current mapping or replay refuses and preserves the ledger |
| R21 | forged/copy/replay cursor/event/outcome/final disposition refuses; every legitimate normal or terminal branch reaches one close |
| R25 | wrong create/mount command/result/index cannot advance current cursor before terminal transfer |

- [ ] **Step 8: Implement descriptor-relative quarantine**

Open the registered parent with
`O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_DIRECTORY`, then the registered image
leaf relative to it with `O_RDONLY | O_CLOEXEC | O_NOFOLLOW`. Verify device,
inode, mode and UID with `fstat` and no-follow `fstatat`. Bind libc through
typed `ctypes` and move only with:

~~~python
renameatx_np(parent_fd, old_leaf, parent_fd, new_leaf, RENAME_EXCL)
~~~

`EEXIST` is unresolved preservation and overwrites nothing. Revalidate
destination facts and source absence relative to `parent_fd`. Approved deletion
then removes the private tombstone fd-relatively without following symlinks and
proves old/tombstone absence; quarantine leaves its registered destination.
Close image/parent FDs independently on every branch. Ban high-level rename,
absolute rename and fallback. Mint `QuarantineReceipt` or `ImageAbsentReceipt`
only after complete revalidation and closes; any rename-success/later-failure
returns `UnresolvedDeletionReceipt` with old/new ledger facts. The parent/image
identity comes only from current cursor provenance. `S3T4_06` is this exclusive
move source oracle; a separate collision oracle proves no overwrite.

- [ ] **Step 9: Implement full Python wait parity**

`PythonOwnedProcessAdapter` uses private object-identity registries for running,
exited-unreaped and post-reap observation tokens. Ban `Popen.poll`,
`Popen.wait` and `Popen.communicate` before the private exact `waitpid`
consumer and after it. Exact `waitpid` writes the closed exit status into a
private reaped-handle record; `Popen.returncode` is never authority. A replayed
waitpid consumes no syscall and cannot change that record.

Match Swift branches for:

- WNOWAIT running/no-event, EINTR, ECHILD, wrong PID/signal/code;
- exact exit and zombie `getsid == ESRCH`;
- TERM/KILL running and exited revalidation;
- waitpid EINTR, ECHILD, wrong PID, exit code and signal;
- private post-reap handle state, replayed waitpid and post-reap
  poll/wait/communicate refusal;
- post-reap original-group ESRCH/present/EPERM/error;
- KILL terminality and every independent close.

`HelperControlClient` validates the total frame grammar and requires the
operation-specific final frame, control EOF and exact helper reap. No frame,
EOF or normal process status can substitute for either other fact. Missing or
abnormal control EOF, wrong helper exit or a missing terminal frame is
`UNCLEAR` even if a child report looks successful.

Encode the exact operation trace counts: create 2 (`create,isEncrypted`), mount
5 (`baselineInfo,attach,validationInfo,isEncrypted,finalInfo`), detach 4
(`isEncrypted,currentMappingInfo,detachCurrentDevice,postDetachAbsenceInfo`),
inspect 0 and delete 0. An operational failure uses only the exact settled
prefix; mount compensation may append only detach-current/absence.

Test every closed tuple independently:

- pre-accept reject: frames `[]`, no response, exit 64;
- pre-accept cancel: `[0x13]`, no response, exit 75;
- accepted success: `[0x10,(0x11,0x12)^k]`, one six-key `OK`, exit 0;
- accepted operational error: same settled prefix, one six-key stable error,
  mapped exit 64 or 70;
- settled cancel: valid prefix, active `0x11,0x12`, then `0x13`, one six-key
  `CANCELLED`, exit 75;
- unresolved active child: prefix ending `0x11,0x14`, exit 74, with one six-key
  `SUPERVISION_UNRESOLVED` only in the stdout-usable variant;
- accepted protocol abnormality: valid prefix, exit 65, with one six-key
  `PROTOCOL_ERROR` only in the stdout-usable variant.

Every row also requires bounded stdout/stderr closure, control EOF and exact
reap. Ordering is checked within each FD only. Any mismatch is `UNCLEAR` and
mints no cursor authority. An intermediate `0x12` leaves control open; only the
final normal or terminal transition closes it.

For `S3T4_12`, feed the exact raw lineage inputs used by R26-R32 to the scripted
`PythonOwnedProcessAdapter` and, separately, to the Task-1 reference machine.
Compare the complete primitive action sequence, terminal reason and final
authority state for equality. The adapter test must not reuse a reducer,
registry, permit or expected-action helper from the implementation under test.

- [ ] **Step 10: Validate every flag/key/value near miss**

For each of the three flags (`--integration`, `--allow-effects`,
`--cleanup-approved`) generate prefix, suffix, wrong-case and every historical
alias case separately, plus missing/duplicate/extra flag matrices. Exact unique
flags are accepted in any order.
For the authorization key and value generate prefix, suffix, wrong-case and
each old alias separately. Every near miss exits 64 with empty streams and zero
preparation/observer/live registry construction.

Keep separate mutants for flag normalization and flag-alias acceptance, plus
separate mutants for authorization-key alias acceptance and authorization-value
normalization. `S3T4_07`, `S3T4_08` and `S3T4_09` each mutate and prove one
alias-acceptance branch for `--integration`, `--allow-effects` and
`--cleanup-approved` respectively; `S3T4_10` and `S3T4_11` cover the
authorization key and value. The exact positive gate uses injected recording
factories only and never executes the live class.

`S3C4_01` enumerates exactly eight accepted vectors: both permutations of
`--integration` and `--allow-effects`, plus all six permutations after adding
`--cleanup-approved`. Run it GREEN before and after Task 4, then apply only
`reject_permuted_effect_flags` and require
`MUTANT_S3C4_01_reject_permuted_effect_flags`. It has
`red_policy=baseline_characterization`.

For the GREEN-before receipt, the unchanged characterization method asks the
source-copy runner to materialize exactly
`git show IMPLEMENTATION_BASE:tests/test_disk_image_keychain_helper.py` as one
owner-only regular ignored file with its recorded blob SHA-256. It imports that
baseline module under a private unique name, calls only its pure
`select_execution_mode` with the eight vectors and an injected exact
authorization mapping, unloads it, deletes the copy and proves residual count
zero. It never invokes the module's main, a live runner or an effect factory.
The GREEN-after and mutant receipts exercise the current pure gate through the
same eight-vector oracle. The oracle bytes and baseline blob remain unchanged
through all three receipts.

- [ ] **Step 11: Typecheck the exact observer source executably**

`REVIEWED_SECURITY_AGENT_OBSERVER_SOURCE` is the sole observer source constant,
and `REVIEWED_SECURITY_AGENT_OBSERVER_SHA256` is computed from its exact UTF-8
bytes in the harness. Tests import both constants and the exclusive writer. The
gate creates a private ignored temporary file,
writes exactly those bytes with no interpolation, verifies the recorded hash,
executes the exact command and requires exit zero:

~~~bash
SDD=.superpowers/sdd/2026-09-03-s3-owned-process-supervision
umask 077
OBSERVER_DIR=$(mktemp -d "$SDD/security-agent-observer.XXXXXX")
OBSERVER_TMP="$OBSERVER_DIR/observer.swift"
trap 'rm -f -- "$OBSERVER_TMP"; rmdir -- "$OBSERVER_DIR"' EXIT
PYTHONPATH="$PWD" "$PYTHON311" -c 'import sys; from pathlib import Path; from tests.disk_image_keychain_harness import write_reviewed_observer_source_exclusive; write_reviewed_observer_source_exclusive(Path(sys.argv[1]))' "$OBSERVER_TMP"
OBSERVER_SHA256=$(shasum -a 256 "$OBSERVER_TMP" | awk '{print $1}')
EXPECTED_OBSERVER_SHA256=$(PYTHONPATH="$PWD" "$PYTHON311" -c 'from tests.disk_image_keychain_harness import REVIEWED_SECURITY_AGENT_OBSERVER_SHA256; print(REVIEWED_SECURITY_AGENT_OBSERVER_SHA256)')
test "$OBSERVER_SHA256" = "$EXPECTED_OBSERVER_SHA256"
xcrun swiftc -typecheck -framework CoreGraphics "$OBSERVER_TMP"
rm -f -- "$OBSERVER_TMP"
rmdir -- "$OBSERVER_DIR"
trap - EXIT
~~~

The test records path class, source hash, exact argv, exit zero and successful
safe deletion. It does not launch the observer. Its structural mutant changes
only an ignored observer-source copy, typechecks it and leaves the harness/test
oracle closure unchanged.

- [ ] **Step 12: Prove the shared cross-process clock domain**

Implement `shared_clock_ns()` as exactly
`time.clock_gettime_ns(time.CLOCK_MONOTONIC)`. Compile a fixed harmless Swift
clock reporter that calls `clock_gettime(CLOCK_MONOTONIC)`. For 20 fresh
samples, take Python `p0`, obtain Swift `s`, then Python `p1`; require
`p0 <= s <= p1` and `p1 - p0 <= 50_000_000`. Unavailable or wider samples are
`UNCLEAR`, not a tolerance increase. Source/AST gates reject the Python
convenience monotonic-nanosecond call and `CLOCK_UPTIME_RAW` in every
transmitted/comparison path. The mapped mutant
`use_python_monotonic_ns_for_shared_deadline` is instead an atomic source-copy
mutant: it replaces only the exact `shared_clock_ns()` return expression in a
private ignored harness copy. That copy must pass `py_compile`, then fail this
unchanged natural-RED cross-language oracle; the checkout and oracle remain
untouched. Process-local diagnostic clocks remain allowed only when their
values never enter requests, reports, comparisons, deadlines or receipts.

- [ ] **Step 13: GREEN and mutant sensitivity**

Run every owned normative/task-local method separately and `S3C4_01` in its
GREEN-before/after protocol. Run the complete Task 4 set under Python 3.11.
Apply every owned mutant individually after GREEN, require its exact mapped
assertion, restore and rerun.

- [ ] **Step 14: Commit Task 4**

~~~bash
git add tests/disk_image_keychain_harness.py \
  tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "test(storage): seal live effect authority"
~~~

Record Task 4 evidence and obtain both fresh read-only reviews.

---

## Task 5: Add the non-suspended guardian/witness fixture and close S3

**Files:**

- Modify: `native/macos/disk_image_keychain.swift`
- Modify: `tests/disk_image_keychain_harness.py`
- Modify: `tests/test_disk_image_keychain_helper.py`

**Normative ownership:** IDs 40 through 43.

**Task-local ownership:** `S3T5_01` through `S3T5_43`.

- [ ] **Step 1: Write and individually observe RED**

Before adding a route, write tests proving:

- fixture spawn lacks START_SUSPENDED and never receives SIGCONT;
- fixture arms self-expiry before START, has no watchdog/PID receipt and cannot
  count self-expiry as normal success;
- active cancellation requires matched `0x12` before narrow `0x13`;
- frame alone without control EOF/helper reap is insufficient;
- control FD does not leak into the fixture;
- the shared-clock parent deadline and every endpoint exist before exact Popen;
- report validation precedes one GO, successful exec retains exact Popen PID,
  and no helper/fixture can exist without GO;
- exact parent Popen keywords/pass-FDs, pre-GO/post-exec inventories and
  CLOEXEC exec-status EOF/failure records;
- testing-only two-second deadline admission is disjoint from production
  70-second admission;
- deadline/cancel guardian close, settlement and witness/reap timing;
- cleanup reserve permits no spawn and uses complete bounded libproc absence;
- compiler-AST fixture call graph, synchronized helper/observer hashes, typed
  mutant manifest, sealed blind package and three independent final
  spec/plan/path comparisons.

Run R40-R43 and every natural-policy Task 5 method individually. Synthetic
manifest/package/hash gates use invalid fixtures; no import/compile/timeout
failure counts as RED.

- [ ] **Step 2: Add only the closed testing routes**

Inside `#if CORTEX_STORAGE_HELPER_TESTING`, allow exactly:

~~~text
--test-scenario
--test-supervisor-scenario
--guardian-witness-probe
--guardian-witness-child
~~~

Production compilation contains no route literal or handler symbol and rejects
each testing flag with exit 64, empty stdout/stderr and zero spawn.

The probe route accepts exact ordered operands:

~~~text
ABSOLUTE_HELPER_PATH
--guardian-witness-probe MODE
--guardian-fd DECIMAL_FD
--witness-fd DECIMAL_FD
--control-fd DECIMAL_FD
--nonce LOWERCASE_HEX32
--test-supervisor-hard-deadline-ns DECIMAL_NS
~~~

MODE is exactly `deadline` or `cancel`. Reject missing, duplicate, reordered,
wrong-case, prefix/suffix or extra operands before any spawn/write. The testing
FD inventory adds only the named guardian/witness FDs to the production set.
The fixture inherits guardian/witness only, never helper control.

The short deadline flag and validator exist only under
`#if CORTEX_STORAGE_HELPER_TESTING`, only for this route, and use
`clock_gettime(CLOCK_MONOTONIC)`. They accept the exact parent-derived
`start + 2.00 s` supervisor hard stop without traversing production's
70-second parser. Production contains/reaches neither symbol and rejects the
testing flag plus any two-second production phase fit before `0x10`, spawn or
write. Map separate source mutants for accepting the short flag in production
and routing the guardian through the production deadline flag.

- [ ] **Step 3: Implement the immediate self-expiring fixture**

Spawn the fixture into its own session with
`POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSID`; do not use
`POSIX_SPAWN_START_SUSPENDED`. It immediately installs absolute self-expiry at
shared-clock start plus 2.50 seconds before writing `START:<nonce>`, creates no descendant,
writes bounded paced data, observes guardian EOF, closes witness on exit and
exposes no PID/PGID/watchdog receipt.

After spawn, the testing adapter observes complete running identity and mints a
`RunningSessionAnchor`. From that point it reuses the production
running/exited/reap/original-group-absence/native-descriptor reducers. It never
calls resume/SIGCONT.

Use compiler AST output, not lexical search alone, to start at the exact
fixture-child entrypoint, resolve every direct/transitive project-local call,
reject unknown/dynamic edges and allow only the spec's explicit Darwin leaves.
A source mutant inserts one reachable forbidden spawn/exec call into a private
typecheckable Swift copy; the unchanged call-graph oracle must fail. A separate
mutant counts self-expiry as success; the normal deadline oracle must fail
because self-expiry is containment only.

The source oracle and every mutated copy run these exact commands against the
same private target; both must exit zero before the AST graph is accepted:

~~~bash
xcrun swiftc -typecheck -D CORTEX_STORAGE_HELPER_TESTING "$SWIFT_TARGET" \
  -framework Security -framework CoreFoundation -framework CoreGraphics
xcrun swiftc -dump-ast -D CORTEX_STORAGE_HELPER_TESTING "$SWIFT_TARGET" \
  -framework Security -framework CoreFoundation -framework CoreGraphics
~~~

The parser consumes compiler AST output from the second command, never source
text as a substitute.

- [ ] **Step 4: Implement exact report-GO-exec with one direct PID**

Before `Popen`, create report, GO, guardian, witness, control and exec-status
channels plus every deadline with `shared_clock_ns()`. Parent owns `report_r`,
`go_w`, `guardian_w`, `witness_r`, `control_parent`, `exec_status_r` and one
direct-child obligation, plus the returned parent stdin/stdout/stderr ends.
Independently cap/drain report/stdout/stderr, require every final EOF and close
every parent endpoint even after another close fails. Child endpoints are
unique integers greater than 2.
Put exact ASCII decimal `parent_outer_hard` only in
`CORTEX_S3_PARENT_HARD_DEADLINE_NS`; child parsing and report equality are
strict, and production request parsing never accepts that key.
`fresh_argv[0]` is absolute `sys.executable`; call exactly:

~~~python
fresh = subprocess.Popen(
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

The parent creates `exec_status_w` close-on-exec, while `pass_fds` carries it
through the first exec. The fixed interpreter bootstrap immediately reasserts
`FD_CLOEXEC` on that writer, proves every other passed child endpoint has the
flag clear, and only then reports. Thus only `exec_status_w` is CLOEXEC in the
exact pre-GO inventory `{0,1,2,report_w,go_r,guardian_r,witness_w,control_child,
exec_status_w}`. It revalidates owner-only `0700` helper parent/target plus
registered device/inode/mode/UID and binary hash. Its one capped report binds
exact PID, nonce, canonical deadline, absolute helper path, argv0, complete
route vector/digest, source SHA and binary SHA. Parent requires PID equal to
registered `Popen.pid` and every field exact before one GO byte. Without GO no
helper or fixture exists.

After GO the interpreter closes report/GO endpoints and calls exactly
`os.execve(helper_path, helper_argv, helper_env)`, with
`helper_argv[0] == helper_path` and the strict guardian route vector. Success
closes the status writer atomically via CLOEXEC; parent requires exact EOF.
`OSError` writes exactly `b"EXEC" + errno.to_bytes(4,"big")`, then exits 127
for `ENOENT` or 126 otherwise. Parent accepts only EOF or that eight-byte record
plus reserved exit and exact-waits the same PID. Post-exec helper inventory is
exactly `{0,1,2,guardian_r,witness_w,control_child}`. Helper alone owns/reaps
the fixture; parent never gets its PID.

Add a distinct Python-AST oracle for the exact Popen keywords, six-entry
pass-FD tuple, absolute interpreter, direct `os.execve`, identical helper
path/argv0 and exact route. Separate mutants cover omitted pass FD, extra FD,
duplicate/stdio-aliased FD, inherited stdio, wrong CLOEXEC, wrong argv0, wrong
exec path, process/shell launch instead of exec, malformed exec-status record
and wrong 126/127 mapping. macOS has no `fexecve`; document the residual helper
hash-to-exec race against a hostile same-UID actor as outside the threat model.

- [ ] **Step 5: Assert both probe contracts**

Use one immutable shared-clock schedule:

~~~text
report_cutoff = start + 0.75 seconds
work_cutoff = start + 1.50 seconds
supervisor_hard = start + 2.00 seconds
fixture_self_expiry = start + 2.50 seconds
cleanup_reserve_start = start + 3.00 seconds
parent_outer_hard = start + 5.00 seconds
~~~

Deadline mode closes `guardian_w` at +1.50 s. Cancel mode sends one `0x01`
then closes `guardian_w`. Both require matching START, witness EOF, complete
settlement tuple, control EOF and exact direct-helper reap before +2.00 s;
cancel additionally requires `0x11,0x12,0x13` in that order. Per-FD ordering is
exact, while witness/control readiness may be observed in either poll order.

The +2.50 s self-expiry is only failure containment and never a PASS witness.
If settlement misses +2.00 s, classify the probe unresolved; fixture self-expiry
must still precede +3.00 s and final witness/libproc absence must complete by
+5.00 s. Map `hold_guardian_open_past_work_cutoff` and
`count_fixture_self_expiry_as_success` to separate tests/mutants.

Run the two probe test IDs, including R40, once in their normal class. The
40-run flake method then launches deadline and cancellation in twenty fresh
interpreters each and requires 40 of 40 complete receipts, matching nonce and
no survivor.

The real oracle does not claim to see the fixture child's internal waitpid and
does not test suspended production bootstrap. Scripted Task 2 matrices retain
those claims.

- [ ] **Step 6: Implement the bounded in-process survivor scan**

Cleanup reserve permits only endpoint closes, positive direct-PID TERM/KILL,
exact waitpid, witness EOF and one in-process scan; no `Popen`, shell or command
scanner is reachable. Check `parent_outer_hard` before and after every call.

Treat `proc_listallpids(NULL, 0)` as a PID count. Select checked capacity no
greater than 4,096 and pass exactly `capacity * sizeof(pid_t)` bytes to the
second call. Negative return, full buffer, count growth or inconsistent
count/byte framing is `incomplete`, never absent. Filter complete
`proc_bsdinfo` records to current UID, then perform a size query and capped
4,096-byte `sysctl(KERN_PROCARGS2)` read for each candidate. Require exact argc
and NUL framing. `ESRCH`, `EPERM`, `ENOMEM`, any other errno, identity change,
cap hit or parse ambiguity is `incomplete`/`error`; only complete absence
passes. Compare nonce then erase bytes immediately; retain no command line.

Use separate mapped mutants for count-as-bytes, full-buffer-as-absent, skipped
procargs error, unbounded enumeration, retained command bytes and a
process-spawning scanner.

- [ ] **Step 7: Install dynamic cross-version inventory**

`DEFAULT_TEST_CASES` lists every module-defined direct/indirect unittest class
except exact identity `DiskImageKeychainLiveIntegrationTests`. Runtime
discovery must equal the tuple; no class-name allowlist.

`REGRESSION_TEST_IDS` has exact keys `R01` through `R45`, 45 unique fully
qualified values, each exactly once in the flattened default suite.
`TASK_LOCAL_TEST_IDS` and `TASK_LOCAL_MUTANTS` contain the exact maps below;
their values are unique and selected in the default suite.

Run the full default suite independently under equipped Python 3.11 and 3.14:

~~~bash
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
  PYTHONHASHSEED=0 PYTHONPATH="$PWD" \
  "$PWD/.venv/py311/bin/python" -m unittest \
  tests.test_disk_image_keychain_helper -v
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
  PYTHONHASHSEED=0 PYTHONPATH="$PWD" \
  "$PWD/.venv/py314/bin/python" -m unittest \
  tests.test_disk_image_keychain_helper -v
~~~

Record ordered `startTest` IDs. Both runs exit zero, skip zero, exclude the live
class and have byte-identical streams. The in-suite cross-version method uses a
non-executing `default_test_ids()` subprocess; nested same-version launches use
`sys.executable`.

- [ ] **Step 8: Synchronize reviewed sources and seal the typed mutant manifest**

Task 5 owns all three implementation files. After its Swift edit, update the
harness-owned `REVIEWED_HELPER_SOURCE_SHA256`, helper binary hash contract,
fixed observer source/hash and fixture/route source manifest. Tests import
those values; no duplicate hash/source constant remains.

Freeze `MUTANT_MANIFEST` as a typed read-only mapping over the exact union of
R01-R45, S3T1/S3T2/S3T3/S3T4/S3T5 keys and S3C4_01. Every entry includes case,
owner, exact test, mutant name, kind, target file, unique anchor, one runtime
branch or source replacement, oracle ID, transitive closure SHA-256, exact
`MUTANT_<CASE>_<NAME>` label and red policy. Projections must equal the maps;
all keys/tests/names/anchors/labels are unique.

Runtime mutants use one named harness/production branch. Source mutants use an
owner-only ignored regular copy, unique anchor, one typecheckable
transformation, original/derived/oracle hashes, unchanged oracle, exact label
and residual-copy count zero. R44, exclusive rename, observer source,
same-PID exec, process-free scan, fixture call graph and synchronized helper
hash are source-kind. Tampered target kind/file/anchor/replacement/oracle hash
or label fails the independent manifest self-test.

- [ ] **Step 9: Seal review packages and final comparison self-tests**

Implement one package generator that accepts only an explicit frozen commit and
the exact five-path final allowlist:

~~~text
docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md
docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md
native/macos/disk_image_keychain.swift
tests/disk_image_keychain_harness.py
tests/test_disk_image_keychain_helper.py
~~~

Read each blob only with `git show S3_FINAL:path`; write a canonical manifest
of path, byte size and SHA-256; refuse missing/extra entries, symlinks,
hardlinks and mismatches. The ignored SDD review tree is unreachable. Synthetic
negative self-tests separately inject an extra entry, wrong hash and forbidden
review path and require refusal before package output.

Add three independently runnable synthetic-gate tests: compare the spec blob
hash to frozen `SPEC_SHA256`; compare the plan blob hash to frozen
`PLAN_SHA256`; compare the sorted `IMPLEMENTATION_BASE..S3_FINAL` changed paths
to exactly the three implementation files. Recording values without equality
comparison fails.

- [ ] **Step 10: Run final executable/source/security gates**

Run Python syntax/import checks under both interpreters. Run the exact observer
typecheck recipe from Task 4 and record its source hash/exit zero/deletion.
Typecheck production Swift without execution:

~~~bash
xcrun swiftc -typecheck \
  native/macos/disk_image_keychain.swift \
  -framework Security \
  -framework CoreFoundation \
  -framework CoreGraphics
~~~

AST/source gates prove:

~~~text
all six obsolete literals/handlers/tests = 0
real child routes except guardian-witness-child = 0
numeric signal receipts = 0
non-final Swift supervisor or issuance registries = 0
public token initializers/registry identities = 0
ObjectIdentifier token storage or registry construction outside private issuers = 0
NativeObligation states differ from exact seven-state set = 0
SuspendedCleanupAnchor erased before exact waitpid = 0
NoActiveChildProof while any obligation/frame remains = 0
process success booleans = 0
safety_only/disposition_active/public record_mount = 0
readDataToEndOfFile = 0
generic caller mappings/argv/live paths/devices = 0
unregistered capability/baseline/context/receipt/grant/proof factories = 0
historical receipt precedence scans = 0
more than one ArtifactCursor current record = 0
more than one post-terminal continuation helper = 0
Swift token/receipt crossing a process boundary = 0
terminal lineage close without DispositionReceipt = 0
negative TERM/KILL sites outside typed signal adapters = 0
negative signal-zero sites outside post-reap adapters = 0
killpg sites = 0
production testing symbols = 0
default live-class selections = 0
hard-coded nested python3.11 relaunches = 0
Popen poll/wait/communicate before private exact waitpid = 0
high-level/plain/absolute quarantine rename fallback = 0
exclusive rename without RENAME_EXCL = 0
control included in NativeSettlementProof = 0
shared deadline producer other than Python CLOCK_MONOTONIC = 0
Swift shared clock other than CLOCK_MONOTONIC = 0
process-spawning survivor scanner = 0
fixture reachable unknown/dynamic/forbidden call edge = 0
intermediate 0x12 control close = 0
~~~

The AST also proves production helper Popen uses `close_fds=True`, exact
`pass_fds=(control_fd,)`, `start_new_session=True`; preparation/live methods
have no caller paths; one serial executor owns latch through first write; and
all waits/actions use an immutable absolute deadline. A separate R43 AST gate
proves absolute `sys.executable`, all three stdio pipes, exact six-entry
pass-FD tuple, new session, direct absolute `os.execve`, helper argv0/path
identity and exact testing route. Runtime FD gates prove pre-GO/post-exec
inventories and CLOEXEC exec-status semantics. The testing short-deadline route
and production 70-second route are disjoint. The compiler-AST fixture graph,
typed manifest isomorphism, 15/22 alphabets, exact cursor/two-cycle chain and
all package/hash self-tests also pass.

Run:

~~~bash
git diff --check "$IMPLEMENTATION_BASE..HEAD"
gitleaks detect --source . --no-banner --redact --log-opts="--all"
gitleaks detect --source . --no-banner --redact --no-git
git diff --name-only "$IMPLEMENTATION_BASE..HEAD"
git diff --binary -- primer.md | shasum -a 256
~~~

Expected changed implementation paths are exactly the three declared files;
primer hash equals `PRIMER_DIFF_SHA256`.

- [ ] **Step 11: GREEN and mutate every Task 5 boundary**

Run each owned normative and task-local method individually, both probe methods
once normally, then the fresh 40-run gate. Enable each mapped mutant alone
after GREEN, require only its mapped method to fail, restore and rerun.

Because Task 5 changes all three implementation files, do not reuse earlier
task receipts as final evidence. After its owned set is GREEN, iterate the
complete 134-entry `MUTANT_MANIFEST` in key order. Recompute and match each
frozen oracle-closure hash before and after the run, apply only that entry,
require only its exact mapped method and assertion label to fail, restore the
target, prove the source-copy residual count zero when applicable, and rerun
the method GREEN. Then run the complete mapped/default suite without mutants
under both equipped Python versions and require the identical zero-skip start
streams again. Any stale owner receipt, changed closure or non-mapped failure
freezes `S3_FINAL`.

- [ ] **Step 12: Commit Task 5**

~~~bash
git add native/macos/disk_image_keychain.swift \
  tests/disk_image_keychain_harness.py \
  tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "test(storage): add contained guardian witness"
~~~

Record Task 5 evidence and obtain both fresh read-only reviews.

- [ ] **Step 13: Freeze exact S3 state**

Immediately before `S3_FINAL`, require:

~~~bash
ACTUAL_STATUS=$(git status --short --untracked-files=all)
test "$ACTUAL_STATUS" = " M primer.md"
test -z "$(git diff --cached --name-only)"
FINAL_SPEC_SHA256=$(shasum -a 256 docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md | awk '{print $1}')
FINAL_PLAN_SHA256=$(shasum -a 256 docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md | awk '{print $1}')
FINAL_PRIMER_DIFF_SHA256=$(git diff --binary -- primer.md | shasum -a 256 | awk '{print $1}')
test "$FINAL_PRIMER_DIFF_SHA256" = "$PRIMER_DIFF_SHA256"
S3_FINAL=$(git rev-parse HEAD)
FINAL_SPEC_SHA256=$(git show "$S3_FINAL:docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md" | shasum -a 256 | awk '{print $1}')
FINAL_PLAN_SHA256=$(git show "$S3_FINAL:docs/superpowers/plans/2026-09-03-s3-owned-process-supervision.md" | shasum -a 256 | awk '{print $1}')
test "$FINAL_SPEC_SHA256" = "$SPEC_SHA256"
test "$FINAL_PLAN_SHA256" = "$PLAN_SHA256"
EXPECTED_PATHS=$(printf '%s\n' \
  native/macos/disk_image_keychain.swift \
  tests/disk_image_keychain_harness.py \
  tests/test_disk_image_keychain_helper.py | sort)
ACTUAL_PATHS=$(git diff --name-only "$IMPLEMENTATION_BASE..$S3_FINAL" | sort)
test "$ACTUAL_PATHS" = "$EXPECTED_PATHS"
~~~

Record the comparisons, not merely the values. Then build the actual five-path
review package from `git show S3_FINAL:path`, verify its path/size/SHA-256
manifest and prove no extra entry exists before delivery.

- [ ] **Step 14: Perform three fresh blind final reviews**

Each reviewer receives only the exact sealed five-path package, declared
requirements and separately hashed non-review execution receipts. The package
generator cannot traverse prior findings/review material and has already
refused extra/wrong-hash/forbidden-path fixtures. Require independently
`P0=0`, `P1=0`, `P2=0`, `Verdict=PASS`. Any finding freezes S3.

## Post-S3 S4 documentation-only rebaseline

After accepted `S3_FINAL`, create a separate reviewed commit that may update
only:

- `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md`;
- `docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md`;
- `docs/superpowers/plans/2026-09-02-v054-completion-program.md`.

It documents that `run_attested_helper` internally creates/validates the control
socket, passes the exact absolute Swift deadline and sole descriptor, and
requires terminal acknowledgement, control EOF and exact helper reap. It is
outside `IMPLEMENTATION_BASE..S3_FINAL`, receives new hashes and independent
review, and precedes all S4 code.

## Normative regression map

The implementation must copy this exact dictionary. Values are unique,
fully-qualified unittest IDs:

~~~python
REGRESSION_TEST_IDS = {
    "R01": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_unresolved_attach_text_cannot_issue_compensation",
    "R02": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_present_original_group_blocks_attach_compensation",
    "R03": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_truncated_attach_output_cannot_issue_receipt",
    "R04": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_capped_attach_output_cannot_issue_receipt",
    "R05": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_settled_attach_allows_one_bound_detach_and_absence",
    "R06": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_held_pipe_exit_uses_exited_anchor_without_zombie_getsid",
    "R07": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_post_reap_token_allows_only_one_group_absence_observation",
    "R08": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_changed_or_incomplete_identity_blocks_resume_input_and_signal",
    "R09": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_waitid_matrix_issues_only_exact_exited_anchor",
    "R10": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_reap_echild_cannot_issue_native_settlement",
    "R11": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_insufficient_command_and_finalization_fit_spawns_nothing",
    "R12": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_single_helper_detach_cutoff_equality_and_next_nanosecond",
    "R13": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_single_helper_absence_stops_at_twenty_six_seconds",
    "R14": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_no_stage_can_reset_original_deadline",
    "R15": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorityTests.test_terminal_preobservation_blocks_every_ordinary_method",
    "R16": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorityTests.test_observer_precedes_compile_and_terminal_compile_mints_no_live_capability",
    "R17": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorityTests.test_caller_operands_cannot_construct_live_work",
    "R18": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_replayed_mounted_cursor_spawns_no_second_continuation",
    "R19": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_each_indexed_mount_issues_one_detach_absence_transition",
    "R20": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_detach_and_absence_use_one_current_mapping_helper",
    "R21": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_every_normal_and_terminal_branch_mints_one_disposition_then_close",
    "R22": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_ambiguous_current_mapping_preserves_without_followup_effect",
    "R23": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_terminal_after_keychain_delete_performs_no_later_keychain_effect",
    "R24": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_securityagent_verdict_precedes_observer_and_cleanup_errors",
    "R25": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_create_and_indexed_mount_evidence_advance_only_current_cursor",
    "R26": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_related_partial_and_foreign_uid_bridge_latch_uncertainty",
    "R27": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_partial_bridge_never_authorizes_grandchild_signal",
    "R28": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_zero_record_live_reread_remains_partial",
    "R29": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_zero_record_esrch_reread_is_vanished",
    "R30": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_late_child_is_never_adopted_or_signalled",
    "R31": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_reused_parent_birth_is_never_adopted_or_signalled",
    "R32": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_tracked_uid_sid_or_group_change_expires_authority",
    "R33": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_term_to_kill_exited_anchor_revalidation_matrix",
    "R34": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_kill_attempt_forbids_later_group_signal",
    "R35": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_suspended_cleanup_obligation_survives_nonexact_reap_and_validate_race",
    "R36": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_total_helper_tuple_and_independent_close_failure_matrix",
    "R37": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_valid_output_without_native_settlement_has_no_authority",
    "R38": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_shared_clock_and_jump_matrix_stop_at_original_deadline",
    "R39": "tests.test_disk_image_keychain_helper.DiskImageKeychainSecretTests.test_application_owned_secret_lifetime_and_erasure_matrix",
    "R40": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_active_cancel_requires_0x12_then_0x13_eof_and_exact_helper_reap",
    "R41": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_production_testing_routes_and_pre_post_exec_descriptor_inventories",
    "R42": "tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_dynamic_python311_python314_inventory_and_order_match",
    "R43": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_report_go_exec_libproc_probes_pass_twenty_fresh_runs_each",
    "R44": "tests.test_disk_image_keychain_helper.DiskImageKeychainLegacyRemovalTests.test_legacy_routes_handlers_and_tests_are_absent_before_default_suite",
    "R45": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_each_flag_and_authorization_near_miss_constructs_zero_live_objects",
}
~~~

## Normative mutant map

Each value selects one implementation branch:

~~~python
REGRESSION_MUTANTS = {
    "R01": "accept_unresolved_attach_output",
    "R02": "ignore_present_original_group",
    "R03": "accept_truncated_attach_output",
    "R04": "accept_capped_attach_output",
    "R05": "skip_bound_absence_query",
    "R06": "call_getsid_after_exact_exit",
    "R07": "issue_term_from_post_reap_token",
    "R08": "resume_changed_identity",
    "R09": "accept_wrong_waitid_pid",
    "R10": "treat_reap_echild_as_success",
    "R11": "spawn_without_finalization_fit",
    "R12": "admit_detach_one_nanosecond_late",
    "R13": "admit_absence_one_nanosecond_late",
    "R14": "recompute_compensation_deadline",
    "R15": "mint_ordinary_after_terminal",
    "R16": "compile_helper_before_observer_baseline",
    "R17": "accept_caller_operation",
    "R18": "accept_replayed_mounted_cursor",
    "R19": "issue_second_cycle_detach_absence",
    "R20": "split_detach_and_absence_helpers",
    "R21": "close_without_terminal_disposition_receipt",
    "R22": "detach_ambiguous_current_mapping",
    "R23": "requery_keychain_after_terminal_delete",
    "R24": "prefer_cleanup_error_verdict",
    "R25": "select_historical_mount_receipt",
    "R26": "ignore_related_partial",
    "R27": "bridge_partial_to_grandchild",
    "R28": "treat_live_reread_as_vanished",
    "R29": "reject_esrch_vanished",
    "R30": "adopt_late_child",
    "R31": "accept_reused_parent_birth",
    "R32": "signal_after_sid_change",
    "R33": "kill_without_exited_revalidation",
    "R34": "allow_term_after_kill",
    "R35": "drop_suspended_cleanup_obligation_before_reap",
    "R36": "accept_incomplete_helper_tuple",
    "R37": "mint_permit_without_native_proof",
    "R38": "use_python_monotonic_ns_for_shared_deadline",
    "R39": "leave_wire_live_at_outcome",
    "R40": "omit_settlement_frame_before_cancel_ack",
    "R41": "accept_invalid_fixture_fd",
    "R42": "omit_dynamic_test_class",
    "R43": "start_probe_cleanup_after_reserved_window",
    "R44": "retain_legacy_process_route",
    "R45": "normalize_authorization_flag",
}
~~~

## Task-local test and mutant maps

These methods are additional to, not substitutes for, the normative 45:

~~~python
TASK_LOCAL_TEST_IDS = {
    "S3T1_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_explorer_stamps_transition_indices_outside_reducer",
    "S3T1_02": "tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_reference_machines_match_full_actions_and_final_state",
    "S3T1_03": "tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_positive_signal_settlement_and_disposition_counters_are_nonzero",
    "S3T1_04": "tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_long_traces_cover_complete_disposition_and_replays",
    "S3T1_05": "tests.test_disk_image_keychain_helper.DiskImageKeychainLegacyRemovalTests.test_legacy_gate_runs_before_default_selection",
    "S3T1_06": "tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_artifact_cursor_reference_requires_two_complete_cycles",
    "S3T1_07": "tests.test_disk_image_keychain_helper.DiskImageKeychainModelArchitectureTests.test_unresolved_effect_ledger_still_mints_one_disposition_and_close",
    "S3T2_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftStructureTests.test_anchor_tokens_reject_foreign_registry_identity",
    "S3T2_02": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftStructureTests.test_supervisor_and_issuance_registries_are_private_final_classes",
    "S3T2_03": "tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_native_settlement_excludes_control_descriptor",
    "S3T2_04": "tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_total_dfa_rejects_duplicate_terminal_frame",
    "S3T2_05": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_pre_request_deadline_rejects_more_than_seventy_seconds",
    "S3T2_06": "tests.test_disk_image_keychain_helper.DiskImageKeychainSecretTests.test_mutable_keychain_staging_is_erased",
    "S3T2_07": "tests.test_disk_image_keychain_helper.DiskImageKeychainSecretTests.test_wire_is_erased_before_settlement_frame",
    "S3T2_08": "tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_normal_exit_kind_keeps_no_child_and_protocol_failure_distinct",
    "S3T2_09": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_suspended_cleanup_anchor_retains_native_obligation_until_exact_reap",
    "S3T2_10": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_one_lifecycle_executor_linearizes_cancel_spawn_and_first_write",
    "S3T2_11": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_spawn_result_matrix_inserts_obligation_only_for_spawned",
    "S3T2_12": "tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_control_closes_only_after_final_normal_or_terminal_transition",
    "S3T3_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_command_permit_rejects_foreign_supervisor_registry",
    "S3T3_02": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_absence_query_rejects_wrong_command_context",
    "S3T4_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_preparation_is_one_shot_and_accepts_no_caller_paths",
    "S3T4_02": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_terminal_transfer_consumes_only_current_cursor",
    "S3T4_03": "tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_terminal_interleavings_cover_spawn_registration_and_first_write",
    "S3T4_04": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_waitid_waitpid_and_popen_lifecycle_match_after_exact_reap",
    "S3T4_05": "tests.test_disk_image_keychain_helper.DiskImageKeychainRequestTests.test_all_ten_values_come_from_registered_context",
    "S3T4_06": "tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_move_uses_descriptor_relative_renameatx_exclusive_only",
    "S3T4_07": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_integration_flag_aliases_are_rejected_without_normalization",
    "S3T4_08": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_allow_effects_flag_aliases_are_rejected_without_normalization",
    "S3T4_09": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_cleanup_approved_flag_aliases_are_rejected_without_normalization",
    "S3T4_10": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_authorization_key_aliases_are_rejected",
    "S3T4_11": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_authorization_value_near_misses_are_rejected_without_normalization",
    "S3T4_12": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_python_adapter_matches_task1_lineage_reference_for_r26_to_r32",
    "S3T4_13": "tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_post_latch_keychain_result_cannot_authorize_success",
    "S3T4_14": "tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_exact_reviewed_observer_source_typechecks_and_is_deleted",
    "S3T4_15": "tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_observer_two_baselines_surround_helper_compile_before_live_issuance",
    "S3T4_16": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_artifact_cursor_has_exact_states_and_current_transfer_slot",
    "S3T4_17": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_two_indexed_mount_verify_detach_absence_cycles_complete",
    "S3T4_18": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_every_consuming_effect_returns_settled_or_unresolved_ledger",
    "S3T4_19": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_terminal_mounted_cursor_starts_exactly_one_continuation_helper",
    "S3T4_20": "tests.test_disk_image_keychain_helper.DiskImageKeychainDeadlineTests.test_continuation_uses_exact_twenty_six_second_current_mapping_schedule",
    "S3T4_21": "tests.test_disk_image_keychain_helper.DiskImageKeychainCleanupTests.test_keychain_absence_is_required_before_image_delete_permit",
    "S3T4_22": "tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_existing_exclusive_target_is_unresolved_and_never_overwritten",
    "S3T4_23": "tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_every_helper_outcome_matches_complete_tuple",
    "S3T4_24": "tests.test_disk_image_keychain_helper.DiskImageKeychainClockTests.test_twenty_shared_clock_samples_fit_fifty_millisecond_brackets",
    "S3T5_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fixture_is_immediate_and_self_expiry_is_containment_only",
    "S3T5_02": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_frame_without_control_eof_is_unclear",
    "S3T5_03": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fixture_does_not_inherit_helper_control_fd",
    "S3T5_04": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_shared_clock_parent_deadline_and_endpoints_exist_before_popen",
    "S3T5_05": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_child_report_cannot_extend_parent_deadline",
    "S3T5_06": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_cleanup_reserve_precedes_hard_deadline",
    "S3T5_07": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_reaps_exact_unreaped_interpreter_on_every_failure",
    "S3T5_08": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_validates_complete_report_before_one_go",
    "S3T5_09": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_interpreter_execs_helper_in_same_registered_pid",
    "S3T5_10": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_popen_ast_has_exact_stdio_flags_and_pass_fds",
    "S3T5_11": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_pre_go_descriptor_inventory_is_exact",
    "S3T5_12": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_status_cloexec_eof_or_fixed_failure_record_is_total",
    "S3T5_13": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_post_exec_helper_descriptor_inventory_is_exact",
    "S3T5_14": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_short_supervisor_deadline_is_testing_only_and_production_rejects_it",
    "S3T5_15": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_cleanup_reserve_reaches_no_child_spawn_path",
    "S3T5_16": "tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_pid_count_and_fill_byte_capacity_are_not_conflated",
    "S3T5_17": "tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_full_pid_buffer_is_incomplete_not_absent",
    "S3T5_18": "tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_procargs_errno_identity_and_framing_are_never_absent",
    "S3T5_19": "tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_survivor_scan_pid_and_procargs_caps_are_fixed",
    "S3T5_20": "tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_survivor_scan_discards_every_command_buffer",
    "S3T5_21": "tests.test_disk_image_keychain_helper.DiskImageKeychainLibprocTests.test_cleanup_scan_has_no_process_or_shell_launch_path",
    "S3T5_22": "tests.test_disk_image_keychain_helper.DiskImageKeychainFixtureCallGraphTests.test_compiler_ast_resolves_closed_fixture_call_graph",
    "S3T5_23": "tests.test_disk_image_keychain_helper.DiskImageKeychainFixtureCallGraphTests.test_reachable_forbidden_call_source_mutant_is_rejected",
    "S3T5_24": "tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_harness_helper_observer_and_fixture_hashes_match_reviewed_sources",
    "S3T5_25": "tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_typed_mutant_manifest_is_isomorphic_and_tamper_evident",
    "S3T5_26": "tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_source_mutants_preserve_oracle_hash_and_delete_private_copy",
    "S3T5_27": "tests.test_disk_image_keychain_helper.DiskImageKeychainReviewPackageTests.test_exact_allowlist_hash_manifest_refuses_three_negative_fixtures",
    "S3T5_28": "tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_final_spec_blob_hash_equals_reviewed_hash",
    "S3T5_29": "tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_final_plan_blob_hash_equals_reviewed_hash",
    "S3T5_30": "tests.test_disk_image_keychain_helper.DiskImageKeychainFinalComparisonTests.test_final_cumulative_paths_equal_exact_three_files",
    "S3T5_31": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_both_modes_close_guardian_by_work_cutoff",
    "S3T5_32": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fixture_self_expiry_cannot_satisfy_normal_success",
    "S3T5_33": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_report_binds_route_digest_paths_and_source_binary_hashes",
    "S3T5_34": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_failure_uses_fixed_errno_record_reserved_exit_and_exact_wait",
    "S3T5_35": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_missing_pass_fd_is_rejected_before_go",
    "S3T5_36": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_extra_pass_fd_is_rejected_before_go",
    "S3T5_37": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_duplicate_or_stdio_aliased_child_fd_is_rejected",
    "S3T5_38": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_status_is_only_child_fd_with_cloexec",
    "S3T5_39": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fresh_interpreter_stdio_are_exact_pipes",
    "S3T5_40": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_argv0_equals_absolute_reviewed_helper",
    "S3T5_41": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_helper_handoff_is_direct_exec_not_new_process",
    "S3T5_42": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_guardian_route_never_uses_production_deadline_flag",
    "S3T5_43": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_exec_path_equals_absolute_reviewed_helper",
}

TASK_LOCAL_MUTANTS = {
    "S3T1_01": "stamp_transition_index_inside_reducer",
    "S3T1_02": "omit_effect_disposition_action",
    "S3T1_03": "suppress_valid_signal_action",
    "S3T1_04": "reject_valid_absence_to_quarantine_transition",
    "S3T1_05": "select_default_before_legacy_gate",
    "S3T1_06": "skip_second_artifact_cycle",
    "S3T1_07": "drop_unresolved_ledger_before_close",
    "S3T2_01": "accept_foreign_anchor_registry",
    "S3T2_02": "expose_nonfinal_supervisor",
    "S3T2_03": "include_control_in_native_proof",
    "S3T2_04": "accept_duplicate_terminal_frame",
    "S3T2_05": "accept_deadline_over_seventy_seconds",
    "S3T2_06": "retain_mutable_keychain_staging",
    "S3T2_07": "emit_settlement_before_wire_erasure",
    "S3T2_08": "conflate_normal_exit_kinds",
    "S3T2_09": "consume_suspended_cleanup_on_first_attempt",
    "S3T2_10": "add_competing_lifecycle_reader",
    "S3T2_11": "treat_spawn_failure_as_active_obligation",
    "S3T2_12": "close_control_after_intermediate_settlement",
    "S3T3_01": "accept_foreign_command_registry",
    "S3T3_02": "accept_wrong_absence_context",
    "S3T4_01": "accept_caller_compile_path",
    "S3T4_02": "accept_copied_historical_cursor",
    "S3T4_03": "release_executor_before_handle_registration",
    "S3T4_04": "call_popen_poll_before_waitpid",
    "S3T4_05": "accept_caller_request_path",
    "S3T4_06": "use_nonexclusive_descriptor_move",
    "S3T4_07": "accept_integration_flag_alias",
    "S3T4_08": "accept_allow_effects_flag_alias",
    "S3T4_09": "accept_cleanup_approved_flag_alias",
    "S3T4_10": "accept_authorization_key_alias",
    "S3T4_11": "normalize_authorization_value",
    "S3T4_12": "continue_python_adapter_after_lineage_uncertainty",
    "S3T4_13": "accept_post_latch_keychain_success",
    "S3T4_14": "accept_untyped_observer_source",
    "S3T4_15": "skip_second_observer_baseline",
    "S3T4_16": "scan_historical_receipts_for_cursor",
    "S3T4_17": "skip_second_mount_cycle",
    "S3T4_18": "drop_unresolved_effect_outcome",
    "S3T4_19": "launch_second_continuation_helper",
    "S3T4_20": "reset_continuation_stage_deadline",
    "S3T4_21": "delete_image_before_keychain_absence",
    "S3T4_22": "overwrite_existing_quarantine_target",
    "S3T4_23": "accept_response_without_exact_tuple",
    "S3T4_24": "accept_clock_sample_outside_bracket",
    "S3T5_01": "suspend_fixture_spawn",
    "S3T5_02": "accept_frame_without_control_eof",
    "S3T5_03": "inherit_control_into_fixture",
    "S3T5_04": "create_parent_deadline_after_popen",
    "S3T5_05": "allow_child_report_deadline_extension",
    "S3T5_06": "start_cleanup_at_parent_hard_deadline",
    "S3T5_07": "skip_exact_interpreter_reap",
    "S3T5_08": "send_go_before_report_validation",
    "S3T5_09": "accept_report_pid_different_from_popen_pid",
    "S3T5_10": "use_relative_fresh_interpreter",
    "S3T5_11": "skip_pre_go_descriptor_inventory",
    "S3T5_12": "accept_malformed_exec_status",
    "S3T5_13": "skip_post_exec_descriptor_inventory",
    "S3T5_14": "accept_test_short_deadline_in_production",
    "S3T5_15": "spawn_during_cleanup_reserve",
    "S3T5_16": "pass_pid_count_as_byte_count",
    "S3T5_17": "treat_full_pid_buffer_as_absent",
    "S3T5_18": "skip_procargs_error",
    "S3T5_19": "remove_survivor_scan_caps",
    "S3T5_20": "retain_scanned_command_bytes",
    "S3T5_21": "use_ps_subprocess_for_survivor_scan",
    "S3T5_22": "insert_reachable_unknown_call",
    "S3T5_23": "insert_reachable_spawn_call",
    "S3T5_24": "desynchronize_reviewed_helper_hash",
    "S3T5_25": "accept_manifest_wrong_target_kind",
    "S3T5_26": "mutate_oracle_copy",
    "S3T5_27": "allow_extra_review_package_entry",
    "S3T5_28": "record_spec_hash_without_comparison",
    "S3T5_29": "record_plan_hash_without_comparison",
    "S3T5_30": "accept_extra_implementation_path",
    "S3T5_31": "hold_guardian_open_past_work_cutoff",
    "S3T5_32": "count_fixture_self_expiry_as_success",
    "S3T5_33": "accept_report_without_route_digest",
    "S3T5_34": "swap_exec_failure_reserved_exit",
    "S3T5_35": "omit_one_pass_fd",
    "S3T5_36": "pass_extra_fd",
    "S3T5_37": "allow_duplicate_child_fd",
    "S3T5_38": "set_cloexec_on_wrong_fd",
    "S3T5_39": "inherit_fresh_interpreter_stdio",
    "S3T5_40": "exec_with_wrong_argv0",
    "S3T5_41": "start_helper_with_popen_instead_of_exec",
    "S3T5_42": "route_guardian_through_production_deadline_flag",
    "S3T5_43": "exec_with_wrong_helper_path",
}

BASELINE_CHARACTERIZATION_TEST_IDS = {
    "S3C4_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_all_eight_valid_flag_permutations_are_preserved",
}

BASELINE_CHARACTERIZATION_MUTANTS = {
    "S3C4_01": "reject_permuted_effect_flags",
}
~~~

The implementation constructs the typed `MUTANT_MANIFEST` over the exact union
of those three test maps and three mutant maps. Ownership is exact:

~~~python
NORMATIVE_OWNER = {
    **{f"R{i:02d}": 3 for i in (*range(1, 6), *range(11, 15), 37)},
    **{f"R{i:02d}": 2 for i in (*range(6, 11), *range(33, 36), 39)},
    **{f"R{i:02d}": 4 for i in (*range(15, 26), 36, 38, 45)},
    **{f"R{i:02d}": 1 for i in (*range(26, 33), 44)},
    **{f"R{i:02d}": 5 for i in range(40, 44)},
}

SOURCE_MUTANT_TARGETS = {
    "R17": "tests/disk_image_keychain_harness.py",
    "R38": "tests/disk_image_keychain_harness.py",
    "R44": "native/macos/disk_image_keychain.swift",
    "S3T2_02": "native/macos/disk_image_keychain.swift",
    "S3T2_10": "native/macos/disk_image_keychain.swift",
    "S3T4_01": "tests/disk_image_keychain_harness.py",
    "S3T4_04": "tests/disk_image_keychain_harness.py",
    "S3T4_05": "tests/disk_image_keychain_harness.py",
    "S3T4_06": "tests/disk_image_keychain_harness.py",
    "S3T4_14": "tests/disk_image_keychain_harness.py",
    "S3T5_09": "tests/disk_image_keychain_harness.py",
    "S3T5_10": "tests/disk_image_keychain_harness.py",
    "S3T5_14": "native/macos/disk_image_keychain.swift",
    "S3T5_15": "tests/disk_image_keychain_harness.py",
    "S3T5_21": "tests/disk_image_keychain_harness.py",
    "S3T5_22": "native/macos/disk_image_keychain.swift",
    "S3T5_23": "native/macos/disk_image_keychain.swift",
    "S3T5_24": "tests/disk_image_keychain_harness.py",
    "S3T5_35": "tests/disk_image_keychain_harness.py",
    "S3T5_36": "tests/disk_image_keychain_harness.py",
    "S3T5_37": "tests/disk_image_keychain_harness.py",
    "S3T5_38": "tests/disk_image_keychain_harness.py",
    "S3T5_39": "tests/disk_image_keychain_harness.py",
    "S3T5_40": "tests/disk_image_keychain_harness.py",
    "S3T5_41": "tests/disk_image_keychain_harness.py",
    "S3T5_42": "native/macos/disk_image_keychain.swift",
    "S3T5_43": "tests/disk_image_keychain_harness.py",
}

SWIFT_RUNTIME_CASES = frozenset({
    *(f"R{i:02d}" for i in (*range(1, 15), *range(33, 36), 37, 39, 40, 41)),
    *(f"S3T2_{i:02d}" for i in range(1, 13)),
    "S3T3_01", "S3T3_02", "S3T5_01", "S3T5_03",
}) - SOURCE_MUTANT_TARGETS.keys()

SYNTHETIC_GATE_CASES = frozenset({
    "S3T5_25", "S3T5_26", "S3T5_27",
    "S3T5_28", "S3T5_29", "S3T5_30",
})
~~~

`owner_for(case)` returns `NORMATIVE_OWNER[case]` for R keys, the integer after
`S3T` for task-local keys, and 4 for `S3C4_01`; every other shape rejects.

Every other manifest entry is `kind=runtime`; its `target_file` is the Swift
source exactly when its case is in `SWIFT_RUNTIME_CASES`, otherwise the
harness. It is never the test/oracle module. Runtime
branches use the unique literal
`CORTEX_RUNTIME_MUTANT::<CASE>::<MUTANT_NAME>`. Source entries use
`CORTEX_SOURCE_MUTANT::<CASE>::<MUTANT_NAME>` and the exact one-anchor
replacement declared by their mapped boundary: R44 inserts the typecheckable
legacy route-table handler/dispatch; private-final removes only `final`;
the lifecycle-reader mutant inserts exactly one competing control-read call;
the Popen-lifecycle mutant inserts exactly one `poll` before private waitpid;
the shared-clock mutant replaces only `shared_clock_ns()`'s exact return call;
no-free-operand signature mutants add exactly one caller parameter;
exclusive move replaces `RENAME_EXCL` with zero; observer/hash mutants change
only the copied source/hash constant; same-PID/Popen/FD entries replace only
their one named call argument or handoff; cleanup scan inserts one forbidden
process-launch call; call-graph entries insert one unknown or forbidden
reachable leaf; short-deadline entries substitute only the one deadline flag or
parser branch. No source replacement targets tests or oracle helpers.

For every case, the materialized record contains:

~~~python
case, owner, test_id, mutant_name, kind, target_file, unique_anchor,
runtime_branch_or_replacement, oracle_id, oracle_sha256, assertion_label,
red_policy
~~~

`red_policy` is `baseline_characterization` only for `S3C4_01`,
`synthetic_gate` only for `SYNTHETIC_GATE_CASES`, and `natural` otherwise.
`oracle_sha256` is the frozen 64-lowercase-hex digest of the transitive oracle
closure. The manifest checker proves exact domain/projection equality, allowed
target kind/file, all unique anchors/names/tests/labels, one transformation,
unchanged closure hash and exact `MUTANT_<CASE>_<MUTANT_NAME>`.

The harness materializes, validates and only then exposes the mapping:

~~~python
ALL_TEST_IDS = MappingProxyType(
    REGRESSION_TEST_IDS | TASK_LOCAL_TEST_IDS | BASELINE_CHARACTERIZATION_TEST_IDS
)
ALL_MUTANTS = MappingProxyType(
    REGRESSION_MUTANTS | TASK_LOCAL_MUTANTS | BASELINE_CHARACTERIZATION_MUTANTS
)
assert ALL_TEST_IDS.keys() == ALL_MUTANTS.keys()
assert ORACLE_CLOSURE_SHA256.keys() == ALL_MUTANTS.keys()

MUTANT_MANIFEST = MappingProxyType({
    case: build_checked_manifest_record(
        case=case,
        owner=owner_for(case),
        test_id=ALL_TEST_IDS[case],
        mutant_name=ALL_MUTANTS[case],
        kind="source" if case in SOURCE_MUTANT_TARGETS else "runtime",
        target_file=target_file_for(case),
        unique_anchor=unique_anchor_for(case, ALL_MUTANTS[case]),
        transformation=transformation_for(case, ALL_MUTANTS[case]),
        oracle_id=ALL_TEST_IDS[case],
        oracle_sha256=ORACLE_CLOSURE_SHA256[case],
        assertion_label=f"MUTANT_{case}_{ALL_MUTANTS[case]}",
        red_policy=red_policy_for(case),
    )
    for case in ALL_MUTANTS
})
~~~

`ORACLE_CLOSURE_SHA256` is a literal 134-entry map frozen only after each
owner's unchanged oracle reaches GREEN; computed-on-demand values are rejected
because they would not detect oracle drift.

## Task ownership

| Task | Normative IDs | Task-local/characterization IDs | Boundary |
| --- | --- | --- | --- |
| 1 | 26-32, 44 | S3T1_01-S3T1_07 | Importable skeleton, independent models, exact cursor reference and source-mutant legacy removal. |
| 2 | 06-10, 33-35, 39 | S3T2_01-S3T2_12 | Strong-identity obligation/cleanup anchors, serial lifecycle, total control/tuples, SpawnResult, deadline and erasure. |
| 3 | 01-05, 11-14, 37 | S3T3_01-S3T3_02 | Swift command provenance, self-contained detach/absence and immutable phase windows. |
| 4 | 15-25, 36, 38, 45 | S3T4_01-S3T4_24; S3C4_01 | Observer-first preparation, shared clock, current cursor/two cycles, total continuation/cleanup/disposition, request and authorization. |
| 5 | 40-43 | S3T5_01-S3T5_43 | All three files: report-GO-exec fixture, exact FDs/status, short test deadline, libproc, call graph, hashes, typed manifest and final package/comparisons. |

## Execution-contract traceability

| Contract | Specification contract | Implementing plan steps | Exact oracle(s) |
| --- | --- | --- | --- |
| Native obligation, retained suspended cleanup and honest owner-destruction boundary | `Private final owner`; `Suspended production bootstrap`; `Closed kernel contracts` | Task 2 Steps 1-3, 8 | R35; S3T2_01-S3T2_02; S3T2_09-S3T2_11 |
| Serial lifecycle, total DFA, exact tuples and final-only control close | `Drain`; `Total control DFA` | Task 2 Steps 1, 5-6, 8; Task 4 Step 9 | R36-R37; R40; S3T2_03-S3T2_04; S3T2_08; S3T2_10; S3T2_12; S3T4_23 |
| Shared cross-process clock and immutable deadlines | `Deadline validation`; `Guardian/witness contract` | Task 2 Step 4; Task 3 Step 4; Task 4 Steps 7, 12; Task 5 Steps 2, 4-6 | R11-R14; R38; R43; S3T4_20; S3T4_24; S3T5_04-S3T5_06; S3T5_14; S3T5_42 |
| Observer-first preparation and no premature live root | `One-shot preparation and fixed artifacts` | Task 4 Steps 1, 3-4, 11 | R15-R17; S3T4_01; S3T4_05; S3T4_14-S3T4_15 |
| Exact current cursor and two complete cycles | `Receipt algebra and terminal disposition`; `Independent effect model` | Task 1 Steps 2, 4; Task 4 Steps 1, 5, 7 | R18-R25; S3T1_06-S3T1_07; S3T4_02; S3T4_16-S3T4_18 |
| One current-mapping detach-plus-absence continuation | `One post-terminal detach-plus-absence continuation` | Task 3 Step 4; Task 4 Steps 1, 5, 7 | R18-R20; R22; S3T4_19-S3T4_20 |
| Keychain-first cleanup, exclusive image move and total disposition | `Receipt algebra`; `Descriptor-relative quarantine` | Task 4 Steps 1, 5, 7-8 | R21-R24; S3T4_06; S3T4_18; S3T4_21-S3T4_22 |
| Python wait/reap parity and lineage-model parity | `Python process parity` | Task 4 Steps 1 and 9 | R06-R10; R26-R36; S3T4_04; S3T4_12 |
| Exact flag near misses plus preserved permutations | `Registry-minted roots only`; `TDD evidence` | Task 4 Steps 1 and 10 | R45; S3T4_07-S3T4_11; S3C4_01 |
| Report-GO-exec same PID, exact Popen/FD/status and short testing deadline | `Guardian/witness contract` | Task 5 Steps 1-5 | R40-R41; R43; S3T5_04-S3T5_14; S3T5_31-S3T5_43 |
| Five-second cleanup, complete libproc scan and no process scanner | `Guardian/witness contract` | Task 5 Steps 5-6 | R43; S3T5_06-S3T5_07; S3T5_15-S3T5_21 |
| Compiler-AST fixture call graph and synchronized sources | `Preparation`; `Guardian/witness`; `Mutation system` | Task 5 Steps 3, 8 | R44; S3T5_22-S3T5_24 |
| Independent models and exhaustive legacy removal | `Independent model architecture`; `Closed routes` | Task 1 Steps 1-6 | R26-R32; R44; S3T1_01-S3T1_07 |
| App-owned secret boundary | `Application-controlled secret lifetime` | Task 2 Steps 1 and 7 | R39; S3T2_06; S3T2_07 |
| Typed mutant system and source-copy integrity | `Test inventory, TDD and release evidence` | Checkpoint protocol; Task 5 Step 8 | S3T5_25-S3T5_26; every exact mutant label |
| Sealed package and compared final bytes/paths | `Review, checkpoint and S4 separation` | Revision-5 gate; blind gate; Task 5 Steps 9, 13-14 | S3T5_27-S3T5_30; five-path manifest; exact hash/path equality commands |

## Final self-review checklist

- [ ] The two production/fixture bootstraps are distinct; only production is
  suspended and only scripted tests claim its bootstrap.
- [ ] Swift owner/registries are private final classes; tokens carry only
  strongly retained private registry identity/generation, and validation uses
  object identity rather than a reusable `ObjectIdentifier` value.
- [ ] `NativeObligation` has the exact seven monotone states;
  `SuspendedCleanupAnchor` and the active record survive every non-exact reap,
  and `NoActiveChildProof` waits for group/close/frame settlement.
- [ ] Suspended validation versus cleanup is atomic; cleanup permits only
  bounded positive-PID retry and the docs make no eventual-reap claim after
  destruction of the owner helper.
- [ ] Native settlement excludes control; Python requires final frame, control
  EOF and exact helper reap; absent/abnormal EOF, wrong exit or missing frame
  is `UNCLEAR`.
- [ ] Control DFA covers every exact frame/response/exit/EOF/reap row, all five
  states and all normal/terminal exit kinds; an intermediate `0x12` never closes
  control.
- [ ] One serial lifecycle executor is the only control reader/lifecycle writer,
  polls cancel before spawn/after insertion/before resume and writes, and holds
  no subordinate lock over a blocking syscall.
- [ ] `SpawnResult` and every other closed kernel/I/O enum member have explicit
  advancing/non-advancing matrices.
- [ ] Pre-request deadline checks cap remaining time at 70 seconds with checked
  arithmetic and no replacement deadline; testing +2 s admission uses only the
  separate testing flag/validator.
- [ ] All transmitted/comparable timestamps share `CLOCK_MONOTONIC` using the
  exact Python and Swift calls; 20 bracket samples meet the fixed 50 ms bound.
- [ ] Terminal detach/absence uses one Python-authorized current-mapping helper
  with exact +8/+14/+20/+26 s stops, no historical-device authority, no second
  helper and no cross-process Swift token.
- [ ] Python every authority root is registry-minted with object identity and
  copy/cross-boundary/replay rejection.
- [ ] Exactly one current `ArtifactCursor` follows the declared state sequence,
  completes indexed cycles 0 and 1, inspects once and consumes only its current
  terminal-transfer slot.
- [ ] Observer source is written/hashed/typechecked/compiled, first empty
  baseline is captured, helper compiles while observed, second empty baseline
  is captured, then and only then live roots/115-second clock are minted.
- [ ] No live method accepts caller path/device/operation/argv.
- [ ] Exact ten-key values preserve current global fields and per-operation
  UUID/cleanup rules.
- [ ] Cleanup proves one Keychain item, consumes `CleanupGrant`, deletes and
  re-queries zero before issuing image permission; terminal after Keychain
  deletion performs no later Keychain effect.
- [ ] Every effect returns a closed settled/unresolved ledger outcome; normal
  success, unapproved quarantine and every failure each mint exactly one
  `DispositionReceipt`, then `close(DispositionReceipt)` once.
- [ ] Quarantine/deletion use descriptor-relative
  `renameatx_np(parent_fd, old_leaf, parent_fd, new_leaf, RENAME_EXCL)`, never
  overwrite collision, revalidate old/new
  facts and close every FD independently.
- [ ] Python and Swift waitid/waitpid branches have full parity and no early
  Popen terminal helper, replayed waitpid or post-reap Popen state authority.
- [ ] Models compare complete externally indexed actions and final state to
  independent machines; alphabets are exactly 15/22 and counts are
  813,616/5,399,043 with positive two-cycle/disposition traces.
- [ ] R43 creates all endpoints/deadlines before exact Popen, validates complete
  report before GO, proves CLOEXEC exec-status, retains direct Popen PID and
  enforces exact pre-GO/post-exec FD inventories.
- [ ] R43 uses +0.75/+1.50/+2.00/+2.50/+3.00/+5.00 s; both modes close guardian,
  normal PASS settles before +2.00, and self-expiry is never counted as PASS.
- [ ] Cleanup reserve spawns nothing; libproc treats count/bytes/full-buffer/
  growth/errors/framing conservatively, is capped, uses current UID and retains
  no command line.
- [ ] Compiler AST closes the fixture call graph and the forbidden reachable
  call mutant typechecks then fails the unchanged oracle.
- [ ] Natural, baseline-characterization and synthetic-gate policies are
  separated; S3C4_01 is GREEN before/after for all eight flag permutations.
- [ ] Typed `MUTANT_MANIFEST` is isomorphic to all maps and each case has unique
  owner/test/name/kind/target/anchor/closure hash/label; R44 and every declared
  structural mutant use a private typecheckable source copy and leave no residue.
- [ ] Each of three flags and authorization key/value has prefix/suffix/case/
  old-alias coverage with distinct mutants.
- [ ] Task 5 owns all three implementation files and synchronizes harness-owned
  helper/observer/fixture source hashes imported by tests.
- [ ] App-owned entropy/Master/Wire/Keychain staging are zeroed; opaque external
  copies are not claimed.
- [ ] Dynamic complete suites pass under Python 3.11 and 3.14 with byte-identical
  ordered starts, zero skip and no live class.
- [ ] Immediately before `S3_FINAL`, exact status is only ` M primer.md`, staged
  output is empty, primer diff is unchanged, spec/plan hashes are compared to
  frozen reviewed values and cumulative paths equal exactly three files.
- [ ] Blind package generation uses only the exact `git show` allowlist, records
  size/hash per entry and rejects extra/wrong-hash/forbidden-review fixtures.
- [ ] The revision-5 documentation completion gate ran no code/test/build/helper
  or live effect, committed exactly the two docs and left `primer.md` unchanged
  and unstaged.
- [ ] S4 rebaseline is a separate later documentation commit.
