# Cortex Bridge 0.6 Completion Plan

> Execution: task-by-task in the existing isolated worktree, with test-first fixes and verification checkpoints.

**Goal:** Deliver a genuinely validated 0.6 candidate without publishing incomplete gates as success.

**Architecture:** Retain the existing Chrome web transport and explicit local execution boundaries. Complete native bootstrap validation before loading generation Python; retain one-shot managed startup and storage admission.

**Tech Stack:** Python, Swift/macOS, Chrome extension, React/Next.js.

**Spec:** ../specs/2026-09-09-v06-product.md

## Global constraints

- No substitution of the ChatGPT web flow by an API.
- Two writing conversations maximum; 50 conversations maximum.
- Windows live acceptance remains owner-deferred.
- No personal paths, secrets or account data in public documentation.
- A test fixture is not a live provider or clean-machine acceptance proof.
- Preserve the dirty worktree; no blanket staging, destructive cleanup or silent installation.
- Public release remains gated separately from a development commit.

## 1. Native startup and installation

Files: native/macos/storage_bootstrap.swift; console/installed_storage_runtime.py;
console/managed_runtime.py; console/generation_install.py;
tests/test_installed_storage_runtime.py; tests/test_generation_install.py.

- [x] Reject duplicate JSON keys (including escaped aliases and nested keys) before exec.
- [x] Pin directory/file descriptors while reading, reject symlink ancestors, validate complete app resources before Python import.
- [x] Transfer validated descriptors and the inherited install lock into the installed runtime.
- [x] Compose native startup with managed startup, prove HTTP, READY, graceful CLOSED and failure without false READY in temporary optional-storage installation.
- [x] Deploy and verify the stable native launcher during initial generation installation; reuse its verified identity during generation updates.
- [ ] Complete the full bootstrap migration matrix (missing bootstrap, existing legacy format, changed source/profile, interruption and rollback); only missing-v1 is currently implemented.
- [x] Explicit missing-v1 migration verifies/preserves an existing complete generation and starts the new installed launcher; default install still refuses this layout.
- [ ] Migrate an existing legacy-format or changed-source bootstrap with approved identity-bound rollback; missing-v1 does not replace one.
- [ ] Prove every generation-update path refuses open or unreconciled storage workflows, beyond publication-journal recovery.
- [x] Wire three-lock install/storage/admission context and read-only workflow gate before staging/publication; test open, preexec-closed, unreconciled and unproven-cleanup cases.
- [ ] Wire acceptance of canonical, matching reconciliation proof; CLOSED alone never qualifies. See 2026-09-09-generation-update-gate.md.
- [x] Reject contradictory mount/detach/delete observations and inconsistent reloaded reconciliation records; canonical/private record reader covered by file tests.
- [ ] Connect retained native broker reconciliation, durable ACK/FINALIZED and exact workflow binding before enabling installer acceptance. See 2026-09-09-reconciliation-validation.md.
- [x] Align the stable bootstrap manifest filename and digest domain with normative S3; real installation test independently checks both. See 2026-09-09-bootstrap-format.md.
- [ ] Prove encrypted-volume admission with a disposable authorized volume; preserve existing user storage.
- [ ] Exercise fresh installation, update refusal/recovery, doctor and uninstall in an isolated environment.
- [x] Doctor inspects the selected generation rather than legacy venv/checkout, and rejects partial or tampered installed state; real-install regression covers this path.
- [ ] Complete broker-backed encrypted-storage Doctor admission and generation-aware uninstall (not proven by integrity diagnosis).

For each fix: add a harmful-input fixture to the real executable test, confirm
exit 0 reproduces the missing rejection, implement rejection, confirm exit 78
and no probe side effect. Run:
`PYTHONPATH=.:console .venv/bin/python -m unittest discover -s tests -p test_installed_storage_runtime.py -v`
then the same command with `test_generation_install.py`.

## 2. Profiles, continuity and adapters

Files: orchestration/execution_profiles.py; orchestration/continuity.py;
orchestration/loop.py; orchestration/store.py; executor/effect_recovery.py.

- [ ] Run execution-profile and continuity suites; map each claimed feature to its actual consumer.
- [ ] Reject stale capabilities, unauthorized provider/cost changes and resume with unresolved effects.
- [ ] Run the same startup/task/error/STOP/resume scenarios on each advertised adapter.
- [ ] Inspect produced artifacts; model statements alone do not prove completion.

Run unittest discovery for `test_execution_profiles.py`, `test_continuity.py`,
`test_process_effect_recovery.py`, `test_effect_recovery_dispatch.py`.
For a missing consumer, first add a failing integration test at mission creation
or resume rather than another isolated data-class test.

## 3. User journey and UI

Files: frontend/components/CortexApp.tsx; frontend/components/SettingsPanel.tsx;
frontend/hooks/useConversationController.ts; frontend/e2e;
console/chat.py; console/chrome_extension.py; transport/browser_chrome_extension.py.

