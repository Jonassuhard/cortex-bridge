# Security model

Cortex Bridge reduces the authority of browser-driven instructions. It is not
a virtual machine or a substitute for backups.

## Chrome boundary

- HTTP and WebSocket services bind to loopback.
- The Manifest V3 extension has host access only to `chatgpt.com` and
  `127.0.0.1:8420`.
- It requests no cookie, password, history, debugger, or all-sites permission.
- Pairing tokens contain 256 bits of entropy, expire after 60 seconds, and are
  consumed once.
- Unpaired connections may heartbeat and request pairing only.
- Commands use a fixed allowlist and structured payloads. Raw remote
  JavaScript is rejected.
- The user performs login, terms, CAPTCHA, rate-limit, and account decisions.
- Conversation identity is checked before delivery; uncertain delivery is
  never retried automatically.
- A disconnect fails closed and never falls back to Playwright.

## Execution boundary

- Chat messages cannot directly trigger local tools.
- Execution starts after a preflight identifies workspace, capabilities,
  approval policy, and limits.
- Paths must resolve inside the approved workspace; traversal, absolute paths,
  and symlink escapes are rejected.
- Process arguments are vectors without a shell and are bounded by time and
  output limits.
- Deployment, publishing, payment, credentials, and account modification are
  unsupported.

## Attachments and screenshots

- The backend validates extension, MIME signature, and Office containers.
- Client paths are rejected; opaque attachment tokens expire and resolve only
  to managed files.
- The extension v0.5 transfer limit is 25 MiB.
- Transfers use bounded chunks and require a visible ChatGPT attachment chip.
- Screenshots must be PNG data from the visible bound ChatGPT tab and are
  written atomically under `CORTEX_HOME`.

## Runtime ownership and release privacy

Start/stop records contain exact process identity. Stop refuses foreign
listeners, stale records, and PID reuse.

Public media must be synthetic or redacted. Release gates scan the tree and
history for secrets, private markers, paths, links, unknown binaries, metadata,
and OCR text. Live evidence never records account identity, cookies,
conversation content, or unredacted screenshots.

See [SECURITY.md](../SECURITY.md) for reporting requirements.
