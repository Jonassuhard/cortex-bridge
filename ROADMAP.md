# Roadmap

Public, best-effort roadmap. Dates are indicative; scope beats schedule.

## v0.5.x — current (technical preview)

- [x] v0.5.0 — release candidate: conversation-first French UI, execution
      preflight, two isolated writers, attachments, consent-bound installer,
      doctor, ownership-limited uninstaller.
- [x] v0.5.1 — classic-chat-only surface guard, click-free CDP screenshot
      capture, contractual-risk opt-in control.
- [x] v0.5.2 — one-command onboarding, French guides, unified mission
      history, clear paused/limit states, stable default workspace.
- [ ] Real-production-extension live capture E2E (currently covered by unit
      and E2E suites plus a documented debug-build live run).
- [ ] External tester feedback round (5 macOS testers — see
      `docs/launch-strategy.md`).

## v0.6 — distribution

- [ ] Packaged extension (`.crx` / Chrome Web Store unlisted) to remove the
      manual `chrome://extensions` step.
- [ ] Signed, notarized app bundle; auto-update channel.
- [ ] GitHub release assets automated in CI (extension zip + checksums).
- [ ] Windows / Linux support assessment (executor and installer are the
      main porting surface).

## v1.0 — product

- [ ] Official-transport evaluation: developer-mode plugin calling an MCP
      server through a public HTTPS endpoint or Secure MCP Tunnel. This is
      the only path that lifts the consumer-site terms conflict; it requires
      Platform permissions and credentials and is an explicit architecture
      change.
- [ ] Multi-conversation scheduling with per-conversation budgets.
- [ ] Plugin SDK for custom deterministic tools.
- [ ] Local-model routing GA (Ollama profiles, per-mission model choice).

## Out of scope (explicit)

- Silent execution without human approval.
- Work/business ChatGPT surfaces.
- Cloud relay of conversation content.
