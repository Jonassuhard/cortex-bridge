# Cortex Bridge v0.3.0 — first public release

**A cloud brain. Local hands. One conversation loop.**

Cortex Bridge connects a cloud orchestrator (ChatGPT in your own browser) to a
local agentic executor on your machine via Ollama. The orchestrator plans;
the local model executes; the report goes back into the conversation and the
loop continues. No OpenAI API key, loopback only.

## ✅ Verified working end-to-end (2026-07-24/25, real chatgpt.com)

- Autonomous missions: contract → decision → tool execution → report → next
  decision, inside a single ChatGPT conversation
- Live ChatGPT chat from the local console, with per-conversation statuses
  (ChatGPT + Agent), pinned/project types with counters (50 max)
- Conversation switching without page reload (0.9–3.2 s measured)
- Attachments: files and images to ChatGPT, plus screenshots of the
  conversation tab — explicit limits (512 MB per file, 20 MB per image) with
  clear French error messages; screenshot round-trip proven live
  (ChatGPT acknowledged receipt)
- File writes with human approval, multi-iteration code repair, policy
  refusals, emergency stop, two-conversation write guard

## 🖥️ The console (French UI, 127.0.0.1:8420)

- First-launch onboarding assistant: five real prerequisite checks
  (Ollama, executor model, WebBridge, ChatGPT tab, workspace) with
  actionable hints
- Explicit send states: "Envoi en cours… → Envoyé ✓"
- Pipeline inspector hidden by default behind "Détails du bridge"
- Animated architecture diagram in Settings › Info
- Diagnostics: real WebBridge/Ollama/SQLite test buttons + one-click
  **anonymized** export (home paths → `~`, conversation ids hashed, no
  message content) safe to paste into a GitHub issue

## 🛠️ One command to run it

```bash
./scripts/cortex.sh start    # console at http://127.0.0.1:8420
./scripts/cortex.sh status   # console + Ollama + WebBridge health
./scripts/cortex.sh stop
```

## Requirements

macOS, [Ollama](https://ollama.com) with an executor model, Chrome with the
WebBridge extension connected to your ChatGPT session. Full manual setup:
[docs/manual-setup.md](docs/manual-setup.md).

## ⚠️ Experimental transport

The web transport automates a consumer product UI and may break when ChatGPT
changes its frontend — read [docs/legal-notes.md](docs/legal-notes.md) and
[docs/chatgpt-web-transport.md](docs/chatgpt-web-transport.md).

## Quality gate

120 automated tests green; frontend typecheck + lint clean; gitleaks
pre-commit hook on every commit.

## Contributing

Ideas and improvements welcome:
[feature requests](https://github.com/Jonassuhard/cortex-bridge/issues/new?template=feature_request.md) ·
[Discussions](https://github.com/Jonassuhard/cortex-bridge/discussions) ·
[CONTRIBUTING.md](CONTRIBUTING.md)
