# Cortex Bridge v0.5.4 Completion Program

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the approved v0.5.4 architecture to one honestly verified macOS candidate by integrating five bounded plans in a strict dependency order, including the explicit separation between vault-backed general missions and narrow local-alias actions, with exact ownership, reviews, and stop gates.

**Architecture:** Storage establishes the only trusted runtime/workspace authority and constructs vault-only `WorkspaceHandle` values. Durable effects consume that handle, implement the fixed attested local-alias worker, and remain the sole mutation/STOP authority. UI/browser reliability consumes storage/effect truth and displays local actions without becoming an authority. The hybrid intent phase then separates `GeneralMission` from `LocalAliasAction`: only the former reaches ChatGPT, writer leases, mission outboxes and `ToolExecutor`; only the latter may perform one approved exact-leaf `mkdirat` through the fixed worker. Live cutover/QA executes only after the implementation graph is green. Each phase has one writer per file, an atomic commit set, and an independent read-only checkpoint.

**Tech Stack:** Python 3.11/3.14, FastAPI/SQLite, Swift/Security.framework, macOS APFS/DiskImages, Bash, Chrome MV3, React/TypeScript/Vitest/Playwright, Git/Gitleaks.

**Spec:** `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md` at SHA-256 `2034280b1b4943c2b602eba888b58742e2d77b428bdc63dc5f93a4b59c72cb5f`; `docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md` at SHA-256 `472ae88687f6df00be1aac7bb33af536b0456fdc7fd04b7bb5f95e637e4b38f5`; and the precedence-setting `docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md` at SHA-256 `38dff2d114ddf3a8f2262f3ac2b37dcbec9fd33951934c5d5c03a9a0c4acc08b`.

**Review-status provenance:** The storage spec's header retains its creation-time `written specification pending review` text. For this program, approval attaches only to the exact SHA-256 above through the reviewed planning-handoff commit; any byte change resets that approval. This documentary approval never authorizes a live Keychain, disk, runtime, browser or ChatGPT effect.

## Global Constraints

- Execute phases in order. No downstream writer starts before the preceding phase has a committed implementation, passing focused/full gates, and a zero-P0/P1/P2 review.
- Use one implementation writer per file at a time. Reviewers are read-only and receive the exact commit hash, not another reviewer's verdict.
- Treat the subordinate plan as authoritative for its code, tests, RED/GREEN commands, and atomic commits. This program defines sequencing and gates; it does not dilute or replace those steps.
- Never alter a spec, threshold, test matrix, weight, evidence rule, or verdict merely to make a phase pass.
- A failure stops the program. Reproduce it, add/fix the regression at its owning phase, rerun that phase, obtain a fresh review, then resume; do not skip forward.
- Design approval does not authorize live vault, Keychain, filesystem, process, Chrome, ChatGPT, push, merge, tag, release, cleanup, or deletion effects.
- Keep the legacy sparsebundle detached and unmodified. Keep all public documentation English and product UI French.
- Do not use the OpenAI API or a separate browser profile as a substitute for the real signed-in Chrome-extension path.
- Never convert Desktop, Documents, or Downloads into a `WorkspaceHandle` or general-mission grant. Never disable or substitute required storage to admit a local action. Startup, routing, and finalization must not open a protected alias; only the separately confirmed access check or the approved local write may do so through the bounded worker.
- No push, merge, tag, release, external message, duplicate deletion, or Windows support claim belongs to this implementation program.

## Dependency and ownership map

