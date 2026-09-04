# S3 Owned-Process Supervision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Preserve
> every checkbox and stop at the first failed gate.
>
> Execute sequentially. Each task starts with its own failing tests, ends with
> exact GREEN and mutant receipts, and receives read-only review before the
> next task changes behavior.

**Goal:** Replace forgeable process/effect authority with two exact
running/exited anchors, an atomic suspended-child bootstrap, narrow native
settlement, absolute deadline/control propagation, sealed Python registries and
closed harmless tests.

**Architecture:** Production Swift starts only fixed `/usr/bin/hdiutil`
children suspended in new sessions, atomically converts a private
`SuspendedChildAnchor` to a `RunningSessionAnchor`, converts exact WNOWAIT exit
to `ExitedUnreapedSessionAnchor`, and consumes it through exact `waitpid`.
Python prepares fixed helper/observer artifacts before the live clock starts,
mints every live root through object-identity registries, serializes effects
through one executor, and accepts completion only after an exact frame, control
EOF and helper reap. Independent reference machines validate complete
process/effect traces. The only real fixture is non-suspended, self-expiring
and descendant-free.

**Tech stack:** Swift 6; Darwin `posix_spawn`, `proc_pidinfo`, `waitid`,
`waitpid` and `poll`; Security.framework; Python 3.11 and 3.14 standard library
`unittest`, `ctypes`, `subprocess` and `selectors`; Git and Gitleaks.

**Spec:** `docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md`

## Global constraints

- Work only in
  `/Users/asterion/Desktop/cortex-bridge/.worktrees/codex-v054-storage-consolidation`
  on branch `codex/v054-storage-consolidation`.
- Implementation starts only after the exact revision-4 spec/plan bytes pass
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
- One writer owns a file at a time. Every task has a dedicated commit and fresh
  read-only spec/code review.
- S4 implementation and S4 rebaseline documentation remain outside S3.

## Revision-4 documentation completion gate

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
~~~

The placeholder search must return no match, fences must be balanced, the
primer hash must equal `DOC_PRIMER_DIFF_SHA256` and no path may be staged before
the explicit candidate stage. A static map checker must then prove: R01-R45
appear once each in both normative maps; every fully qualified test ID is
unique; every task ownership range equals its test and mutant map keys; every
primary mutant is one branch without `or`; and every task-local map entry has
one method, mutant and `MUTANT_<KEY>_<MUTANT>` label contract.

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
git commit -m "docs(storage): complete S3 revision 4 review candidate"
test "$(git status --short --untracked-files=all)" = " M primer.md"
~~~

Only after that exact docs-only commit may the blind documentation gate run.

## Blind documentation gate

- [ ] Freeze the candidate commit and compute exact SHA-256 for the spec and
  plan from that commit.
- [ ] Give each fresh reviewer only the exact candidate bytes/hashes, declared
  requirements, reviewed baseline and necessary source context.
- [ ] Exclude every prior findings file, consolidated findings document,
  verdict, reviewer identity and reviewer conclusion from each package.
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

The primer hash must equal `PRIMER_DIFF_SHA256`. Before the first production
change to each task boundary:

1. add that task's normative tests and `TASK_LOCAL_TEST_IDS` methods;
2. add the exact map entries without changing an oracle;
3. run each method alone under Python 3.11;
4. require a natural assertion RED for the missing boundary;
5. record test-source SHA, interpreter path/version, command, exit status,
   exact failing assertion and expected cause.

If a new test passes before its boundary is implemented, stop: it is not a
valid RED. Tighten only an incomplete oracle until the missing required
behavior fails naturally. A mutant never substitutes for this natural RED.

Use the same individual runner for normative and task-local IDs:

~~~bash
PYTHON311="$PWD/.venv/py311/bin/python"
CASE_KEY=S3T1_01
TEST_ID=$("$PYTHON311" -c 'import sys; from tests.test_disk_image_keychain_helper import ALL_TEST_IDS; print(ALL_TEST_IDS[sys.argv[1]])' "$CASE_KEY")
env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin LANG=C LC_ALL=C \
  PYTHONHASHSEED=0 PYTHONPATH="$PWD" \
  "$PYTHON311" -m unittest "$TEST_ID" -v
~~~

`ALL_TEST_IDS` is a read-only merge of `REGRESSION_TEST_IDS` and
`TASK_LOCAL_TEST_IDS`; duplicate keys or values fail import.

`ALL_MUTANTS` is a read-only merge of `REGRESSION_MUTANTS` and
`TASK_LOCAL_MUTANTS`; duplicate keys or values fail import. For every closed
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

Every mutant changes exactly one production/harness branch. Composite
`A_or_B` mutants and test/oracle mutation are forbidden. The test-only mutant
dispatcher rejects unknown names and changes only the named
production/harness branch; reference machines and assertions never take a
mutant-dependent path. For each run set
`ASSERTION_LABEL="MUTANT_${CASE_KEY}_${MUTANT}"`, require that exact label in
the mapped method's failure, record it with the branch name, then restore the
branch. After each task GREEN, run every normative and task-local mutant owned
by that task one at a time, require its exact mapped method and label to fail,
then rerun the complete task-owned set without mutants.

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

**Task-local ownership:** `S3T1_01` through `S3T1_05`.

- [ ] **Step 1: Write and individually observe task-local and normative RED**

Add independent reference-machine tests before reducer or route changes. The
RED set proves:

- transition indices are attached by the explorer, outside both reducers;
- full indexed action sequence and full primitive final state are equal to the
  independent reference result;
- positive signal/native-settlement/full-disposition counters are nonzero;
- complete long disposition and replay traces exist;
- the legacy-route structural gate runs before any default-suite selection and
  is naturally RED while all six legacy literals, handlers, launchers and test
  names remain present.

Run all owned normative and task-local methods individually. Record only
assertion failures tied to these missing boundaries.

- [ ] **Step 2: Create the harness and implement the process model without live process calls**

Create the new test-only `tests/disk_image_keychain_harness.py` module; it has
no baseline implementation, reducer, registry or model API to preserve. Define
this exact ordered alphabet there:

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
WNOWAIT exit, exact reap, original-group absence, pipes closed and native
settlement, followed by replay attempts.

- [ ] **Step 3: Implement the independent effect model**

Use exactly:

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

The effect reducer and registry are independent of the process model. Enumerate
all prefixes through depth five and assert 5,399,043. The independent reference
machine compares the full externally indexed action sequence and final
primitive state. Long traces cover:

