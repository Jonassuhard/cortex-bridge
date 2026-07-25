# UX Audit — Cortex Bridge console

Date: 2026-07-25 · Scope: local web console (Next.js static export + FastAPI,
127.0.0.1:8420), French UI. Method: manual walkthrough of every surface plus
the live verification runs documented in [testing.md](testing.md).

## Surfaces reviewed

1. First launch (onboarding)
2. Conversation sidebar (list, statuses, types, collapsed mode)
3. Chat workspace (composer, send states, attachments)
4. Pipeline inspector ("Détails du bridge")
5. Settings panel (7 tabs + Info)
6. Mission mode (launch, approvals, stop)

## What works well

- **Dual status per conversation** (ChatGPT + Agent) makes it obvious who is
  working. Verified in screenshots during P1a.
- **Explicit send states** — "Envoi en cours… → Envoyé ✓" — removed the
  biggest source of user blindness (P2a).
- **Pipeline hidden by default**: technical detail is one click away but does
  not clutter the chat (P1b).
- **Conversation switching without reload** (0.9–3.2 s measured, P0b) makes
  the app feel native.
- **Onboarding assistant** (added 2026-07-25): five real prerequisite checks
  with actionable hints, dismissible, persisted server-side.
- **Anonymized diagnostic export** (added 2026-07-25): one click produces a
  GitHub-issue-safe bundle (home paths → `~`, conversation ids hashed, no
  message content).

## Findings and recommendations

| # | Severity | Finding | Recommendation |
|---|----------|---------|----------------|
| 1 | Medium | "Tester WebBridge / Tester Ollama / Vérifier SQLite" buttons in Diagnostics are placeholders | Wire them to real checks (reuse `/api/onboarding` checks) or remove them |
| 2 | Low | Settings tabs are numerous (8); new users may not find the model switcher | Consider grouping Models + Transport under "IA" — or rely on onboarding to guide |
| 3 | Low | No empty-state guidance when zero conversations exist | Show a "Ouvre chatgpt.com dans Chrome" hint card in the sidebar |
| 4 | Low | Attachments: the 512 MB / 20 MB limits are enforced with clear French errors, but not communicated *before* the user picks a file | Add the limits to the paperclip tooltip |
| 5 | Info | The animated architecture diagram (Settings › Info) helps explain the loop | Keep it in sync if the transport ever changes |
| 6 | Info | Two-conversation write guard protects drafts but may surprise power users | The 409 message already explains why — keep as is |

## Accessibility notes

- Overlays use `role="dialog"` + `aria-modal`, icon buttons have labels.
- `prefers-reduced-motion` disables decorative animations (signal sweep,
  diagram pulses).
- Remaining gap: keyboard focus trap inside modals is not implemented —
  acceptable for a local single-user tool, worth fixing if the user base grows.

## Conclusion

The console is **operational and understandable**: a new user is guided from
first launch to first mission, every asynchronous action has visible state,
and diagnostics are exportable without leaking personal data. The only
non-placeholder follow-up worth scheduling is finding #1 (dead diagnostic
buttons).
