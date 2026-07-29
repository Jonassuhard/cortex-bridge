# Manual setup

Prefer the plan-based installer in [INSTALL.md](../INSTALL.md). Use this page
only when inspecting each step manually.

## Python runtime

```bash
python3 -m venv "$HOME/.local/share/cortex-bridge/venv"
"$HOME/.local/share/cortex-bridge/venv/bin/python" -m pip install \
  --require-hashes -r requirements.lock
```

No Playwright browser download is required for normal use. Playwright Chromium
is only for the synthetic development test suite.

## Chrome extension

1. Open `chrome://extensions` in the Google Chrome profile that will use
   ChatGPT.
2. Enable Developer mode.
3. Select **Load unpacked**.
4. Choose the repository's `chrome-extension` directory.
5. Confirm Cortex Bridge 0.5.0 is enabled.

This action is manual. No script should click the Chrome confirmation or grant
permissions for the user.

## Start and connect

```bash
./scripts/cortex.sh doctor --json
./scripts/cortex.sh start
```

Open `http://127.0.0.1:8420` in the same Chrome window and press **Open and
connect ChatGPT**. Complete login or verification in the ChatGPT tab, then
retry in Cortex.

`CORTEX_HOME` must be absolute. Keep mutable runtime data outside the
repository.
