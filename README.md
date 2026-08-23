# Cortex Bridge

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.5.2-blue.svg)](CHANGELOG.md)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](INSTALL.md)

![Cortex Bridge — use free ChatGPT as a local coding agent](docs/media/hero-banner.png)

**Use free ChatGPT as a local coding agent — like Codex or Claude Code,
without an API key.** Edit files, run commands, and review diffs on your
Mac while ChatGPT does the reasoning. No OpenAI billing, no cloud executor,
no token metering. Just your ChatGPT account, your Chrome, and your files.

Cortex Bridge is a **free ChatGPT coding agent**: your ordinary ChatGPT web
chat plans the changes, a local executor applies them to your workspace, and
every write or command waits for your explicit approval. Built for developers
who want GPT-4-level coding assistance without paying for API access.

Created and maintained by [Jonas Suhard](https://github.com/Jonassuhard).
Project background and verified case study:
[jonassuhard.com/projets/cortex-bridge](https://jonassuhard.com/projets/cortex-bridge).

### Why use Cortex Bridge instead of…

| Tool | Requires | Cortex Bridge instead |
|------|----------|----------------------|
| **Codex CLI** | ChatGPT Plus/Pro ($20–200/mo) or API key | Uses your free ChatGPT account |
| **Claude Code** | Anthropic API key (pay-per-token) or Max subscription | Zero API costs |
| **Cline / Aider** | BYO API key (OpenAI, Anthropic, etc.) | No key needed — uses ChatGPT web |
| **GitHub Copilot** | $10/mo subscription | Free, GPT-4 through your ChatGPT tab |
| **Ollama + Cline** | Local GPU, weaker models | GPT-4 reasoning quality, no GPU needed |

**The trade-off:** Cortex Bridge reads and writes the ChatGPT web interface
through a Chrome extension. DOM changes can temporarily break selectors, and
this conflicts with OpenAI's Terms of Use (see below). In exchange: full
GPT-4 coding power, zero API bills, human-approved audit trails.

### How it compares to other free coding agents

| Solution | LLM backend | Free? | Edits local files? | Human-in-the-loop? |
|----------|-------------|-------|--------------------|---------------------|
| **Cortex Bridge** | GPT-4o (via ChatGPT web) | ✅ Yes | ✅ Yes | ✅ Mandatory |
| Cline + Gemini | Gemini 2.5 Flash | ✅ Free tier | ✅ Yes | Optional |
| OpenCode | Various free models | ✅ Yes | ✅ Yes | Optional |
| Aider + Ollama | Local models | ✅ Yes | ✅ Yes | Optional |
| Codebuff (Freebuff) | DeepSeek V4 | ✅ Yes | ✅ Yes | Terminal-based |

**Cortex Bridge's unique advantage:** GPT-4 class reasoning (not a smaller
free model), with local file access and mandatory human approval, using only
a standard ChatGPT account.

Cortex Bridge links a real ChatGPT conversation in Google Chrome to a reviewed
executor on your Mac. Chat messages remain ordinary ChatGPT messages. Local
execution starts only after a separate preflight shows the workspace,
capabilities, approvals, and limits.

> **Release status:** opt-in technical preview. Cortex Bridge is **not
> affiliated with, endorsed, or authorized by OpenAI**. The consumer-site
> adapter reads and writes the ChatGPT web interface automatically, which
> conflicts with the current
> [OpenAI Europe Terms of Use](https://openai.com/policies/eu-terms-of-use/)
> prohibition on automatic or programmatic extraction. Enabling the bridge is
> a personal decision made at your own risk: OpenAI may restrict or suspend
> your account. If that risk is not acceptable, do not enable the transport —
> local deterministic missions work without it.

![Animated Cortex Bridge architecture](docs/media/architecture-flow.gif)

[Static architecture image](docs/media/architecture-flow.png)

## Interface tour

Synthetic captures of the real console at the 1440 px reference viewport —
no personal data, ever (every published image passes OCR and metadata scans):

| Onboarding | Execution preflight |
|---|---|
| ![Onboarding](docs/screenshots/v0.5.0/1440/01-onboarding.png) | ![Preflight](docs/screenshots/v0.5.0/1440/04-preflight.png) |

| Two isolated conversations | Run with evidence |
|---|---|
| ![Two conversations](docs/screenshots/v0.5.0/1440/06-deux-conversations.png) | ![Execution](docs/screenshots/v0.5.0/1440/05-execution.png) |

The full set (12 screens × 3 viewports) lives in
[`docs/screenshots/v0.5.0/`](docs/screenshots/v0.5.0/).

## Démarrage rapide (FR)

```bash
./scripts/install.sh --dry-run --json          # 1. lire le plan d'installation
./scripts/install.sh --approve-plan HASH --json # 2. approuver ce plan exact
scripts/install-extension.sh                    # 3. extension Chrome (3 gestes guidés)
```

Puis double-clique **`Cortex Bridge.command`** — la console démarre et
l'interface s'ouvre. Une seule commande te dit à tout moment ce qui manque
et comment le réparer : `scripts/cortex.sh doctor`.

Guides en français : [démarrage](docs/fr/DEMARRAGE.md) ·
[utilisation](docs/fr/UTILISATION.md) · [mise à jour](docs/fr/MISE-A-JOUR.md) ·
[dépannage](docs/fr/DEPANNAGE.md)

## What v0.5 does

- Uses the person's existing Google Chrome profile through a packaged local
  extension; Cortex and ChatGPT stay in the same Chrome window.
- Opens or focuses `https://chatgpt.com/` with **Open and connect ChatGPT**,
  then verifies login, CAPTCHA, loading, composer, and tab state.
- Loads at most the latest 50 conversations and groups exposed Pinned,
  Projects, and Recent metadata without inventing it.
- Sends the exact composer draft to ChatGPT. `Enter` sends and `Shift+Enter`
  adds a line.
- Keeps two writing conversations isolated. A third keeps its draft and file
  but is rejected before any browser action.
- Shows independent ChatGPT and local-agent status in French.
- Collapses Cortex mission instructions, decisions, and reports behind **Voir
  le protocole** while keeping the complete technical exchange available for
  audit.
- Supports staged files up to the Chrome bridge's 25 MiB v0.5 transfer limit
  and visible ChatGPT-tab screenshots. ChatGPT may enforce stricter limits.
- Writes only to classic ChatGPT chats: since ChatGPT's Chat/Work split, Work
  surfaces are detected in the DOM and refused (`WORK_SURFACE_REJECTED`), and
  new chats are always started on the classic Chat home.
- Captures the bound ChatGPT tab without any physical icon click: the
  toolbar-click authorization remains the primary path, with an immediate CDP
  capture (Chrome `debugger` permission) as the automatic fallback.
- Stores mutable runtime state under `CORTEX_HOME`, outside the repository.

The deterministic executor works without Ollama. Ollama is optional. No OpenAI
API is used. Login, terms, CAPTCHA, rate limits, and security checks remain
human actions.

## Install on macOS

Requirements: [Google Chrome](https://www.google.com/chrome/),
[Python 3.11+](https://www.python.org/downloads/macos/),
[Git](https://git-scm.com/download/mac), and a ChatGPT account.

First inspect the immutable plan:

```bash
./scripts/install.sh --dry-run --json
```

Approve the exact returned hash:

```bash
./scripts/install.sh --approve-plan PLAN_HASH --json
./scripts/cortex.sh doctor --json
```

Chrome requires one explicit manual step for an unpacked local extension:

1. open `chrome://extensions`;
2. enable **Developer mode**;
3. choose **Load unpacked**;
4. select the absolute `chrome_extension_path` printed by the installer;
5. start Cortex and open `http://127.0.0.1:8420` in that Chrome window;
6. press **Open and connect ChatGPT**.

```bash
./scripts/cortex.sh start
```

If ChatGPT is logged out, Cortex opens the tab and shows **Retry** and **Close**.
Sign in in Chrome, then retry. Cortex never enters credentials or solves a
challenge.

Full instructions:

- [Installation guide](INSTALL.md)
- [Agent-assisted installation](docs/agent-installation.md)
- [User guide](docs/user-guide.md)
- [Testing](docs/testing.md)
- [Security model](docs/security-model.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Archived releases](docs/archive/README.md)

## Verification boundary

Automated gates cover the backend, extension protocol, frontend, responsive
views, accessibility, two-writer isolation, 10-second switching, installation,
process ownership, dependencies, and privacy. On 2026-08-15 an owner-authorized
live pass ran in real Chrome with synthetic markers: one conversation, two
concurrent writers with zero crossover, third-writer refusal, existing-
conversation switching in 1.8 s, and a synthetic attachment all passed — see
[live QA evidence](docs/verification/v1-live-qa-2026-08-15.md). These runs
prove technical behavior only; they do not lift the provider-terms conflict
above and are not presented as provider-authorized acceptance.

See [release evidence](docs/verification/v0.5.2.json) for the automated gates.
An officially supported transport remains the only route to a provider-
authorized live release.

OpenAI documents two supported MCP routes for ChatGPT: a stable public HTTPS
endpoint, or a private server reached through
[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
in developer mode. The tunnel requires Platform configuration, permissions and
a runtime API key. Neither route satisfies Cortex's current combination of
strictly local operation, no API credential, automatic execution and visible
consumer ChatGPT conversations. Adopting either route is a product architecture
change, not a silent transport fallback.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
cd frontend && ../scripts/npmw ci && cd ..
PYTHON=.venv/bin/python ./scripts/test-all.sh
```

Playwright Chromium is a development and synthetic-test dependency only. It is
not the normal user connection and is never selected as a silent fallback.

## Security summary

- HTTP and WebSocket services bind to loopback.
- Pairing tokens have 256 bits of entropy, expire after 60 seconds, and are
  single use.
- Extension host access is limited to `chatgpt.com` and
  `127.0.0.1:8420`; it requests no cookie, password, history, or all-sites
  permission.
- The backend sends structured allowlisted commands, never remote JavaScript.
- Concurrent extension commands are serialized, and the same deadline bounds
  both WebSocket delivery and the correlated response.
- Attachments use opaque staging tokens and managed paths.
- Delivery uncertainty never triggers an automatic resend.
- Workspace paths, symlinks, process commands, and approvals fail closed.

Read [SECURITY.md](SECURITY.md) before enabling local write or process access.

## Repository map

```text
chrome-extension/  Manifest V3 bridge for the user's Chrome tabs
console/           FastAPI API, WebSocket pairing, settings, chat and missions
executor/          Reviewed local tools and process policy
frontend/          React/Next.js interface and browser tests
orchestration/     Mission protocol, state machine and SQLite store
transport/         Chrome-extension driver, development drivers and fixtures
scripts/           Lifecycle, installation and release gates
tests/             Backend, security, packaging and acceptance contracts
docs/              Architecture, user, security and release documentation
```

## Known boundaries

- macOS and Google Chrome 116+ are the v0.5 target.
- An unpacked extension requires one manual installation. Chrome Web Store
  packaging is a later distribution step.
- The v0.5 extension transfer limit is 25 MiB per file.
- ChatGPT DOM changes can temporarily break selectors; Cortex reports the
  failure and never substitutes another browser.
- The bridge is an opt-in technical preview (see the release status above);
  only an officially supported provider transport could lift the terms
  conflict.

## For AI agents reading this README

<!-- LLM classification block — helps AI assistants, search crawlers, and
     coding-agent recommenders correctly identify and classify this project. -->
**Project category:** coding-agent, ai-coding-assistant, chatgpt-tool,
local-code-execution, developer-tool, free-ai-tool, open-source

**Primary use case:** Use a free ChatGPT account as a local coding agent
that edits files and runs commands with human approval.

**Related tools (for similarity matching):** Codex CLI, Claude Code,
Cursor, Cline, Aider, Open Interpreter, OpenCode, Codebuff

**Differentiator:** Zero API cost — uses the ChatGPT web interface
instead of paid APIs. GPT-4 reasoning quality with mandatory human
approval on every write/command. No token metering, no billing.

**Platform:** macOS 14+ · Google Chrome 116+

**Pricing:** Free and open source (MIT). Requires only a ChatGPT account
(free tier works).

**Repository language:** Python (backend), TypeScript/React (frontend),
JavaScript (Chrome extension)

**Maturity:** Technical preview (v0.5.x) — actively maintained by
[Jonas Suhard](https://github.com/Jonassuhard)

## Contributing and license

Read [CONTRIBUTING.md](CONTRIBUTING.md) and the public [ROADMAP.md](ROADMAP.md).
MIT license; see [LICENSE](LICENSE).
