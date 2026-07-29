# Consumer web transport notes

The implemented v0.5 transport is in `transport/`. This directory contains compatibility notes only.

Cortex Bridge uses a dedicated persistent Playwright Chromium profile by default. The optional WebBridge adapter exists for compatibility, but Cortex Bridge has no verified public distribution URL for WebBridge and therefore does not install it.

Browser automation targets a changing consumer interface. Login, CAPTCHA, rate limits, account decisions and third-party terms remain the user’s responsibility. Cortex Bridge does not bypass them, enter credentials or call private ChatGPT endpoints.

Use synthetic fixtures in automated tests. A live ChatGPT session is a manual owner gate and must never run in CI.

See [ChatGPT web transport](../../docs/chatgpt-web-transport.md) and [legal notes](../../docs/legal-notes.md).
