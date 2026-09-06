# Cortex Bridge v0.5.4 completion plan

## Objective

Finish the v0.5.4 storage/runtime path honestly: prove the S3 contract, wire a
real installed runtime entrypoint and lifespan, fix reproducible defects without
weakening gates, rerun the required test matrix, and leave durable evidence for
the release candidate. GitHub push remains a separate explicitly confirmed
action.

## Phases

- [complete] Phase 1 — Revalidate source, plan, entrypoints, and existing evidence.
- [complete] Phase 2 — Implement the next production behavior only when its
  installed entrypoint and contract are present; otherwise add a fail-closed
  regression and record the missing product input.
- [in_progress] Phase 3 — Run focused dual-Python tests, full hermetic tests, Swift
  compile checks, link checks, and release-evidence validation.
- [in_progress] Phase 4 — Update anonymized English verification docs and
  planning evidence; preserve the user-owned primer and generated UI artifact.
- [pending] Phase 5 — Request explicit push approval, then push only the verified
  candidate if all publish gates are PASS.

## Acceptance gates

- No invented installed generation, server path, or macOS proof.
- Focused suites PASS on the equipped Python 3.14 and Python 3.12 interpreters.
- Full suite results recorded exactly; any failure remains FAIL/UNCLEAR.
- Swift sources compile; links and JSON evidence validate.
- No personal data or secrets in evidence/docs.
- No user-owned unrelated files staged or committed.

## Errors encountered

| Error | Attempt | Resolution |
| --- | --- | --- |
| Managed launcher is a deliberate `STARTUP_RUNTIME_NOT_WIRED` stub | Existing implementation | Keep fail-closed; inspect frozen plan for a real installed entrypoint before changing it. |
| Full hermetic suite leaves descendant process groups observable | Dual-Python runs | Keep as an explicit blocker; do not weaken the harness or claim PASS. |
| Desktop launcher masked the storage guard exit code and did not dispatch `doctor` arguments | Reproduced with a missing mounted volume | Add a regression-tested argument path, preserve the exact exit code, and show storage-specific guidance. |
| Canonical release evidence points to an older source commit and the worktree is dirty | Evidence validator | Do not rewrite canonical evidence to hide drift; bind only truthful focused evidence. |

## Current status

Phase 1 was revalidated on 2026-09-06. The concrete result is that the
installed-generation publisher/bootstrap and the managed server entrypoint are
not present, while the fail-closed composition and lifespan primitives are.
Phase 2 added descriptor-relative bootstrap-handle validation to the composition
factory and a selector-digest regression. The bounded launcher gate then added
storage-aware doctor output and preserved the fail-closed storage error code.
It did not invent or wire an installed entrypoint that is absent from the
product tree.
