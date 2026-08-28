# Cortex Bridge Chrome extension

This unpacked Manifest V3 extension links the local Cortex Bridge application
to ChatGPT tabs in the same Google Chrome window.

It can access only `http://127.0.0.1:8420/*` and
`https://chatgpt.com/*`. It does not request cookie, password, history, or
all-sites permissions. Pairing requires a single-use token created by the local
application.

Permissions: `activeTab` and `scripting` drive the composer, `storage` keeps
local pairing and uncertain-tab quarantine state, and `debugger` lets the
service worker take a CDP screenshot of the exact Cortex-bound ChatGPT tab.
Toolbar and automatic captures use that same exact-tab operation; the debugger
session is detached right after each capture. The extension masks visible
navigation, sidebar and account areas before reading pixels and aborts if that
private mask cannot be confirmed and restored on the same document. Chrome shows its standard
"debugging this browser" banner while a capture is in flight.

Since ChatGPT's Chat/Work split, the content script refuses to compose on Work
surfaces (`WORK_SURFACE_REJECTED`) and only ever writes to classic chats.

Installation is intentionally manual for v0.5.4: open `chrome://extensions`,
enable Developer mode, choose **Load unpacked**, and select this directory.
