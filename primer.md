# Cortex Bridge project primer

## Source candidate
- Version: 0.6.1. Technical preview; not a verified live or installed release.
- Public repository: linked from README.md.
- Primary branch: main. Candidate branch: codex/v061-atelier.
- See README.md, docs/verification-v061.md and CHANGELOG.md for current evidence.

## Implemented
- Atelier conversation layout, geometric project card and task states.
- Optional French full-screen CORTEX terminal on the shared FastAPI backend;
  `--plain` keeps the line-oriented compatibility client.
- Conversation history, replies, delivery acknowledgement and isolated drafts.
- Workspace selection, mission preflight, current-action approvals and scoped stop.
- Public use-case diagrams, terminal guide and historical benchmark context.
- Textual 8.2.8 is locked and the `tui` package is included in the wheel.

## Invariants
- No silent transport fallback, automatic resend or fabricated completion.
- At most two active writing conversation leases.
- Terminal drafts are in-memory, not persisted across exits.
- Expected action identity is required for terminal approval.
- Real ChatGPT/account, clean installation and provider acceptance are separate gates.

## Current publication work
- All changes stay in the independent candidate; the original local checkout
  and installed runtime must not be modified.
- User authorized commit/push and main integration if the gates permit it.
- Local dependency upgrades/installations were approved and applied.
- Primary-branch integration is blocked while dependency or verification gates fail.
- Public reports must not include personal paths, account details or private records.
- Local session details, if present, are retained in ignored docs/LOCAL_SESSION_V061.md.

## Next action
Run the release/installation gates against the current candidate, then request
explicit publication approval. The 81-test terminal/TUI slice and the 718-test
Python suite pass; frontend unit/runtime, typecheck, lint and static build pass.
The local `~/.local/bin/cortex` launcher points to this candidate only.
Real-interface preflight is recorded in docs/live-acceptance-v061.md.
The terminal startup interpreter bug is corrected locally; 73 terminal tests
pass. GUI pairing works, but the selected ChatGPT Settings modal triggered a
false-positive limitation. Detector and explicit Settings/Work corrections pass
138 extension, 40 driver and 10 onboarding fixtures; independent review passes.
Live replay requires the user to load/reload the candidate Chrome extension.
Provide current, truthful installation and live release evidence
before main integration. The initial full backend run had 708 tests and three
uninstall failures caused by fixture port collision with the running QA app.
After fixture isolation, the fresh complete suite passes 710 tests in 165.449 s.
A SQLite ResourceWarning remains observed. These are not live acceptance. The
frontend baseline has 207 unit/runtime tests plus typecheck, lint and build; npm
audit passes with zero findings. Live ChatGPT, file/screenshot, mission,
clean-install, release-evidence and main-integration gates remain open. See
docs/verification-v061.md and docs/PLAN_WEB_TUI_LUNA.md. Keep dependency changes
in this candidate PR; do not merge while the remaining release gates are incomplete.
