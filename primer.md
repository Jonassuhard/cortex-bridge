# Cortex Bridge session primer

Current state: 2026-08-26. Read this file with `README.md`,
`docs/release-checklist.md` and `docs/verification/v0.5.3-test-report.md`.

## Repository

- Worktree: `.worktrees/codex-critical-qa`; branch `codex/critical-qa`.
- Canonical version: **0.5.3** in `VERSION`, Python metadata, frontend package
  and lock, Chrome manifest and installer metadata.
- Canonical remote: `origin`; default branch: `main`; rebase base: `3bb2cdb`.
- The branch is published at `origin/codex/critical-qa`; PR #13 targets `main`.
  `main` is unchanged. Merge, tag and release still require explicit approval.

## Product invariants

- Product transport is the unpacked local extension in the user's real signed-in
  Chrome profile and the same Chrome window. No API or separate Playwright
  profile may substitute for this flow.
- Cortex writes only to classic ChatGPT chats. Work/business surfaces fail
  closed with `WORK_SURFACE_REJECTED`.
- At most two distinct conversations may write concurrently. A third retains
  its draft and staged file in deterministic E2E coverage and is refused in
  French before any browser action.
- Local actions stay inside the selected workspace and approval policy.
  Ambiguous browser delivery is never automatically replayed.

## Candidate work completed

- Protocol-v2 pairing, same-window tab allocation, exact route selection, FIFO
  activation and trusted send-control revalidation.
- Exact-tab CDP screenshots with serialized private masking, restoration proof
  and discard-on-uncertainty behavior.
- Durable fail-closed quarantine for uncertain writer tabs across every session
  class and extension restart.
- Exact durable pause/resume state, no second response consumer, and no pause
  during an in-flight local effect.
- Bounded, single-use file transfer; cancelled Swift compile/helper processes
  are killed and reaped.
- Install/start/uninstall share the lifecycle lock; uninstall accepts only a
  verified stopped runtime and preserves foreign resources.
- Optional Freebuff walkthrough with package pinning, source inspection,
  immutable dry-run plan and exact `APPROVE <plan_hash>` consent.

## Fresh v0.5.3 evidence

- Backend: 628/628. Extension: 126/126. Mapped crash recovery: 6/6;
  dedicated Chrome recovery/anti-replay: 6/6.
- Frontend: 155/155 unit and 33/33 runtime/privacy; typecheck, lint and build pass.
- Browser fixtures: 12 pass, one intentional guide-generation skip; a11y 4/4
  at 375, 768 and 1440 px; zero fixture console/page/hydration errors.
- Ten cold dual-writer runs: zero crossover, third draft and file retained.
  Cached usability: 231.1 ms; switch p95/max: 141.7 ms.
- Two normalized builds: 28 files each, aggregate SHA-256
  `a401609dd88bc4fc2562ffd4563c07854105f3d4c8324198ee5a712ec180666a`.
- Privacy: 329 files and 43 images. Links: 121, including 56 external. Gitleaks:
  240 commits. Audits, ShellCheck, Python, runtime and diff checks pass.
- A clean Git archive includes the extension, static chunk, Freebuff guide and
  Swift helper. Extension 126/126 and packaging 6/6 pass from that archive; its
  wheel includes the Swift source.
- Isolated macOS lifecycle: immutable plan, install, Doctor, start/status/API,
  stop, idempotent reinstall and uninstall pass without `sudo`; foreign
  sentinels are preserved and no listener remains.
- A detached self-diagnostic worktree completed install, replay refusal,
  Doctor, start/status/API/tasks, stop, reinstall and uninstall, then was
  removed without merge. Two failed evidence wrappers remain disclosed.
- Owner-authorized live technical observations already recorded for this
  candidate cover one text chat, two writers plus third refusal, one synthetic
  file, one masked screenshot and three disposable mini-sites. No account or
  conversation identity is public evidence.

## Honest release state

- Target verdict: **`OPT_IN_TECHNICAL_PREVIEW`**, never `READY`.
- Consumer-site automation conflicts with the provider's published prohibition
  on automatic/programmatic extraction. Owner approval does not remove it.
- Still unproven: truly clean macOS account/VM lifecycle; live staged-file
  preservation on third-writer refusal; real cold/warm switch under ten seconds;
  live tab-close/reload recovery without resend.
- `docs/verification/v0.5.3.json` must reference the final clean source commit
  and then be committed alone.

## Verified post-candidate fixes

- A real Cortex-only send exposed one persisted turn plus its local overlay.
- Reconciliation now requires new message identities captured at send start;
  repeated identical turns and the poll-before-accept race have regression tests.
- Pipeline truth now requires an exact conversation scope; global legacy,
  contradictory and mismatched responses fail closed without A-to-B leakage.
- Inspector is readable and French, hides idle mission controls, separates the
  global stop and distinguishes executor availability from actual use.
- Proof: 155/155 frontend, 33/33 runtime/privacy, typecheck, lint, canonical
  build, live scoped API, anonymized Chrome capture and zero console issues.
- Duplicate and inspector fixes are published on `codex/critical-qa`.
  Resealing remains independent.

## Next exact action

Keep `main` unchanged; wait for PR #13 CI. Reseal, merge, tag and release separately.
