# Explicit missing-bootstrap migration

## Scope and authorization

`install --generation-wheel <wheel> --bootstrap-migration missing-v1` produces
a dry-run plan for an already selected, fully verifiable generation whose
bootstrap directory is absent. Applying it requires the exact reviewed plan hash
through the existing approval path. The flag alone does not approve changes.

The previous selector, record, manifest and generation identity are part of the
hashed plan. Its complete application tree and native identities are checked
before planning, again under the install/storage exclusive locks at apply time,
and immediately before publication. An altered previous generation is refused.
The installer retains the previous generation; it builds a new launcher and
generation and uses the existing recoverable selector-publication transaction.

No existing bootstrap is replaced by this option. Missing or malformed previous
generation evidence is not repaired implicitly. Changed-source and legacy-format
bootstrap replacement require a separate migration implementation and remain open.

## Evidence

- Initial real migration test reached the missing build_plan keyword and errored
  in 59.530 s after successfully creating the initial real installation.
- Missing/invalid generation, partial Doctor, publication and wheel checks:
  twelve PASS, 7.225 s.
- CLI requires an explicit generation wheel: one PASS, 2.597 s.
- Actual missing-bootstrap migration: one PASS, 116.625 s, including preserved
  old generation, tamper refusal and new native-managed HTTP/READY/CLOSED.
- Normal installed-Doctor/HTTP regression: one PASS, 84.134 s.
- Tampered approval, changed wheel, legacy interruption and pending publication
  regressions: four PASS, 2.518 s.
- Changed approved target: one PASS, 4.190 s. Twenty targeted methods executed
  across these commands; no whole-release verdict.

The real fixture first installs a generation, preserves its launcher outside the
active bootstrap path to emulate the previous no-bootstrap layout, confirms
ordinary installation refuses that layout, approves an explicit migration plan,
alters/restores an installed source file to verify refusal without publication,
then migrates. It verifies the old generation remains byte-valid and the new
launcher reaches managed HTTP/READY/CLOSED with no orphan.

## Remaining release gates

This is not the complete migration/release gate. Required encrypted-storage
admission, interrupted bootstrap replacement/rollback, and exhaustive open or
unreconciled storage-workflow checks before generation updates remain to be
completed. Existing publication recovery refuses pending journals and retains
failed staging; it does not automatically reconcile native storage effects.
Initial bootstrap publication and selector publication are separate durable
steps, not one all-or-nothing multi-file transaction. No user installation,
legacy image, Git commit, push or release is changed by this test lot.