- [ ] Execute frontend unit, type and accessibility checks.
- [ ] Use Cortex only to submit one conversation, two conversations, and a refused third draft.
- [ ] Verify 50-item cap and observed pinned/project/recent categorization.
- [ ] Send a file and screenshot; check pending/sent/failed feedback without duplication.
- [ ] Run simple folder, sorting, mini-site and bug-fix missions in disposable workspaces.
- [ ] Inspect resulting files and local HTTP; test STOP while running.

Use existing UI test scripts in frontend/package.json. Live checks require an
observed connected Chrome profile; never replace unavailable provider results
with fixtures in the release ledger.

## 4. Resilience

Files: console/startup_lease.py; console/storage_contract.py;
console/storage_lifecycle.py; transport/chatgpt_web/adapter.py; orchestration/loop.py.

- [ ] Exercise disconnected browser, network loss, expired login and exhausted quota.
- [ ] Exercise interrupted startup, sleep/wake and unavailable storage without modifying the user's volume.
- [ ] Verify ambiguous sends/effects are not blindly replayed.
- [ ] Re-run all relevant regression suites after fixes.

## 5. Documentation and privacy

Files: README.md; INSTALL.md; CHANGELOG.md; ROADMAP.md; llms.txt; docs/.

- [ ] Replace unsupported claims with measured capabilities and named limits.
- [ ] Document agent-assisted installation with approval before dependency/provider changes.
- [ ] Verify official product links; produce illustrated English guide and updated animated architecture.
- [ ] Use synthetic data for publishable captures; inspect rendered images for personal information.
- [ ] Record external human first-use timing as UNCLEAR until actually observed.

## 6. Release

Files: VERSION; pyproject.toml; frontend/package.json; chrome-extension/manifest.json;
docs/verification/; repository metadata.

- [ ] Build a requirement-level PASS/FAIL/UNCLEAR ledger with fresh command results.
- [ ] Run backend, extension, frontend tests/build, security and privacy checks.
- [ ] Review exact diff and preserve unrelated changes; prepare coherent commits.
- [ ] Bump versions consistently only for the verified candidate.
- [ ] Before publishing show branch, commit, remaining limitations and exact destination.
- [ ] Verify remote branch, main, tag and release independently after authorized publication.

## Current execution

The production native spawn factory now creates suspended children, retains
ownership before registration, isolates descriptors and refuses premature
release after failed registration. Four real-process cases plus regressions
pass: 73 tests in 40.352 s. See 2026-09-09-native-spawn-owner.md. The persistent
operation/control loop is still missing; no storage-effect success is claimed.

Native child registration/control primitives now have six real suspended-child
scenarios; 69 combined targeted tests pass in 28.911 s. See
2026-09-09-native-child-registration.md. They are not yet connected to production
spawn ownership or the persistent operation loop. Next: make that connection
without reusing the legacy unguarded cleanup runner.

Native recovery root is now retained in mutable memory and erased on broker
return; 63 targeted tests pass in 22.744 s. See
2026-09-09-native-recovery-root.md. Recovery authentication is still absent.
Inspection confirms the legacy spawn/cleanup runner is not S3-compliant:
implement suspended registration and fresh identity/waitability checks before
connecting native effects. Do not reuse its unguarded signal/reap sequence.

The default public broker client now launches the real Swift broker, validates
peer/executable identity, persists RUNNING, grants and sends START. 59 targeted
tests pass in 17.048 s. See 2026-09-09-broker-launch-owner.md. Swift recognizes
authorization but returns INVALID_STATE because supervised dispatch is missing;
the client preserves OPEN_UNRESOLVED instead of claiming success. Next: native
retained recovery/effects, terminal commit and persistent application ownership.

**Critical dependency correction:** the persistent native broker currently
implements HELLO and START authorization validation, not authorized storage
execution. Python's default public client reaches that boundary; private probes
and recovery are not connected. Follow
2026-09-09-native-path-audit.md in order: START grant, real launch/session owner,
native effect state machine, durable commit, then reconciliation. Passing negative
handshake tests or optional-storage installation does not close these gates.

Goal active. No lot is globally accepted merely because an earlier targeted
suite passed. Native JSON/tree validation and descriptor transfer into managed
runtime are implemented. Stable launcher deployment and native-to-managed startup
from the installer-returned path pass targeted tests. Initial bootstrap publication
and selector publication are not one atomic multi-file transaction; see
2026-09-09-bootstrap-install.md for retained failure state and eight-case evidence.
Explicit bootstrap migration and mounted storage acceptance remain open.

### Fresh baseline findings