- activate, mount, terminal, begin disposition, detach issue/consume/settle,
  absence issue/consume/settle, quarantine issue/consume/settle, finalization
  and close;
- mapping receipt, preterminal-unmounted proof, terminal transfer and
  descriptor-relative quarantine;
- terminal no-artifact, create-only, mapping-unknown and unresolved preservation
  through final disposition and close;
- replay of every derivative slot, terminal transfer, detach, absence,
  quarantine and disposition receipt.

Positive counters require ordinary success, a quarantined disposition, a
preserved disposition and close.

- [ ] **Step 4: Delete legacy routes exhaustively**

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

Do not add the guardian route yet. The pre-default structural test scans both
source files and discovered unittest method names. It must run before any
default test that can compile or spawn.

- [ ] **Step 5: GREEN and mutate every owned boundary**

Run each owned normative/task-local method individually, then the Task 1 set.
Enable each mapped mutant alone and require only its mapped method to fail.
The long-trace suite must catch replay and omitted-success mutants; exact count
tests must catch alphabet or enumeration changes.

- [ ] **Step 6: Commit Task 1**

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

**Task-local ownership:** `S3T2_01` through `S3T2_08`.

- [ ] **Step 1: Write and individually observe RED**

Before changing the supervisor, add scripted tests for:

- private final supervisor and private final issuance registries;
- forged/stale/replayed/cross-registry suspended/running/exited tokens;
- strongly retained registry identity with allocator-reuse refusal;
- atomic validate-versus-abort interleavings;
- native proof excluding control;
- complete control DFA including every invalid input/state;
- distinguishable `strictRejected`, `acceptedNoChild` and
  `protocolAbnormal` normal exits;
- pre-request maximum-deadline arithmetic;
- Wire erasure before every outcome/frame and app-owned Keychain staging
  erasure.

Run every owned method alone and record natural RED.

- [ ] **Step 2: Create final owners and registry-only anchors**

Make `OwnedProcessSupervisor`, `AnchorRegistry`,
`CommandIssuanceRegistry` and `ControlIssuanceRegistry` private final reference
types. Give each registry an unexported strongly retained `RegistryIdentity`,
lock and monotonic generation. Tokens hold that private identity reference plus
generation, and every validation uses `===` against the issuing registry; no
`ObjectIdentifier` value is used or accepted. A copied token retains the same
identity but cannot duplicate its record; a stale identity cannot become valid
after allocator reuse. Registry records contain PID, birth seconds/microseconds,
effective UID, PGID, SID, command generation and consumption state.

Production `spawnSuspendedSession` uses only
`POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSID |
POSIX_SPAWN_START_SUSPENDED`, stores raw PID privately, and returns
`SuspendedChildAnchor`.

Under one registry lock, `validateSuspendedIdentity` consumes the suspended
anchor into `RunningSessionAnchor` only after the two complete proc records and
intermediate `getsid` agree exactly. The competing
`abortAndReapSuspendedDirectChild` consumes it before positive-PID abort and
exact reap. Neither path can run after the other; abort never uses a negative
target.

The private control registry mints `NoActiveChildProof` only after its locked
child table is empty for valid START/IDLE cancellation. Its strong registry
identity and generation are consumed by exactly one `0x13` transition; copied,
stale or cross-registry proofs emit no frame and authorize no effect.

- [ ] **Step 3: Implement running and exited anchors**

Revalidate running authority before SIGCONT, TERM and KILL with:

~~~text
complete proc_bsdinfo
getsid(pid)
complete proc_bsdinfo
~~~

Require unchanged PID, birth, effective UID, PGID and SID. Exact WNOWAIT exit
zero-initializes `siginfo_t` and accepts only exact PID, SIGCHLD and
CLD_EXITED/CLD_KILLED/CLD_DUMPED. Consume running authority and mint
`ExitedUnreapedSessionAnchor`. Do not call `getsid` on that zombie.

Observe exited authority before each remaining signal and exact reap with
zero-initialized `waitid(WNOWAIT)`; that observation never reaps. Only exact
`waitpid == pid` consumes it and mints one `ReapedGroupObservationToken`;
consume that token before one signal-zero original-group observation. ECHILD,
wrong PID/status, EINTR after deadline, EPERM, present group or any other error
remains unresolved. Once KILL is attempted, issue no later TERM/KILL.

- [ ] **Step 4: Implement bounded request/deadline admission**

Accept only production argv:

~~~text
--control-fd DECIMAL_FD --swift-hard-deadline-ns DECIMAL_NS
~~~

Validate the exact descriptor inventory, set CLOEXEC/nonblocking, then sample
`now` once and prove before reading request bytes:

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

Cover cancel after first/second pairs, no-child completion, not-spawned,
unresolved without cancel, helper exit in each state, EOF, EAGAIN, unknown,
duplicate/out-of-order bytes and all terminal replays. Recheck the cancel latch
immediately before spawn, SIGCONT, child input and every nonterminal frame.
Keep `NormalExitKind.strictRejected` (exit 64/no frame),
`NormalExitKind.acceptedNoChild` (exit 0/final `0x10`) and
`NormalExitKind.protocolAbnormal` (exit 65) separate through the Python
verdict. The latter, absent/abnormal control EOF, wrong helper exit or a
missing terminal frame is `UNCLEAR`; no accepted no-child verdict may share
that path.

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
shutdown and close helper control endpoint
~~~

A control close failure has no later frame. It is detected by Python as missing
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
for every `IdentityResult`, `ResumeResult`, `ExitObservation`, `SignalResult`,
`ReapResult`, `GroupPresence`, `PollResult`, `IOResult`, `CloseResult` and
`SuspendedAbortResult`; fail each descriptor position independently. Include
the three `NormalExitKind` classes and their Python frame/EOF/reap verdicts.

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
failure never resets compensation/absence deadlines. These are the original
live helper's pre-terminal windows only. Task 4 creates any post-terminal
detach/absence continuation as a fresh sealed helper invocation with one
immutable 14- or 12-second hard deadline that must fit inside the unchanged
outer 115-second deadline; it never derives a replacement live epoch.

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

**Task-local ownership:** `S3T4_01` through `S3T4_14`.

- [ ] **Step 1: Write and individually observe RED**

Before changing the harness, add task-local tests for:

