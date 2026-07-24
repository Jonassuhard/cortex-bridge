# Phase 5 — Live DOM contract validation (read-only)

Date: 2026-07-24. Target: user's Chrome, chatgpt.com (Pro account, **French UI**),
via WebBridge daemon `http://127.0.0.1:10086`, session `cortex-bridge-loop`
(tab on an existing technical conversation, 3 user + 3 assistant messages).
**All probing was strictly read-only** (list_tabs + evaluate reading DOM state).
No send/fill/click on real ChatGPT. No message content was recorded below —
only structural facts.

## Findings per contract item

### (a) Messages + fenced code blocks

- `[data-message-author-role]` works: 6 elements, roles `user`×3 / `assistant`×3.
- Code blocks are **CodeMirror read-only viewers**: `pre.cm-content` inside
  `.cm-scroller` inside `.cm-editor`. The `pre` textContent is the verbatim code.
- **No language label exists in the code-block header** on this build. The
  block container (`bg-(--code-block-...)`) contains only a floating copy
  button (`aria-label="Copier"`). Earlier `language-*` class / header-label
  assumptions are invalid.
- Consequence: cortex-decision blocks are identified by **content sniffing** —
  a code block whose `textContent` parses as JSON with
  `"protocol": "cortex.v1"` is the decision block. This is UI-language-proof
  and version-proof.
- Long conversations embed ProseMirror "writing blocks" (`pre` inside
  `.ProseMirror`, 86 in one message here); these are artifact editors, not
  reply code blocks. Extraction scans `pre.cm-content` blocks only and the
  protocol's exactly-one-block rule plus content sniffing keep this safe.

### (b) Composer

- `#prompt-textarea` — `div[contenteditable="true"].ProseMirror` ✓ (fill works
  per WebBridge docs; NOT exercised this phase).

### (c) Send button

- `button[data-testid="send-button"]` **does not exist** on this build.
- With an empty composer, the submit position shows a voice-mode button:
  `button.composer-submit-button-color` (aria "Démarrer le mode vocal").
  When text is present the same position becomes the send button.
- Selector chain (first match wins): `button[data-testid="send-button"]` →
  `button[aria-label="Envoyer le message"], button[aria-label="Send message"]` →
  `form button.composer-submit-button-color` (skip when disabled). Only
  `composer-plus-btn` testid exists in the composer form otherwise.

### (d) Streaming / stop button

- Not streaming during probe. Contract: stop button
  `[data-testid="stop-button"], button[aria-label*="Stop"], button[aria-label*="Arr"]`
  (French "Arrêter") and `.result-streaming` on the streaming assistant
  message. Either signal counts as "generating" (conservative: both absent +
  message stable = complete).

### (e) Message identity

- Every message element has `data-message-id`, and all 6 observed ids are
  backend UUIDs (e.g. `9de0abaf-…`). These are server-assigned and survive
  reloads → stable identity, no positional fallback needed (kept as safety).

### (f) Blocker heuristics (conservative; false positive = safe pause)

- Live probe of the healthy page: `/se connecter|inscrivez/i` **false-positives**
  (sidebar/menu text on a logged-in page). → login detection MUST be gated on
  **missing composer** AND login text (EN+FR).
- CAPTCHA: ungated text/DOM markers (`verify you are human`, `vérifiez que
  vous êtes humain`, `cf-chl`, `challenge-platform`, `#cf-chl-widget`).
- Rate limit: specific phrases only (`rate limit`, `too many requests`,
  `limite de requêtes`) — generic words like "quota" are excluded.
- Healthy page with these rules: zero blockers, composer present ✓.

### (g) Conversation list (§8 selection)

- `nav a[href^="/c/"]` (also `aside a[href^="/c/"]`) → 31 conversations with
  title text and `/c/<uuid>` hrefs ✓. Used for the selection UI candidates.

## Exact JS snippets adopted in `WebBridgeDriver`

See `_STATE_JS` / `_CONVERSATIONS_JS` / `_SEND_JS` in
`transport/chatgpt_web/adapter.py` — each was derived from the probes above.
`_SEND_JS` is implemented but deliberately **not executed** until Phase 7
(user go + dedicated disposable conversation).

## Remaining live unknowns (to verify in Phase 7, still read-only where possible)

1. Exact send-button aria/testid when the composer contains text.
2. Stop-button aria/testid during real streaming.
3. Rate-limit banner actual wording on this account.
All three fail safe: transport pauses (CONVERSATION_MISMATCH /
CHATGPT_RESPONSE_TIMEOUT / blocker heuristics) rather than acting blindly.
