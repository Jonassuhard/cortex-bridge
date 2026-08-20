# Cortex Bridge Chrome extension

This unpacked Manifest V3 extension links the local Cortex Bridge application
to ChatGPT tabs in the same Google Chrome window.

It can access only `http://127.0.0.1:8420/*` and
`https://chatgpt.com/*`. It does not request cookie, password, history, or
all-sites permissions. Pairing requires a single-use token created by the local
application.

Installation is intentionally manual for v0.5.0: open `chrome://extensions`,
enable Developer mode, choose **Load unpacked**, and select this directory.
