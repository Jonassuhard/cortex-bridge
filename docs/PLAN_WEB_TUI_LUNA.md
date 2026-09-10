# Cortex Web + terminal delivery plan

> For agentic workers: implement only after the owner approves execution. Use
> `superpowers:executing-plans` or `superpowers:subagent-driven-development`.
> Read this complete specification before accepting one lot. Checkboxes are
> implementation status; the execution addendum and verification document carry
> the command-level evidence. This document does not authorize push,
> dependency installation, account access or permission changes by itself.

**Goal:** Make `cortex` launch a polished, full-screen terminal; finish the Chrome
Atelier interface; let both interfaces use the same verified ChatGPT planner,
selected supported execution engine, conversations, approvals and evidence.

**Architecture:** Keep one local FastAPI backend and the existing Chrome
extension. Add a nonblocking Python TUI rather than a second orchestration engine.
The backend owns identity, permissions, write slots and mission state. Each UI
owns focus, layout and drafts, not authoritative execution success.

**Tech stack:** existing Python >=3.11 and React/Next; Textual 8.2.8 is now
locked and packaged for the candidate. The execution status below distinguishes
what is implemented from the remaining live gates.

**Spec:** sections 1–5 of this document. Sections 6–11 are the implementation and
acceptance plan. Authored 2026-09-10, inspected candidate commit `7219fe4`.

## Execution status — 2026-09-10

The coordinator has executed the first implementation slice in this candidate:

- `textual==8.2.8` is locked in `requirements.lock`, the `tui` package is
  included in the wheel metadata, and the candidate virtualenv imports it.
- `scripts/cortex` now opens the full-screen TUI by default; `--plain` keeps the
  old line client explicit. The TUI has side-by-side ChatGPT/executor state,
  bounded 50-item conversation list, background API workers, draft preservation,
  explicit send acknowledgement and a connect/retry action.
- The focused terminal/TUI slice is 81 passing tests. The complete Python suite
  is 720 passing tests. Frontend checks are 207 unit/runtime tests, typecheck,
  lint contract, and static build. These are fixture/local proofs, not signed-in
  ChatGPT delivery or a clean user installation.
- No model-backed executor was invented: the TUI exposes the deterministic local
  tools as the only verified executor until an adapter passes the contract. A
  healthy Ollama/model pair is a candidate signal only; the UI says so until a
  real executor run records its model and kind.

The live Chrome pairing and one real text delivery now pass in the candidate
profile. Open gates remain: fresh-shell installation on a clean home, real
file/screenshot and mission runs, multi-conversation signed-in isolation, and
any authorized publication to `main`.

## 1. Actual starting point and assessment

| Requirement | Observed source/evidence | Work still required |
| --- | --- | --- |
| Terminal | `console/terminal_app.py` uses `input_fn("cortex> ")` and printed lines | Real TUI, not more ASCII decoration |
| Command | `pyproject.toml` declares `cortex = terminal_cli:main`; `scripts/cortex` works | A verified user installation, stable path and fresh-shell discovery |
| Web | Existing Atelier components and static build | Live connection, finishing layout, state accuracy and usability |
| Planner selection | `console/settings.py` exposes ChatGPT discovery/selection | Observe actual selected model and reasoning setting, reject unsupported choices |
| Executor selection | `console/missions.py` rejects non-deterministic `executor_kind`; legacy primary/fallback fields are ignored | Real supported adapter integration; a selector alone is insufficient |
| Freebuff | Installed local launcher delegates to a cached binary | Verify supported integration surface, license/source availability, cancellation and result protocol; do not claim source audit |
| Connection | False quota, Settings/Work and startup fixes committed | Replay loaded extension against corrected backend; distinguish pairing from readiness |
| Tests | Prior run: 710 Python, 138 extension; frontend baseline: 207 unit, 36 runtime, 26 browser + 1 skip | Re-run affected tests on new bytes; complete real user workflows |
| Release | Missing 0.6.1 evidence manifest; no completed new multi-model missions | Clean macOS lifecycle, real evidence and main publication |

The request is coherent, but contains three deliverables: usability, transport
reliability, and execution-model integration. Complete them in that order of
dependency, not by hiding missing integration behind a polished screen.

Recent session observation: a fresh ChatGPT page opened on Work; it was switched
to Chat using the visible radio. Old Settings/Work tabs were closed with owner
authorization. This does not prove a successful Cortex message or mission.

## 2. Final product contract

### 2.1 Launch and setup

- `cortex` from a newly opened terminal outside the repository opens the TUI.
- `cortex ui` opens the Web interface; `cortex --plain` retains the old CLI for
  diagnostics/accessibility; `--help` and `--version` work offline.
- Default launch may start the owned local backend after the installation's
  saved startup consent. Before first consent, show a start confirmation.
- Never start or stop a foreign listener, duplicate daemon, or other checkout.
- No user-facing command needs `cd`, `CORTEX_HOME` or a development path.
- First setup has three screens: ChatGPT connection, planner/executor choices,
  then workspace/permission summary. Login and extension permissions remain
  genuine human steps, not counted as fictitious one-click automation.
