# Terminal installation

This guide installs the Cortex Bridge 0.6.1 candidate as a local Python
package. It does not log in to ChatGPT, install the Chrome extension, grant
Accessibility permission, or select an execution model on the user's behalf.

## Supported local path

From the repository root:

```sh
python3 --version
./scripts/install.sh --dry-run --json
```

Review the complete plan and its `plan_hash`. Apply only the exact hash that was
reviewed:

```sh
./scripts/install.sh --approve-plan PLAN_HASH --json
./scripts/cortex.sh doctor --json
```

With `--json`, standard output contains exactly one JSON payload suitable for
an installation agent; dependency progress and compiler logs are sent to
standard error. Parse the payload before continuing and stop on a non-zero exit
code.

The installer owns only its `CORTEX_HOME` resources. It never uses `sudo`,
downloads an Ollama model unless that option is explicitly included in the
reviewed plan, and never replaces a foreign process.

On an existing managed installation, the plan compares the SHA-256 of
`requirements.lock` with the ownership manifest. A stale owned runtime is
recreated in staging, the previous virtualenv is kept as a rollback slot, and
the manifest is updated only after the replacement is complete. A venv missing
from the manifest is treated as foreign and is never overwritten.

## Launch

In a checkout, the shortest command is:

```sh
scripts/cortex
```

The default is the full-screen terminal client. It shows ChatGPT and executor
status side by side, lists at most 50 conversations, keeps requests off the UI
thread, and reports whether a send is confirmed. Use `Ctrl+N`, `Ctrl+R`,
`Ctrl+K` and `Ctrl+Q` for the common actions.

For a terminal without the required Textual capabilities, use the explicit
compatibility client:

```sh
scripts/cortex --plain
```

The package declares a `cortex` entry point. A distribution installer may expose
that entry point in a user-selected virtual environment; this repository does
not modify `PATH` or silently install a global command. If a user-managed
launcher is already present in `~/.local/bin`, a fresh shell can run `cortex`
directly; verify it with `command -v cortex` and `cortex --version`. The
repository launcher remains the portable checkout-local path.

## Chrome connection pause

Load `chrome-extension/` manually from `chrome://extensions`, open the local
Cortex page in that same Chrome window, then use **Open and connect ChatGPT**.
Login, terms, CAPTCHA and browser permission prompts remain human steps. Verify
pairing and readiness separately; a paired extension is not proof that the
ChatGPT composer is ready.

## Agent handoff

An installation agent must show the dry-run JSON, target, disk estimate,
`plan_hash`, rollback and human pauses before applying anything. It must ask for
the exact `APPROVE PLAN_HASH` confirmation, run Doctor afterwards, and report
local install, server, extension, ChatGPT connection and file-send states as
separate values. See [agent-installation.md](agent-installation.md).

No fixture, wheel import or local TUI test proves a live ChatGPT message, a
file/screenshot upload, a model-backed mission or a clean macOS lifecycle.
