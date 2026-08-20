# Conversation-first interface

## Product contract

Cortex Bridge is a local ChatGPT conversation client with an optional, separately approved execution path. The main interface must explain what is happening without exposing an operations dashboard by default.

## Layout

### Conversation sidebar

- New ChatGPT conversation at the top.
- Search over at most the latest 50 conversations.
- Pinned, Projects and Recent groups only when the transport provides that metadata.
- Message counts only when available; the UI never invents them.
- One unambiguous collapse and expand control.

### Conversation workspace

- Visible user and ChatGPT messages.
- Exact composer draft; `Enter` sends and `Shift+Enter` inserts a line.
- Sending, delivered, uncertain and failed states remain visible.
- ChatGPT and executor status appear next to each other.
- Two conversation writers may send independently. A third keeps its draft and attachment but cannot send until a slot is released.
- Conversation selection has one absolute 10-second budget and exposes a retry action on failure.

### Secondary surfaces

Pipeline detail, settings, diagnostics and the animated architecture explanation stay behind explicit buttons. The center conversation retains priority at 375, 768 and 1440 pixels.

## Chat versus execution

There is no persistent Chat/Mission mode. A normal send always sends the exact text to ChatGPT. When the user requests local work, the interface opens a preflight that shows workspace, capabilities, approvals and limits. Execution begins only after explicit confirmation.

This removes a mode whose meaning had to be remembered and replaces it with a visible decision at the moment it matters. Quite a luxury: the button now says what it does.

## Accessibility and motion

- Keyboard-visible controls and focus restoration.
- Accessible names for icon-only actions.
- Escape closes dialogs and drawers where safe.
- Status is conveyed by text, not color alone.
- Non-essential motion is disabled by `prefers-reduced-motion`.
- Loading, empty, offline, timeout and retry states are explicit.