- Returning user: saved profile -> select/reuse conversation -> type. Target
  <=3 activation actions before typing, excluding text entry and external login.
- External disk absent: name the missing configured volume and offer retry or
  explicit reconfiguration. Do not silently move runtime data onto the internal disk.

### 2.2 Web and TUI layout

Shared hierarchy: compact CORTEX identity; planner and executor status side by
side; central transcript; bounded composer; small model/workspace/attachment
controls; diagnostics hidden behind a labelled control.

Web: retain Atelier rather than rebuilding it. Sidebar groups are Pinned,
Projects and Recent, translated in the French UI; source metadata determines
membership. Missing category or message count is unknown, not inferred as zero.
Load at most 50 recent unique conversations; pin/project labels apply within
that bounded set until a different product rule is approved. Deduplicate IDs.
Deletion in ChatGPT removes the item after authoritative reconciliation; a
failed or partial fetch must not erase the list. Never write directly to ChatGPT
storage to fabricate categories.

Collapsed sidebar: unambiguous expand button, conversation access and new chat;
no duplicate mission-creation controls. Keep active mission and selected
conversation visually distinct. Add the missing A-running/B-selected regression.

TUI: full screen, fixed composer, scrollable transcript, spaced sections,
responsive model cards, modal settings and command palette. CORTEX banner is
compact at 80 columns and larger at >=120, never overflowing horizontally.
Show a one-line identity during conversation, not the giant launch banner.
Use original Cortex colors/tokens, not Freebuff branding or its green identity.

Controls: Tab/Shift-Tab focus, arrows in menus, Enter confirms selection, Escape
closes the current modal and restores focus. Composer Enter sends only outside
multiline/paste handling; provide visible Send button/shortcut. Test actual
Terminal.app escape sequences before promising Shift-Enter behavior. Pasted
multiline text must never submit by itself. Ctrl-C must not cancel a mission
implicitly; explicit Stop targets the selected activity. Restore terminal mode
and cursor on exit/crash. Plain mode remains available if terminal capabilities
are insufficient; explain the fallback instead of silently claiming TUI success.

### 2.3 Modes, models and context

Default typing is verbatim chat. Offer a clear Execute action in the same
composer, not a separate competing mission tab. Optional intent suggestions may
ask whether to execute, but must not silently rewrite ordinary chat, grant
permissions or send hidden extra messages. Automatic intent routing is not a
prerequisite for this release; explicit Execute satisfies an unambiguous flow.

Planner selector: discovered ChatGPT model, supported reasoning levels,
selection-pending/error states, observed current value. Executor selector:
installed supported engines, connection/availability, observed model and
capabilities. Show deterministic tools honestly as tools, not an LLM.

Selected, available, verified and actually used are separate fields. Show unknown
quotas as unknown. Do not hardcode screenshot prices, model lists, quotas or
"unlimited" claims. An unavailable option can be explained but cannot start a run.

Changing models applies to future actions. During execution, queue a requested
change for a safe checkpoint or require stop/confirmation. Snapshot each mission's
planner/executor configuration; never silently change an active run. A handoff
packet contains objective, permitted workspace, constraints, verified artifacts,
pending action and unresolved errors—not invented reasoning or hidden chain of thought.

### 2.4 State and feedback

Connection states: disconnected, connecting, needs-login, needs-extension,
needs-pairing, ui-blocker, provider-limited, ready, error. Readiness requires a
fresh valid classic Chat probe, not just an open WebSocket.

Message states: draft, submitting, queued, delivered, responding, done, failed,
uncertain. Queued is not delivered. Timeout after submission is uncertain and
must not cause an automatic resend. Keep the submitted text visible with its
status; reconcile IDs instead of deleting and recreating message blocks.

Separate actual provider wait from local UI latency. Show elapsed time, no fake
percentage. After 10 seconds of unsuccessful connection, show a useful explanation
and recovery action; do not claim the provider always responds within 10 seconds.
Animations are small, tied to state, disabled by reduced-motion preference.
Errors never disappear behind a spinner. Logs and technical details are expandable.

### 2.5 Shared safety and data

- Two active writing conversation leases maximum across Web and TUI combined;
  idle read-only navigation does not permanently consume a slot.
- Enforce approvals and workspace boundaries in the backend, not only UI.
- A network-enabled or unrestricted executor cannot be labelled network-off.
  Exclude it from that profile if the boundary cannot be enforced.
- Escape terminal ANSI/OSC/control sequences from model text, paths and logs;
  do not render untrusted Rich markup. No clipboard escape sequences.
- Profiles contain IDs/settings, never credentials. Draft persistence requires
  a retention/clear control and protected local storage; do not write drafts to Git.
- Attachments/captures have preview and explicit send; separate selected filename
  from confirmed provider upload. Display configured local size limits accurately,
  not an invented ChatGPT limit. Test limits using fixtures, not a huge paid upload.
- No original checkout modification, production migration or publishing personal
  screenshots. Windows native validation remains deferred and labelled unverified.

