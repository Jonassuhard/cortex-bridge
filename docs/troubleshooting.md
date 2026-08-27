# Troubleshooting

Start with:

```bash
./scripts/cortex.sh doctor --json
./scripts/cortex.sh status --json
```

## Chrome extension not found

Open `chrome://extensions`, enable Developer mode, choose **Load unpacked**,
and select the `chrome_extension_path` printed by the installer. Ensure Cortex
Bridge is enabled, reload the Cortex tab, and retry.

## The extension is detected but not paired

Since v0.5.4 the console pairs the extension automatically on load, so this
should resolve by itself within a few seconds. After a console restart the
extension also reconnects on its own within about 30 seconds. If it does not:
reload the Cortex tab, check that the server is running
(`./scripts/cortex.sh status`), and use the manual pairing button in the
console. The **Guide de démarrage** button in the sidebar shows the live state
of each setup step.

## The tab group is not created

The console and ChatGPT tabs are grouped under **Cortex Bridge** by the
extension. Grouping is best-effort and never blocks a mission; if the group is
missing, reload the extension on `chrome://extensions` (the `tabGroups`
permission was added in v0.5.4) and reopen ChatGPT from the console.

## Cortex says the extension must be reloaded

The files on disk are newer than the service worker currently running in
Chrome. Open `chrome://extensions`, reload only Cortex Bridge, close the
extensions page, then select **Retry** in Cortex. Cortex reloads its own page
once, resumes pairing automatically, and rejects an older protocol generation
before spending the pairing ticket. An outdated extension can no longer appear
connected, and a stale second copy cannot alter the status of the active one.

## ChatGPT requires login, CAPTCHA, or verification

Use the ChatGPT tab that Cortex opened in the same Chrome window. Complete the
human action, then press **Réessayer**. Cortex does not type credentials,
accept terms, solve CAPTCHA, or bypass rate limits.

## ChatGPT stays in loading state

Wait for the ChatGPT page to finish, check that the composer is visible, and
retry. If the page changed incompatibly, the probe reports missing selectors;
Cortex does not open Playwright as a substitute.

## Conversation switching times out

Chrome URL navigation returns as soon as the requested target is exposed, then
Cortex waits separately for the ChatGPT composer. The complete selection still
has a 10-second budget. Use **Recharger la conversation** after checking the
bound ChatGPT tab. A send is never retried automatically.

## A message is uncertain

Inspect the ChatGPT conversation directly. The click may have happened but the
visible confirmation did not. Resolve it manually before sending again.

For an attachment, this is `DELIVERY_UNCERTAIN`: the macOS press may have
started, but Cortex did not find a new DOM user message with the exact text and
file. Do not press Send or retry from Cortex until you have inspected the
conversation, otherwise a duplicate is possible.

## A third conversation cannot send

Two writer leases are active. Finish or cancel one. The third draft and file
remain in place.

## A file is rejected

The Chrome extension transfer limit is 25 MiB in v0.5. Check file type,
content, size, symlinks, and the visible ChatGPT error. Office files must have
the expected ZIP container structure.

If staging succeeds but sending fails, inspect the structured error:

| Error | Meaning | Action |
| --- | --- | --- |
| `NATIVE_HELPER_UNAVAILABLE` | `swiftc`, the helper source, compiled binary, or configured override is unavailable or unsafe | Run Doctor. Install Apple Command Line Tools if `swift_toolchain` fails; keep `CORTEX_HOME` absolute and do not use a symlinked helper. |
| `NATIVE_PERMISSION_REQUIRED` | macOS denied Accessibility access | Enable the exact Cortex helper in **System Settings > Privacy & Security > Accessibility**, then rerun Doctor. |
| `NATIVE_ACTIVATION_REQUIRED` | The extension did not return a verified native handoff | Reload only the Cortex Bridge extension, refresh Cortex, reconnect, and stage the file again. |
| `SEND_REJECTED` | The unique global AX target, toolbar omnibox, composer hash, bounded file/composer/send group, or AX deadline failed before the press | Focus the Cortex-bound ChatGPT tab, verify the visible file and exact draft, then create a fresh send. |
| `DELIVERY_UNCERTAIN` | The press may have started but the required new DOM message was not proven | Inspect ChatGPT manually. Never resend automatically. |

`./scripts/cortex.sh doctor --json` exposes the related checks:

- `swift_toolchain`: Apple `swiftc` is available;
- `macos_ax_helper`: the local helper is present and executable;
- `macos_accessibility`: the helper has the user's manual permission.

These checks do not block Cortex startup or text-only chat. A warning or
failure does block file sends. If Accessibility was granted to an older helper
after an update, remove that stale System Settings entry and enable the exact
current helper path reported by Doctor.

The native helper receives only the expected URL, plain filename and the
SHA-256 of normalized composer text through standard input capped at 64 KiB.
It does not receive or log the plaintext prompt, attachment path, or file
content. It also applies a 250 ms global AX timeout and accepts only one stable
target across all Chrome windows: one visible toolbar omnibox outside the web
area, plus a file, composer, and send control sharing one exact bounded common
AX ancestor. If an error occurs and the press may already have started,
inspect ChatGPT and do not retry: the bridge deliberately cannot prove that a
second send would be safe.

Doctor's helper hash, shared lock, and before/after inode checks protect
against ordinary tampering and concurrent Cortex updates. They are not meant
to contain a process already able to write as the same macOS user. Because
Darwin cannot execute the verified open descriptor through Python, a
swap-and-restore race remains theoretically possible; that same-UID attacker
is outside the current local threat model. Preventing it would require helper
signing and a native launcher.

## Screenshot capture is rejected

The bound ChatGPT tab must be the visible active tab in its Chrome window.
Cortex refuses to capture another page by accident.
The macOS Accessibility helper is not used for screenshots.

## Console, fallback, or stop problems

If the fallback page appears, run `./scripts/build-ui.sh`. If the port is owned
by another process or the persisted identity is stale, Cortex refuses to take
ownership or signal it. Inspect Doctor and identify that process separately.

## Installer approval fails

Any option change creates a new hash. Generate a fresh dry run, review it, and
approve that exact hash. Never reuse a hash from another plan or machine.

Logs live under `CORTEX_HOME`. Remove personal content before sharing them.
