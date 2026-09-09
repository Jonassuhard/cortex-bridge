# Staged durable effect schema — implementation checkpoint

Parent plan: [approved durable-effects and executor plan](2026-09-02-v054-durable-effects-and-executor.md), Task 1.
Product scope: [0.6](../specs/2026-09-09-v06-product.md).

## Implemented, not enabled in the installed application
- orchestration/effect_schema_sql.py contains the final v3 DDL copied from the approved plan.
- orchestration/effect_schema.py exposes upgrade_effect_schema(connection), applying canonical v1-to-v2 and v2-to-v3 stages inside one immediate transaction.
- Legacy approvals are retained in approvals_legacy_v1 and never assigned an epoch or nonce.
- Both rebuilt tables have their original-column row count and canonical digest checked before either swap. The copied effect graph references the new table, not the retiring one.
- Six explicit test failpoints abort before publication, preserving original data and schema. No runtime/environment configuration activates them.
- Foreign keys and CHECK constraints are enforced; synchronous=FULL is set; foreign_key_check and quick_check gate commit.
- Only known exact schema definitions are accepted. Partial/modified tables, indexes, unsupported versions and missing control/migration records fail closed. Semantically equivalent but differently authored schemas require review rather than automatic acceptance.
- No live database, Store constructor, approval consumer, route or dispatch was switched to v3. The current Store.record_approval is incompatible with the new table and MUST be replaced alongside EffectGate before enabling the upgrade.

## Executed evidence
Initial eight tests failed because the migration module did not exist, then passed. Nonempty v2 coverage found a real deferred foreign-key failure at commit: corrected by referencing effects_v3 during copying, then letting SQLite rewrite the self-reference on rename. Missing unique-index and missing-control-state tests failed before stricter source validation. A caller leaving ignore_check_constraints enabled also reproduced unsafe acceptance; enforcing that pragma OFF fixed the new test.

Final command:
`PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p test_effect_schema.py -q`
Result: 15 tests PASS. Includes six failpoint subcases for original v1 and six for nonempty v2, actual file database reopen, current approval-field preservation, retained outcome_unclear parent/child graph, foreign keys and direct/admin request uniqueness.

Regression commands using the same interpreter: test_continuity.py (16 PASS), test_store_serialization.py (1 PASS), test_protocol_state_store.py (31 PASS). git diff --check PASS. These do not prove the full application works on v3.

## Remaining Task 1 / integration gates
- Full local-alias approval/XOR mutation matrix and every recognized effect state.
- Crash/process interruption beyond injected exceptions; invalid/nonfinite record handling.
- Store.schema_version, transaction_immediate, control_row and effect_rows with coordinated approval consumers.
- EffectGate capabilities, STOP epochs, activation permits and actual worker reconciliation.
- Fresh installed-runtime lifecycle acceptance, then context/harness UI handoff.

Do not mark the parent task or 0.6 complete from these migration fixtures. No commit, push, version bump or publication occurred.
