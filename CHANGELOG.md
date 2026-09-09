# Changelog

All notable changes are recorded here.

## 0.6 development checkpoint — not released

- Work in progress on immutable generation installation, native process
  supervision, descriptor-bound workspaces, execution profiles and continuity.
- The storage contract now requires journal-bound encrypted-image proof;
  production native proof and full effect/terminal/recovery execution remain
  incomplete. A committed journal alone is not runtime readiness.
- Added targeted regression evidence and an explicit
  [checkpoint matrix](docs/verification/v06-development-checkpoint-2026-09-10.md).
- No 0.6 version bump, release tag or full-candidate acceptance claim.

## 0.5.4 - Unreleased

### Added

- `scripts/cortex.sh go` launches everything in one command: it starts the
  console, opens the console tab in the Chrome profile that carries the
  extension, and prints the next steps in French.
- The Chrome extension pairs with the console automatically when the console
  detects an unpaired extension; the manual pairing button remains available.
- The console and ChatGPT tabs are grouped in one **Cortex Bridge** Chrome tab
  group, created and maintained by the extension (new `tabGroups` permission).
- A **Guide de démarrage** button in the sidebar reopens a 3-step checklist
  (pairing, ChatGPT tab, first mission) with live completion state.
- The extension self-heals its connection: a Chrome alarm wakes the service
  worker every 30 seconds and reconnects to the console after a console
  restart (new `alarms` permission).
- `cortex.sh selftest` runs a 4-step self-diagnostic (server, extension
  pairing, DOM probe, version consistency) and reports results in French.
- Optional encrypted external storage can be bound to an exact APFS volume UUID
  and sparse bundle. Official startup fails closed when the volume, writable
  state, storage root or encrypted backing image cannot be verified.
- Deterministic storage manifests inventory canonical artifacts without
  exposing absolute paths or following external symlinks.

### Changed

- `Cortex Bridge.command` now runs the full `cortex.sh go` flow instead of only
  starting the server.
- The ChatGPT connection button is labelled **Ouvrir ChatGPT**.
- Mutable runtime state is owner-only and remains on the local disk. Oversized
  logs are rotated without deleting old backups; external-storage installs
  archive them in the configured quarantine tree.

### Fixed

- Installation repairs virtual environments whose entry-point shebangs still
  reference atomic staging paths, while preserving foreign replacements.
- Install recovery and uninstall now bind virtual environments and the native
  helper to exact identities and hashes. Within the documented threat model,
  lexical quarantine plus post-move verification detects ordinary symlink and
  path substitutions and preserves replacements whose identity is unproven.
- Legacy state migration publishes only complete private files or directories
  when the destination is still absent at atomic publication time; an existing
  destination is preserved.

## 0.5.3 - 2026-08-25

### Added

- A native macOS accessibility helper can activate a staged attachment in the
  real Chrome profile without replacing that profile or using the OpenAI API.
- An optional Freebuff-assisted installation guide gives the assistant a
  read-only inspection phase, a hashed dry-run plan, explicit human approval
  and manual checkpoints for Chrome, macOS permissions and account login.
- Screenshot capture now applies a fail-closed private mask to visible
  navigation, sidebar and account areas before the exact-tab CDP path can read
  pixels. Capture aborts if the mask cannot be confirmed.

### Changed

- Mission preflight now states the runtime truth: the deterministic executor is
  selected and network access is disabled. The submitted mission payload is
  normalized to the same values.
- A fresh text-chat installation no longer requires Swift. When Apple's
  Command Line Tools are missing, the reviewed plan records file sending as an
  unavailable optional capability and installs the remaining local runtime.
- Uninstall now refuses to remove owned runtime files while the Cortex server
  is still running, any foreign listener is present or its state cannot be
  verified. Start and uninstall now coordinate on the same lifecycle lock.
- The public privacy policy allows the maintainer identity in the optional
  Freebuff guide only where the exact official clone URL is required.

### Fixed

- The macOS accessibility scan no longer treats a legitimate unlabeled button
  as an unreadable accessibility value.
- Attachment delivery now binds to the current composer, detects composer
  remounts, transfers each file once and confirms file tiles from the same user
  message. A `DELIVERY_UNCERTAIN` result remains uncertain and is never hidden
  by an automatic retry.
- Release evidence validation now rejects missing or unrelated source commits,
  source-code drift after the audited commit and dirty source trees.
- Conversation selection now requires the requested ChatGPT route and a ready
  composer together, so stale paint from the previously visible conversation
  cannot satisfy a switch.
- Delivery activation is serialized across writer tabs, refocuses the exact
  writer before preparation and trusted input, and rejects expired queued work
  before `mousePressed`.
- ChatGPT send-control re-renders after focus or hover are reacquired within a
  bounded deadline. The exact route, live hit target, attachment and normalized
  composer text are revalidated before the single trusted click.
