# Chrome Tab Bridge Design

**Status:** Approved for implementation  
**Date:** 2026-07-30  
**Target:** Cortex Bridge v0.5.0

## Objective

Cortex Bridge must use the person's real, already-authenticated Google Chrome
profile. Pressing `Open and connect ChatGPT` in Cortex opens or focuses
`https://chatgpt.com/` as a tab in the same Chrome window as Cortex, verifies
the page, and links it to the local bridge. A separate Playwright browser is
never opened by the normal product flow.

The flow is complete only when Cortex can distinguish and display:

- the local Chrome extension is missing;
- the extension is installed but not paired;
- ChatGPT is opening or loading;
- ChatGPT requires login;
- ChatGPT requires a human verification or CAPTCHA;
- the composer is present and the tab is linked;
- the tab was closed or the extension disconnected.

## User flow

1. The user opens Cortex at `http://127.0.0.1:8420` in Google Chrome.
2. The primary action reads `Open and connect ChatGPT`.
3. Cortex creates a single-use pairing token and publishes it to the extension
   content script running on the Cortex page.
4. The extension proves possession of the token over the loopback WebSocket.
5. The extension focuses an existing `chatgpt.com` tab in the same Chrome
   window, or creates one immediately next to the Cortex tab.
6. Cortex displays `Checking the ChatGPT connection...` and runs a read-only
   DOM probe.
7. A usable composer produces `ChatGPT connected` and enables synchronization.
8. A login page produces a dialog that says the user must sign in in the
   opened Chrome tab. The only actions are `Retry` and `Close`.
9. A CAPTCHA or verification produces the same human-only recovery pattern.
10. Closing the dialog never sends a message, solves a challenge, or opens a
    fallback browser.

If the extension is absent, Cortex shows an installation explanation and the
path of the unpacked extension. Chrome does not permit a normal local
application to silently install an unpacked extension, so installation remains
an explicit one-time user action.

## Architecture

```text
Cortex tab (127.0.0.1:8420)
  -> one-time pairing token
Chrome MV3 extension service worker
  -> authenticated loopback WebSocket
Cortex FastAPI bridge manager
  -> allowlisted commands and correlated results
Chrome extension content script
  -> DOM of the bound chatgpt.com tab
```

The extension uses Manifest V3 and requires Chrome 116 or newer. Its service
worker maintains an outbound WebSocket to
`ws://127.0.0.1:8420/api/chrome-extension/ws` and sends a heartbeat every 20
seconds. Chrome documents this pattern for keeping an MV3 service worker active
from Chrome 116 onward.

The extension stores the Cortex tab's `windowId`, tab ID, and index when it
receives a pairing token. `chrome.tabs.create` or `chrome.tabs.update` then
opens/focuses ChatGPT in that exact window. It never creates a Chrome window.

The backend exposes four public operations:

- `POST /api/chrome-extension/pairing`: create a 60-second, single-use token;
- `GET /api/chrome-extension/status`: return connection, pairing, tab, and
  ChatGPT probe state;
- `POST /api/chrome-extension/open`: open/focus ChatGPT and return the probe;
- `POST /api/chrome-extension/retry`: rerun the read-only probe.

The WebSocket endpoint is an internal transport. Every request carries a
random request ID, a logical browser session ID, an allowlisted command name,
and structured arguments. Responses carry the same request ID and either a
structured result or a stable error code. Raw JavaScript evaluation is not
part of the extension protocol.

## Session and tab ownership

The existing maximum of two writing conversations remains authoritative.
Writer leases are acquired before a browser tab is assigned.

- the read-only synchronization session follows the primary linked ChatGPT tab;
- the first writer may claim the primary tab when it matches its conversation;
- the second writer receives a second ChatGPT tab in the same Chrome window;
- each writer session remains bound to one tab and one canonical conversation;
- a third writer is rejected before any tab is opened or message is sent;
- closing a bound tab pauses that session with `TAB_CLOSED`.

Switching a conversation uses the ChatGPT SPA link when available and otherwise
navigates the bound tab. The existing absolute 10-second selection deadline
continues to apply.

## Extension command surface

The extension implements only these command families:

- tab: open/focus, navigate, list, close;
- page: probe, full state, light state, list conversations;
- composer: send text, stop, await attachment, send attachment-only;
- model: list and select;
- media: staged file upload and visible-tab screenshot.

DOM logic lives in the packaged `chatgpt-content.js` file. The backend cannot
inject arbitrary code. Content scripts run only on `https://chatgpt.com/*` and
the pairing relay runs only on `http://127.0.0.1:8420/*`.