- one-shot preparation with no caller compile/observer paths;
- copied/cross-session/cross-registry receipts, terminal-snapshot consumption
  and atomic active-lineage transfer at the terminal latch;
- executor linearization at every latch/spawn/register/first-write boundary;
- Python waitid/waitpid parity, replay refusal, private post-reap handle state
  and the ban on Popen poll/wait/communicate before and after exact reap;
- exact scripted Python-adapter parity with the independent Task-1 raw
  lineage oracles for every R26-R32 trace;
- exact ten-key values and zero caller operands;
- descriptor-relative quarantine;
- separate prefix/suffix/wrong-case/old-alias rejection for each of
  `--integration`, `--allow-effects` and `--cleanup-approved`;
- separate authorization-key alias and authorization-value normalization
  rejection;
- a synchronous Keychain result returning after terminal;
- executable typecheck of the exact reviewed observer source.

Add the owned normative tests and run every method alone to natural RED.

- [ ] **Step 2: Implement registry-minted authority roots**

Define frozen, slotted, `eq=False` shells containing only `_issuance_id:
object` for:

~~~text
PreparationCapability
LiveExecutionCapability
ObserverBaseline
SecurityAgentSnapshot
TerminalEventReceipt
DispositionStartReceipt
ArtifactContext
CommandReceipt
CreateCommandReceipt
MountCommandReceipt
MappingCommandReceipt
DetachCommandReceipt
AbsenceCommandReceipt
CleanupGrant
PreTerminalUnmountedProof
DetachedUnmountedProof
DetachPermit
AbsencePermit
QuarantinePermit
QuarantineReceipt
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

Expose only:

~~~python
PreparationSession.compile_helper()
PreparationSession.prepare_observer()
~~~

Both take no operands. Use one checked 30-second absolute preparation deadline
and the exact Python process adapter. Hash/typecheck the reviewed observer,
collect complete process/window baseline, and mint an empty
`ObserverBaseline`. Only then consume preparation authority and mint one
`LiveExecutionCapability` plus one `ArtifactContext`.

Create the 115-second live absolute deadline after those issuances. Registry
context fixes transaction, generated image/mount names, volume
`CORTEX_BRIDGE_SPIKE`, size `64m`, filesystem APFS and disposable true. It
captures the private parent directory's no-follow descriptor facts
(device/inode/mode/UID) at issuance. Settled create captures the image leaf's
same four facts through that parent descriptor; the sealed create/mount
receipts, never a caller path or later string lookup, carry them to
descriptor-relative quarantine.

- [ ] **Step 4: Serialize every observation and effect**

One session executor lock spans terminal-latch check, deadline/phase check,
registry lookup, `Popen`, handle registration and first-write authorization.
Do not release between these points. Observation uses the same executor.
Deterministic barriers schedule the terminal latch immediately before/after
each point and prove no spawn or write crosses it.

If a synchronous Keychain syscall is in flight at terminal, register only its
late diagnostic result. It cannot mint any receipt, authorize a new effect or
change FAIL/UNCLEAR to success.

The fixed observer bridge alone mints a terminal `SecurityAgentSnapshot` from
complete SecurityAgent detection evidence or the closed
`observer_unavailable` result. `latch_terminal(snapshot)` consumes it under
that same lock, increments the epoch, revokes ordinary authority and atomically
consumes eligible active mount or preterminal-unmounted roots into a sealed
`TerminalEventReceipt` lineage. Old ACTIVE tokens are never grandfathered
across the epoch. The receipt is then consumed by `begin_disposition` to mint
one `DispositionStartReceipt` with exactly one lineage kind: no-artifact,
create-only, mounted, preterminal-unmounted, mapping-unknown or unresolved.

- [ ] **Step 5: Implement only the sealed method catalogue**

Implement exact no-free-operand signatures:

~~~python
create_image(context: ArtifactContext) -> CreateCommandReceipt
mount_image(
    context: ArtifactContext,
    create: CreateCommandReceipt,
) -> MountCommandReceipt
detach_normal(mount: MountCommandReceipt) -> DetachCommandReceipt
inspect_item(create: CreateCommandReceipt) -> CommandReceipt
delete_item(
    create: CreateCommandReceipt,
    grant: CleanupGrant,
) -> CommandReceipt
probe_encryption(create: CreateCommandReceipt) -> CommandReceipt
probe_disk(mount: MountCommandReceipt) -> CommandReceipt
probe_mapping(mount: MountCommandReceipt) -> MappingCommandReceipt
prove_preterminal_unmounted(
    mapping: MappingCommandReceipt,
) -> PreTerminalUnmountedProof
observe_terminal_snapshot() -> SecurityAgentSnapshot
latch_terminal(snapshot: SecurityAgentSnapshot) -> TerminalEventReceipt
begin_disposition(event: TerminalEventReceipt) -> DispositionStartReceipt
detach_permit(start: DispositionStartReceipt) -> DetachPermit
detach_for_disposition(permit: DetachPermit) -> DetachCommandReceipt
absence_permit(detach: DetachCommandReceipt) -> AbsencePermit
prove_absence_for_disposition(
    permit: AbsencePermit,
) -> AbsenceCommandReceipt
detached_unmounted_proof(
    absence: AbsenceCommandReceipt,
) -> DetachedUnmountedProof
preterminal_quarantine_permit(
    start: DispositionStartReceipt,
) -> QuarantinePermit
quarantine_permit(proof: DetachedUnmountedProof) -> QuarantinePermit
quarantine_for_disposition(
    permit: QuarantinePermit,
) -> QuarantineReceipt
preserve_for_disposition(
    start: DispositionStartReceipt,
) -> PreservationReceipt
finalize_disposition(
    outcome: QuarantineReceipt | PreservationReceipt,
) -> DispositionReceipt
close(disposition: DispositionReceipt) -> FinalVerdict
~~~

There is no public `record_mount`, generic runner, argv, raw path/device
parameter, operation/cleanup request field, safety switch or alternate close.
`mount_image` atomically returns the registry-issued
`MountCommandReceipt` containing the exact complete command receipt, UUID,
device, image, mount and transaction evidence.

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

Use the spec's receipt-algebra table literally. Each producer stores complete
predecessor identity and exact result. Each consumer atomically consumes the
expected issuance before effect. `close` consumes only a
`DispositionReceipt`. Generic `CommandReceipt` values are immutable
same-session evidence only: no generic receipt may mint a permit, capability,
command or disposition. The Swift control-only `NoActiveChildProof` is minted
and consumed exclusively by Task 2; it is not a Python receipt and cannot
cross this boundary.

