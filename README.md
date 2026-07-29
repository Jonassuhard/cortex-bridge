# Cortex Bridge

Cortex Bridge connects a ChatGPT conversation to a reviewed executor on your Mac. Messages stay messages. Local execution starts only after a separate preflight shows the workspace, capabilities, approval policy and limits.

![Animated Cortex Bridge architecture](docs/media/architecture-flow.gif)

[Static architecture image](docs/media/architecture-flow.png)

## What v0.5 does

- Mirrors the latest 50 ChatGPT conversations through a dedicated Playwright Chromium profile.
- Groups real conversations as Pinned, Projects and Recent without inventing metadata.
- Sends the exact composer draft to ChatGPT. `Enter` sends, `Shift+Enter` adds a line.
- Keeps two conversation writers isolated. A third conversation keeps its draft and file but cannot send until a slot is free.
- Shows independent ChatGPT and executor status in French.
- Uses an explicit execution preflight. File writes, processes and network access are disabled by default.
- Supports PNG, JPEG, GIF, WebP, PDF, UTF-8 text, JSON, CSV, Markdown, DOCX, XLSX and PPTX attachments.
- Enforces 20 MiB per image and 512 MiB per other supported file.
- Stores runtime state under `CORTEX_HOME`, outside the repository.
- Starts and stops only processes whose persisted identity Cortex Bridge can prove.

The deterministic executor works without Ollama. Ollama is optional. WebBridge remains a compatibility transport and has no public official distribution.

## Current verification

The fixture release gates cover backend behavior, frontend unit tests, three responsive viewports, accessibility, two-conversation isolation, a 10-second hard switch limit, installation dry-runs, process ownership and privacy contracts.

Fixture tests do not prove that the current ChatGPT website still matches the browser adapter. ChatGPT login and live acceptance remain manual, explicit gates because automating a consumer web UI is inherently fragile.

See [Testing](docs/testing.md) and the machine-readable [release evidence](docs/verification/v0.5.0.json) when it is generated for the final commit.

## Install on macOS

Read the plan before allowing any mutation:

```bash
./scripts/install.sh --dry-run --json
```

The JSON output lists every command, official URL, estimated disk use, rollback and `plan_hash`. Review it, then run the exact same plan with explicit approval:

```bash
./scripts/install.sh --approve-plan PLAN_HASH --json
./scripts/cortex.sh doctor --json
./scripts/cortex.sh start
```

Open `http://127.0.0.1:8420`. The Playwright profile opens separately so you can sign in to ChatGPT yourself. Cortex Bridge never enters credentials or accepts third-party terms.

Full instructions:

- [Installation guide](INSTALL.md)
- [Agent-assisted installation](docs/agent-installation.md)
- [User guide](docs/user-guide.md)
- [v0.5 UI audit](docs/ui-audit-v0.5.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Launch strategy](docs/launch-strategy.md)

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
corepack enable
cd frontend && corepack npm ci && cd ..
PYTHON=.venv/bin/python ./scripts/test-all.sh
```

The repository pins Python dependencies by hash and npm by lockfile plus `npm@11.18.0`. `scripts/npmw` always delegates to the package-manager version declared by the frontend package.

## Security model

Cortex Bridge reduces risk but is not a general-purpose security sandbox.

- The HTTP service binds to loopback.
- Work is confined to the approved workspace by path and symlink checks.
- Process commands pass through capability and per-command approval policies.
- Delivery uncertainty never triggers an automatic resend.
- Attachments use opaque, expiring tokens rather than client paths.
- Stop refuses foreign listeners and stale or reused PIDs.

Read [Security](SECURITY.md) and the [security model](docs/security-model.md) before using execution capabilities on important files.

## Repository map

```text
console/        FastAPI API, settings, chat and mission endpoints
executor/       Reviewed local tools and process policy
frontend/       React/Next.js conversation interface and browser tests
orchestration/  Mission protocol, state machine and SQLite store
transport/      Playwright transport, compatibility adapter and fixtures
scripts/        Lifecycle, install, verification and release gates
tests/          Backend, security, packaging and acceptance contracts
docs/           Architecture, user, security and release documentation
```

## Known boundaries

- macOS is the only v0.5 release target.
- Live ChatGPT behavior can change without notice.
- Login, CAPTCHA, rate limits and account policy decisions stay with the user.
- Three live mini-site missions are never run without explicit approval for the ChatGPT profile and disposable workspace.
- Historical privacy cleanup may require a separate repository-history decision even after the current tree is clean.

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests must keep the backend, frontend, browser, privacy, link and release-evidence gates green.

## License

MIT. See [LICENSE](LICENSE).
