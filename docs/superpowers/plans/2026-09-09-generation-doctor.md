# Doctor for immutable generation installations

## Problem and change

Doctor previously inspected the legacy venv/native layout and checkout extension
even after apply_install published an immutable generation. It now dispatches to
generation inspection whenever a selector, generations directory or bootstrap
entry exists; a partial installation cannot silently fall back to legacy checks.

Under the retained install-shared lock, it verifies the selected metadata and
complete application inventory, native helper identities, retained bootstrap
sources/profile/signature and publication journal. It reports the installed
extension path, not the checkout path, and preserves the configured local port.
No selected Python module is imported and no browser action is performed.

## Test evidence

- Real-install RED: missing generation diagnosis, 57.425 s.
- First complete installation run after correction: seven PASS, 80.113 s;
  includes Doctor success, real installed-file tamper rejection, native startup,
  HTTP and shutdown.
- Publication and wheel regression: nine PASS, 4.005 s.
- Partial-generation refusal plus four legacy Doctor regressions: five PASS,
  4.445 s before adding the configured-port assertion.
- Configured-port RED: one failed assertion, 2.712 s; URL field then corrected.
- Complete installation suite including configured port and partial-generation
  refusal: eight PASS in 87.418 s. A subsequent real-install run additionally
  invokes Doctor using installed Python with `-I -S -B`: PASS, 85.351 s,
  including real installed HTTP and graceful shutdown afterward.
- Four legacy Doctor regressions rerun after the port correction: PASS, 2.217 s.

Separate product baseline: profiles and continuity component suites pass 34
tests in 0.137 s. Source mapping still shows deterministic-only mission creation
and no consumption of these profile/continuity contracts by the mission flow;
these results do not prove executor switching or cross-harness resume.

Checkpoint: 55 distinct targeted tests plus the strengthened real-install rerun.
Diff whitespace check passes; pre-existing unrelated changes remain preserved.

## Limits

Installation integrity is not Chrome pairing, accessibility permission, provider
availability or successful mission execution. Those untested states stay
explicit. A configured encrypted-storage bootstrap produces a required warning
and ok=false until broker-backed admission diagnosis is implemented; Doctor
does not substitute direct disk utilities or a mount attempt for that proof.
The legacy Doctor path is retained for installations without generation entries.
Development-format migration and generation-aware uninstall remain open.
No user installation or Git publication performed.
