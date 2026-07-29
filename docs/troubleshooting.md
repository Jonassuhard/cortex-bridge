# Troubleshooting

Start with:

```bash
./scripts/cortex.sh doctor --json
./scripts/cortex.sh status --json
```

## Extension Chrome introuvable

Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**,
and select the `chrome_extension_path` printed by the installer. Ensure Cortex
Bridge is enabled, reload the Cortex tab, and retry.

## ChatGPT requires login, CAPTCHA, or verification

Use the ChatGPT tab that Cortex opened in the same Chrome window. Complete the
human action, then press **Réessayer**. Cortex does not type credentials,
accept terms, solve CAPTCHA, or bypass rate limits.

## ChatGPT stays in loading state

Wait for the ChatGPT page to finish, check that the composer is visible, and
retry. If the page changed incompatibly, the probe reports missing selectors;
Cortex does not open Playwright as a substitute.

## Conversation switching times out

The complete switch has a 10-second budget. Use **Recharger la conversation**
after checking the bound ChatGPT tab. A send is never retried automatically.

## A message is uncertain

Inspect the ChatGPT conversation directly. The click may have happened but the
visible confirmation did not. Resolve it manually before sending again.

## A third conversation cannot send

Two writer leases are active. Finish or cancel one. The third draft and file
remain in place.

## A file is rejected

The Chrome extension transfer limit is 25 MiB in v0.5. Check file type,
content, size, symlinks, and the visible ChatGPT error. Office files must have
the expected ZIP container structure.

## Screenshot capture is rejected

The bound ChatGPT tab must be the visible active tab in its Chrome window.
Cortex refuses to capture another page by accident.

## Console, fallback, or stop problems

If the fallback page appears, run `./scripts/build-ui.sh`. If the port is owned
by another process or the persisted identity is stale, Cortex refuses to take
ownership or signal it. Inspect Doctor and identify that process separately.

## Installer approval fails

Any option change creates a new hash. Generate a fresh dry run, review it, and
approve that exact hash. Never reuse a hash from another plan or machine.

Logs live under `CORTEX_HOME`. Remove personal content before sharing them.
