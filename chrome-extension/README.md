# Cortex Bridge Chrome extension

This unpacked Manifest V3 extension links the local Cortex Bridge application
to ChatGPT tabs in the same Google Chrome window.

It can access only `http://127.0.0.1:8420/*` and
`https://chatgpt.com/*`. It does not request cookie, password, history, or
all-sites permissions. Pairing requires a single-use token created by the local
application.

Permissions: `activeTab` and `scripting` drive the composer, `storage` keeps
local pairing state, and `debugger` lets the service worker take an immediate
CDP screenshot of a Cortex-bound ChatGPT tab when no fresh toolbar-click
authorization is available — the click-authorized path remains primary, and
the debugger session is detached right after each capture. Chrome shows its
standard "debugging this browser" banner while a capture is in flight.

Since ChatGPT's Chat/Work split, the content script refuses to compose on Work
surfaces (`WORK_SURFACE_REJECTED`) and only ever writes to classic chats.

Installation is intentionally manual for v0.5.0: open `chrome://extensions`,
enable Developer mode, choose **Load unpacked**, and select this directory.
