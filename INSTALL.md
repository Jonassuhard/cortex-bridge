# Install Cortex Bridge v0.5 on macOS

The installer is plan-based. A dry-run cannot mutate the machine. Installation requires the exact hash of the plan you reviewed.

## Requirements

- [Git for macOS](https://git-scm.com/download/mac)
- [Python 3.11 or newer for macOS](https://www.python.org/downloads/macos/)
- [Playwright Chromium](https://playwright.dev/python/docs/browsers), downloaded only after approval
- A [ChatGPT](https://chatgpt.com/) account, signed in manually

Optional:

- [Node.js](https://nodejs.org/en/download) to rebuild the interface
- [Ollama for macOS](https://ollama.com/download/mac) for an optional local model

WebBridge is compatibility-only. There is no public official distribution link, so Cortex Bridge does not install it.

## 1. Inspect the plan

```bash
./scripts/install.sh --dry-run --json
```

Review:

- `commands`, including every argument;
- `official_url` for each install source;
- `disk_bytes`;
- `rollback`;
- `human_pauses`;
- `plan_hash`.

The plan must not contain `sudo`. Login, terms, extensions, secrets and large downloads remain human pauses.

## 2. Approve that exact plan

```bash
./scripts/install.sh --approve-plan PLAN_HASH --json
```

Changing an option changes the hash. Generate and review a new plan before approving it.

Optional UI rebuild:

```bash
./scripts/install.sh --dry-run --json --rebuild-ui
```

Optional Ollama model:

```bash
./scripts/install.sh --dry-run --json --with-ollama-model MODEL_TAG
```

Neither option runs until its exact plan hash is approved.

## 3. Diagnose the installation

```bash
./scripts/cortex.sh doctor --json
```

The deterministic mode must be available without Ollama. Optional services appear as warnings, not fake failures.

## 4. Start Cortex Bridge

```bash
./scripts/cortex.sh start
./scripts/cortex.sh status --json
```

Open `http://127.0.0.1:8420`. Complete ChatGPT login in the dedicated Chromium profile yourself.

## Runtime data

By default, mutable data lives under:

```text
~/.local/share/cortex-bridge
```

Set an absolute `CORTEX_HOME` before installation to choose another location. Relative paths are rejected.

Model storage uses this priority:

1. `CORTEX_MODEL_DIR`
2. legacy `CORTEX_STORAGE_PATH`
3. `~/.ollama/models`

## Stop

```bash
./scripts/cortex.sh stop
```

Stop refuses a foreign listener or a process whose persisted identity no longer matches.

## Uninstall

Inspect first:

```bash
./scripts/uninstall.sh --dry-run --json
```

Then approve the exact uninstall plan:

```bash
./scripts/uninstall.sh --approve-plan PLAN_HASH --json
```

The uninstaller removes only resources listed in Cortex Bridge’s ownership manifest. Settings, databases, runs, attachments, browser profiles and logs are preserved unless the user removes them separately.

## Agent-assisted installation

Agentic LLMs must follow [docs/agent-installation.md](docs/agent-installation.md). They may inspect and present a plan, but they cannot approve it on the user’s behalf.
