# ChatGPT web transport

## Runtime

The default v0.5 transport uses the packaged Cortex Bridge Manifest V3 Chrome
extension. It controls ChatGPT in the person's existing Chrome profile and in
the same Chrome window as the Cortex tab. It does not use an OpenAI API or
launch a separate browser.

Earlier owner-authorized runs observed the transport technically, but they do
not qualify as release acceptance. The current
[OpenAI Europe Terms of Use](https://openai.com/policies/eu-terms-of-use/)
prohibit automatic or programmatic extraction of data or Output, which this
adapter performs. Owner approval cannot replace provider authorization, so the
live gate remains blocked and the transport stays opt-in and experimental.

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
- No cookie, password, history, or all-sites permission. The extension does
  request Chrome's `debugger` permission for bounded trusted-input and visible-
  tab screenshot operations, attaches only to the selected ChatGPT tab, and
  detaches after each operation.
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

Text-only delivery stays inside the extension. Attachment delivery adds a
local macOS activation boundary:

1. The extension transfers one managed file, waits for its visible attachment
   chip, prepares the exact text, records existing user-message IDs, and
   verifies the canonical ChatGPT URL plus one usable send control.
2. The backend computes `expected_text_sha256` from the whitespace-normalized
   composer text. It invokes `cortex-macos-ax-send` with only the executable in
   the activation argument vector, then writes a JSON request capped at 64 KiB
   with the expected ChatGPT URL, plain filename and digest to standard input.
   The full plaintext prompt and attachment path never enter the helper
   request, arguments, or logs.
3. The helper requires a manual macOS Accessibility grant. It installs a
   250 ms global AX messaging timeout, scans all Chrome applications and
   windows, and accepts exactly one stable global target. That target must
   expose exactly one visible omnibox under `AXToolbar` and outside
   `AXWebArea`, with the expected canonical URL.
4. Inside that exact window, the normalized composer value must hash to
   `expected_text_sha256`. The file control, composer and unique localized
   **Send prompt** control must share the exact bounded common AX ancestor and
   pass visibility, window-bound and alignment checks. Only then does the
   helper perform one Accessibility press.
5. The driver polls the DOM for a new user-message ID whose normalized text and
   structured attachment name match. Only that new DOM evidence completes the
   send.

The discovery and focus phases have 5-second and 2.5-second absolute deadlines
in addition to the global messaging timeout. The backend bounds the complete
helper process to 10 seconds. A timeout or mismatch before the press fails
closed. Any loss of proof after the press is `DELIVERY_UNCERTAIN`; Cortex tells
the user to inspect ChatGPT and never replays the message.

Doctor hashes the installed helper and checks its device and inode identity
around the permission probe. This detects ordinary replacement but cannot
eliminate a swap-and-restore race by a process already running as the same
macOS user; that same-UID case is outside the current threat model. See the
[Doctor integrity boundary](security-model.md#doctor-integrity-boundary).

Blocker states include login, CAPTCHA, rate limit, loading, closed tab,
conversation mismatch, unreadable state, and timeout.

## Attachments and screenshots

The HTTP API resolves opaque staged-file tokens under `CORTEX_HOME`. The Chrome
extension transport accepts one file at a time up to 25 MiB in v0.5, transfers
bounded chunks, reconstructs a browser `File`, and waits for a visible
attachment chip. ChatGPT may impose stricter product limits.

On macOS, file sending also requires Apple Command Line Tools so Cortex can
compile the tracked Swift helper under `CORTEX_HOME/bin`, plus the manual
Accessibility permission described above. These requirements do not block
startup or text-only chat. `./scripts/cortex.sh doctor --json` reports them as
`swift_toolchain`, `macos_ax_helper`, and `macos_accessibility`.

A screenshot captures only the visible bound ChatGPT tab. If another tab is
active, Cortex asks the user to show the correct tab instead of capturing
unrelated content.

## Development transport

Playwright remains an explicit Advanced/development option for synthetic local
pages and CI. It is not installed by the normal user plan, does not share the
user's Chrome profile, and is never a silent fallback.

## Testing boundary

Automated suites test the protocol, DOM fixtures, helper handoff, exact
post-send proof, UI states, two-writer limit, files, screenshots, and failures.
They do not by themselves prove that the current macOS Accessibility path works
against a real signed-in ChatGPT page. A separate owner-authorized synthetic
observation on 2026-08-25 confirmed the current text, file and privacy-masked
screenshot paths in the production extension. That is technical compatibility,
not provider authorization. Authenticated consumer-site runs remain outside an
authorized release gate under the current provider terms; a future compliant
gate requires an officially supported transport.