Implement named one-shot derivative slots rather than treating a receipt as
having one ambiguous consumer: create owns distinct mount/probe/inspect/delete
slots; mount owns distinct normal-detach/mapping/terminal-transfer slots.
Read-only consultation validates the exact registry payload but can mint no
effect. At the terminal latch, consume the eligible mount or preterminal proof
slot and re-mint its private lineage inside `TerminalEventReceipt` under the
same executor lock. No stale ACTIVE token is accepted after epoch increment.

`begin_disposition` consumes that receipt and makes total disposition explicit:
no-artifact, create-only, mapping-unknown and unresolved start records consume
only `preserve_for_disposition`; mounted records consume only an exact detach
permit, then exact absence and quarantine; preterminal-unmounted records
consume only the transferred descriptor-relative quarantine route. Each route
mints `DispositionReceipt` and then `close`. Unknown mapping performs no new
query/inspect/delete/quarantine. After terminal, ordinary methods and cleanup
grants are revoked.

After valid predecessor frame, control EOF and exact helper reap, a mounted
start may create one fresh Swift detach continuation only if a checked
`now + 14 s` fits inside immutable `outer_hard_ns`; exact settled detach may
then create one fresh absence continuation only if checked `now + 12 s` fits.
Both inherit the same strict argv/deadline validation and sealed receipt
context. Insufficient fit or any unresolved predecessor mints preservation with
zero spawn; neither continuation may reset, extend or borrow a deadline.

Write the receipt forgery matrix test-by-test, not as a pooled assertion:

| Normative ID | Exact forged/copy/session/result oracle |
| --- | --- |
| R18 | forged, copied, stale and replayed `DetachPermit` cause zero second detach spawn |
| R19 | copied/inter-session/inter-registry/wrong-epoch `MountCommandReceipt` cannot issue a second detach or terminal-transfer slot |
| R20 | wrong command, result, device, lineage or replayed `DetachCommandReceipt` cannot issue absence |
| R21 | forged/copy/replay `TerminalEventReceipt`, `DispositionStartReceipt`, quarantine/preservation output and final disposition all refuse; each legitimate terminal lineage reaches `close` once |
| R25 | wrong create/mount command or result value cannot register nonzero evidence before terminal propagation |

- [ ] **Step 8: Implement descriptor-relative quarantine**

Open the registered parent with
`O_RDONLY | O_CLOEXEC | O_NOFOLLOW | O_DIRECTORY`, then the registered image
leaf relative to it with `O_RDONLY | O_CLOEXEC | O_NOFOLLOW`. Verify device,
inode, mode and UID with `fstat` and no-follow `fstatat`. Rename only with:

~~~python
os.rename(
    old_leaf,
    new_leaf,
    src_dir_fd=parent_fd,
    dst_dir_fd=parent_fd,
)
~~~

Revalidate destination facts and source absence relative to `parent_fd`.
Close image/parent FDs independently on every branch. Ban `Path.rename`,
absolute rename and fallback. Mint `QuarantineReceipt` only after complete
revalidation and closes. The parent/image device, inode, mode and UID compared
here come only from the sealed `ArtifactContext` and settled create/mount
receipt capture; a later stat result is verification evidence, never replacement
provenance.

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

For `S3T4_12`, feed the exact raw lineage inputs used by R26-R32 to the scripted
`PythonOwnedProcessAdapter` and, separately, to the Task-1 reference machine.
Compare the complete primitive action sequence, terminal reason and final
authority state for equality. The adapter test must not reuse a reducer,
registry, permit or expected-action helper from the implementation under test.

- [ ] **Step 10: Validate every flag/key/value near miss**

For each of the three flags (`--integration`, `--allow-effects`,
`--cleanup-approved`) generate prefix, suffix, wrong-case and every historical
alias case separately, plus missing/duplicate/reordered/extra flag matrices.
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

- [ ] **Step 11: Typecheck the exact observer source executably**

`REVIEWED_SECURITY_AGENT_OBSERVER_SOURCE` is the sole observer source constant,
and `REVIEWED_SECURITY_AGENT_OBSERVER_SHA256` is computed from its exact UTF-8
bytes in the test module. The gate creates a private ignored temporary file,
writes exactly those bytes with no interpolation, verifies the recorded hash,
executes the exact command and requires exit zero:

~~~bash
SDD=.superpowers/sdd/2026-09-03-s3-owned-process-supervision
umask 077
OBSERVER_DIR=$(mktemp -d "$SDD/security-agent-observer.XXXXXX")
OBSERVER_TMP="$OBSERVER_DIR/observer.swift"
trap 'rm -f -- "$OBSERVER_TMP"; rmdir -- "$OBSERVER_DIR"' EXIT
PYTHONPATH="$PWD" "$PYTHON311" -c 'import sys; from pathlib import Path; from tests.test_disk_image_keychain_helper import write_reviewed_observer_source_exclusive; write_reviewed_observer_source_exclusive(Path(sys.argv[1]))' "$OBSERVER_TMP"
OBSERVER_SHA256=$(shasum -a 256 "$OBSERVER_TMP" | awk '{print $1}')
EXPECTED_OBSERVER_SHA256=$(PYTHONPATH="$PWD" "$PYTHON311" -c 'from tests.test_disk_image_keychain_helper import REVIEWED_SECURITY_AGENT_OBSERVER_SHA256; print(REVIEWED_SECURITY_AGENT_OBSERVER_SHA256)')
test "$OBSERVER_SHA256" = "$EXPECTED_OBSERVER_SHA256"
xcrun swiftc -typecheck -framework CoreGraphics "$OBSERVER_TMP"
rm -f -- "$OBSERVER_TMP"
rmdir -- "$OBSERVER_DIR"
trap - EXIT
~~~

The test records path class, source hash, exact argv, exit zero and successful
safe deletion. It does not launch the observer.

- [ ] **Step 12: GREEN and mutant sensitivity**

Run every owned normative/task-local method separately. Run the complete Task
4 set under Python 3.11. Apply every owned mutant individually after GREEN,
require its exact mapped assertion, restore and rerun.

- [ ] **Step 13: Commit Task 4**

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
- Modify: `tests/test_disk_image_keychain_helper.py`

**Normative ownership:** IDs 40 through 43.

