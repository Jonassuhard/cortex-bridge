# Troubleshooting

## Mission pauses with `DELIVERY_UNCERTAIN`

The transport could not prove that a send landed. **It never resends on its
own.** Open the ChatGPT tab and look:

- **Contract/report visible in the chat** → it was delivered; resume the
  mission (the resume logic only re-sends what was never proven).
- **Text sitting in the composer, unsent** → resume: the send is idempotent
  and will click send on the existing draft, not duplicate it.
- **Nothing there** → resume sends the payload normally.

Known causes (all fixed as of 2026-07-24, kept here for reference):

| Symptom | Cause | Fix shipped |
|---|---|---|
| Send always failed | ProseMirror ignores `textContent =` | `execCommand('insertText')` |
| Voice mode opened instead of sending | `.composer-submit-button-color` matches "Démarrer le mode vocal" before React arms the real button | Only `data-testid="send-button"` / send aria-labels are accepted |
| Send reported failed but message visible | Post-send check raced the SPA render | Poll ≤ 30 s for the message to appear |
| Report send "not visible" though present | Markdown eats the ` ```cortex-report ` fence and its label | Delivery marker = first substantial content line, matched in message + code blocks |
| Draft lost | Send attempted while ChatGPT was still streaming | Transport waits out the stream first |

## Mission pauses with `CONVERSATION_MISMATCH`

The page no longer shows the conversation the mission is locked to. This
protects you from mission content leaking into the wrong chat. Bring the
locked conversation back (its URL is in the mission's conversation binding)
and resume.

Note: right after the first send, ChatGPT shows a transient `/c/WEB:<uuid>`
URL before the canonical `/c/<uuid>`. The transport waits for the canonical
form before locking; if you see a binding with a `WEB:` identity (created
before that fix), start a fresh mission.

## `LOGIN_REQUIRED` / `CAPTCHA` / `RATE_LIMIT`

ChatGPT is asking something of the human. Solve it in the tab (log in, pass
the challenge, wait out the rate limit) — the transport **never** bypasses
these — then resume.

## Resume fails with `cannot re-attach conversation`

The conversation binding holds a URL that no longer resolves to the same
identity (deleted conversation, logged-out session). Start a new mission on
a fresh conversation; the store keeps the old mission for audit.

## The mission loops protocol violations

ChatGPT is not following the cortex.v1 contract (missing/duplicate fenced
block, wrong iteration, non-UUID actionId, unknown argument). The loop
reports each violation back; after 3 consecutive ones the mission fails.
The contract already embeds the tool argument schemas — if you see
`MALFORMED_ARGUMENTS: unknown argument ...`, check the report: it tells
ChatGPT the exact schema to use next.

## ChatGPT changed its frontend

Selectors live in `transport/chatgpt_web/adapter.py` (`_STATE_JS`,
`_SEND_JS`, `_CONVERSATIONS_JS`) and are documented in
[phase5-dom-contract.md](phase5-dom-contract.md). While you fix them,
missions still work in [manual fallback](manual-fallback.md) mode.

## Console won't start / port busy

```bash
lsof -tiTCP:8420 -sTCP:LISTEN | xargs kill
cd console && python3 server.py
```

## Ollama executor unreachable

The console checks `http://127.0.0.1:11434`. If models live on an external
drive, make sure it is mounted before starting Ollama
(`ln -sfn /Volumes/YOUR_DRIVE/ollama/models ~/.ollama/models`).
