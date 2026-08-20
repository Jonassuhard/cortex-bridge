# Chrome extension transport notes

The implemented v0.5 transport lives in `chrome-extension/` and `transport/`.
It links Cortex to ChatGPT tabs in the user's existing Chrome window through an
authenticated loopback WebSocket and structured commands.

This directory contains architecture notes only. Login, CAPTCHA, rate limits,
account decisions, and third-party terms remain the user's responsibility.
Cortex does not enter credentials, call private ChatGPT endpoints, or fall back
to a separate browser.

Use synthetic fixtures in CI. A real ChatGPT session is a manual owner gate
with redacted evidence.

See [ChatGPT web transport](../../docs/chatgpt-web-transport.md) and
[security model](../../docs/security-model.md).
