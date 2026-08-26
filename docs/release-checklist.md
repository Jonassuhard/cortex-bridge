# Cortex Bridge v0.5.3 release checklist

**Current status: `PARTIAL`. Target public verdict: `OPT_IN_TECHNICAL_PREVIEW`.**

Candidate date: 2026-08-26. Live gates completed the same evening (see
`docs/verification/v0.5.3-test-report.md`, "Live gates 2026-08-26 (evening)").

This candidate is not `READY` and is not authorized by OpenAI. Its
machine-readable manifest is committed separately after the audited source
commit so it cannot hash itself. Every checked item below has current v0.5.3
evidence; v0.5.2 evidence and developer memory do not satisfy a v0.5.3 gate.
Only two kinds of items remain open: the genuinely clean macOS account/VM
lifecycle, and the explicit owner approvals under "External actions".

## Source and package

- [x] `VERSION`, Python metadata, frontend package and lock all report `0.5.3`.
- [x] Python lock is revalidated as exact and hashed on the final source tree.
- [x] npm lock and package-manager version are revalidated through Corepack on
      the final source tree.
- [x] Two consecutive static builds contain the same 28 files and have the
      identical aggregate SHA-256.
- [x] Worktree is clean after the reproducible build.

## Product

- [x] A real classic ChatGPT conversation receives one synthetic text message.
- [x] Two real conversation writers complete without crossover.
- [x] A third writer is refused in French and preserves its draft.
- [x] A blocked third writer also preserves a staged file across the refusal
      (2026-08-26: two live writers held both slots, the third attempt with an
      attachment was refused in French with HTTP 409, and the separately
      user-staged file token still resolved with intact content afterwards; no
      third tab or run was created).
- [x] A real conversation switch completes within the 10-second maximum
      (2026-08-26: four live switches between the two synthetic conversations,
      maximum 5.3 s, correct URL and content each time, no crossover).
- [x] A real synthetic file is delivered once and confirmed in the same user
      message.
- [x] A real synthetic screenshot is delivered only after the private mask is
      visually inspected.
- [x] Timeout exposes explicit reload without automatic resend (2026-08-26:
      the writer tab was closed mid-flight; the run ended in a terminal
      explicit error, the message stayed delivered exactly once in the
      conversation, no retry or automatic resend occurred, and the UI exposes
      an explicit reload action).

## Quality

- [x] Backend suite passes with temporary `CORTEX_HOME` on the final source
      tree.
- [x] Frontend unit and runtime tests pass.
- [x] TypeScript, lint and static build pass.
- [x] Chrome-extension unit tests cover private masking, attachment transfer,
      composer remounts and uncertain-delivery preservation.
- [x] Browser E2E and accessibility pass at 375, 768 and 1440 pixels on the
      final source tree.
- [x] No unexpected page, console or hydration error appears in the final live
      run (2026-08-26: after pairing, every live operation returned 2xx except
      the two intentional 409 refusal proofs and one operator 422; the final
      transport probe reported `failures: []` and `warnings: []`; the server
      log shows no traceback or unexpected error for the session).
- [x] Shell syntax and ShellCheck pass on the final source tree.
- [x] npm and Python dependency audits pass on the final source tree.

## Installation and lifecycle

- [x] An isolated `CORTEX_HOME` on macOS completes dry-run, exact hashed
      approval, installation, Doctor, start/status/stop and uninstall without
      `sudo`.
- [ ] A genuinely clean macOS account or VM repeats that lifecycle.
- [x] Wrong or missing approval cannot mutate the target.
- [x] Reinstall is idempotent.
- [x] Interrupted install rolls back staging only.
- [x] Doctor reports the installed v0.5.3 instance truthfully and distinguishes
      an on-disk manifest from a paired extension.
- [x] Foreign ports, stale owners and PID reuse are rejected.
- [x] Uninstall refuses a running owned server, removes only manifest-owned
      resources and preserves a foreign sentinel.
- [x] The optional Freebuff contract verifies its public links, performs an
      immutable Cortex dry run, requires an exact plan hash and keeps login,
      extension and permission decisions human-only.

## Public tree

- [x] Primary English docs, localized French guides and French application
      labels are verified for the correct language on the final source tree
      (2026-08-26: 24 public docs checked, all English docs English, all
      `docs/fr/` guides French, root README English, French UI labels present
      in the static build).
- [x] Every documented command is executed on the final release candidate
      (2026-08-26: lifecycle, doctor, status, logs, install dry-run and exact
      approval, uninstall dry-run, update, autostart install/remove, extension
      guide, Freebuff and toolchain commands all executed with exit 0;
      destructive uninstall approval and heavyweight dependency/bootstrap
      commands are covered by the isolated-lifecycle and reproducible-build
      gates; optional Ollama model pull not re-downloaded).
- [x] Relative, anchor and external links pass.
- [x] Final tree passes personal-marker, path, URL and secret scans.
- [x] Public binaries are known formats.
- [x] Images pass EXIF and English/French OCR scans.
- [x] Every public screenshot contains only synthetic data and passes the
      required viewport checks (2026-08-26: 11 screens × 375, 768 and 1440 px
      families plus proofs and media verified by dimension; content is
      fixture-synthetic and already covered by the EXIF/OCR scans).
- [x] Historical privacy decision is recorded separately.

## Acceptance

- [x] 20 consecutive fixture missions pass without retry masking on the final
      source tree.
- [x] Ten cold dual-conversation fixture runs pass without crossover and keep
      the refused third draft and staged file.
- [x] Six historically mapped crash/recovery tests pass; six dedicated Chrome
      recovery/anti-replay tests also pass.
- [x] Three distinct mini-site missions complete in disposable workspaces and
      pass their acceptance checks.
- [x] A self-diagnostic mission runs in a disposable worktree and does not
      merge itself.
- [x] The production Chrome extension passes the complete v0.5.3 technical
      conversation, file and private-screenshot flow.
- [x] The consumer-site terms blocker is explicit and cannot be overridden by owner approval.
- [x] `docs/verification/v0.5.3.json` matches the audited source commit and
      artifact hashes with the owner-assumed `OPT_IN_TECHNICAL_PREVIEW`
      verdict. This verdict does not mean OpenAI authorization.

## External actions

- [ ] Owner reviews the final v0.5.3 diff and evidence manifest.
- [ ] Owner explicitly approves the v0.5.3 push.
- [ ] Owner explicitly approves the v0.5.3 tag and GitHub release.
- [ ] Owner approves social publication.
