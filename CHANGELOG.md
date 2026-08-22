# Changelog

All notable changes are recorded here.

## 0.5.2 - 2026-08-20

### Added

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
