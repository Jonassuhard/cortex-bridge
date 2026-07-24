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
| Reply complete | Stop button gone **and** message content (text **and** code blocks) stable for 2 s, and never empty within the 45 s empty-reply grace window |
| New chat lock | First send turns `/` into `/c/WEB:<uuid>` (transient), then the canonical `/c/<uuid>` — the lock waits for the canonical form |

## Adaptive selectors + DOM probe (2026-07-25)

Every role resolves through an **ordered candidate list**; the first match
wins and is reported back (`state["selectors"]`) so a silent UI drift shows
up as a fallback selector in use instead of a broken mission:

| Role | Candidates (in order) |
|---|---|
| Composer | `#prompt-textarea` → `div[contenteditable][role="textbox"]` → `div[contenteditable]` → `form textarea` |
| Messages | `[data-message-author-role]` → `article[data-testid^="conversation-turn"]` → `main article` |
| Send | testid `send-button` → send aria-label → form `button[type="submit"]` (never `.composer-submit-button-color`, which also matches the voice-mode button) |
| Stop | testid `stop-button` → aria `Stop`/`Arrêter` |

`GET /api/transport/probe` runs a **read-only health check** on the live tab
(no typing, no clicks): per-role matched selector, `failures` (composer,
messages — mission-critical) vs `warnings` (send/stop are contextual on an
idle page: the send button only exists once the composer holds text), plus
raw button/contenteditable diagnostics.

A Kimi **watchdog Automation** re-checks the probe every 30 min through a
firing condition: while healthy, nothing happens (no run, no notification);
on failure it produces a structured report run and pushes a warning
notification. Near-real-time breakage detection without daily spam.

## Thinking models: the empty assistant shell (2026-07-25)

Thinking models render an **empty assistant placeholder** while reasoning,
with a paint gap between "stop button gone" and the code block appearing.
The old stability check read empty == empty as stable and extracted the
shell, declaring `NO_DECISION_BLOCK` on replies that were in fact perfect
cortex-decision blocks. Fix in `await_response`:

- the stability signature covers **code block contents**, not just text;
- an empty assistant message is **never final** within
  `empty_reply_grace` (default 45 s; `0` restores legacy behavior);
- streaming phases reset the grace clock.

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
6. Thinking models paint an empty assistant shell before the real reply —
   covered by the empty-reply grace window (see above).

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
the whole test suite (104 tests): conversations, reply queue, simulated
streaming, tab closure, blocker modes, browser restart. It emulates markdown
rendering (fences consumed, language labels dropped) so the tests exercise
the same quirks as the real UI. No test ever touches the network or a real
browser. The probe and empty-reply-grace logic are covered by dedicated
scripted-driver tests (`tests/test_probe.py`,
`tests/test_empty_reply_grace.py`).