| Phase | Plan | Creates the authority used downstream | Shared-file rule |
| --- | --- | --- | --- |
| 1 | `2026-09-02-v054-storage-runtime-foundation.md` | `StorageContract`, `StorageBinding`, vault-only `WorkspaceHandle`, read-only runtime readiness, storage transaction/CLI, managed start | Sole writer of storage/helper/installer/lifecycle files until checkpoint S |
| 2 | `2026-09-02-v054-durable-effects-and-executor.md` | schema v3 `EffectGate`, exact approvals, durable STOP, effect-bound `ToolExecutor`/browser permits, fixed attested `LocalAliasWorkerRunner` | Begins only after S; sole writer of executor/orchestration/direct-effect/worker-install files until checkpoint E |
| 3 | `2026-09-02-v054-runtime-ui-and-browser-reliability.md` | authoritative runtime projection, local-action presentation, switch deadlines, tab provenance, categories, diagnostic export | Begins only after E; owns shared `console/chat.py`, extension and frontend files until checkpoint U |
| 4 | `2026-09-02-v054-hybrid-intent-router.md` | deterministic/local-model routing, clarification, `GeneralMission`/`LocalAliasAction` split, alias catalog/access/finalization services | Begins only after U; consumes rather than redefines storage/effect/UI contracts until checkpoint I |
| 5 | `2026-09-02-v054-live-cutover-and-release-qa.md` | live storage/runtime/evidence verdict, including zero-chat `LOCAL_ALIAS` acceptance, for v0.5.4 | Begins only after I; product fixes return to the owning phase rather than being patched in QA |

## Frozen subordinate plan hashes

| Phase | Plan | SHA-256 |
| --- | --- | --- |
| S | `docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md` | `97b20fec13e7030dbb06bf39aa1d2ffdeb353ca33527e4155d3e9defd3994275` |
| E | `docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md` | `7974f73e672077956d5e03a6416711791524ab520a8549b729ec4a2feb7c102c` |
| U | `docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md` | `25d04484e4dcf337728ce96f0af642d3894be71dea0ef9a616f2552cd9121245` |
| I | `docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md` | `73987192c4d5dbe3d0fcabf3637bd46f60b0ef50f15c8184b93452b1e7e66fc8` |
| L | `docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md` | `b8dda2316401eaee1b6408aa6cc68136b783524d6b99e5b30f64db7c30e83277` |

## Planning handoff gate

Before any implementation session begins, the planning owner must create one local documentation commit containing exactly the six plans listed below. The three specifications are already tracked at their frozen hashes and are not amended by this commit.

```bash
git add \
  docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md \
  docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md \
  docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md \
  docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md \
  docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md \
  docs/superpowers/plans/2026-09-02-v054-completion-program.md
git diff --cached --check
git diff --cached --name-only
EXPECTED_STAGED="$(printf '%s\n' \
  docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md \
  docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md \
  docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md \
  docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md \
  docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md \
  docs/superpowers/plans/2026-09-02-v054-completion-program.md | LC_ALL=C sort)"
ACTUAL_STAGED="$(git diff --cached --name-only | LC_ALL=C sort)"
test "$ACTUAL_STAGED" = "$EXPECTED_STAGED"
git commit -m "docs: plan v0.5.4 completion program"
```

The staged-name output must contain those six paths exactly and no source, runtime, evidence, secret, or `primer.md` file. The planning owner then recomputes all three spec hashes, all five subordinate plan hashes, and the master-plan hash from the committed tree. A mismatch stops handoff and requires a new reviewed documentation commit. The implementation owner never creates or repairs this baseline: if the six plans are untracked, modified, absent from `HEAD`, or differ from the frozen table, Task 1 returns `FAIL` before Phase S.

---

### Task 1: Establish the immutable planning baseline

**Files:**
- Inspect: `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md`
- Inspect: `docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md`
- Inspect: `docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-completion-program.md`
- Create during execution: `docs/superpowers/plans/2026-09-02-v054-completion-ledger.json`
- Modify during execution only: `primer.md`

**Interfaces:**
- Consumes: the already completed planning handoff gate and its local documentation commit.
- Produces: base commit, spec hashes, plan hashes, clean/known Git status, equipped Python paths, and phase ledger.

- [ ] **Step 1: Verify frozen bytes and branch**

