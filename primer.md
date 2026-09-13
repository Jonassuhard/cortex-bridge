# Cortex Bridge project primer

## Source candidate
- Version: 0.6.5 unfinished preview, published by explicit user request.
  PREVIEW_V065.md records open gates; this is not a stable-release validation.
- Public repository: linked from README.md.
- Primary branch: main. Candidate branch: codex/v061-atelier.
- See PREVIEW_V065.md for publication checks/open gates; original private plans retained locally. Storage session9a300392ca7149bfaa9adc188db16ae7.

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
- The candidate commit `cf1dac81d018a3b8a3b2acf1dd3d9e726bbb17ec` is now pushed
  to the public `codex/v061-atelier` branch. `main` remains unchanged.
- Primary-branch integration remains blocked while provider and clean-install
  gates are unavailable.
- Public reports must not include personal paths, account details or private records.
- Local session details, if present, are retained in ignored docs/LOCAL_SESSION_V061.md.

## Current verification state
The sealed commit `cf1dac81d018a3b8a3b2acf1dd3d9e726bbb17ec` is pushed on
`codex/v061-atelier`; that baseline was clean. Current 0.6.5 work is uncommitted.
ChatGPT Pro reviewed the
sanitized production archive plus `orchestration/runner.py` and returned READY
on the listed invariants, based on static inspection only.
The candidate remains a technical preview; `main` is intentionally not
integrated while provider-backed and clean-install gates remain unresolved.