**Task-local ownership:** `S3T5_01` through `S3T5_07`.

- [ ] **Step 1: Write and individually observe RED**

Before adding a route, write tests proving:

- fixture spawn lacks START_SUSPENDED and never receives SIGCONT;
- fixture arms self-expiry before START and has no watchdog/PID receipt;
- active cancellation requires matched `0x12` before narrow `0x13`;
- frame alone without control EOF/helper reap is insufficient;
- control FD does not leak into the fixture;
- the parent deadline exists before Popen, child reports cannot extend it and
  cleanup reserve begins before its hard deadline;
- exact unreaped interpreter/helper cleanup is mandatory.

Run the four normative and seven task-local methods individually to natural RED.

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
--guardian-witness-probe MODE
--guardian-fd DECIMAL_FD
--witness-fd DECIMAL_FD
--control-fd DECIMAL_FD
--nonce LOWERCASE_HEX32
--swift-hard-deadline-ns DECIMAL_NS
~~~

MODE is exactly `deadline` or `cancel`. Reject missing, duplicate, reordered,
wrong-case, prefix/suffix or extra operands before any spawn/write. The testing
FD inventory adds only the named guardian/witness FDs to the production set.
The fixture inherits guardian/witness only, never helper control.

- [ ] **Step 3: Implement the immediate self-expiring fixture**

Spawn the fixture into its own session with
`POSIX_SPAWN_CLOEXEC_DEFAULT | POSIX_SPAWN_SETSID`; do not use
`POSIX_SPAWN_START_SUSPENDED`. It immediately installs absolute self-expiry at
start plus 0.90 seconds before writing `START:<nonce>`, creates no descendant,
writes bounded paced data, observes guardian EOF, closes witness on exit and
exposes no PID/PGID/watchdog receipt.

After spawn, the testing adapter observes complete running identity and mints a
`RunningSessionAnchor`. From that point it reuses the production
running/exited/reap/original-group-absence/native-descriptor reducers. It never
calls resume/SIGCONT. Structural reachability forbids spawn/fork/exec/system,
Foundation Process/NSTask and dynamic loading from the child entry point.

- [ ] **Step 4: Create the parent deadline before Popen**

The outer Python R43 parent creates `parent_outer_hard_ns` before starting each
fresh interpreter and passes its exact ASCII decimal value only in the
test-only environment key `CORTEX_S3_PARENT_HARD_DEADLINE_NS`:

~~~python
parent_started_ns = time.monotonic_ns()
parent_outer_hard_ns = checked_add_u64(parent_started_ns, 1_200_000_000)
fresh_env["CORTEX_S3_PARENT_HARD_DEADLINE_NS"] = str(parent_outer_hard_ns)
fresh = subprocess.Popen(fresh_argv, env=fresh_env, start_new_session=True)
~~~

The child validates the value before its first report and must report the
identical `parent_outer_hard_ns`. The parent retains its own value, rejects a
missing/malformed/different/later report and permits the child only to shorten
its phase deadline. The same original parent deadline bounds interpreter
import, first structured report, probe work, exact cleanup and one nonce scan;
the production helper parser never accepts this test-only environment key.

Use exact phase offsets:

~~~text
work_cutoff = start + 0.50 seconds
supervisor_hard = start + 0.65 seconds
fixture_self_expiry = start + 0.90 seconds
cleanup_reserve_start = start + 1.00 seconds
parent_outer_hard = start + 1.20 seconds
~~~

On silent/malformed/delayed START, far-future report or timeout, TERM/KILL/reap
only the exact still-unreaped direct interpreter registered from that `Popen`
under the same deadline; its nested helper cleanup remains separately exact and
bounded by the unchanged parent deadline. Cover EINTR/ECHILD/wrong PID/status.
At `cleanup_reserve_start`, start no new probe work, child spawn, report
acceptance or nonce scan. Reserve the final 0.20 seconds only for exact
close/TERM/KILL/reap and one bounded `/bin/ps -axo command=` scan; filter the
nonce in memory and store no command line. Exhausting that reserve is a
failure, never permission to extend `parent_outer_hard`.

- [ ] **Step 5: Assert both probe contracts**

Deadline mode requires matching START and witness EOF between 0.50 and 0.65
seconds, followed by valid control EOF and exact helper reap. Cancellation mode
requires `0x11`, one `0x01`, the active child's matching `0x12`, witness EOF,
then narrow `0x13`, control EOF and exact helper reap before the parent
deadline. `0x12` must precede `0x13`. ACK and EOF may be observed in either
poll order, but neither is optional. The exact cleanup reserve must begin at
1.00 seconds and finish by 1.20 seconds.

Run the two probe test IDs, including R40, once in their normal class. The
40-run flake method then launches deadline and cancellation in twenty fresh
interpreters each and requires 40 of 40 complete receipts, matching nonce and
no survivor.

The real oracle does not claim to see the fixture child's internal waitpid and
does not test suspended production bootstrap. Scripted Task 2 matrices retain
those claims.

- [ ] **Step 6: Install dynamic cross-version inventory**

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

- [ ] **Step 7: Run final executable/source/security gates**

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
process success booleans = 0
safety_only/disposition_active/public record_mount = 0
readDataToEndOfFile = 0
generic caller mappings/argv/live paths/devices = 0
unregistered capability/baseline/context/receipt/grant/proof factories = 0
raw SecurityAgentSnapshot/MountReceipt/PreTerminalProof begin_disposition operands = 0
terminal lineage close without DispositionReceipt = 0
negative TERM/KILL sites outside typed signal adapters = 0
negative signal-zero sites outside post-reap adapters = 0
killpg sites = 0
production testing symbols = 0
default live-class selections = 0
hard-coded nested python3.11 relaunches = 0
Popen poll/wait/communicate before private exact waitpid = 0
Path.rename or absolute quarantine fallback = 0
control included in NativeSettlementProof = 0
~~~

The AST also proves production helper Popen uses `close_fds=True`, exact
`pass_fds=(control_fd,)`, `start_new_session=True`; preparation/live methods
have no caller paths; the executor lock covers latch through first write; and
all waits/actions use an immutable absolute deadline.

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

- [ ] **Step 8: GREEN and mutate every Task 5 boundary**

Run each owned normative and task-local method individually, both probe methods
once normally, then the fresh 40-run gate. Enable each mapped mutant alone
after GREEN, require only its mapped method to fail, restore and rerun.