```bash
PLANNING_COMMIT="$(git rev-parse HEAD)"
git rev-parse --abbrev-ref HEAD
git status --short
shasum -a 256 docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md
shasum -a 256 docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md
shasum -a 256 docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md
shasum -a 256 \
  docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md \
  docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md \
  docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md \
  docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md \
  docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md \
  docs/superpowers/plans/2026-09-02-v054-completion-program.md
git ls-files --error-unmatch \
  docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md \
  docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md \
  docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md \
  docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md \
  docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md \
  docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md \
  docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md \
  docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md \
  docs/superpowers/plans/2026-09-02-v054-completion-program.md
git diff --exit-code "$PLANNING_COMMIT" -- \
  docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md \
  docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md \
  docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md \
  docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md \
  docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md \
  docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md \
  docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md \
  docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md \
  docs/superpowers/plans/2026-09-02-v054-completion-program.md
```

Expected: branch `codex/v054-storage-consolidation`; `PLANNING_COMMIT` is the planning handoff commit or a later descendant that leaves all nine documents byte-identical; exact spec hashes from the header; all nine documents tracked by `PLANNING_COMMIT`; zero document diff. Unrelated pre-existing changes may be recorded, but none may overlap these nine files. If the handoff commit was not created, stop with `FAIL`; the implementation session does not stage or commit the plans itself.

- [ ] **Step 2: Equip runtimes without changing dependency locks**

Resolve the repository's supported Python 3.11 and 3.14 interpreters and existing locked frontend install. Record executable versions. Do not upgrade Remotion, npm, Python packages, or any unrelated dependency during this program.

- [ ] **Step 3: Create the phase ledger**

The root integrator alone owns `docs/superpowers/plans/2026-09-02-v054-completion-ledger.json`. Create schema version 1 with `planning_commit`, `master_plan_sha256`, the three exact spec hashes, the five subordinate plan hashes frozen in this program, and phases `S`, `E`, `U`, `I`, and `L`. Each phase stores `{base_commit, implementation_commit, focused_tests, full_gate, review_id, review_verdict, blockers}`; incomplete fields are `null`. Phase E additionally freezes `effect_schema_version=3`, the exact effect owner/category registries, and the installed local-worker identity fields; Phase I freezes the exact execution-class and local-operation registries. Valid verdicts are `PASS`, `FAIL`, or `UNCLEAR`; no average score is allowed. Validate JSON, commit it as `chore: initialize v0.5.4 completion ledger`, and let only the root integrator update/commit it after each independent checkpoint review.

---

### Task 2: Execute Phase S — storage and runtime foundation

**Files:**
- Follow exactly: `docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md`

**Interfaces:**
- Produces for Phase E:

```python
StorageContract.open() -> StorageBinding
StorageContract.open_workspace(binding, requested) -> WorkspaceHandle
StorageContract.assert_runtime_ready() -> StorageStatus
WorkspaceHandle.revalidate() -> WorkspaceIdentity
WorkspaceHandle.duplicate_workspace_fd() -> int
```

- [ ] **Step 1: Dispatch one storage implementation owner**

Use this exact handoff:

```text
Implement docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md task by task with TDD. You own only the files named by that plan. Keep WorkspaceHandle vault-only and expose only the read-only StorageContract.assert_runtime_ready() -> StorageStatus gate for local actions; do not add a local-root constructor or open a protected alias. Do not edit durable-effect, UI, intent, live evidence, spec, or primer files. Do not run any production Keychain/vault/cutover action. Preserve unrelated changes. Stop on any failed gate and report the exact command/output. Commit each atomic task exactly as the plan specifies.
```

- [ ] **Step 2: Verify checkpoint S**

Run every focused command in the storage plan, Python 3.11/3.14 coverage required there, the full gate, `git diff --check`, both Gitleaks scans, and inspect the commit range. A skipped native helper test is `FAIL`.

- [ ] **Step 3: Obtain independent storage review**

Give a read-only reviewer the Phase S base and terminal commits plus all three frozen specs. Require zero P0/P1/P2, including proof that local actions cannot bypass absent/detached/transitioning storage or a missing managed-start lease and that no personal-folder handle exists. Fix findings under the same owner and re-review the new terminal commit.