## Current verification
The synthetic `cortex-context-request.v1` flow was inspected in the local UI:
three proposals render, per-item approve/reject actions are readable, and the
state transitions are visible. A deterministic demo-clock fix removed the
hydration mismatch found during that inspection. Do not send a real file,
screenshot or link through an unsupported desktop capability. The user later
authorized a separate Chrome attachment channel for 0.6.5 (see below).
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
- Active 0.6.5 work: see PLAN_V065.md and V065_TESTS_BENCHMARK.md.
  The user authorizes stepwise implementation and technical validation; stop on
  major errors or material changes. First gate: real desktop text/attachments.
  T01 desktop text round trip PASS. The user authorized the Chrome attachment
  channel; T02 document and T03/T04 image/ZIP delivery/read PASS.
  artifacts.py and agent CLI implemented; 22 new and 8 existing tests PASS.
  CLI --goal connects frozen file hashes/sizes to the existing context packet.
  Runner persists outbound attempts before sending; definitive pre-send aborts
  permit retry, uncertain sends do not. Six recovery and seven runner tests PASS.
  Full backend 771 PASS before the final abort/cross-payload increment.
  Fresh full backend run: 766 tests PASS (165.966 s); SQLite warning remains.
  HARNESS_V065.md is the operator guide; full integration remains incomplete.
  Native macOS file picker succeeded; injected chooser stalled. Require
  last-message continuity across desktop/browser, not just the same URL.
  Reload restored the latest desktop review; permanent branch divergence is
  not established. Never resend solely because a read has not caught up.
  Supervisor reviewed the four-source archive in response
  [private receipt ID retained locally]. Checkpoint, technical mission marker
  and strict two-observation resume reconciliation are now implemented.
  Focused checks: 10 runner, 8 recovery, 15 mission API tests PASS (fixtures).
  Full backend rerun: 779 tests PASS, 167.522 s; SQLite warning still open.
  No fresh live mission or release claim.
  Organizer pilot correction received/applied separately; 11 functional and
  4 safety checks PASS on explicit physical root. Default /var path FAIL
  (system symlink); preserved, not silently resolved. Complete README received.
  Local pilot/evidence pointer: .qa-live-v061/v065-organizer-pilot/PILOT.md.
  Native instruction bundle added: cortex-supervisor/SKILL.md, installer and
  SUPERVISOR_INSTALL.md; 3 isolated installation tests PASS, no global install.
  Official skill validator PASS using existing cached PyYAML, no installation.
  Real Codex CLI discovers installed skill in isolated CODEX_HOME; no model call.
  Native journal/JSON CLI implemented on existing Store; 4 native, 8 recovery,
  32 store checks PASS. Fixed CLI-triggered startup recovery pausing missions.
  Full backend 786 PASS, 168.397 s; then six focused native tests PASS.
  Real journal round trip PASS; user [private receipt ID retained locally],
  ACK [private receipt ID retained locally]; no duplicate after reopen.
  Installed skill now bundles stdlib journal helper; Python -I outside checkout
  verifies init/status. Three installer + six native tests and validator PASS.
  Installed artifact helper now tested with Python -I outside checkout: actual
  ZIP bytes/hashes/context packet and non-delivered state verified. 39 targeted
  tests PASS, official skill validator and git diff --check PASS.
  Native action reservation/receipt CLI added on existing tool_executions.
  45 targeted tests PASS, including real process exit after file creation before
  receipt; replay refused, observed exit 17 retained as failure, not success.
  Installed action workflow verified outside checkout: real subprocess file,
  observed exit/hash receipt, no replay. Fresh full backend 792 PASS, 173.061 s;
  existing SQLite ResourceWarning remains. Skill validator PASS.
  Live installed pilot code received/executed unchanged: six checks PASS, two
  evaluator stream-assumption FAIL preserved/reported. 179 vs <150 lines.
  Evidence .qa-live-v061/INSTALLED_LIVE.md; follow-up receipt remains pending.
  Concrete gap: apply_patch has no integer exit; action contract must support
  actual non-process host receipts, not invent exit0. No full workflow claim.
  Follow-up reconciled by two native reads; brain identified real line/path gaps.
  Non-process receipt contract now implemented, kind fixed before effect and
  exit_code null. Actual apply_patch+readback probe PASS; 46 targeted tests PASS.
  Corrected inventory pilot 148 lines, 8/8 frozen checks PASS plus lexical ..
  refusal. Original FAIL/code/evaluator preserved; corrections operator-labelled.
  Final report sent via installed message helper, receipt pending.
  Lifecycle implemented: verified archive uninstall/prepared replacement,
  owned-byte receipt, no deletion. Nine tests PASS; actual isolated Codex CLI
  discovers before and not after archival. .qa-live-v061/SUPERVISOR_LIFECYCLE.md.
  Explicit activation recovery implemented: fresh plan, absent target, intact
  copies required. Twelve tests PASS including process exit17 after first move,
  reappearing target and mutated candidate refusals. No power-loss claim.
  Task B preflight reconciled; reference PNG rendered and inspected. Actual
  brief/image received and read: reply [private receipt ID retained locally].
  Injected image upload stalled; native picker succeeded. No duplicate sent.
  Installed receipt confirmation FAIL: host text changes paragraph breaks and
  adds attachment summaries. Pending send retained; do not resend or normalize
  evidence silently. See .qa-live-v061/BOARD_CONTEXT.md. 23 targeted tests PASS.
  Explicit confirm_rendered now implemented; raw receipt retained, narrow
  boundary grammar only, content hashes unchanged. 34 focused tests PASS.
  Two fresh real reads reconcile the task-B message with updated checkout
  helper; original strict FAIL retained. Installed snapshot unchanged.
  Task-B request reconciled; response [private receipt ID retained locally]
  truncated at 20k host limit. No partial code executed. Requested unchanged
  JS chunk: pending [private receipt ID retained locally], do not resend.
  Complete JS received, request reconciled. Initial board copied unchanged;
  10/10 real browser scenarios PASS, screenshots 375/768/1440 inspected.
  Proof .qa-live-v061/board-pilot/PILOT.md. README received/reconciled;
  boundaries and keyboard: 14/14 browser checks PASS, unchanged application.
  Focus root cause rAF steals Tab target: controlled FAIL->PASS, regression18/18PASS.
  Freebuff GLM5.3Flash UI smoke PASS; unchanged script passes independent3/3.
  Live bound normalizer4/4PASS; final review reconciled. Prior full829PASS,173.455s.
  Installed skill aligned; isolated bound workflow and81 targetedPASS,5.059s; validatorPASS.
  Eight chats authorized; two-chat recall/scoped-stop PASS, no pending sends;39 regressionPASS. Evidence .qa-live-v061/LIVE_ISOLATION.md. Next: six benchmark chats; privacy/generated-string finding retained.
- Run the remaining live/provider-backed acceptance gates in a fresh macOS
  environment; do not merge into `main` until those gates have evidence.
- npm scripts remain blocked by the local npm `11.11.1` versus repository
  requirement `11.18.0`; direct installed binaries were used for frontend
  verification without changing dependencies.
