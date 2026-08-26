# Cortex Bridge v0.5.3 release checklist

**Current status: `PARTIAL`. Target public verdict: `OPT_IN_TECHNICAL_PREVIEW`.**

Candidate date: 2026-08-26.

This candidate is not `READY` and is not authorized by OpenAI. Its
machine-readable manifest is committed separately after the audited source
commit so it cannot hash itself. Every checked item below has current v0.5.3
evidence; v0.5.2 evidence and developer memory do not satisfy a v0.5.3 gate.

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
- [ ] A blocked third writer also preserves a staged file across the refusal.
- [ ] A real conversation switch completes within the 10-second maximum.
- [x] A real synthetic file is delivered once and confirmed in the same user
      message.
- [x] A real synthetic screenshot is delivered only after the private mask is
      visually inspected.
- [ ] Timeout exposes explicit reload without automatic resend.

## Quality

- [x] Backend suite passes with temporary `CORTEX_HOME` on the final source
      tree.
- [x] Frontend unit and runtime tests pass.
- [x] TypeScript, lint and static build pass.
- [x] Chrome-extension unit tests cover private masking, attachment transfer,
      composer remounts and uncertain-delivery preservation.
- [x] Browser E2E and accessibility pass at 375, 768 and 1440 pixels on the
      final source tree.
- [ ] No unexpected page, console or hydration error appears in the final live
      run.
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

- [ ] Primary English docs, localized French guides and French application
      labels are verified for the correct language on the final source tree.
- [ ] Every documented command is executed on the final release candidate.
- [x] Relative, anchor and external links pass.
- [x] Final tree passes personal-marker, path, URL and secret scans.
- [x] Public binaries are known formats.
- [x] Images pass EXIF and English/French OCR scans.
- [ ] Every public screenshot contains only synthetic data and passes the
      required viewport checks.
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
