# Cortex Bridge

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.5.3-blue.svg)](CHANGELOG.md)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](INSTALL.md)

![Cortex Bridge — use free ChatGPT as a local coding agent](docs/media/hero-banner.png)

**Use a ChatGPT web conversation as a local coding agent, without an OpenAI
API key.** Edit files, run commands, and review diffs on your Mac while the
model selected in ChatGPT does the reasoning. No OpenAI API billing, no cloud
executor, and no API token metering. Just your ChatGPT account, your Chrome,
and your files.

Cortex Bridge is a **ChatGPT web coding bridge**: your ordinary ChatGPT web
chat plans the changes, a local executor applies them to your workspace, and
every write or command waits for your explicit approval. The model and usage
limits are whatever ChatGPT exposes to the account at that time; Cortex does
not promise or select a particular model version.

Created and maintained by [Jonas Suhard](https://github.com/Jonassuhard).
Project background and verified case study:
[jonassuhard.com/projets/cortex-bridge](https://jonassuhard.com/projets/cortex-bridge).

### Why use Cortex Bridge instead of…

| Tool | Typical setup | Cortex Bridge approach |
|------|---------------|------------------------|
| **Codex CLI** | Supported OpenAI account or API configuration | Uses the signed-in ChatGPT web session, without an API key |
| **Claude Code** | Supported Anthropic account or API configuration | Uses ChatGPT web instead of an Anthropic API |
| **Cline / Aider** | Bring an API provider or local model | Uses the model exposed in the ChatGPT conversation |
| **GitHub Copilot** | GitHub account and an eligible plan | Uses the existing ChatGPT web account |
| **Ollama + Cline** | Local model runtime and suitable hardware | No local model or GPU is required |

**The trade-off:** Cortex Bridge reads and writes the ChatGPT web interface
through a Chrome extension. DOM changes can temporarily break selectors, and
this conflicts with OpenAI's Terms of Use (see below). In exchange, Cortex
keeps API billing out of the path and requires human-approved audit trails.

### How it compares to other free coding agents

| Solution | LLM backend | Free? | Edits local files? | Human-in-the-loop? |
|----------|-------------|-------|--------------------|---------------------|
| **Cortex Bridge** | Model currently exposed in ChatGPT web | Can use a free ChatGPT account | Yes | Mandatory |
| Cline + Gemini | User-selected Gemini model | Free tiers may be available | Yes | Optional |
| OpenCode | Provider selected by the user | Free options may be available | Yes | Optional |
| Aider + Ollama | Local model selected by the user | Yes | Yes | Optional |
| Freebuff | Freebuff-managed model catalog | Check current Freebuff terms | Yes | Terminal-based |

**Cortex Bridge's distinction:** it connects the model already available in a
standard ChatGPT web conversation to local file access with mandatory human
approval. External model names, tiers, and limits can change independently of
Cortex Bridge.

### What Cortex Bridge does that ChatGPT and Codex don't

ChatGPT, Codex, and Cortex Bridge all use OpenAI models under the hood.
But they give you very different levels of control over your own machine.

| Capability | **ChatGPT (free web)** | **Codex (CLI / desktop)** | **Cortex Bridge** |
|------------|----------------------|--------------------------|-------------------|
| **LLM** | GPT-5.6 Luna | GPT-5.6 Terra/Sol (plan-gated) | GPT-5.6 Luna (via ChatGPT web) |
| **Edits your local files** | ❌ No — sandbox only | ✅ Yes (sandbox clone or local) | ✅ Yes — direct local filesystem |
| **Runs shell commands** | ❌ No | ✅ Yes | ✅ Yes (after your approval) |
| **Reads your real project** | ❌ Upload manually | ✅ Git clone or local folder | ✅ Direct folder access |
| **Sees your .env / node_modules** | ❌ No | ❌ Sandbox clone doesn't have them | ✅ Real project, real state |
| **Human approves every write** | N/A | ❌ Auto-applies | ✅ Mandatory |
| **Audit trail per change** | ❌ | ❌ Only git history | ✅ Every action timestamped |
| **Works offline** | ❌ | ❌ (cloud sandbox) | ✅ Local executor |
| **Cost** | Free | $20–200/mo or API token | Free |
| **ToS risk** | None (official) | None (official) | ⚠️ Browser automation (see below) |

**The bottom line:** ChatGPT is a chatbot that can't touch your files.
Codex is an agent that can, but costs money and runs in a sandbox.
Cortex Bridge gives you the agent-like local control, for free, with mandatory
human oversight — at the cost of a ToS gray area.

### How it compares to similar projects (ChatGPT web → local agent)

A handful of open-source projects share the same idea: use the free ChatGPT
web interface as a coding agent. Here is how Cortex Bridge stacks up.

| Project | Approach | GUI? | Agent loop? | Human approval? | Security model | Status |
|---------|----------|------|-------------|-----------------|---------------|--------|
| **Cortex Bridge** | Chrome Extension + FastAPI | ✅ React GUI | ✅ Mission protocol | ✅ Mandatory | Tokens, loopback, allowlist | ✅ Active (v0.5.2) |
| [chatgpt-browser-agent](https://github.com/abdallhMoukdad/chatgpt-browser-agent) | Puppeteer browser daemon | ❌ CLI + MCP only | ✅ `agent.js` (RUN/FILE blocks) | ⚠️ Optional (`--auto`) | None | ✅ Active |
| [headless-chatgpt](https://github.com/HalilCan/headless-chatgpt) | Puppeteer API emulator | ❌ REST API only | ❌ Prompt → response only | ❌ No execution layer | None | ❌ Dormant |
| [codex-chatgpt-control](https://github.com/adamallcock/codex-chatgpt-control) | SDK for Codex → ChatGPT delegation | ❌ SDK (Node/Python) | ❌ Delegates to Codex | ⚠️ Via Codex | Via Codex bridge | ✅ Alpha |
| [DevSpace](https://github.com/waishnav/devspace) | MCP server (official protocol) | ❌ ChatGPT UI | ❌ Tool-based | ✅ ChatGPT prompts you | MCP + owner password | ✅ Active (v1.0) |

> **DevSpace uses ChatGPT's official Developer Mode — which requires ChatGPT
> Plus ($20/mo). All other projects in this table work with a free ChatGPT
> account by automating the consumer web interface.**

**Cortex Bridge is the only project in this category that offers:** a graphical
console, mandatory human-in-the-loop on every write/command, a security model
with token pairing and command allowlisting, and two-writer conversation
isolation — all with a free ChatGPT account.

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

## Quick start

```bash
./scripts/install.sh --dry-run --json           # 1. Read the installation plan
./scripts/install.sh --approve-plan HASH --json # 2. Approve that exact plan
scripts/install-extension.sh                    # 3. Follow the Chrome extension guide
```

Then double-click **`Cortex Bridge.command`**. The console starts and opens the
interface. At any time, `scripts/cortex.sh doctor` reports what is missing and
how to repair it.

French guides: [getting started](docs/fr/DEMARRAGE.md) ·
[usage](docs/fr/UTILISATION.md) · [updating](docs/fr/MISE-A-JOUR.md) ·
[troubleshooting](docs/fr/DEPANNAGE.md)

No coding agent yet? The
[optional Freebuff-assisted walkthrough](docs/freebuff-installation.md) provides
a copyable, step-by-step installation prompt. Freebuff is a separate
third-party service, not a Cortex dependency or endorsed installer. Review its
current terms and privacy policy before sharing the repository.

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
  For a file send, the extension prepares the exact ChatGPT URL, filename and
  composer text. A small local macOS Accessibility helper receives only the
  URL, plain filename and `expected_text_sha256`, the SHA-256 of the normalized
  text, through standard input capped at 64 KiB; the plaintext prompt never
  enters the helper request. It applies a global AX timeout, verifies one
  unique target across all Chrome windows, and presses the send control only
  when the file, composer, and control share one exact bounded AX ancestor.
  Cortex then requires a new DOM message containing the exact text and
  attachment. No OpenAI API is involved and uncertain delivery is never
  retried.
- Writes only to classic ChatGPT chats: since ChatGPT's Chat/Work split, Work
  surfaces are detected in the DOM and refused (`WORK_SURFACE_REJECTED`), and
  new chats are always started on the classic Chat home.
- Captures the exact bound ChatGPT tab through CDP (Chrome `debugger`
  permission), never through whichever tab merely happens to be visible. A
  toolbar click can prepare a one-shot capture; unattended missions use the
  same exact-tab path directly.
- Stores mutable runtime state under `CORTEX_HOME`, outside the repository.

The deterministic executor works without Ollama. Ollama is optional. No OpenAI
API is used. Login, terms, CAPTCHA, rate limits, and security checks remain
human actions.

## Install on macOS

Requirements: [Google Chrome](https://www.google.com/chrome/),
[Python 3.11+](https://www.python.org/downloads/macos/),
[Git](https://git-scm.com/download/mac), and a ChatGPT account.
Sending files also requires Apple's Command Line Tools (`swiftc`) and one
manual macOS Accessibility permission. Neither is required to start Cortex or
use text-only chat.

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

Before the first file send, run `./scripts/cortex.sh doctor --json` and check
`swift_toolchain`, `macos_ax_helper`, and `macos_accessibility`. The first two
verify the compiler and installed helper. The last one requires the user to
enable the helper in **System Settings > Privacy & Security > Accessibility**.
A permission warning does not block startup or text chat, but file sends fail
closed until it is granted.

If ChatGPT is logged out, Cortex opens the tab and shows **Retry** and **Close**.
Sign in in Chrome, then retry. Cortex never enters credentials or solves a
challenge.

Full instructions:

- [Installation guide](INSTALL.md)
- [Agent-assisted installation](docs/agent-installation.md)
- [Optional Freebuff-assisted installation](docs/freebuff-installation.md), for
  users who do not already have a coding agent
- [User guide](docs/user-guide.md)
- [Testing](docs/testing.md)
- [Security model](docs/security-model.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Archived releases](docs/archive/README.md)

## Verification boundary

Automated gates cover the backend, extension protocol, frontend, responsive
views, accessibility, two-writer isolation, 10-second switching, installation,
process ownership, dependencies, and privacy. On 2026-08-15 an owner-authorized
live pass ran in real Chrome with synthetic markers; see
[live QA evidence](docs/verification/v1-live-qa-2026-08-15.md). That report
predates the current macOS Accessibility activation path and does not prove
that path. A fresh signed-in Chrome file-send observation must record the
extension preparation, native press and DOM delivery proof before the current
attachment gate can be marked passed. These runs prove technical behavior
only; they do not lift the provider-terms conflict above and are not presented
as provider-authorized acceptance.

See the [release checklist](docs/release-checklist.md) for the current gate
status. The immutable v0.5.3 evidence manifest is generated only from the final
clean release commit. An officially supported transport remains the only route
to a provider-authorized live release.

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
- File sends require a separate macOS Accessibility grant. The helper is
  compiled locally under `CORTEX_HOME/bin` and accepts the expected ChatGPT
  URL, filename and normalized-text SHA-256 through bounded standard input.
  Its activation arguments and logs contain no prompt, attachment path, file
  content, or target URL.
- Doctor hashes the installed helper and checks its file identity around the
  permission probe. This does not prevent a same-UID process from racing the
  executable path; see the documented [integrity boundary](docs/security-model.md#doctor-integrity-boundary).
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
- Text-only chat does not require macOS Accessibility. File sending does, and
  Cortex refuses the send if the permission, exact Chrome tab, prepared file,
  or unique send control cannot be verified.
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

**Differentiator:** Uses the ChatGPT web interface instead of an OpenAI API,
with mandatory human approval on every write or command. Cortex does not
promise a particular ChatGPT model, plan, quota, or price.

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