- [ ] **Step 9: Commit Task 5**

~~~bash
git add native/macos/disk_image_keychain.swift \
  tests/test_disk_image_keychain_helper.py
git diff --cached --name-only
git commit -m "test(storage): add contained guardian witness"
~~~

Record Task 5 evidence and obtain both fresh read-only reviews.

- [ ] **Step 10: Freeze exact S3 state**

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
~~~

Record all four values before any later document edit.

- [ ] **Step 11: Perform three fresh blind final reviews**

Each reviewer receives only exact spec/plan/implementation bytes and hashes,
declared requirements, necessary source context, non-review execution receipts
and the exact `IMPLEMENTATION_BASE..S3_FINAL` diff. Exclude previous findings,
consolidated findings, review receipts, verdicts, reviewer identities and
reviewer conclusions. The package manifest must assert those exclusions before
delivery. Require independently `P0=0`, `P1=0`, `P2=0`, `Verdict=PASS`. Any
finding freezes S3.

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
    "R12": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_detach_cutoff_equality_and_next_nanosecond",
    "R13": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_absence_cutoff_equality_and_next_nanosecond",
    "R14": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_normal_failure_cannot_reset_compensation_deadlines",
    "R15": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorityTests.test_terminal_preobservation_blocks_every_ordinary_method",
    "R16": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorityTests.test_terminal_during_compile_or_info_cancels_without_continuation",
    "R17": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorityTests.test_caller_operands_cannot_construct_live_work",
    "R18": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_replayed_exact_detach_permit_spawns_nothing",
    "R19": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_mount_receipt_issues_only_one_detach_permit",
    "R20": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_absence_permit_requires_exact_settled_detach",
    "R21": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_every_terminal_lineage_mints_exact_disposition_then_close",
    "R22": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_unknown_mapping_preserves_without_followup_effect",
    "R23": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_terminal_states_never_inspect_or_delete_keychain",
    "R24": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_securityagent_verdict_precedes_observer_and_cleanup_errors",
    "R25": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_nonzero_create_mount_evidence_and_wrong_values_are_registered_before_terminal",
    "R26": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_related_partial_and_foreign_uid_bridge_latch_uncertainty",
    "R27": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_partial_bridge_never_authorizes_grandchild_signal",
    "R28": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_zero_record_live_reread_remains_partial",
    "R29": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_zero_record_esrch_reread_is_vanished",
    "R30": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_late_child_is_never_adopted_or_signalled",
    "R31": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_reused_parent_birth_is_never_adopted_or_signalled",
    "R32": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessModelTests.test_tracked_uid_sid_or_group_change_expires_authority",
    "R33": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_term_to_kill_exited_anchor_revalidation_matrix",
    "R34": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_kill_attempt_forbids_later_group_signal",
    "R35": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftSupervisorTests.test_suspended_anchor_strong_identity_and_validate_abort_race",
    "R36": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_observer_process_and_independent_close_failure_matrix",
    "R37": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_valid_output_without_native_settlement_has_no_authority",
    "R38": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_clock_jump_matrix_stops_actions_at_original_deadline",
    "R39": "tests.test_disk_image_keychain_helper.DiskImageKeychainSecretTests.test_application_owned_secret_lifetime_and_erasure_matrix",
    "R40": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_active_cancel_requires_0x12_then_0x13_eof_and_exact_helper_reap",
    "R41": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_production_testing_routes_and_descriptor_inventory",
    "R42": "tests.test_disk_image_keychain_helper.DiskImageKeychainManifestTests.test_dynamic_python311_python314_inventory_and_order_match",
    "R43": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_deadline_probes_pass_twenty_fresh_runs_each",
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
    "R16": "continue_after_terminal_cancel",
    "R17": "accept_caller_operation",
    "R18": "accept_replayed_detach_permit",
    "R19": "issue_second_detach_permit",
    "R20": "issue_absence_before_settled_detach",
    "R21": "close_without_terminal_disposition_receipt",
    "R22": "query_unknown_mapping",
    "R23": "inspect_keychain_after_terminal",
    "R24": "prefer_cleanup_error_verdict",
    "R25": "discard_nonzero_mount_evidence",
    "R26": "ignore_related_partial",
    "R27": "bridge_partial_to_grandchild",
    "R28": "treat_live_reread_as_vanished",
    "R29": "reject_esrch_vanished",
    "R30": "adopt_late_child",
    "R31": "accept_reused_parent_birth",
    "R32": "signal_after_sid_change",
    "R33": "kill_without_exited_revalidation",
    "R34": "allow_term_after_kill",
    "R35": "allow_validate_after_abort",
    "R36": "stop_closing_after_first_failure",
    "R37": "mint_permit_without_native_proof",
    "R38": "act_after_original_deadline",
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
    "S3T2_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftStructureTests.test_anchor_tokens_reject_foreign_registry_identity",
    "S3T2_02": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftStructureTests.test_supervisor_and_issuance_registries_are_private_final_classes",
    "S3T2_03": "tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_native_settlement_excludes_control_descriptor",
    "S3T2_04": "tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_total_dfa_rejects_duplicate_terminal_frame",
    "S3T2_05": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftDeadlineTests.test_pre_request_deadline_rejects_more_than_seventy_seconds",
    "S3T2_06": "tests.test_disk_image_keychain_helper.DiskImageKeychainSecretTests.test_mutable_keychain_staging_is_erased",
    "S3T2_07": "tests.test_disk_image_keychain_helper.DiskImageKeychainSecretTests.test_wire_is_erased_before_settlement_frame",
    "S3T2_08": "tests.test_disk_image_keychain_helper.DiskImageKeychainControlTests.test_normal_exit_kind_keeps_no_child_and_protocol_failure_distinct",
    "S3T3_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_command_permit_rejects_foreign_supervisor_registry",
    "S3T3_02": "tests.test_disk_image_keychain_helper.DiskImageKeychainSwiftProvenanceTests.test_absence_query_rejects_wrong_command_context",
    "S3T4_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainPreparationTests.test_preparation_is_one_shot_and_accepts_no_caller_paths",
    "S3T4_02": "tests.test_disk_image_keychain_helper.DiskImageKeychainReceiptTests.test_terminal_lineage_transfer_refuses_copied_active_receipts",
    "S3T4_03": "tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_terminal_interleavings_cover_spawn_registration_and_first_write",
    "S3T4_04": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_waitid_waitpid_and_popen_lifecycle_match_after_exact_reap",
    "S3T4_05": "tests.test_disk_image_keychain_helper.DiskImageKeychainRequestTests.test_all_ten_values_come_from_registered_context",
    "S3T4_06": "tests.test_disk_image_keychain_helper.DiskImageKeychainQuarantineTests.test_quarantine_uses_only_descriptor_relative_rename",
    "S3T4_07": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_integration_flag_aliases_are_rejected_without_normalization",
    "S3T4_08": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_allow_effects_flag_aliases_are_rejected_without_normalization",
    "S3T4_09": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_cleanup_approved_flag_aliases_are_rejected_without_normalization",
    "S3T4_10": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_authorization_key_aliases_are_rejected",
    "S3T4_11": "tests.test_disk_image_keychain_helper.DiskImageKeychainAuthorizationTests.test_authorization_value_near_misses_are_rejected_without_normalization",
    "S3T4_12": "tests.test_disk_image_keychain_helper.DiskImageKeychainProcessParityTests.test_python_adapter_matches_task1_lineage_reference_for_r26_to_r32",
    "S3T4_13": "tests.test_disk_image_keychain_helper.DiskImageKeychainExecutorTests.test_post_latch_keychain_result_cannot_authorize_success",
    "S3T4_14": "tests.test_disk_image_keychain_helper.DiskImageKeychainObserverTests.test_exact_reviewed_observer_source_typechecks_and_is_deleted",
    "S3T5_01": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fixture_is_running_immediately_and_self_expires",
    "S3T5_02": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_frame_without_control_eof_is_unclear",
    "S3T5_03": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_fixture_does_not_inherit_helper_control_fd",
    "S3T5_04": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_deadline_exists_before_fresh_interpreter_popen",
    "S3T5_05": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_child_report_cannot_extend_parent_deadline",
    "S3T5_06": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_cleanup_reserve_precedes_hard_deadline",
    "S3T5_07": "tests.test_disk_image_keychain_helper.DiskImageKeychainContainedProcessProbeTests.test_parent_reaps_exact_unreaped_interpreter_on_every_failure",
}

