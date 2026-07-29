# Manual development setup

Use this path when you want to inspect every command instead of running the consent-bound installer.

## Prerequisites

- Git
- Python 3.11 or newer
- Node.js with Corepack for frontend development

ChatGPT login and Playwright Chromium remain separate human actions.

## Python environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
```

Install Playwright Chromium only after reviewing the download:

```bash
.venv/bin/python -m playwright install chromium
```

## Frontend environment

```bash
corepack enable
cd frontend
corepack npm ci
cd ..
```

Do not replace `npm ci` with `npm install`; the release uses the committed lockfile and `npm@11.18.0`.

## Runtime data

```bash
export CORTEX_HOME="$HOME/.local/share/cortex-bridge"
```

`CORTEX_HOME` must be absolute. Do not place browser profiles, databases or attachments inside the repository.

## Build and test

```bash
scripts/build-ui.sh
PYTHON=.venv/bin/python scripts/test-all.sh
```

## Start

```bash
scripts/cortex.sh doctor --json
scripts/cortex.sh start
```

Open `http://127.0.0.1:8420` and complete login in the dedicated browser profile.

## Optional Ollama

Install Ollama only if you want a local model executor. The deterministic executor remains the default and requires no model download. Cortex Bridge lists detected Ollama tags after a capability probe and marks tested tags as recommendations without blocking other installed tags.

## Remove the installation

Use the ownership-aware plan in [INSTALL.md](../INSTALL.md). Manual deletion of `CORTEX_HOME` also deletes user data and is intentionally outside the automated uninstaller.
