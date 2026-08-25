# Cortex Bridge session primer

Current state: 2026-08-26. Read this file with `README.md` and
`docs/release-checklist.md`; do not infer release readiness from older v0.5.2
evidence.

## Repository

- Worktree: `.worktrees/codex-critical-qa`; branch `codex/critical-qa`.
- Canonical version: **0.5.3** in `VERSION`, Python metadata, frontend package
  and lock, Chrome manifest and installer metadata.
- Remote: `https://github.com/Jonassuhard/cortex-bridge.git`; default branch is
  `main`.
- The branch is not published. The complete source candidate is ready for its
  local pre-rebase commit; `origin/main` is four commits ahead.
- Never claim that a branch, tag, release or `main` changed without checking
  each one separately. Push, tag and release require Jonas's explicit approval.

## Product invariants

- Product transport = the unpacked local Chrome extension in the user's real
  signed-in Chrome profile and the same Chrome window. No OpenAI API and no
  separate Playwright profile may substitute for this flow.
- Cortex writes only to classic ChatGPT chats. Work/business surfaces fail
  closed with `WORK_SURFACE_REJECTED`.
- At most two distinct conversations may write concurrently. A third keeps its
  draft and is refused in French.
- Every local action remains bounded to the selected workspace and approval
  policy. Ambiguous browser delivery is never automatically replayed.

## Candidate work completed

- Extension protocol-v2 pairing, same-window tab allocation, exact route
  selection, FIFO delivery activation and trusted send-control revalidation.
- File and screenshot staging are bounded, single-use and fail closed. Private
  screenshots require a confirmed mask over navigation, sidebar and account
  areas before pixels are read.
- Mission resume recovers only one stable valid unconsumed decision after a
  read failure. Manual resume waits for an already-active loop and never starts
  a second consumer on the same response. Safe pauses restore their exact
  durable state; an in-flight local action cannot be paused mid-effect.
- Private screenshots use only exact-tab CDP capture, serialize the mask cycle
  per tab and discard pixels unless same-document restoration is attested.
  Uncertain writer tabs are durably quarantined from every session class.
- Text-only installation no longer requires Swift. The native macOS helper is
  an optional file-send capability. Child compilation/activation processes are
  killed and reaped on cancellation. Uninstall requires a verified stopped
  runtime, and start shares the installer lifecycle lock.
- `docs/freebuff-installation.md` documents Freebuff only as an optional,
  non-affiliated assistant: inspect and pin its package, show the immutable
  Cortex dry-run plan, require `APPROVE <plan_hash>`, never use `sudo` or secrets,
  and leave login, terms, extension and permissions to the human.

## Current evidence

- Last full backend baseline: 515 tests before the latest five regression
  tests. Current targeted backend/lifecycle suites and 126 extension tests
  pass. A full post-rebase rerun is still required. Frontend: 145 unit tests
  and 35 runtime/privacy tests pass; typecheck, lint and production build pass.
- Browser fixtures: 12 E2E pass, one guide-generation test is intentionally
  skipped; four accessibility tests pass at 375, 768 and 1440 pixels.
- Ten cold dual-writer fixture runs have zero crossover. Cached usability is
  154.1 ms; ten fixture switches have p95 65.6 ms and max 65.6 ms.
- Two consecutive normalized static builds contain 28 files and share aggregate
  SHA-256 `050590ee0364a13b64c0636c6279403e0cf65ff7dc50e96e89505e2e51fd546f`.
- Privacy scan passes 317 files and 42 images; links pass 117/117, including 52
  external checks; Gitleaks passes 239 commits. npm audit and pip-audit report
  zero known findings. ShellCheck and `git diff --check` pass.
- Owner-authorized live technical observations passed: one text chat, two real
  writers plus third refusal, one small synthetic file, one masked screenshot,
  and three accepted disposable mini-sites. No account or conversation identity
  is publishable evidence.
- Isolated macOS `CORTEX_HOME` install/reinstall/Doctor/start/status/stop/
  uninstall passed without `sudo`; this is not a genuinely clean account or VM.
- A wheel built from the candidate contains
  `transport/macos_ax_send.swift`; generated build metadata was kept outside
  the repository.

## Honest release state and blockers

- Target verdict remains **`OPT_IN_TECHNICAL_PREVIEW`**, never `READY`.
- Current consumer-site automation conflicts with OpenAI's published terms on
  automatic/programmatic extraction. Owner approval does not remove that
  provider blocker; an official MCP/plugin transport is the future compliant
  route and a separate architecture decision.
- Still unproven live: staged-file preservation on a refused third writer,
  real cold/warm switch under 10 seconds, tab-close recovery and self-diagnostic
  mission. A genuinely clean macOS account/VM lifecycle is also pending.
- `docs/verification/v0.5.3.json` must remain absent until the exact source
  commit is clean. The evidence manifest then needs its own commit.

## Next exact action

Create the complete local source commit (including all three previously
untracked release files), rebase onto `origin/main`, rerun every final gate,
then generate and validate `docs/verification/v0.5.3.json`.
