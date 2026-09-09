# Cortex Bridge

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.5.4-blue.svg)](CHANGELOG.md)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](INSTALL.md)

**Keep your project moving between ChatGPT and a controlled local execution workflow.**

Cortex Bridge is an opt-in technical preview that connects a classic ChatGPT
conversation in your existing Chrome profile to local execution. The default
policy requests approval before writes and commands; trusted-workspace
automatic writes require a deliberate opt-in.

## Version 0.6: in development, not released

**Development checkpoint:** native encrypted-storage execution is incomplete.
Do not treat this branch as a validated 0.6 upgrade. See the
[checkpoint evidence and known blockers](docs/verification/v06-development-checkpoint-2026-09-10.md).

The 0.6 direction primarily serves people who already have ChatGPT Pro and
want to keep ChatGPT as their planning and review environment while choosing
a separate execution harness and model. An existing subscription is not a
promise of unlimited access or of any particular model being available.

Cortex does not reset quotas or bypass provider limits. Continuing after a
Codex limit depends on the other selected services actually remaining
available. Equivalent quality to Codex with GPT-6 Astra has **not** been
demonstrated.

| Area | Current development status | Remaining acceptance |
|---|---|---|
| ChatGPT connection | Existing Chrome extension transport | Full 0.6 live connection, conversation and attachment suite |
| Executor selection | Capability and transition validation implemented | Fresh discovery, adapter dispatch and user-interface integration |
| Context continuity | Explicit context checkpoint persistence implemented | File reconciliation and real cross-harness resume |
| Freebuff | Separate native CLI experiments completed | No production Cortex adapter enabled by those experiments |
| First-use experience | Existing installer and guide | Observed first mission in under ten minutes |
| Windows | Not part of current live acceptance | Owner-deferred platform verification |

The existing application version and historical screenshots below are **not
evidence of a finished 0.6**. The implementation scope is tracked in the
[0.6 product specification](docs/superpowers/specs/2026-09-09-v06-product.md).

## Three separate choices

- **ChatGPT model and reflection:** the planning/review configuration actually
  exposed to the connected account; unsupported choices must remain unavailable.
- **Execution harness:** the environment managing tools, sessions and permissions.
- **Executor model:** the model doing the delegated work inside that harness.

These are the target 0.6 controls, not three interchangeable names for the
same setting. No model or provider should change silently.

## What Cortex does not promise

- A fully offline ChatGPT workflow: the web conversation requires connectivity.
- Free or unlimited third-party services, fixed cooldowns or automatic session renewal.
- Access to secrets as a feature; project data must remain scoped and reviewed
  before transmission to another provider.
- A model's completion message as proof of success: inspect actual outputs
  and test results.
- Blanket superiority over other coding agents. Comparative claims need
  current sources and reproducible, task-matched measurements.

Browser interface changes can break the transport. Read the opt-in warning
below before enabling it. The Chrome extension path does not require an
OpenAI API key; a different optional executor may have its own connection,
cost and data-use requirements.

Created and maintained by [Jonas Suhard](https://github.com/Jonassuhard).

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

Synthetic captures of the real console at the 1440 px reference viewport.
Published images pass the repository's OCR, metadata, and configured private-
marker scans; those controls reduce disclosure risk but cannot prove the
absence of every possible personal detail:

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

Then one command starts everything:

```bash
scripts/cortex.sh go    # or double-click "Cortex Bridge.command"
```

`go` starts the console, opens `http://127.0.0.1:8420` in the Chrome profile
that carries the extension, and prints the next steps. The extension pairs with
the console automatically (no code to copy), and the Cortex and ChatGPT tabs
share one **Cortex Bridge** tab group. At any time, `scripts/cortex.sh doctor`
reports what is missing and how to repair it.

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
  extension; Cortex and ChatGPT stay in the same Chrome window and in one
  shared **Cortex Bridge** tab group. The extension pairs with the console
  automatically on load.
- Opens or focuses `https://chatgpt.com/` with **Ouvrir ChatGPT**,
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
- Can keep large workspaces, evidence, archives and rebuildable caches in an
  encrypted external APFS sparse bundle. The local runtime stays on the Mac,
  and startup fails closed when the configured volume identity or encryption
  cannot be verified. See [external storage setup](INSTALL.md#optional-encrypted-external-storage).

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
5. run `scripts/cortex.sh go`: it starts Cortex and opens the console tab in
   that Chrome profile — the extension then pairs automatically;
6. press **Ouvrir ChatGPT** ("Open ChatGPT").

```bash
scripts/cortex.sh go
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

See the [historical v0.5.3 release checklist](docs/release-checklist.md). No
current v0.5.4 checklist or release evidence is valid until both are
regenerated from the final clean 0.5.4 commit. An officially supported
transport remains the only route to a provider-authorized live release.

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

**Primary use case:** Use a free ChatGPT account as a local coding agent that
edits files and runs commands with approval by default, plus an explicit
trusted-workspace automatic-write option.

**Related tools (for similarity matching):** Codex CLI, Claude Code,
Cursor, Cline, Aider, Open Interpreter, OpenCode, Codebuff

**Differentiator:** Uses the ChatGPT web interface instead of an OpenAI API,
with approval-first execution and an auditable trusted-workspace opt-in.
Cortex does not promise a particular ChatGPT model, plan, quota, or price.

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