## 3. Proposed shared interfaces (new, not existing endpoints)

Lot 0 freezes these interfaces before clients implement them. Existing routes
remain backwards compatible. Do not replace the working API merely for uniformity.

| Existing route | Consumer use |
| --- | --- |
| GET /api/settings; PUT /api/settings | Existing settings, preserving unrelated values |
| GET/PUT /api/models/chatgpt | Planner discovery and confirmed selection |
| GET /api/models/ollama | Legacy discovery only; not proof of mission integration |
| POST /api/chrome-extension/open; POST /api/chrome-extension/retry | Shared connection lifecycle |
| GET /api/conversations/snapshot | Selected transcript |
| POST /api/chat/send | Verbatim text submission |
| GET /api/chat/runs/{run_id}/events | Run events; use existing transport semantics |
| POST /api/chat/attachments; POST /api/chat/send-with-attachment | File flow |
| POST /api/chat/send-screenshot | Explicit capture flow |

New additive contract proposal:

```python
# console/session_contract.py — proposed pure model, NOT implemented by this plan
from dataclasses import dataclass
from enum import Enum

class Delivery(str, Enum):
    DRAFT = "draft"
    SUBMITTING = "submitting"
    QUEUED = "queued"
    DELIVERED = "delivered"
    FAILED = "failed"
    UNCERTAIN = "uncertain"

@dataclass(frozen=True)
class Choice:
    selected_id: str | None
    observed_id: str | None
    verified: bool

    @property
    def matches(self) -> bool:
        return bool(self.verified and self.selected_id
                    and self.selected_id == self.observed_id)

def automatic_resend_allowed(state: Delivery) -> bool:
    # User can explicitly submit a NEW request; reconnect never resends one.
    return False
```

```python
# tests/test_session_contract.py — red before creation of the module above
import unittest
from console.session_contract import Choice, Delivery, automatic_resend_allowed

class SessionContractTest(unittest.TestCase):
    def test_selected_is_not_observed(self):
        self.assertFalse(Choice("planner-a", None, False).matches)
        self.assertFalse(Choice("planner-a", "planner-b", True).matches)
        self.assertTrue(Choice("planner-a", "planner-a", True).matches)

    def test_reconnect_never_replays_submission(self):
        for state in Delivery:
            with self.subTest(state=state):
                self.assertFalse(automatic_resend_allowed(state))
```

The function is a guard specification, not a resend feature. Add integration
assertions on actual POST count; a pure helper alone cannot prove no duplication.

New `/api/executors` GET response: `schema_version: 1`, `items`, each with `id`,
`label`, `available`, `reason`, `models`, `capabilities`, `verification_source`.
Capabilities: `files`, `processes`, `network_boundary`, `cancel`, `structured_results`.
No credential fields. Unverified adapters return available=false with a reason.

New `/api/profiles` GET/POST and `/api/profiles/{id}` PUT use server-generated ID,
revision, name, planner ID/effort, executor ID/model, workspace and policy profile.
Reject stale revision (409), unsupported values (422), unauthorized paths (403).
Saving a profile never submits a mission. Mission construction resolves the
saved profile into an immutable execution snapshot. Retain legacy payload support.

## 4. Executor contract and scope

```python
# executor/adapters/base.py — proposed adapter boundary
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class ExecutionRequest:
    run_id: str
    action_id: str
    workspace: str
    objective: str
    model_id: str | None
    policy_profile: str
    deadline_seconds: float

@dataclass(frozen=True)
class ExecutionResult:
    run_id: str
    action_id: str
    status: str  # succeeded, failed, cancelled, uncertain; validate at boundary
    observed_model_id: str | None
    artifact_paths: tuple[str, ...]
    error_code: str | None

class ExecutorAdapter(Protocol):
    async def execute(self, request: ExecutionRequest) -> ExecutionResult: ...
    async def cancel(self, run_id: str) -> bool: ...
```

Registry lookup, capability checks and existing policy/approval checks happen
BEFORE invoking an adapter. Adapter output is untrusted: validate IDs, statuses,
paths, actual artifacts, timeout and cancellation. A success sentence is not proof.
Do not expose raw shell arguments from an untrusted model directly to subprocess.

Deliver deterministic adapter plus at least one genuinely working model-backed
adapter before claiming selectable LLM execution. Prefer supported local interfaces
already available. Freebuff is a separate feasibility gate: supported invocation,
interactive/noninteractive I/O, auth, termination, results, limits, license. No
unsupported screen-scrape daemon or tool-policy workaround. If Freebuff cannot
provide the contract, document that result; do not mark the model-executor goal
complete merely because deterministic tools still work.

## 5. Ownership and execution order

All agents use the approved independent candidate. Read primer, local project
instructions and Storage protocol; open/close targeted sessions. Do not overwrite
other workers. No push without coordinator release approval. Luna is the requested
worker model; review cannot be replaced by an implementer's own PASS statement.