TASK_LOCAL_MUTANTS = {
    "S3T1_01": "stamp_transition_index_inside_reducer",
    "S3T1_02": "omit_effect_disposition_action",
    "S3T1_03": "suppress_valid_signal_action",
    "S3T1_04": "reject_valid_absence_to_quarantine_transition",
    "S3T1_05": "select_default_before_legacy_gate",
    "S3T2_01": "accept_foreign_anchor_registry",
    "S3T2_02": "expose_nonfinal_supervisor",
    "S3T2_03": "include_control_in_native_proof",
    "S3T2_04": "accept_duplicate_terminal_frame",
    "S3T2_05": "accept_deadline_over_seventy_seconds",
    "S3T2_06": "retain_mutable_keychain_staging",
    "S3T2_07": "emit_settlement_before_wire_erasure",
    "S3T2_08": "conflate_normal_exit_kinds",
    "S3T3_01": "accept_foreign_command_registry",
    "S3T3_02": "accept_wrong_absence_context",
    "S3T4_01": "accept_caller_compile_path",
    "S3T4_02": "accept_copied_mount_receipt",
    "S3T4_03": "release_executor_before_handle_registration",
    "S3T4_04": "call_popen_poll_before_waitpid",
    "S3T4_05": "accept_caller_request_path",
    "S3T4_06": "use_absolute_quarantine_rename",
    "S3T4_07": "accept_integration_flag_alias",
    "S3T4_08": "accept_allow_effects_flag_alias",
    "S3T4_09": "accept_cleanup_approved_flag_alias",
    "S3T4_10": "accept_authorization_key_alias",
    "S3T4_11": "normalize_authorization_value",
    "S3T4_12": "continue_python_adapter_after_lineage_uncertainty",
    "S3T4_13": "accept_post_latch_keychain_success",
    "S3T4_14": "accept_untyped_observer_source",
    "S3T5_01": "suspend_fixture_spawn",
    "S3T5_02": "accept_frame_without_control_eof",
    "S3T5_03": "inherit_control_into_fixture",
    "S3T5_04": "create_parent_deadline_after_popen",
    "S3T5_05": "allow_child_report_deadline_extension",
    "S3T5_06": "start_cleanup_at_parent_hard_deadline",
    "S3T5_07": "skip_exact_interpreter_reap",
}
~~~

## Task ownership

| Task | Normative IDs | Boundary |
| --- | --- | --- |
| 1 | 26-32, 44 | Independent models and exhaustive legacy-route removal before the default suite. |
| 2 | 06-10, 33-35, 39 | Strong-identity Swift suspended/running/exited authority, DFA, native proof, deadline and app-owned erasure. |
| 3 | 01-05, 11-14, 37 | Swift command provenance, compensation and immutable phase windows. |
| 4 | 15-25, 36, 38, 45 | Python preparation/capability/receipt/process parity, total disposition, continuation, request, quarantine and authorization. |
| 5 | 40-43 | Non-suspended fixture, route/FD boundary, inventory and parent-deadline probes with cleanup reserve. |

## Execution-contract traceability