- Mission resume can recover exactly one stable, fully valid, unconsumed reply
  that appeared immediately before a read timeout. Duplicate actions, invalid
  decisions, streaming output and ambiguous candidates fail closed; transport
  errors during resume remain paused instead of becoming runner crashes.
- A manual resume now serializes behind the mission loop that observed the
  pause. It cannot start a second consumer while the original loop is still
  receiving the same ChatGPT response.
- Screenshot route selection and masked capture now share the read-surface
  operation lock. The extension attests the expected ChatGPT URL before and
  after reading pixels, so concurrent views or navigation cannot cross-capture
  another conversation.
- Invalid protocol decisions remain violation evidence but no longer count as
  a consumed iteration or action during visible-reply recovery. A corrected
  valid decision at the same iteration can resume normally.
- Manual pause now records its exact stable origin. Pending approvals resume as
  approvals, ChatGPT waits resume as waits, and a pause request is refused
  while a local action is already changing the workspace.
- A writer tab released after uncertain delivery is durably quarantined in
  Chrome local storage from writer, read-only and screenshot allocation. A
  release or later read fails closed if that tombstone cannot be persisted or
  restored.
- Private capture cycles are serialized per tab. Toolbar and automatic
  screenshots both use `Page.captureScreenshot` against the exact bound tab;
  ambiguous `captureVisibleTab` pixels are no longer accepted.
- Cancelling either Swift compilation or a started macOS activation kills and
  reaps the child process. A cancellation after activation starts is reported
  as `DELIVERY_UNCERTAIN`, never as a clean unsent cancellation.

## 0.5.2 - 2026-08-20

### Added

- Public maintainer attribution in `README.md` and `CITATION.cff`, linked to
  the verified portfolio case study. The privacy scanner permits those exact
  identity fingerprints only in those two files and continues to reject them
  everywhere else.
- One-command owner experience: `Cortex Bridge.command` starts the console and
  opens the UI by double-click, `scripts/install-autostart.sh` installs an
  optional login LaunchAgent, `scripts/install-extension.sh` opens
  `chrome://extensions` with the extension path already on the clipboard, and
  `scripts/update.sh` pulls the latest code and prepares the re-install plan
  (approval hash still required).
- French operator guides under `docs/fr/` (démarrage, utilisation, mise à
  jour, dépannage) and a French quickstart in the README.
- `scripts/cortex.sh doctor` now prints an actionable French checklist
  (✅ / ⚠️ / ❌ + one repair command per missing piece) instead of raw JSON;
  `--json` output is unchanged for automation.
- Unified mission history: `GET /api/missions` merges legacy `chat-runs.json`
  and `iterations.json` runs read-only (flagged `legacy`), and
  `GET /api/missions/{id}` serves a detail view for them, so the UI shows one
  continuous past. A new **Historique** panel in the sidebar lists every
  mission and archived run.
- Paused missions now explain themselves in the UI: `RATE_LIMIT` renders as
  "ChatGPT a atteint sa limite d'utilisation…" with a resume hint, and the
  usage-limit banners ("You've hit your usage limit" / "limite d'utilisation")
  are now detected by both the extension and adapter probes.

### Changed

- The default workspace is now the visible, auto-created
  `~/cortex-workspaces`; a stored default pointing at a purged temp directory
  (`/tmp`, `/private/tmp`, `/var/folders`) is reset to that stable default on
  load. Custom existing paths are untouched.
- The mission database and transport opt-in marker now live under
  `CORTEX_HOME` (migrated by the existing legacy-state migration) instead of
  inside the repository, matching the documented runtime-state rule.

### Fixed

- `scripts/cortex.sh status` now reports the real owner of the listening port
  (pid + command) in French, and automatically cleans a stale pid record when
  both the recorded process and the listener are gone — `status` and `doctor`
  can no longer disagree about which instance is actually serving. Found and validated by a live mini-site mission.

## 0.5.1 - 2026-08-20

### Added

- Classic-Chat-only surface guard: ChatGPT now exposes two surfaces (classic
  Chat and Work) behind the same `/c/<id>` URL scheme, distinguishable only in
  the DOM (", Work" suffix on the sidebar self-link, Chat/Work radiogroup on
  the home page). Every delivery-sensitive action (`prepare_text`,
  `attachment_begin`, `send_bare`) now fails closed with
  `WORK_SURFACE_REJECTED` on a Work surface, and a brand-new chat started on
  the Work home automatically switches back to the Chat radio. The current
  surface is reported as `surface` in `probe` and state payloads so drift is
  visible to the DOM probe. Validated live: a Work conversation refused
  delivery while a classic chat completed end to end.
