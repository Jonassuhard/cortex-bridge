# ChatGPT web transport

## Runtime

The default v0.5 transport uses the packaged Cortex Bridge Manifest V3 Chrome
extension. It controls ChatGPT in the person's existing Chrome profile and in
the same Chrome window as the Cortex tab. It does not use an OpenAI API or
launch a separate browser.

Owner-authorized authenticated acceptance passed for the v0.5 release
candidate. The transport remains an experimental consumer-site integration,
not an officially supported OpenAI route. Review the current
[OpenAI Europe Terms of Use](https://openai.com/policies/eu-terms-of-use/)
before distribution or production use.

Install the extension once from `chrome://extensions`, then press **Open and
connect ChatGPT**. Cortex creates a 60-second single-use pairing token. The
extension connects outbound to `ws://127.0.0.1:8420/api/chrome-extension/ws`,
proves possession of the token, and opens or focuses `https://chatgpt.com/` in
the Cortex tab's `windowId`.

Login, terms, CAPTCHA, verification, and rate-limit recovery remain human
actions. Cortex shows **Retry** and **Close** and never bypasses the page.

## Security boundary

- Host permissions: `https://chatgpt.com/*` and
  `http://127.0.0.1:8420/*` only.
- No cookie, password, history, debugger, or all-sites permission.
- Structured allowlisted commands only; raw JavaScript is rejected.
- Pairing tokens use 256 bits of entropy, expire after 60 seconds, and are
  consumed once.
- A disconnect fails closed and never falls back to Playwright.
- Concurrent backend commands use one serialized WebSocket writer. The command
  deadline covers both delivery to the extension and its correlated response.

## Conversation behavior

- Return at most the latest 50 conversations.
- Preserve pinned/project/recent metadata only when the page exposes it.
- Bind a writer session to one Chrome tab and one canonical conversation.
- Complete each switch within the existing absolute 10-second budget or return
  a recoverable error.
- Permit two writer sessions; reject a third before opening a tab or sending.
- Never let a late response overwrite a newer selection.
- Collapse Cortex orchestration contracts, decisions, and reports behind an
  explicit technical-protocol disclosure without deleting them.

## Delivery integrity

The extension updates the visible composer and observes the page after send. A
click alone is not proof. An uncertain delivery ends in
`DELIVERY_UNCERTAIN` and is never retried automatically.

Blocker states include login, CAPTCHA, rate limit, loading, closed tab,
conversation mismatch, unreadable state, and timeout.

## Attachments and screenshots

The HTTP API resolves opaque staged-file tokens under `CORTEX_HOME`. The Chrome
extension transport accepts one file at a time up to 25 MiB in v0.5, transfers
bounded chunks, reconstructs a browser `File`, and waits for a visible
attachment chip. ChatGPT may impose stricter product limits.

A screenshot captures only the visible bound ChatGPT tab. If another tab is
active, Cortex asks the user to show the correct tab instead of capturing
unrelated content.

## Development transport

Playwright remains an explicit Advanced/development option for synthetic local
pages and CI. It is not installed by the normal user plan, does not share the
user's Chrome profile, and is never a silent fallback.

## Testing boundary

Automated suites test the protocol, DOM fixtures, UI states, two-writer limit,
files, screenshots, and failures. Separate owner-authorized live tests cover
the real signed-in Chrome tab. Neither class of test implies provider
endorsement.
