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
- Optional for file attachments: [Apple Command Line Tools](https://developer.apple.com/xcode/resources/)
  (`swiftc`). A fresh installation without `swiftc` still installs and starts
  text chat; its reviewed plan records file sending as unavailable. To add
  file sending later, complete Apple's `xcode-select --install` dialog, then
  generate and approve a new Cortex installation plan.

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
5. confirm that **Cortex Bridge 0.5.3** is enabled.

The extension can access only `https://chatgpt.com/*` and
`http://127.0.0.1:8420/*`. It does not request cookies, passwords, history, or
all-sites access.

## 4. Run Doctor and start the local interface

```bash
./scripts/cortex.sh doctor --json
./scripts/cortex.sh start
./scripts/cortex.sh status --json
```

Doctor must report the `chrome_extension` manifest as `pass`. This check proves
only that the unpacked extension files on disk have a valid manifest; it does
not prove that Chrome loaded the extension or that the extension is paired.
Open
`http://127.0.0.1:8420` in Google Chrome, then press **Open and connect
ChatGPT**. Cortex opens or focuses ChatGPT in the same Chrome window.

After the human Chrome step, verify the separate runtime state:

```bash
curl --fail --silent http://127.0.0.1:8420/api/chrome-extension/status
curl --fail --silent http://127.0.0.1:8420/api/transport/probe
```

The first response must report `paired: true` and a compatible protocol. The
second must report no blocker and a present composer before ChatGPT is called
ready.

Doctor also reports three file-send checks:

- `swift_toolchain`: whether `swiftc` can build the local helper;
- `macos_ax_helper`: whether the installed helper is executable, non-symlinked,
  and matches its recorded source and binary hashes;
- `macos_accessibility`: whether macOS has granted Accessibility access.

These checks do not prevent Cortex from starting or sending text. Any failed
helper check blocks file sending. `macos_accessibility` is expected to remain a
warning until the person using the Mac grants the permission.

If the dialog says login or verification is required, complete it in the
ChatGPT tab and press **Retry**. Cortex never types credentials, accepts terms,
or solves CAPTCHA.

## 5. Enable file sending once

The extension cannot create a macOS-trusted click. For attachments, it stages
the file and verifies the exact ChatGPT tab, filename and unique send control.
The local `cortex-macos-ax-send` helper then performs the single Accessibility
press. Cortex accepts success only after the ChatGPT DOM exposes a new user
message with the exact text and attachment.

1. Apply the reviewed installation plan. On macOS, that plan compiles the
   tracked Swift helper in staging and installs it atomically.
2. Open **System Settings > Privacy & Security > Accessibility**.
3. Enable the Cortex helper requested by macOS. This is a manual user decision;
   the installer and an installation agent cannot grant it.
4. Run `./scripts/cortex.sh doctor --json` again and confirm that
   `macos_accessibility` is `pass` before testing a synthetic file.

The helper receives a bounded JSON request on standard input containing only
the expected ChatGPT HTTPS URL, plain filename and `expected_text_sha256`, the
SHA-256 of the whitespace-normalized composer text. It never receives the full
prompt. Activation arguments identify only the helper executable; no target
URL, prompt, attachment path, file content, or credential is placed in process
arguments or logs.

## Runtime data

Mutable data defaults to `~/.local/share/cortex-bridge`. Set an absolute
`CORTEX_HOME` before installation to choose another location. Relative paths
are rejected. The compiled attachment helper lives in `CORTEX_HOME/bin` with
owner-only execution permissions. Symlinked helper paths are rejected.

## Stop and uninstall

```bash
./scripts/cortex.sh stop
./scripts/uninstall.sh --dry-run --json
./scripts/uninstall.sh --approve-plan PLAN_HASH --json
```

The uninstaller removes only manifest-owned runtime resources, including its
recorded virtual environment and native helper. It does not delete the
repository extension, Chrome data, settings, databases, runs, attachments, or
logs. Remove the helper's stale Accessibility entry separately after the
approved uninstall.

## Agent-assisted installation

Agents must follow [docs/agent-installation.md](docs/agent-installation.md).
They may inspect and apply an approved plan, but they cannot approve the hash,
install the extension, sign in, or accept third-party terms for the user.

If you do not already have a coding agent, the
[optional Freebuff walkthrough](docs/freebuff-installation.md) explains how to
install the separate Freebuff CLI, protect private data, and give it the exact
Cortex installation contract. Freebuff is not a Cortex dependency and is not
affiliated with or endorsed by Cortex Bridge. Freebuff currently advertises a
no-key CLI, but its models, access, limits, terms, and privacy practices can
change. Verify them on Freebuff's official pages before installing it.