| Lot | Owner | Exclusive writes |
| --- | --- | --- |
| 0 + 8 | Coordinator | Shared contracts, packaging/dependency files, route registration, main integration |
| 1 | Luna connection | chrome-extension/* production/tests; transport/browser_chrome_extension.py; console/onboarding.py; corresponding existing tests |
| 2 | Luna backend | console/profiles.py, console/executor_registry.py, console/session_contract.py, console/missions.py, new profile/contract tests |
| 3 | Luna adapters | executor/adapters/, tests/test_executor_adapters.py |
| 4 | Luna TUI | console/tui/, tests/test_tui_*.py, console/terminal_cli.py, tests/test_terminal_cli.py |
| 5 | Luna Web | frontend/components/, frontend/hooks/, frontend/lib/, frontend/e2e/; no package files |
| 6 | Luna installation | console/installer.py, scripts/install.sh, scripts/cortex, installation tests, docs/installation-terminal.md |
| 7 | Luna QA | tests/acceptance/, docs/ACCEPTANCE_WEB_TUI.md, sanitized proof assets only |

Sequence: Lot 0 -> Lot 1 and contract-backed Lots 2/3 -> Lots 4/5 -> Lot 6 -> Lot 7
-> Lot 8. With limited slots: run connection, adapters and coordinator first;
then TUI and Web in parallel against frozen contracts. Never have Lot 2 and the
coordinator edit session_contract.py simultaneously: coordinator hands ownership
to Lot 2 once contract review is accepted. Every shared-file handoff is explicit.

## 6. Implementation lots and delivery gates

Every lot follows RED -> minimal implementation -> focused GREEN -> independent
read-only review -> commit when authorized. Record exact commands, exit codes,
commit/diff hash, failures and limitations. A test count is not a benchmark.

### Lot 0 — Freeze interfaces and validate TUI foundation

- [x] Revalidate Git state and current runtime; do not assume old proofs describe
  the running instance. Read existing client/controller boundaries.
- [ ] Add failing `tests/test_session_contract.py` above; freeze profile/executor
  schemas and a JSON fixture shared by Python/TypeScript tests.
- [x] Check a locked Textual version in a disposable environment with Python 3.11
  and the candidate interpreter. Confirm wheel includes TUI package and style assets.
- [ ] Implement pure contract above; command:
  `.venv/bin/python -m unittest tests.test_session_contract -v`.
- [x] Prototype resize + keyboard + nonblocking delayed request before adopting
  Textual. Only coordinator edits pyproject.toml and requirements.lock.

Delivery: approved schema examples, dependency audit, failing-then-passing contract
tests, installation/import proof outside checkout. No permanent dependency selected
only because a screenshot looks good.

### Lot 1 — Finish actual Chrome connection

- [ ] Reproduce fresh home Chat, home Work, Settings, marketing /work/extension/installed,
  logged-out screen, genuine active quota banner and an old conversation mentioning limits.
- [ ] Add fixtures before code. Existing settings false-positive tests must stay green.
- [ ] Select the explicit paired tab where valid; otherwise offer a visible valid
  Chat target or a new Chat tab. Avoid silently selecting arbitrary user history.
- [ ] Verify content-script freshness after extension reload/page navigation.
  An extension version label alone does not prove loaded content-script bytes.
- [ ] Make manual blockers immediate, and display useful recovery within 10 seconds.
  Do not interpret pairing as ready, dismiss provider challenges, or bypass login.
- [ ] Run `node --test chrome-extension/tests/extension.test.mjs` and
  `.venv/bin/python -m unittest tests.test_chrome_extension_driver tests.test_chrome_connection_api -v`.
- [ ] Execute C01/C02 below from Cortex; inspect ChatGPT read-only for confirmation.

Delivery: actual connection and one confirmed text round-trip in Chrome, fresh
extension/backend provenance, clear failure cases, zero sends outside Cortex.

### Lot 2 — Shared profiles, truth and context

- [ ] Create profile/registry modules above; add route registration through coordinator.
- [ ] RED tests: missing observed model, stale profile revision, unsupported executor,
  changing global defaults during a mission, two concurrent clients requesting a third lease.
- [ ] Preserve settings merge semantics and existing approval action identity.
- [ ] Implement immutable per-mission profile, checkpoint handoff and persisted
  profile preferences without tokens. Do not automatically switch execution engines.
- [ ] Test malformed IDs, stale events, connection-ready but no composer, nonmatching
  model observations, failed cancellation and partial artifact reports.
- [ ] Run `.venv/bin/python -m unittest tests.test_session_contract tests.test_profiles tests.test_executor_registry tests.test_missions_api tests.test_terminal_settings -v`.

Delivery: both clients consume the same state; selected vs used is distinguishable;
model change cannot alter a running action; third writer is refused globally.

### Lot 3 — Model-backed execution

- [ ] Write registry/fake-adapter tests for denied policy, unsupported capabilities,
  timeout, wrong run/action ID, output outside workspace and uncertain cancellation.
- [ ] Implement deterministic wrapper preserving current behavior.
- [ ] Evaluate Freebuff with a harmless synthetic request using its supported
  interface. Do not use it to implement the requested QA artifacts behind Cortex.
- [ ] Implement one supported model-backed adapter and wire it via Lot 2 registry.
  Verify actual model provenance; do not label planner diversity executor diversity.
- [ ] Run `.venv/bin/python -m unittest tests.test_executor_adapters -v` and C03/C04
  through each UI with that adapter, verifying artifacts independently.

Delivery: actual selected adapter executes; cancellation and constraints are proven;
Freebuff integration is PASS/FAIL/UNCLEAR with evidence, not a marketing label.

### Lot 4 — Full-screen TUI

Create `console/tui/__init__.py`, `app.py`, `state.py`, `controller.py`,
`screens.py`, `widgets.py`, `app.tcss`. Keep rendering separate from API calls.

- [x] RED headless tests: composer visible at 80x24; modal Escape restores draft;
  delayed API does not freeze keyboard; model selection not marked applied early.
- [x] Build CORTEX welcome, compact status strip, transcript and bounded composer.
- [x] Bind typed actions to ApiClient; run blocking urllib calls off UI thread,
  marshal events back through Textual workers/messages. No second backend.
- [ ] Add setup/profile/model/workspace modals, attachments with preview, history,
  approvals and explicit Stop. No hidden command knowledge required.
- [ ] Persist drafts with conversation identity and retention policy; never auto-send.
- [x] Add `--plain` dispatch to existing TerminalApp; normal interactive launch
  uses TUI. Non-TTY/help errors remain intelligible and never start the backend.
- [x] Disable markup interpretation for model/log content, scrub ANSI/OSC and test it.
- [x] Run `.venv/bin/python -m unittest discover -s tests -p 'test_tui_*.py' -v` and
  existing terminal modules. Confirm actual PTY behavior beyond headless tests.

Delivery: C01–C09 and V01–V04 below pass for TUI; at least one real mission; visible
selected/used models, no clipped text, keyboard usable, clean terminal restoration.

Suggested red UI test (Lot 4 defines constructor `CortexTui(offline=True)`):

```python
import unittest
from console.tui.app import CortexTui
from textual.widgets import TextArea

class TuiSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_small_terminal_keeps_composer(self):
        app = CortexTui(offline=True)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            composer = app.query_one("#composer", TextArea)
            self.assertGreater(composer.region.height, 0)
            self.assertLessEqual(composer.region.bottom, 24)
            composer.focus()
            await pilot.press("h", "i")
            self.assertEqual(composer.text, "hi")
```

This is pre-code, not a claim of compatibility with an uninstalled version.
Verify against the version locked in Lot 0. Add width/focus/paste/resize and actual
API-post-count assertions; this smoke test alone is insufficient.

### Lot 5 — Finish Web Atelier, preserve existing work

Modify existing `ChatWorkspace.tsx`, `Composer.tsx`, `ConversationSidebar.tsx`,
`StatusRail.tsx`, `ChatGPTConnectionDialog.tsx`, `SettingsPanel.tsx`,
`PipelineInspector.tsx` and corresponding tests only as needed.

- [ ] RED: diagnostic panel hidden initially; collapse button unambiguous; active
  mission A distinct while viewing B; failed fetch keeps prior conversations.
- [ ] Reuse shared profile/model API; add observation-pending feedback. Keep execute
  as explicit composer action, normal chat verbatim.
- [ ] Add correct pinned/project/recent grouping, bounded 50-item reconciliation,
  known counts and selected title in synchronization status.
- [ ] Keep send bubble stable through queued/delivered/error. Restore retry controls
  without automatically retrying a message whose delivery is uncertain.
- [ ] Confine project-card CSS to the card; keep reduced-motion behavior; small
  screens must retain composer, status, and expand control.
- [ ] Preserve visible viewport while reading older replies; do not jump to bottom
  on every update. Switching cached conversation never reloads whole Chrome page.
- [ ] Run frontend unit/runtime/typecheck/lint/build/e2e commands in section 9.

Delivery: Web C01–C09/V01–V04, actual text and mission proof, responsive screenshots,
no personal content in public assets, no regression in existing dialogs/approvals.

### Lot 6 — Install `cortex`, update and recovery

- [ ] Add installer fixture RED: new shell cannot resolve cortex before install,
  then resolves managed entrypoint after approved install; existing foreign cortex
  command is never overwritten; install twice is idempotent.
- [ ] Integrate entrypoint in existing approve-plan installation and owned-resource
  manifest. Plan hash must change if command target/version/location changes.
- [ ] Use a stable managed release path and resolved runtime config, never
  `.qa-live-v061` or a developer checkout hardcoded into distributed launchers.
- [ ] Store startup preference, validate owned server, handle missing volume,
  unavailable backend/dependency and extension-required state explicitly.
- [ ] Uninstall only proven owned resources, preserve workspaces and foreign files;
  update retains profile/drafts without reinterpreting old permissions.
- [ ] Local Storage refusal of a protected command directory remains an explicit
  installation blocker until its scoped exception is approved; no alternate-path
  bypass or sudo workaround. The earlier exception request has no recorded approval.
- [ ] Run `.venv/bin/python -m unittest tests.test_installer tests.test_terminal_cli -v`.
- [ ] Run I01/I02 below in isolated fixtures, then genuine clean macOS lifecycle.

Delivery: user opens Terminal and types `cortex`; real TUI appears without a path;
help/version work; original installation untouched; lifecycle receipts complete.

### Lot 7 — User QA and sanitized evidence

- [ ] Freeze source before live runs; record exact commit, OS/runtime, extension
  loaded state, interface, planner/executor observed IDs and prompt.
- [ ] Run the simple matrix first. Stop on failed prerequisite, fix with a regression
  test and rerun the affected case. Do not skip a failed case into PASS.
- [ ] Perform the two mission scenarios in both interfaces with two observed planner
  models. Reuse C04 as the larger test; no need for a huge arbitrary benchmark.
- [ ] Record duration separately for startup, navigation, provider response and
  execution. A timeout is evidence, not a prompt to send again.
- [ ] Publish only synthetic transcript/screenshots. Inspect actual pixels/metadata;
  avoid capturing real account UI where possible instead of relying on blur.
- [ ] Complete clean install gates and attachment/isolation requirements required by
  current release validator; this plan does not weaken those existing gates.

Delivery: report with PASS/FAIL/UNCLEAR per case and artifact hashes; all attempts
listed; no fabricated fixtures labelled human runs. Reviewer rechecks files.

### Lot 8 — Documentation, independent review and main

- [ ] Complete the GitHub maintenance subsection below before final publication;
  do not treat automated dependency PRs as community contributions.
- [ ] Coordinator reviews all diffs, ownership, locks, package contents and absence
  of private QA files. Update README, TERMINAL.md, TERMINAL_ACCEPTANCE.md,
  INSTALL.md, llms.txt, CHANGELOG and verification report with current scope.
- [ ] Update three animated diagrams: chat, mission feedback loop, interface choice.
  Add planner-vs-executor explanation and readable static/reduced-motion alternatives.
- [ ] Benchmark table separates historical fixtures, current automated tests and
  real workflows; sample count, method, failures, model IDs, source commit and scope.
- [ ] Run all gates; produce evidence manifest only from valid records. Respect the
  validator's source-commit/allowed-drift rules; no unrelated change after sealing.
- [ ] Review exact final commit independently, then use approved GitHub remote
  (not the local-checkout origin), merge to main without force, verify remote hash,
  VERSION, README, image links, installation commands and CI. Tag only if approved.

Delivery: main actually contains the delivered version and truthful evidence;
working tree clean, no unresolved required failure, no claim of Windows validation.

#### GitHub activity and repository maintenance

Verified on 2026-09-10 through GitHub REST/GraphQL; this is a dated snapshot,
not a live counter. Public contributor names are omitted from this plan.

| Signal | Observed result | Interpretation |
| --- | --- | --- |
| Stars | 1, from an account other than the owner | Interest only; not proof of installation or testing |
| Forks | 0 | No public fork observed |
| Issues and Discussions | 0 each; Discussions enabled | No feedback thread observed |
| External human PRs, comments and reviews | None observed | No external human contribution established |
| Listed code contributors | Owner only | GitHub contributor listing, not a count of AI-assisted work |
| Open PRs | 11: 9 Dependabot, owner PRs #14 and #16 | Automated maintenance plus existing release work |
| Dependabot comments | Configured `dependencies` label missing | Repository configuration needs repair |

Owner: Lot 8 coordinator. Repository metadata mutations require the applicable
owner approval; editing this plan is not permission to create labels or close PRs.

- [ ] Re-query PRs, labels, reviews and comments immediately before maintenance.
  Preserve any feedback or contribution that appeared after this snapshot.
- [ ] Inspect `.github/dependabot.yml` and repository labels. If `dependencies`
  is still required and absent, create that label after approval. Do not remove
  Dependabot or disable its checks to silence the warning.
- [ ] Inventory the nine observed dependency PRs: #4, #6, #7, #8, #9, #10, #11,
  #12 and #15. For each, compare its proposed version with the final candidate
  lockfile, identify major-version changes and choose integrate, superseded or
  defer with a reason. Never bulk-merge on the basis of the bot's description.
- [ ] For integrations, run affected regression suites, package/build checks and
  a fresh dependency audit. Re-check installation and release evidence when the
  source changes. A duplicate update can be closed only after its replacement
  is demonstrably present in the target branch and closure is approved.
- [ ] Compare owner PR #14 with candidate #16: identify any unique required work
  before marking it superseded. Do not close #14 merely because #16 is newer.
- [ ] Inspect existing CONTRIBUTING guidance and issue templates. Ensure users
  can report OS, Cortex version, Web/TUI interface, reproduction, expected/actual
  result and sanitized logs. Explicitly warn against posting cookies, tokens,
  private conversations or unredacted screenshots. Keep guidance in English.
- [ ] Record maintenance decisions in the release report with PR links, actual
  checks and unresolved items. Do not contact the stargazer, post announcements
  or claim independent user validation as part of this maintenance lot.

Delivery: required label exists; every then-open dependency PR has a documented
decision; integrated updates are tested; no unique release work is discarded;
feedback instructions are discoverable; automated activity and human feedback
remain distinguishable. Deferred non-blocking updates may stay open with a clear
reason, but an unresolved required security/release gate still blocks main.

## 7. Simple shared user-test matrix

Run each applicable row in Web AND TUI. Preparation can create empty disposable
workspaces; only Cortex creates requested mission artifacts. Inspectors may read
files or execute independent verification, never secretly complete the mission.

| ID | Steps / exact input | PASS conditions |
| --- | --- | --- |
| C01 | Launch, connect, select new chat; send `Reply exactly CORTEX-HELLO-01` | One sent message; response matches; UI shows delivery; no typing in ChatGPT |
| C02 | Type `draft-alpha`, switch A->B->A before sending | Draft preserved in A only; no POST; correct title and history |
| C03 | Execute: `In the selected workspace create hello.txt containing exactly Bonjour Cortex followed by a newline. Do not modify any other file.` | Exact UTF-8 bytes; appropriate approval; real artifact; selected engine observed |
| C04 | Execute the sorting prompt below | Originals preserved; copies and manifest exact; only workspace writes |
| C05 | Open model selector, choose another available planner, send `Reply exactly CORTEX-MODEL-02` | Actual observed model matches or explicit unsupported/error; no silent fallback |
| C06 | While two writing leases are active, submit a third conversation; then release one and retry explicitly | Third refused with explanation and intact draft; released slot reusable; no crossover |
| C07 | Submit once; inject fixture connection timeout after receipt; reconnect | One POST only; uncertain/delivered reconciled correctly; no auto-resend |
| C08 | Start bounded synthetic mission, refuse pending write; then stop selected activity | Refused file not created; correct action ID; other activity unaffected |
| C09 | Attach tiny note.txt; preview; send. Repeat with synthetic screenshot | Actual provider attachment confirmed; correct file/hash; no private screenshot |
| V01 | Resize TUI 80x24/120x35/160x50; Web 375/768/1440 px | Composer/status usable, no overlap or horizontal text loss |
| V02 | Open/close every modal with keyboard, inspect focus and draft | Focus returns to initiating control/composer; no accidental send |
| V03 | Slow fake provider 15 s; type, navigate settings; disable animations | UI responsive; truthful wait state; no fake percentage |
| V04 | Display long code, accented text, ANSI/OSC attack string; paste multiple lines | Plain safe content, no terminal control/clipboard side effect, no paste-submit |
| I01 | Fresh isolated HOME and port: plan/install/doctor/launch/reinstall/uninstall | Approved plan only; command resolves; no duplicate server; sentinels preserved |
| I02 | New real macOS account/VM, same lifecycle, real Chrome authorization | Authentic clean-environment proof, not a renamed directory on existing account |

C06 long-lived leases and C07 timeout injection should first use controlled local
fixtures. Live C06 still required by release policy; never bypass it with backend
POSTs when claiming a UI run. Do not interrupt another user's real network traffic.

Exact C04 mission prompt:

```text
In the selected disposable workspace, create inbox/alpha.txt containing
alpha plus a newline, inbox/beta.md containing # Beta plus a newline, and
inbox/numbers.csv containing n,value then 1,10 then 2,20 on separate lines,
with a final newline. Copy them respectively to sorted/text/alpha.txt,
sorted/markdown/beta.md and sorted/data/numbers.csv. Preserve originals.
Create inventory.json as a JSON array with one row per copied file:
source, destination, bytes, sha256. Use relative paths. No network,
deletion or writes outside this workspace. Report the verified outcome.
```

Independent C04 verifier pre-code (read-only, standard library):

```python
# tests/acceptance/verify_sort.py — inspector, NOT a mission executor
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve(strict=True)
expected = {
    "alpha.txt": (b"alpha\n", "text"),
    "beta.md": (b"# Beta\n", "markdown"),
    "numbers.csv": (b"n,value\n1,10\n2,20\n", "data"),
}
rows = json.loads((root / "inventory.json").read_text(encoding="utf-8"))
assert isinstance(rows, list) and len(rows) == 3
for name, (content, category) in expected.items():
    source = f"inbox/{name}"
    destination = f"sorted/{category}/{name}"
    for relative in (source, destination):
        path = root / relative
        assert not path.is_symlink()
        assert path.resolve().is_relative_to(root)
        assert path.read_bytes() == content, relative
    record = {"source": source, "destination": destination,
              "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    assert rows.count(record) == 1, destination
print("PASS: three original/copy pairs and inventory verified")
```

Add a separate directory before/after inventory to prove no extra workspace writes;
this verifier only checks the seven requested files. It cannot prove absence of
outside-workspace writes—use executor policy evidence as a separate gate.

Additional larger scenario, retained for existing release mini-site requirements:
`Create a dependency-free Orbital Notes mini-site in this workspace with index.html,
style.css, app.js, README.md, increment/reset counter and Node tests. Run the tests.
No external assets or network. Give a loopback launch command.` Independently
launch on a free local port and click increment/reset; verify no external requests.
Keep the required three mini-site runs; do not relabel three unit cases as missions.

## 8. Evidence format and performance targets

One record per attempt; actual values only:

```json
{
  "schema_version": 1,
  "case_id": "C03",
  "interface": "tui",
  "source_commit": null,
  "planner_observed": null,
  "executor_observed": null,
  "prompt": "",
  "verdict": "UNCLEAR",
  "elapsed_ms": null,
  "artifact_sha256": {},
  "evidence_paths": [],
  "reason": "Template only; this is not a recorded run"
}
```

Never place this template in a release proof directory as an executed record.
Null identity/time is unknown, never zero. Log every failed attempt and correction.
For basic missions C03/C04: Web x two planners and TUI x two planners = eight
attempts; add executor variation where supported and record it separately. Do not
claim model superiority from this small sample.

Proposed acceptance targets (not measurements): local visible feedback <=150 ms,
cached conversation switch <=300 ms, first cached transcript <=1 s, remote switch
result OR actionable state <=10 s. Measure 20 controlled repetitions for local
latencies and publish min/median/p95 with environment; provider response has no
promised bound. Persistent reconnect must not reset focus or erase drafts.

## 9. Commands and stopping rules

Existing regression commands, from repository root (use isolated runtime home):

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:console .venv/bin/python -m unittest discover -s tests
node --test chrome-extension/tests/extension.test.mjs
cd frontend
../scripts/npmw run test:unit
../scripts/npmw run test:runtime
../scripts/npmw run typecheck
../scripts/npmw run lint
../scripts/npmw run build
../scripts/npmw run test:e2e
../scripts/npmw run test:a11y
../scripts/npmw audit --audit-level=low
```

Return to root for `scripts/verify-links.sh`, public privacy scanner, Gitleaks,
`scripts/verify-release-evidence.py` and canonical `scripts/test-all.sh`. Inspect
their current requirements before running; do not omit required markers or paths.
New TUI/adapter tests must join the canonical suite rather than remain manual.

Stop on: unexpected write target; dirty overlap with another worker; auth/permission
request; unsupported executor; ambiguous send; missing model proof; provider limit;
clean-install environment unavailable; protected Storage refusal. Diagnose locally,
fix only authorized code and ask for necessary human action. Never lower gates.

## 10. Luna handoff message

```text
Work only in the independent Cortex Bridge 0.6.1 candidate supplied by the
coordinator. Read primer.md and docs/PLAN_WEB_TUI_LUNA.md completely.
Your assigned lot number determines your exclusive write ownership.
You are not alone in the codebase: preserve other edits and request shared-file
changes from their owner. Read project/Storage instructions and begin/finish
targeted sessions before/after writes. Do not edit the original installation.
Implement the assigned lot only, using failing tests first. Existing and proposed
APIs are explicitly distinguished in the plan; do not assume proposed ones exist.
Keep French UI copy and English public documentation. Never publish user data.
Report files changed, RED evidence, GREEN commands/results, limitations, source
hash and delivery criteria one by one. Do not invent live runs, model identity or
completion. No push, permission workaround, automatic ambiguous resend or change
to another agent's files. Stop for independent review at the lot boundary.
```

Coordinator sends this message with the specific lot and dependency commit. No
worker should infer that all seven lots belong to them. Use a separate reviewer
after each lot; model name alone does not confer independence.

## 11. Final acceptance checklist

- [ ] `cortex` launches a genuinely installed TUI in a fresh terminal.
- [ ] Web and TUI share connection/profile/model/execution truth.
- [ ] Actual planner choice and supported model-backed executor choice work.
- [ ] No fake readiness, silent rewriting, automatic resend or privilege fallback.
- [ ] Simple user cases pass in both interfaces, plus required release cases.
- [ ] Two writing conversations remain isolated across interfaces.
- [ ] Layout, keyboard, resizing and transitions are visually verified.
- [ ] Attachments/captures have actual confirmation and sanitized evidence.
- [ ] Clean macOS installation lifecycle passes; Windows remains explicitly deferred.
- [ ] Documentation, animated/static diagrams and benchmark scope match delivered code.
- [ ] GitHub label configuration and dependency PR triage are complete; community
  activity is described accurately and sanitized feedback guidance is available.
- [ ] Privacy, secrets, dependency, test and release-evidence gates pass on sealed source.
- [ ] Approved merge actually reaches main; remote content and CI verified.

## References checked for the proposed TUI

- [Textual testing](https://textual.textualize.io/guide/testing/): headless pilot,
  keyboard/mouse simulation and terminal-size tests.
- [Textual workers](https://textual.textualize.io/guide/workers/): background work
  to avoid blocking UI interaction. Framework mechanics do not prove Cortex behavior.

The plan intentionally keeps terminal rendering in Python, rather than adding a
second Node/React terminal build or hand-writing a full ANSI event/layout engine.
If the compatibility gate fails, stop and revise the design before implementation.
