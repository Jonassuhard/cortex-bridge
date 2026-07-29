# Changelog

All notable changes are recorded here.

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

### Changed

- `Enter` now sends only the exact ChatGPT draft. Local execution is a separate confirmed action.
- The fallback page is diagnostic-only and cannot start chat or execution.
- The deterministic executor is the default; Ollama is optional.
- Frontend and Python package versions now share the canonical `0.5.0` value.

### Security

- Conversation selection uses one absolute 10-second budget.
- Late results cannot replace a newer selected conversation.
- Uncertain delivery never retries automatically.
- File staging rejects traversal, symlinks, misleading extensions and unsupported MIME types.
- Stop operations reject foreign listeners, stale owners and PID reuse.

### Pending owner gates

- Manual ChatGPT login and live browser compatibility.
- Three live disposable mini-site missions.
- Decision on cleaning historical repository data if the history scan finds private artifacts.
- Push, tag and GitHub release publication.