Attachments use the existing opaque staged-file tokens and validated paths.
The extension transport moves file data in bounded chunks and reconstructs a
`File` inside the ChatGPT content script. Cortex reports its own safe transfer
limit separately from ChatGPT's current product limit and rejects oversized
files before transmission. It never claims that Chrome accepted a file until
an attachment chip is visible.

Screenshots use the extension's tab capture capability on the bound, visible
ChatGPT tab. Captures are written only beneath `CORTEX_HOME`, then exposed to
the existing staged-attachment flow. Capture failure is explicit and never
substituted with an unrelated screen.

## Pairing and security

- WebSocket connections are accepted only on loopback.
- Pairing tokens use at least 256 bits of entropy, expire after 60 seconds, and
  are consumed once.
- An unpaired extension may only send heartbeats and a pairing request.
- The backend rejects duplicate request IDs, unknown command names, oversized
  payloads, and messages without a paired connection.
- Extension host access is restricted to `chatgpt.com` and
  `127.0.0.1:8420`.
- The extension never reads Chrome cookies, passwords, history, or other sites.
- Credentials, DOM message contents, file bytes, and pairing tokens are never
  written to application logs.
- Login, terms, CAPTCHA, rate limits, and security checks are never automated.
- A disconnect fails closed. Cortex does not fall back to Playwright silently.

Playwright remains available only as an explicit development and synthetic-test
transport under Advanced settings. It is not presented as the normal user
connection.

## UI states and copy

The paired status rail remains visible beside the conversation title:

- `ChatGPT — Disconnected` / `Checking` / `Login required` / `Connected`;
- `Local agent — Unavailable` / `Ready` / `Working` / `Approval required`.

The connection dialog uses a stable code-to-copy mapping:

| Code | Title | Body |
| --- | --- | --- |
| `EXTENSION_MISSING` | `Chrome extension not detected` | Install or enable the Cortex Bridge extension, then retry. |
| `LOGIN_REQUIRED` | `Sign in to ChatGPT` | ChatGPT is open in Chrome, but you are not signed in. Sign in in the ChatGPT tab, then retry. |
| `CAPTCHA` | `Verification required` | Complete the verification in the ChatGPT tab, then retry. |
| `CHATGPT_LOADING` | `ChatGPT is still loading` | Keep the tab open and retry in a moment. |
| `CONNECTED` | `ChatGPT connected` | Cortex is linked to this Chrome tab. |
| `TAB_CLOSED` | `ChatGPT tab closed` | Reopen and connect ChatGPT to continue. |

The dialog has `Retry` and `Close` actions for recoverable states, closes on
Escape, traps focus, and returns focus to the triggering button. Technical
diagnostics remain behind the existing activity/settings surfaces.

## Installation and distribution

The repository ships an unpacked extension directory and an English guide:

1. run the Cortex installer;
2. open `chrome://extensions`;
3. enable Developer mode;
4. choose `Load unpacked` and select the printed extension directory;
5. open Cortex in Chrome and press `Open and connect ChatGPT`;
6. approve/sign in only in Chrome;
7. run Doctor and require the extension and ChatGPT checks to pass.

The agent installation guide must ask the person to approve extension
installation before opening Chrome settings. A later Chrome Web Store package
may remove the unpacked-install step, but it is not a v0.5.0 release claim.

## Verification

Automated gates must cover:

- pairing token entropy, expiry, single use, and replay rejection;
- WebSocket disconnects, timeouts, request correlation, and allowlist rejection;
- same-window tab selection and no `windows.create` call;
- extension-missing, login, CAPTCHA, loading, connected, and tab-closed states;
- one writer, two isolated writers, and third-writer rejection;
- text send delivery states, one small file, one screenshot, and oversized-file
  rejection;
- French UI copy, keyboard dialog behavior, accessibility, responsive layout,
  build, privacy scan, dependency audit, install, Doctor, and uninstall.

The final live gate uses the owner's real Chrome session and must record only
redacted evidence. Automated fixtures do not turn that gate green.

## Official Chrome references

- [WebSockets in extension service workers](https://developer.chrome.com/docs/extensions/how-to/web-platform/websockets)
- [Chrome tabs API](https://developer.chrome.com/docs/extensions/reference/api/tabs)
- [Content scripts](https://developer.chrome.com/docs/extensions/develop/concepts/content-scripts)
- [Extension permissions](https://developer.chrome.com/docs/extensions/develop/concepts/declare-permissions)