- Click-free screenshot capture: when no fresh toolbar-click authorization
  (`pendingCapture`) is available, `capture_screenshot` now falls back to an
  immediate CDP capture of the Cortex-bound tab via the `debugger` permission
  (`Page.captureScreenshot`), so unattended local automation never depends on
  a physical icon click. The toolbar-click path remains primary and its
  60-second same-conversation scope is unchanged; the debugger session is
  detached immediately after capture. Validated live: ChatGPT confirmed it
  received the captured image.
- Explicit contractual-risk opt-in control in Settings → Transport: the bridge
  is labeled as not authorized by OpenAI, with the account-suspension risk
  stated in French before activation (the opt-in API existed without any UI).
- Live QA evidence document `docs/verification/v1-live-qa-2026-08-15.md` and a
  local-models restore plan `docs/local-models.md`.

### Changed

- Public status wording: the project is presented as an opt-in technical
  preview with an explicit non-authorization and account-risk notice, instead
  of a permanently blocked preview.
- Live acceptance now covers: deletion sync (ChatGPT → Cortex), three
  disposable mini-site missions verified by `scripts/acceptance-mini-site.py`
  (one axe contrast finding self-corrected by a follow-up mission), a
  self-diagnostic mission that queries the service's own loopback APIs through
  approved `run_process` calls, the isolated macOS install/doctor/service/
  reinstall/uninstall lifecycle with a foreign-sentinel check, and a fresh
  local-models gate (granite4.1:8b primary + qwen3.5:9b fallback on an external
  volume, fresh 10/10 benchmark).

### Fixed

- A definitive pre-delivery refusal from the driver (`WORK_SURFACE_REJECTED`,
  `PRE_DELIVERY_NOT_READY`) now surfaces with its own clean code instead of
  being wrapped as `DELIVERY_UNCERTAIN` and pausing the transport: nothing was
  composed, so the delivery was never uncertain and no human resolution is
  needed.
- `select_model` on the Chrome-extension transport now confirms the switch from
  a freshly reacquired trigger and fails closed with `MODEL_CONFIRM_FAILED`
  instead of reporting success unconditionally (stale-node bug class).
- A writer session's first navigation now has a bounded 30 s budget so two
  concurrent writers no longer race the 10 s deadline through the extension's
  serialized tab allocation; conversation switches keep the strict 10 s
  contract. Validated live with two concurrent writers, zero crossover.
- The mission decision parser now accepts the whole-message bare
  `cortex-decision` form, because ChatGPT's DOM rendering strips code fences
  from the extracted text; embedded or repeated blocks remain protocol
  violations.


## 0.5.0 - release candidate

### Added

- Conversation-first French interface with Pinned, Projects and Recent groups.
- Explicit execution preflight instead of a persistent Chat/Mission mode.
- Two isolated conversation writers with draft preservation for a blocked third writer.
- Independent ChatGPT, executor and send-lifecycle status.
- Dedicated Playwright Chromium profile and deterministic reload after timeout.
- Attachment descriptors with opaque tokens, MIME validation, Office-container checks and restart cleanup.
- Canonical `CORTEX_HOME`, process ownership records and non-destructive legacy migration.
- Consent-bound installer, JSON doctor and ownership-limited uninstaller.
- Responsive, accessibility, performance, privacy, link and release-evidence gates.
- Shared French/English architecture diagram with reduced-motion behavior.
- Collapsible mission-protocol disclosure that keeps orchestration prompts and
  raw `cortex.v1` exchanges out of the primary conversation view.

### Changed

- `Enter` now sends only the exact ChatGPT draft. Local execution is a separate confirmed action.
- The fallback page is diagnostic-only and cannot start chat or execution.
- The deterministic executor is the default; Ollama is optional.
- Frontend and Python package versions now share the canonical `0.5.0` value.
- Historical mission conversations recognize and collapse Cortex protocol
  exchanges even after their local mission association is no longer loaded.

### Security

- Conversation selection uses one absolute 10-second budget.
- Late results cannot replace a newer selected conversation.
- Uncertain delivery never retries automatically.
- File staging rejects traversal, symlinks, misleading extensions and unsupported MIME types.
- Stop operations reject foreign listeners, stale owners and PID reuse.
- WebSocket command writes are serialized and covered by the command deadline,
  so a stalled concurrent send cannot leave permanent pending commands.

### Completed acceptance gates

- Real signed-in Chrome pairing, one and two conversations, third-writer
  refusal, file and screenshot delivery, and closed-tab recovery.
- Three disposable mini-site missions plus one Cortex-led repair.
- Clean macOS install, doctor, restart, reinstall, uninstall and foreign-port
  preservation.

### Remaining owner decisions

- Provider-terms and distribution decision for consumer-site automation.
- Merge, tag and GitHub release publication after pull-request review.
