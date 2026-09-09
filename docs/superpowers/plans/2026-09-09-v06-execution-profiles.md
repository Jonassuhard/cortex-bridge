# Cortex 0.6 Execution Profiles Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this bounded foundation task-by-task. Do not expand this into a live provider integration without its own adapter contract.

**Goal:** Reject unsupported executor selections and unsafe handoffs before any runtime/provider side effect.

**Architecture:** A pure immutable profile contract consumes observed harness/model capabilities and mission/effect state. It does not discover models, run tools, persist consent or claim live availability. Later adapters and authenticated routes must supply trusted observations and human authorization.

**Tech Stack:** Python 3.11+, standard-library dataclasses; unittest.

**Spec:** docs/superpowers/specs/2026-09-09-v06-product.md

## Global Constraints
- No quota bypass, API substitution, provider/model fallback or fabricated readiness.
- No existing runtime route switched until adapter and continuity integration tests pass.
- Existing 0.5 modifications and evidence remain preserved; no version bump or push.

### Task 1: Profile selection and transition gate

**Files:** create orchestration/execution_profiles.py; tests/test_execution_profiles.py.

**Interfaces:** immutable ModelOption(id, reflection_levels), HarnessSnapshot(id, provider, cost_class, observed_at, available, models), ExecutionProfile(harness_id, model_id, reflection); validate_profile(profile, snapshot, now, max_age=60) and validate_handoff(current, target, source, destination, mission_state, effect_states, recipient_change_approved, now) raise ProfileError with stable code. A pass is compatibility only, not permission to execute.

- [x] Write tests asserting unsupported models/reflection, unavailable targets, future/stale observations and malformed numbers fail closed; valid observed selection returns unchanged.
- [x] Run `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_execution_profiles.py -v`; record the missing implementation RED.
- [x] Implement strict validation with immutable dataclasses, finite timestamps, exact boolean availability, non-empty unique identifiers and reflection values. Do not normalize IDs or substitute models.
- [x] Add handoff cases: running mission rejected; unknown/running effects rejected; provider/cost change requires explicit approval; safe paused transition accepted; invalid target rejected even with approval.
- [x] Run focused tests and existing protocol/state/store regression suite with bytecode disabled. Record actual results.
- [ ] Review every error path and preserve uncaught infrastructure failures; update status before any selective commit.

## Follow-on sequence
After this foundation, specify durable checkpoints against the existing SQLite Store before implementing adapter dispatch. Then implement actual harness discovery/probes and a real adapter contract suite. Profile tests alone cannot enable Freebuff in the UI or validate a model transition. Remaining product lots and gates are tracked in the linked specification.

## Execution checkpoint — 2026-09-09
RED: 16 assertion failures because execution_profiles was absent. GREEN: 16/16 profile tests. Existing test_protocol_state_store.py: 31/31 PASS. Commands used Python unittest with PYTHONDONTWRITEBYTECODE=1; no provider calls or live runtime writes.
The gate is not yet wired into runtime routes. Authorization is a trusted caller input, not a new consent system. Source snapshots may be expired to permit leaving an unavailable provider; target observations must be fresh. The caller must bind source identity and serialize validation with dispatch.
Existing approved docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md specifies EffectGate as the exclusive durable-effect authority. Do not create a competing ledger for 0.6: reconcile this dependency before implementing checkpoint persistence. The 0.6 completion goal stays active; no release, commit or push performed.
