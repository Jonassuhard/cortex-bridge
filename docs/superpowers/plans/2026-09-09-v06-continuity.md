# Cortex 0.6 Explicit Context Checkpoints Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans and test-driven-development. This is context persistence, not an alternative effect ledger.

**Goal:** Preserve explicit mission context across process restarts and reject stale or altered snapshots before any later handoff.

**Architecture:** Append versioned checkpoint events to the existing SQLite transport_events table, under a write transaction. Bind checkpoints to a canonical digest of the mission and existing evidence tables. Read checks integrity and freshness without granting execution authority. EffectGate remains the sole planned authority for durable effects.

**Tech Stack:** Python standard library, SQLite, unittest.

**Spec:** docs/superpowers/specs/2026-09-09-v06-product.md

## Global Constraints
- Context is explicit working data, not hidden reasoning, permission or effect proof.
- No new executor, provider calls, runtime auto-resume or schema-version bypass.
- No truncation of constraints to meet size limits; reject oversized context.
- Full source digest stays local; no raw logs automatically exported.

## Task 1: Durable checkpoint contract
Files: orchestration/continuity.py, orchestration/store.py, tests/test_continuity.py.
Interfaces: Store.context_source_digest(mission_id)->str; save_context_checkpoint(checkpoint_id, mission_id, context, expected_source_digest)->dict; load_context_checkpoint(checkpoint_id, mission_id)->dict. Envelope fields: schema_version=1, mission_id, source_digest, context, digest; read adds source_current bool. Context fields exactly constraints, decisions, open_questions (lists of strings), next_action (string). Objective/workspace/effects remain authoritative in Store, never overwritten by this packet.
- [x] RED tests: persistence across actual database reopen; stale expectation rejection; altered packet rejection; different mission rejection; immutable checkpoint ID; idempotent exact retry; subsequent mission/tool changes flag stale; failed save leaves no event; no new schema tables; no transition caused by save/load.
- [x] Implement strict context validation (64 KiB serialized maximum, no unknown fields), canonical SHA-256 and schema checks in continuity.py.
- [x] Implement transactional save and consistent read in Store. Reject nested transactions; no auto-fallback to stale snapshots. Exclude checkpoint events themselves from source digest; include other evidence and transport events.
- [x] Run new tests plus profile and existing Store/loop suites. Keep the installed runtime unchanged until integrated adapter tests pass.

## Runtime follow-on
Authenticated pause/resume routes will create/read checkpoints only after the durable EffectGate is available. A current checkpoint is necessary but insufficient for execution: workspace file reconciliation, provider consent, capabilities, approval and STOP epoch must still pass. Model-generated notes never establish any of those facts.

## Evidence and limits — 2026-09-09
Initial ten tests failed on the missing checkpoint method. All ten passed after implementation. Six additional defensive characterization cases then passed: unknown schema despite matching hash, input mutation, independent mission activity, transport ambiguity, rollback and nested transaction refusal. These six are not claimed as separate RED/GREEN cycles.
Fresh unittest results with PYTHONDONTWRITEBYTECODE=1: continuity16, profiles16, protocol/state/store31, loop26, runner7, all PASS (96 total). Existing eleven-table assertion passes: no new schema ledger. git diff --check passes.
SQLite reopen is tested on an isolated file, not the installed runtime or power-loss behavior. Hashes detect accidental alteration; they are not signatures or protection against a same-user database editor recomputing them. Source freshness covers database evidence, not live file contents. Single-owner Store access must be serialized by the caller; cross-thread safety is not claimed. No public export, model submission, automatic handoff or new route is enabled.
Next: implement the approved durable-effect/STOP prerequisite before connecting checkpoints to resume and cross-harness dispatch. Then prove real transition through the UI and actual file reconciliation.

## Shared connection serialization follow-up
Reproduced a real race: while checkpoint encoding was suspended inside its transaction, another thread's Store.set_iteration completed and committed that transaction. Added a per-instance reentrant lock around every public Store operation, including close and reads. The concurrent test failed before the change and passed after it, asserting actual blocking and final database state. No external provider is mocked. The test suspends only the encoder to make the race deterministic.
An intermediate mechanical edit mistakenly decorated the decorator itself, producing RecursionError on import; that edit was corrected before testing. Final results: serialization1, continuity16, profiles16, protocol/state/store31, loop26, runner7 PASS (97 tests). The project venv also passes serialization1 and version6. System Python initially failed one version test because uvicorn was absent; no package installation or assertion weakening was used.
Public Store calls now serialize across threads on one instance. Private raw connection access and compound operations spread across several calls remain outside this guarantee; cross-process ownership and durable EffectGate are still required. This supersedes only the earlier caller-serialization limitation, not the checkpoint's lack of execution authority.
README introductory comparison claims were replaced by an explicit 0.6 development-status table and separate model/harness/reflection explanation. Existing Freebuff test data stays private and unchanged. Offline link checker: PASS, 125 checked, 50 external skipped; no external-link freshness claim. No version bump, installed runtime change, commit or push.