- Descriptor volume UUID added through read-only fgetattrlist; real probe agrees
  with an independent OS observation.40 targeted tests PASS72.467s. See
  `2026-09-10-descriptor-volume-uuid.md`. This extends the probe metadata contract;
  integration review, actual installed invocation and encryption/image proof
  remain open. No environment UUID is promoted by the optional Python field.

- Managed workspace root binding fixed: unrelated same-device roots and mount
  pathname replacement were reproduced, then rejected using descriptor-relative
  root opening and final inode checks.29 targeted tests PASS92.191s. See
  `2026-09-10-managed-root-binding.md`. Synthetic mount facts isolate directory
  binding; actual UUID/private broker proof remains open.

- Zero-cleanup admission corrected in Python and native grants, with unchanged
  40s/12s/52s limits. Private probe reserves positive cleanup duration.
  48 broker/grant tests PASS15.069s plus 35 generation/lifecycle tests
  PASS277.350s. See `2026-09-10-positive-cleanup-budget.md`. These are targeted
  checks, not complete encrypted-storage/product acceptance.

- Early cleanup deadline corrected: cancellation/owner-loss now start the cleanup
  budget immediately. Real TERM-ignoring fixture stays owned/unresolved when the
  short budget expires; no forced success. 100 targeted tests PASS in 67.156
  seconds; see `2026-09-10-cleanup-deadline.md`. Full broker budget admission and
  persistent effect integration remain open.

- Disposable Keychain lifecycle now requires create/inspect/delete confirmations
  for one transaction/image/UUID before SPIKE_PASSED. Missing terminal evidence
  previously passed and now fails. 35 targeted tests PASS in 82.269 seconds; see
  `2026-09-10-spike-lifecycle.md`. Broker results are synthetic in orchestration
  tests, not a live encrypted-storage acceptance result.

- Mount-probe unsigned identity schema and bootstrap canonical-escape fix:
  51 targeted tests PASS in 114.616 seconds. Real installed bootstrap initially
  rejected a newline-containing generation; its independent encoder is now
  aligned and tested with all control scalars. See `2026-09-09-mount-probe-u32.md`.
  Installed probe invocation and verified UUID provenance remain unconnected.

- Public START structural validation and canonical control-escape fix: 97 targeted
  tests PASS in 68.610 seconds. See `2026-09-09-broker-request-schema.md`.
  Remaining producer mismatches: mount/detach volume_name, missing expected
  encryption identity. Zero-cleanup admission is now corrected; see
  `2026-09-10-positive-cleanup-budget.md`. Absolute-deadline integration remains open.
  No native effect/descriptor-attestation/release acceptance is implied.

- Running controls: 76 targeted tests PASS in 60.642 seconds, including fourteen
  real socket/child control subcases. Fixed reproduced blocking send on a full
  socket by enforcing O_NONBLOCK. See `2026-09-09-running-control.md`.
  Authenticated START dispatch, cleanup STATUS/terminal sequence handoff and
  terminal acknowledgment remain open; no deployed execution acceptance.

- Incremental native framing: 75 targeted tests PASS in 46.632 seconds, including
  ten real socket subcases in one method. Production handshake/grant readers now
  share this bounded incremental implementation. See
  `2026-09-09-incremental-control-reader.md`; running-control authorization and
  effect dispatch remain open.

- Native command pump: 74 targeted tests PASS in 47.009 seconds, including ten
  real subprocess subcases in one pump test method. See
  `2026-09-09-native-command-pump.md`. This does not close the persistent dispatch,
  wire cancellation, terminal acknowledgment, recovery or installation gates.

- Profiles: 16 tests PASS (0.001 s); continuity: 18 PASS (0.162 s).
- Process recovery: 5 PASS (0.050 s); effect recovery dispatch: 10 PASS (0.126 s).
- These 49 tests are component/regression evidence, not cross-harness acceptance.
- The mission API still rejects non-deterministic executors with HTTP 422.
- Profile validation is not yet consumed by the mission flow. Continuity
  persistence exists in Store, but mission resume does not yet consume it.
- Native duplicate-key cases reproduced three failing subtests before the fix
  (32.205 s), including Unicode-escaped and nested aliases. After implementation,
  the fresh native/installed suite passes: 12 tests in 64.852 s.
- The scanner compares decoded UTF-8 keys per object, traverses arrays and
  nested objects, caps nesting at 128 and rejects trailing data. Foundation
  still validates JSON syntax before the unique-key scan.
- Fresh real generation installation also passes: 6 tests in 66.682 s.
  Session total: 67 targeted tests (49 components + 12 native + 6 install).
  This is not a global release verdict. No commit, push or user installation.
- Storage sessions: native `d95015c4ed9448eb84a04b1e7b98e264`, tests
  `63836adc49ab480bbd94be3f8fed4825`, plans
  `f3345a4f09f34deda4c2567fb8b88c7e`, root
  `22f7639bdbc740a7b6e2615f4c6f3fdb`.