- [ ] **Step 4: Freeze handoff S**

Record terminal commit and interface signatures in the ledger. Phase E may import them; it may not redesign them silently.

---

### Task 3: Execute Phase E — durable effects and executor

**Files:**
- Follow exactly: `docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md`

**Interfaces:**
- Consumes: Phase S `WorkspaceHandle` and `StorageContract`.
- Produces for Phase U/I:

```python
EffectGate.activate_mission_effect(...) -> EffectActivation
EffectGate.begin_direct_intent(...) -> EffectIntent
EffectGate.activate_direct_intent(effect_id: str, *, blocked_worker_permit: BlockedWorkerActivationPermit | None = None) -> EffectActivation
EffectGate.register_local_alias_approval(*, action_id: str, grant_id: str, catalog_entry_id: str, catalog_revision: int, alias: LocalAlias, operation: Literal["create_directory"], allowed_leaf: str, payload_digest: str, authorization_epoch: int) -> LocalAliasApprovalChallenge
EffectGate.local_alias_approval_receipt(*, action_id: str, epoch: int, arguments_digest: str) -> LocalAliasApprovalReceipt
EffectGate.begin_local_alias_intent(*, action_id: str, epoch: int, operation: Literal["create_directory"], payload_digest: str, grant_id: str) -> EffectIntent
EffectGate.activate_local_alias_intent(effect_id: str, *, approval: LocalAliasApprovalReceipt, blocked_worker_permit: BlockedWorkerActivationPermit) -> EffectActivation
EffectGate.request_stop() -> StopStatus
EffectGate.reset_stop(*, expected_epoch: int) -> StopStatus
ToolExecutor(workspace: WorkspaceHandle, *, effect_gate: EffectGate, test_commands=...)
LocalAliasWorkerRunner(effect_gate: EffectGate, installed_home: Path, storage_contract: StorageContract)
LocalAliasWorkerRunner.assert_pre_activation_ready(*, intent: EffectIntent) -> BlockedWorkerActivationPermit
LocalAliasWorkerRunner.run(*, request: LocalAliasWorkerRequest, activation: EffectActivation, deadline_seconds: Literal[60] = 60) -> LocalAliasWorkerReceipt
```

- [ ] **Step 1: Dispatch one effect implementation owner**

```text
Implement docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md task by task with TDD on top of checkpoint S. Consume WorkspaceHandle exactly; do not reopen absolute workspace paths or alter the storage contract. Migrate effects to schema v3, keep ToolExecutor vault-only, and implement the manifest-owned fixed local-alias worker plus bounded runner exactly as planned; this worker is not a general process capability. You own only files named by the plan. Do not edit UI/intent/live/spec/primer files. Preserve unrelated changes. Stop on a failed gate, fix root cause, and commit each atomic task as specified.
```

- [ ] **Step 2: Verify checkpoint E**

Run all effect/approval/STOP/executor/browser-permit/local-worker focused tests, then the full gate under both required Python versions, extension tests, Gitleaks scans, and diff checks. Prove schema v2→v3 rebuilds both approvals and effects while creating the four local tables in one immediate transaction, preserves recognized mission approvals by exact row count/digest, enforces typed-subject XOR/partial indexes, and rejects cross-subject nonce replay. Also prove exact effect registry equality, legacy mutating POST routes returning 410 with zero effect, worker attestation before spawn, blocked-process ownership before release, strict 60-second termination, full descriptor-chain checks, and no local-handle entry into ToolExecutor.

- [ ] **Step 3: Obtain independent safety review**

Require the reviewer to trace every direct, mission, local-alias, admin, browser, filesystem, process, sensitive-read, attachment, settings, onboarding, STOP and reset path to `EffectGate`. The accepted owner set must be exactly `mission|direct_ui|admin_ui|local_alias_action`; categories must be exactly `filesystem|process|browser|sensitive_read`. Any first byte before durable activation, worker release before durable PID/PGID/start ownership, or local-alias access through a generic executor is P0 and blocks U.

