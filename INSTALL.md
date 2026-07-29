# Install Cortex Bridge v0.5 on macOS

The installer is plan-based. A dry run cannot mutate the machine, and applying
the plan requires the exact hash that was reviewed.

v0.5 installs a technical prototype. Authenticated consumer-site acceptance is
`BLOCKED_BY_PROVIDER_TERMS` under the current
[OpenAI Europe Terms of Use](https://openai.com/policies/eu-terms-of-use/),
which prohibit automatically or programmatically extracting data or Output.
Installing the local components does not clear that release gate.

## Requirements

- [Google Chrome](https://www.google.com/chrome/) 116 or newer
- [Git for macOS](https://git-scm.com/download/mac)
- [Python 3.11 or newer](https://www.python.org/downloads/macos/)

Optional: [Node.js](https://nodejs.org/en/download) for a UI rebuild and
[Ollama](https://ollama.com/download/mac) for an optional local model.
Playwright Chromium is needed only for development browser tests.

## 1. Inspect the plan

```bash
./scripts/install.sh --dry-run --json
```

Review `commands`, `official_url`, `disk_bytes`, `rollback`, `human_pauses`,
`chrome_extension_path`, and `plan_hash`. The plan must not contain `sudo`.

## 2. Approve that exact plan

```bash
./scripts/install.sh --approve-plan PLAN_HASH --json
```

Changing an option changes the hash. Generate and review a new plan before
approving it.

Optional UI rebuild:

```bash
./scripts/install.sh --dry-run --json --rebuild-ui
```

Optional Ollama model:

```bash
./scripts/install.sh --dry-run --json --with-ollama-model MODEL_TAG
```

## 3. Review the Chrome extension

Chrome does not allow a local application to silently install an unpacked
extension. This one-time step requires the person using Chrome:

1. open `chrome://extensions`;
2. enable **Developer mode**;
3. choose **Load unpacked**;
4. select the absolute `chrome_extension_path` printed by the installer;
5. confirm that **Cortex Bridge 0.5.0** is enabled.

The extension can access only `https://chatgpt.com/*` and
`http://127.0.0.1:8420/*`. It does not request cookies, passwords, history, or
all-sites access.

## 4. Run Doctor and start the local interface

```bash
./scripts/cortex.sh doctor --json
./scripts/cortex.sh start
./scripts/cortex.sh status --json
```

Doctor must report the `chrome_extension` manifest as `pass`. Open
`http://127.0.0.1:8420` in Google Chrome, then press **Open and connect
ChatGPT**. Cortex opens or focuses ChatGPT in the same Chrome window.

If the dialog says login or verification is required, complete it in the
ChatGPT tab and press **Retry**. Cortex never types credentials, accepts terms,
or solves CAPTCHA.

## Runtime data

Mutable data defaults to `~/.local/share/cortex-bridge`. Set an absolute
`CORTEX_HOME` before installation to choose another location. Relative paths
are rejected.

## Stop and uninstall

```bash
./scripts/cortex.sh stop
./scripts/uninstall.sh --dry-run --json
./scripts/uninstall.sh --approve-plan PLAN_HASH --json
```

The uninstaller removes only manifest-owned runtime resources. It does not
delete the repository extension, Chrome data, settings, databases, runs,
attachments, or logs.

## Agent-assisted installation

Agents must follow [docs/agent-installation.md](docs/agent-installation.md).
They may inspect and apply an approved plan, but they cannot approve the hash,
install the extension, sign in, or accept third-party terms for the user.
