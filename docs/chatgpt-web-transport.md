# ChatGPT Web Transport

The transport lets Cortex Bridge run missions through a **ChatGPT Pro web
session** instead of the OpenAI API: the cloud orchestrator is whatever model
your subscription gives you, driven through the real chatgpt.com UI in your
own Chrome.

> ⚠️ This automates a consumer product UI. It is experimental, can break on
> any ChatGPT frontend deploy, and you use it at your own discretion. No
> CAPTCHA, authentication or anti-bot bypass is implemented or ever will be.
> See [legal-notes.md](legal-notes.md).

## How it connects

```
Cortex Bridge console ──► WebBridge daemon (127.0.0.1:10086) ──► Chrome
        (WebBridgeDriver)            WebSocket/HTTP bridge         (your session)
```

- Chrome runs the **WebBridge** extension with your logged-in ChatGPT tab.
- The transport drives a dedicated browser **session** (`cortex-bridge`) so
  missions never touch the tabs you are personally using.
- Everything is **DOM-only**: read page state, type in the composer, click
  send/stop. `/backend-api/` endpoints are never called.

## The DOM contract (validated 2026-07-24, FR + EN UI)

| Action | Mechanism |
|---|---|
| Page state | Single `evaluate` returning URL, conversation id, blocker, streaming flag, messages (`[data-message-author-role]`) with code blocks (`pre.cm-content`) |
| Composer | `#prompt-textarea` (ProseMirror) |
| Typing | `document.execCommand('insertText')` — the **only** injection ProseMirror/React acknowledges; `textContent =` is silently ignored |
| Send button | `button[data-testid="send-button"]` or aria `Envoyer le prompt` / `Send prompt`; appears only after text is present (poll ≤ 10 s) |
| Send proof | Composer empties, then the user message appears in the DOM (poll ≤ 30 s) |
| Streaming | Stop button (`[data-testid="stop-button"]`, aria `Arrêter`/`Stop`) present, or `.result-streaming` |
| Reply complete | Stop button gone **and** message text stable for 2 s |
| New chat lock | First send turns `/` into `/c/WEB:<uuid>` (transient), then the canonical `/c/<uuid>` — the lock waits for the canonical form |

Real-world quirks discovered during live verification (all handled, see
[troubleshooting.md](troubleshooting.md)):

1. ProseMirror ignores direct DOM writes — `insertText` is mandatory.
2. While React has not armed the send button yet, `.composer-submit-button-color`
   matches the **voice-mode** button ("Démarrer le mode vocal"), which is not
   disabled. The selector never falls back to it.
3. Markdown consumes the leading ` ``` ` fence **and** its language label, so
   delivery confirmation matches the first substantial content line of the
   payload, not the fence.
4. The sent user message renders asynchronously — a single immediate check
   races the render and must poll.
5. Sending while ChatGPT is still streaming loses the draft — the transport
   waits out the stream first.

## Pause reasons (fail-safe taxonomy)

`LOGIN_REQUIRED`, `CAPTCHA`, `RATE_LIMIT`, `TAB_CLOSED`,
`CONVERSATION_MISMATCH`, `DELIVERY_UNCERTAIN`, `TRANSPORT_PAUSED`,
`STREAM_TIMEOUT`, `CHATGPT_RESPONSE_TIMEOUT`, `STATE_UNREADABLE`.

Every pause preserves the mission: resume re-attaches the locked conversation,
re-sends only what was never proven delivered, and continues. The send is
idempotent — if the composer still holds the exact draft (e.g. after a failed
click), it is sent as-is rather than duplicated.

## The local fixture

`transport/chatgpt_web/fixture.py` is an in-process fake chatgpt.com used by
the whole test suite (89 tests): conversations, reply queue, simulated
streaming, tab closure, blocker modes, browser restart. It emulates markdown
rendering (fences consumed, language labels dropped) so the tests exercise
the same quirks as the real UI. No test ever touches the network or a real
browser.
