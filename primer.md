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
- Desktop supervisor protocol is documented in
  `docs/CHATGPT_SUPERVISOR_PROTOCOL.md`: Codex prepares a bounded context
  packet, asks ChatGPT for the path, and reports only verified local actions;
  the mission runtime now validates and injects an optional packet.

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

## Current verification state
The last sealed commit is pushed at `821fddd` on `codex/v061-atelier`; the
working tree now contains uncommitted context-proposal hardening and related
test updates. ChatGPT Pro reviewed the sanitized production archive plus
`orchestration/runner.py` and returned READY on the listed invariants, based
on static inspection only.
The candidate remains a technical preview; `main` is intentionally not
integrated while provider-backed and clean-install gates remain unresolved.

## Current verification
The synthetic `cortex-context-request.v1` flow was inspected in the local UI:
three proposals render, per-item approve/reject actions are readable, and the
state transitions are visible. A deterministic demo-clock fix removed the
hydration mismatch found during that inspection. Do not send a real file,
screenshot or link until the desktop ChatGPT attachment capability is
explicitly exposed.
The latest local run passes 746 Python tests, 214 Vitest tests and 33 runtime
tests, alongside TypeScript typecheck, Oxlint, the lint-contract fixtures and
a production Next build. The fresh Playwright export
passes 26 browser tests with one optional guide test skipped, the responsive
collision suite passes at 375/768/1024/1440, offline links pass 133 checks,
and public privacy passes on 428 files and 92 images. The supervisor
prompt/report formatters are pure and explicitly surface the desktop
attachment boundary.
Historical
runtime/privacy, browser, accessibility and npm-audit evidence remains in the
verification documents; it does not prove the desktop attachment capability.
The local `~/.local/bin/cortex` launcher points to this candidate only.
Real-interface preflight is recorded in docs/live-acceptance-v061.md.
The terminal startup interpreter and full-screen quit paths are corrected; the
focused terminal/TUI checks pass, and a fresh PTY launch now exits with code 0
on `Ctrl-Q`. A disposable hash-approved install/doctor/uninstall lifecycle
also passes; this is not evidence from a clean macOS account. The installed
runtime was then repaired through the manifest-scoped uninstall/reinstall path;
its helper hash, Accessibilité check, backend start/status/API/stop cycle now
pass as well. The candidate
extension now pairs in the real Chrome window;
the 2026-09-10 real-profile selftest reported `paired`, found a ChatGPT
composer, and switched one conversation without sending a new message;
one text message sent through Cortex was confirmed in 9.6 s and one screenshot
transfer through the Cortex capture button completed as run
`8fb810edbea04d32b6889045563d319f` with a 7.7 s observed UI latency. The
native helper correction is covered by nine focused driver checks and a Swift
permission check. The runtime still reports the local Ollama engine as a
candidate, not a verified executor. A SQLite ResourceWarning remains observed.
Live arbitrary-file, mission, two-conversation isolation, clean-install and
main-integration gates remain open. The recent Cortex-only file attempt failed
closed with `PRE_DELIVERY_NOT_READY` because the ChatGPT composer was not clean
and stable; no file delivery is claimed. See
docs/verification-v061.md and docs/PLAN_WEB_TUI_LUNA.md. Keep dependency changes
in this candidate PR; do not merge while the remaining release gates are incomplete.

The desktop supervisor proposal is documented and the bounded packet is wired
into the mission contract. Codex can read and write exposed ChatGPT/Codex
tasks, while Cortex still uses its own mission transport. Desktop file
attachments require an explicit application capability; no silent full-disk
handoff is implemented. ChatGPT context proposals now have a strict
`cortex-context-request.v1` parser, a French per-item approval card, and
`POST /api/chat/approve-context`; files are reconfined to the selected
workspace and links/screenshot targets are bounded before transport.
Context approvals now also reject unknown item fields with Pydantic
`extra="forbid"`; the regression is covered by `tests/test_context_approval.py`.

## Next action
- Reconcile the current diff into a deliberate commit after reviewing the
  remaining user-owned UI/docs changes; do not push or merge without explicit
  authorization.
- npm scripts remain blocked by the local npm `11.11.1` versus repository
  requirement `11.18.0`; direct installed binaries were used for frontend
  verification without changing dependencies.
