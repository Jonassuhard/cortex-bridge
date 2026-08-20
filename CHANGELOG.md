# Changelog

All notable changes are recorded here.

## Unreleased

### Added

- Explicit contractual-risk opt-in control in Settings → Transport: the bridge
  is labeled as not authorized by OpenAI, with the account-suspension risk
  stated in French before activation (the opt-in API existed without any UI).
- Live QA evidence document `docs/verification/v1-live-qa-2026-08-15.md` and a
  local-models restore plan `docs/local-models.md`.

### Fixed

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
  violations. Found and validated by a live mini-site mission.

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