- [ ] **Step 4: Freeze handoff E**

Record terminal commit, schema version 3, exact effect inventory, installed worker hash/device/inode/owner/mode, and exact HTTP/Python contracts. Client-supplied `owner_kind` or effect `category` is forbidden; routes derive both server-side.

---

### Task 4: Execute Phase U — runtime UI and browser reliability

**Files:**
- Follow exactly: `docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md`

**Interfaces:**
- Consumes: Phase S runtime/storage observations and Phase E effect/browser/local-worker permits and receipts.
- Produces: one authoritative UI projection, truthful `Action locale` access/preflight/active/created/uncertain states, cache-first bounded switches, safe tab provenance, useful categories, and observable diagnostic export. It creates no model, executor, storage, alias, approval, or effect authority.

- [ ] **Step 1: Dispatch one sequential UI/browser owner**

```text
Implement docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md task by task with TDD on checkpoints S and E. You are the sole writer of every shared console/chat, extension, and frontend file during this phase. Consume storage/effect/local-worker contracts without redefining them. Render local-action truth in French, including per-alias access verification, possible macOS prompt, no-ChatGPT capability statement, and outcome-unclear warning; do not place an executor or model in the frontend. Do not edit intent/live/spec/primer files. Preserve unrelated changes; stop and report any failed gate; commit atomically as specified.
```

- [ ] **Step 2: Verify checkpoint U**

Run the named backend/extension/frontend unit, runtime, typecheck, lint, fresh build, tagged E2E, and accessibility commands. Require non-zero test selection, deterministic fault trace, no hidden production fault endpoint, no background protected-alias access, and accurate keyboard/live-region behavior for verification-required, active, created, denied, permission-required, STOP, and outcome-unclear states.

- [ ] **Step 3: Obtain independent runtime/UX review**

Review exact bytes for contradictory readiness, false local-action success, any claim that ChatGPT/model/executor performed a local action, stale/superseded conversation state, unsafe user-tab closure/reuse, dead archive control, ambiguous icons/copy, silent diagnostics, privacy leaks, and accessibility regressions.

- [ ] **Step 4: Freeze handoff U**

Record terminal commit, local-action selectors/state mapping, response schemas, timeout constants, and extension provenance fields. Phase I may bind routing state to them but may not add a second truth source.

---

### Task 5: Execute Phase I — hybrid intent router

**Files:**
- Follow exactly: `docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md`

**Interfaces:**
- Consumes: `StorageContract`, vault-only `WorkspaceHandle`, `EffectGate`, `LocalAliasWorkerRunner`, repaired conversation state, two-writer admission, and real Chrome-extension transport.
- Produces: exact chat, vault-backed `GeneralMission`, separate `LocalAliasAction`, ambiguous clarification, per-alias access observation/grant/action persistence, and safe fallback routes from one composer.

- [ ] **Step 1: Dispatch one intent implementation owner**

```text
Implement docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md task by task with TDD on checkpoints S, E, and U. Do not create a parallel approval, workspace, conversation, browser, effect, or worker authority. Keep general missions vault-only. Standard aliases are server-owned local-action targets, never WorkspaceGrants. The local Ollama model is optional and never selects or overrides execution class, alias, leaf, grant, approval, owner kind, category, or policy. You own only the files named by the plan. Preserve unrelated changes, stop on failures, and commit atomically as specified.
```

- [ ] **Step 2: Verify checkpoint I**

Run pure routing, schema-v3 migration, backend, extension, frontend, tagged E2E, privacy, and exact-chat regressions. Prove the obvious Desktop request freezes `execution_class=local_alias_action` through deterministic rules before ChatGPT, uses no model, creates zero mission/writer/outbox/browser/extension artifact, performs no alias open during startup/routing/finalization, and cannot proceed when storage readiness or a current access observation is absent. Prove ambiguity never causes an external send and classifier absence/invalidity falls back safely.

- [ ] **Step 3: Obtain independent architecture/security/UX reviews**

