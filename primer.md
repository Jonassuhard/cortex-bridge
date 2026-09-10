# Cortex Bridge project primer

## Source candidate
- Version: 0.6.1. Technical preview; all offline release gates pass, while
  provider terms and clean-install lifecycle remain explicit blockers.
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
- Managed runtime repair compares the lock hash and safely replaces only an
  owned stale virtualenv; executor UI distinguishes candidate from verified.
- Conversation rows expose Pinned, Project and Recent categories without
  inventing unknown metadata.

## Invariants
- No silent transport fallback, automatic resend or fabricated completion.
- At most two active writing conversation leases.
- Terminal drafts are in-memory, not persisted across exits.
- Expected action identity is required for terminal approval.
- Real ChatGPT/account, clean installation and provider acceptance are separate gates.
- A paired extension, healthy Ollama process or discovered model is not proof
  that an executor has run.

## Current publication work
- All changes stay in the independent candidate; the original local checkout
  and installed runtime must not be modified.
- Dependency upgrades/installations are applied and the complete local gate is green.
- The candidate may be tagged as a technical preview; primary-branch integration
  remains blocked while provider and clean-install gates are unavailable.
- Public reports must not include personal paths, account details or private records.
- Local session details, if present, are retained in ignored docs/LOCAL_SESSION_V061.md.

## Next action
Seal the final evidence commit, push the candidate branch and technical-preview
tag, then repair and republish the portfolio dependency baseline.
The 81-test terminal/TUI slice and the 724-test Python suite pass; frontend 207
unit tests, 36 runtime/privacy tests, typecheck, lint, build, 26 browser tests,
4 accessibility tests and npm audit pass.
The local `~/.local/bin/cortex` launcher points to this candidate only.
Real-interface preflight is recorded in docs/live-acceptance-v061.md.
The terminal startup interpreter bug is corrected locally; focused terminal and
TUI checks pass. The candidate extension now pairs in the real Chrome window;
one text message sent through Cortex was confirmed in 9.6 s and one screenshot
transfer through the Cortex capture button completed as run
`8fb810edbea04d32b6889045563d319f` with a 7.7 s observed UI latency. The
native helper correction is covered by nine focused driver checks and a Swift
permission check. The runtime still reports the local Ollama engine as a
candidate, not a verified executor. A SQLite ResourceWarning remains observed.
Live arbitrary-file, mission, two-conversation isolation, clean-install,
release-evidence and main-integration gates remain open. See
docs/verification-v061.md and docs/PLAN_WEB_TUI_LUNA.md. Keep dependency changes
in this candidate PR; do not merge while the remaining release gates are incomplete.