| Contract | Specification contract | Implementing plan steps | Exact oracle(s) |
| --- | --- | --- | --- |
| Strong Swift registry identity and atomic suspended bootstrap | `Private final owner and issuance registries`; `Suspended production bootstrap` | Task 2 Steps 1-3 | R35; S3T2_01; S3T2_02 |
| Non-suspended guardian/witness fixture | `Non-suspended fixture bootstrap`; `Guardian/witness contract` | Task 5 Steps 1-5 | R40; R43; S3T5_01 |
| Native settlement excludes control and Python demands complete exchange | `Drain, settlement and control exclusion` | Task 2 Steps 1, 5-6; Task 4 Step 9; Task 5 Step 5 | R36; R37; R40; S3T2_03; S3T5_02 |
| Total DFA and distinct harmless versus abnormal exits | `Total control DFA` | Task 2 Steps 1 and 5-8 | S3T2_04; S3T2_08; R40 |
| Immutable live/continuation deadlines and reserved cleanup | `Deadline validation before request read`; `Post-terminal continuation deadlines` | Task 2 Step 4; Task 3 Step 4; Task 4 Step 7; Task 5 Steps 4-5 | R11-R14; R38; R43; S3T5_04-S3T5_06 |
| Registry-minted preparation, observer, capability and no free operands | `Registry-minted roots only`; `One-shot preparation and fixed artifacts` | Task 4 Steps 1-5 | R15-R17; S3T4_01; S3T4_05 |
| Serialized latch linearization and late Keychain result | `Serialized executor and no free operands` | Task 4 Steps 1 and 4 | R15; R16; S3T4_03; S3T4_13 |
| Ten-key context derivation and quarantine provenance | `Exact ten-key request value matrix`; `Descriptor-relative quarantine` | Task 4 Steps 3, 6 and 8 | R17; R21; S3T4_05; S3T4_06 |
| Terminal snapshot, atomic lineage transfer and total disposition | `Receipt algebra and terminal disposition` | Task 4 Steps 1, 4, 5 and 7 | R18-R25; S3T4_02 |
| Controlled receipt forks, preservation and continuation refusal | `Receipt algebra and terminal disposition`; `Post-terminal continuation deadlines` | Task 4 Step 7 | R18-R25; R37; exact R18/R19/R20/R21/R25 matrix in Step 7 |
| Python wait/reap parity and lineage-model parity | `Python process parity` | Task 4 Steps 1 and 9 | R06-R10; R26-R36; R38; S3T4_04; S3T4_12 |
| Independent exhaustive model action equality and complete effect alphabet | `Independent model architecture` | Task 1 Steps 1-3 | R26-R32; S3T1_01-S3T1_04 |
| Legacy removal and closed testing routes | `Closed routes and real fixture` | Task 1 Step 4; Task 5 Step 2 | R44; R41; S3T1_05; S3T5_03 |
| Exact authorization matrix | `Registry-minted roots only` | Task 4 Steps 1 and 10 | R45; S3T4_07-S3T4_11 |
| Exact observer-source extraction/typecheck/deletion | `One-shot preparation and fixed artifacts` | Task 4 Steps 1, 3 and 11 | S3T4_14; Task 4 Step 11 command and hash assertions |
| App-owned secret boundary | `Application-controlled secret lifetime` | Task 2 Steps 1 and 7 | R39; S3T2_06; S3T2_07 |
| Mutant sensitivity, candidate bytes and blind package isolation | `Test inventory, TDD and release evidence`; `Review, checkpoint and S4 separation` | Revision-4 documentation completion gate; Blind documentation gate; Task 5 Steps 10-11 | `MUTANT_<KEY>_<MUTANT>` labels; static map checker; exact package manifest; `test "$ACTUAL_STATUS" = " M primer.md"` |

## Final self-review checklist

- [ ] The two production/fixture bootstraps are distinct; only production is
  suspended and only scripted tests claim its bootstrap.
- [ ] Swift owner/registries are private final classes; tokens carry only
  strongly retained private registry identity/generation, and validation uses
  object identity rather than a reusable `ObjectIdentifier` value.
- [ ] Suspended validation versus abort is atomic and at most one path issues
  an action.
- [ ] Native settlement excludes control; Python requires final frame, control
  EOF and exact helper reap; absent/abnormal EOF, wrong exit or missing frame
  is `UNCLEAR`.
- [ ] Control DFA is total across five exact states, all input/exit cases and
  distinct `strictRejected`, `acceptedNoChild` and `protocolAbnormal` exits.
- [ ] Pre-request deadline checks cap remaining time at 70 seconds with checked
  arithmetic and no replacement deadline.
- [ ] Terminal detach/absence uses only sealed fresh continuation helpers with
  fixed 14/12-second hard deadlines inside the immutable outer envelope.
- [ ] Python every authority root is registry-minted with object identity and
  copy/cross-boundary/replay rejection.
- [ ] A fixed observer snapshot is consumed into one terminal receipt, and the
  latch atomically transfers active mount/preterminal lineage without accepting
  an old-epoch token.
- [ ] Preparation fixes helper/observer source and target, has its own finite
  deadline, and precedes the 115-second live clock.
- [ ] One executor lock covers latch check through handle registration and
  first-write authorization.
- [ ] No live method accepts caller path/device/operation/argv.
- [ ] Exact ten-key values preserve current global fields and per-operation
  UUID/cleanup rules.
- [ ] Mount returns its receipt directly; no public `record_mount`.
- [ ] Receipt producer, consultation and named derivative-slot rules are
  explicit; every terminal lineage reaches `DispositionReceipt` and
  `close(DispositionReceipt)` exactly once through quarantine or preservation.
- [ ] Quarantine is descriptor-relative, no-follow, revalidated and closes all
  FDs independently using sealed parent/image device, inode, mode and UID
  provenance.
- [ ] Python and Swift waitid/waitpid branches have full parity and no early
  Popen terminal helper, replayed waitpid or post-reap Popen state authority.
- [ ] Models compare complete externally indexed actions and final state to
  independent machines; exhaustive counts and positive long traces are exact.
- [ ] Each task observed natural RED, GREEN and post-GREEN single-branch mutant
  failure with its exact `MUTANT_<KEY>_<MUTANT>` label for normative and
  task-local maps.
- [ ] Legacy removal is Task 1; authorization matrix is Task 4; route/FD probe
  is Task 5.
- [ ] Parent probe deadline is created before Popen and bounds import/report/
  cleanup without child extension; its 0.20-second cleanup reserve begins
  before the hard deadline.
- [ ] Each of three flags and authorization key/value has prefix/suffix/case/
  old-alias coverage with distinct mutants.
- [ ] Observer typecheck extracts exact reviewed bytes, hashes, runs
  `swiftc -typecheck -framework CoreGraphics`, exits zero and safely deletes.
- [ ] App-owned entropy/Master/Wire/Keychain staging are zeroed; opaque external
  copies are not claimed.
- [ ] Dynamic complete suites pass under Python 3.11 and 3.14 with byte-identical
  ordered starts, zero skip and no live class.
- [ ] Immediately before `S3_FINAL`, exact status is only ` M primer.md`, staged
  output is empty and spec/plan/primer hashes are freshly recorded.
- [ ] Blind packages exclude prior findings, review receipts, verdicts,
  reviewer identities and conclusions, as proven by the package manifest.
- [ ] The revision-4 documentation completion gate ran no code/test/build/helper
  or live effect, committed exactly the two docs and left `primer.md` unchanged
  and unstaged.
- [ ] S4 rebaseline is a separate later documentation commit.
