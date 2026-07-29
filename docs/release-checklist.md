# Cortex Bridge v0.5 release checklist

Every item must link to evidence from one release commit. A previous branch or a developer’s memory is not evidence.

## Source and package

- [ ] `VERSION`, Python metadata, frontend package and lock all report `0.5.0`.
- [ ] Python lock is exact and hashed.
- [ ] npm lock and package-manager version are respected through Corepack.
- [ ] Two consecutive static builds have identical hashes.
- [ ] Worktree is clean after the reproducible build.

## Product

- [ ] Enter sends only to ChatGPT.
- [ ] Execution requires confirmed preflight.
- [ ] Sidebar groups are exclusive and capped at 50.
- [ ] Two writers pass ten cold runs without crossover.
- [ ] Third writer preserves draft and file.
- [ ] Cached UI is usable below 2 seconds.
- [ ] Switch p95 is below 3 seconds and maximum does not exceed 10 seconds.
- [ ] Timeout exposes explicit reload without automatic resend.

## Quality

- [ ] Backend suite passes with temporary `CORTEX_HOME`.
- [ ] Frontend unit and runtime tests pass.
- [ ] TypeScript, lint, build and coverage gates pass.
- [ ] Browser E2E and accessibility pass at 375, 768 and 1440 pixels.
- [ ] No unexpected page, console or hydration error.
- [ ] Shell syntax and ShellCheck pass.
- [ ] Dependency audits pass.

## Installation and lifecycle

- [ ] Dry-run is immutable and produces a complete hashed plan.
- [ ] Wrong or missing approval cannot mutate the target.
- [ ] Reinstall is idempotent.
- [ ] Interrupted install rolls back staging only.
- [ ] Doctor JSON is stable.
- [ ] Foreign ports, stale owners and PID reuse are rejected.
- [ ] Uninstall removes only manifest-owned resources.

## Public tree

- [ ] README and public docs are English; application labels remain French.
- [ ] Every documented command was executed on the release candidate.
- [ ] Relative, anchor and external links pass.
- [ ] Current tree passes personal-marker, path, URL and secret scans.
- [ ] Public binaries are known formats.
- [ ] Images pass EXIF and English/French OCR scans.
- [ ] All screenshots are synthetic at the required viewports.
- [ ] Historical privacy decision is recorded separately.

## Acceptance

- [ ] 20 consecutive fixture missions pass without retry masking.
- [ ] Ten cold dual-conversation runs pass.
- [ ] Six crash points recover without duplicate send or execution.
- [ ] Self-diagnostic mission runs in a disposable worktree and does not merge itself.
- [ ] An officially supported provider transport passes every live ChatGPT and mini-site gate.
- [ ] The consumer-site blocker is not relabelled as owner approval or fixture success.
- [ ] `docs/verification/v0.5.0.json` matches the final commit and artifact hashes.

## External actions

- [ ] Owner approves history policy.
- [ ] Owner approves source model and license decision.
- [ ] Owner approves push.
- [ ] Owner approves tag and GitHub release.
- [ ] Owner approves social publication.
