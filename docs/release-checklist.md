# Cortex Bridge v0.5 release checklist

Every item must link to evidence from one release commit. A previous branch or a developer’s memory is not evidence.

## Source and package

- [x] `VERSION`, Python metadata, frontend package and lock all report `0.5.0`.
- [x] Python lock is exact and hashed.
- [x] npm lock and package-manager version are respected through Corepack.
- [x] Two consecutive static builds have identical hashes.
- [x] Worktree is clean after the reproducible build.

## Product

- [x] Enter sends only to ChatGPT.
- [x] Execution requires confirmed preflight.
- [x] Sidebar groups are exclusive and capped at 50.
- [x] Two writers pass ten cold runs without crossover.
- [x] Third writer preserves draft and file.
- [x] Cached UI is usable below 2 seconds.
- [x] Switch p95 is below 3 seconds and maximum does not exceed 10 seconds.
- [x] Timeout exposes explicit reload without automatic resend.

## Quality

- [x] Backend suite passes with temporary `CORTEX_HOME`.
- [x] Frontend unit and runtime tests pass.
- [x] TypeScript, lint, build and coverage gates pass.
- [x] Browser E2E and accessibility pass at 375, 768 and 1440 pixels.
- [x] No unexpected page, console or hydration error.
- [x] Shell syntax and ShellCheck pass.
- [x] Dependency audits pass.

## Installation and lifecycle

- [x] Dry-run is immutable and produces a complete hashed plan.
- [x] Wrong or missing approval cannot mutate the target.
- [x] Reinstall is idempotent.
- [x] Interrupted install rolls back staging only.
- [x] Doctor JSON is stable.
- [x] Foreign ports, stale owners and PID reuse are rejected.
- [x] Uninstall removes only manifest-owned resources.

## Public tree

- [x] README and public docs are English; application labels remain French.
- [ ] Every documented command was executed on the release candidate.
- [x] Relative, anchor and external links pass.
- [x] Current tree passes personal-marker, path, URL and secret scans.
- [x] Public binaries are known formats.
- [x] Images pass EXIF and English/French OCR scans.
- [x] All screenshots are synthetic at the required viewports.
- [x] Historical privacy decision is recorded separately.

## Acceptance

- [x] 20 consecutive fixture missions pass without retry masking.
- [x] Ten cold dual-conversation runs pass.
- [x] Six crash points recover without duplicate send or execution.
- [ ] Self-diagnostic mission runs in a disposable worktree and does not merge itself.
- [ ] A provider-authorized transport passes every live ChatGPT and mini-site gate.
- [x] The consumer-site terms blocker is explicit and cannot be overridden by owner approval.
- [ ] `docs/verification/v0.5.0.json` matches the final audited source commit and artifact hashes.

## External actions

- [ ] Owner approves history policy.
- [ ] Owner approves source model and license decision.
- [x] Owner approves push.
- [ ] Owner approves tag and GitHub release.
- [ ] Owner approves social publication.