All three review the same terminal commit and all three frozen specs. Require zero P0/P1/P2, then re-run full gates after every fix. A model-only routing claim, an ordinary ChatGPT refusal, a general mission, a WorkspaceGrant, or a browser/extension command for the frozen obvious-local phrase is `FAIL`.

- [ ] **Step 4: Freeze handoff I**

Record terminal commit, exact execution-class/local-alias registries, candidate setting defaults, and the negative-capability inventory. Do not run the live Desktop acceptance here; that belongs to Phase L and needs separate access-check and write action-time approvals.

---

### Task 6: Execute Phase L — live cutover and release QA

**Files:**
- Follow exactly: `docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md`

**Interfaces:**
- Consumes: frozen checkpoints S, E, U, and I.
- Produces: storage/runtime/install evidence, T12-T18, R1-R5, and distinct `LOCAL_ALIAS` verdicts, privacy manifest, reviewed public aggregate evidence, and a stopped candidate.

- [ ] **Step 1: Dispatch a QA recorder owner before live effects**

```text
Implement only the code/test tasks in docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md first. Do not mutate Keychain, disks, production CORTEX_HOME, Chrome, ChatGPT, or a live workspace. Stop after the pre-live gates and report every exact action-time approval still required.
```

- [ ] **Step 2: Verify the code-ready live checkpoint**

Review the evidence recorder/manifest implementation, run full gates and scans, and freeze its commit. Only then proceed through live tasks one authorization boundary at a time.

- [ ] **Step 3: Execute live actions without bundling authority**

For each dry-run plan or external/browser/write/process/sensitive-read effect, show the exact target/content/impact and obtain only its required approval. The local-alias acceptance requires one explicit access-check authorization and a later distinct exact-directory write authorization; Cortex never accepts a macOS TCC prompt for the owner. A prior plan/spec/program approval is not accepted as runtime authority.

- [ ] **Step 4: Return defects to their owning phase**

If live QA reproduces a bug, mark the live gate `FAIL`, stop safely, add a RED test in S/E/U/I according to ownership, implement there, re-run/re-review that checkpoint and every downstream gate, then restart the affected live test with a new synthetic run ID.

- [ ] **Step 5: Verify checkpoint L**

Require every mandatory gate, including `LOCAL_ALIAS`, to be `PASS`, three independent frozen-evidence reviews, complete privacy/secret/full-suite gates, stopped runtime, detached vault, and clean intended Git state. `LOCAL_ALIAS` requires direct proof of one local access effect, one local filesystem effect, one exact inode, and zero ChatGPT/writer/mission/outbox/upload/browser/extension delta. Independent recovery may remain `UNCLEAR` only with synthetic/rebuildable data and must stay visible.

---

### Task 7: Close the candidate without publishing

**Files:**
- Modify: `primer.md`
- Inspect: `docs/verification/v0.5.4.json`
- Inspect: `docs/release-checklist.md`
- Inspect: complete candidate diff and private evidence manifest hash

**Interfaces:**
- Produces: an exact candidate commit, open limitations, Git status, and one separately gated publication decision.

- [ ] **Step 1: Recompose final proof from fresh sources**

Do not reuse narrative summaries. Re-run version, full tests, evidence verification, privacy, links, history/working-tree Gitleaks, diff check, status, and runtime stopped/detached probes.

- [ ] **Step 2: Update the project primer**

Keep it below 200 lines and record the five terminal commits/verdicts, exact next action, independent-recovery limitation, live evidence hash, and any blocker. Do not include a private path, user/account data, token, secret, or stale count.

- [ ] **Step 3: Obtain final independent candidate review**

Review the exact base-to-candidate diff plus all three frozen specs and the frozen public/private evidence boundary. Require `PASS` with zero P0/P1/P2; otherwise return to the owning phase.

- [ ] **Step 4: Report the boundary**

State candidate commit, tests/reviews, remaining `UNCLEAR` items, private evidence location by redacted label, and Git status. The sole next action is owner review of a separate push/merge/tag/release plan; do not perform it here.
