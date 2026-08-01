# Architecture

## Runtime flow

```text
Cortex tab on 127.0.0.1:8420
    | one-time pairing token
    v
Chrome MV3 extension <---- authenticated loopback WebSocket ----> FastAPI
    | structured allowlisted DOM commands
    v
ChatGPT tab in the same Chrome window
    | exact message or explicit execution preflight
    v
mission protocol ----> deterministic executor / optional Ollama ----> workspace
    |
    +---- scoped status, evidence and approvals ----> selected conversation UI
```

The Chrome extension is the default product transport. Playwright is an
explicit development and fixture transport, never a silent fallback.

## Components

### `chrome-extension/`

Manifest V3 service worker and content scripts. The service worker opens or
focuses ChatGPT in the Cortex tab's `windowId`, maintains the loopback
WebSocket, binds logical sessions to tab IDs, and accepts structured commands
only. Host access is limited to ChatGPT and Cortex loopback.

### `frontend/`

React and Next.js static UI. It creates the pairing token, explains connection
states in French, and keeps conversation state reduced per identity. Late
responses cannot overwrite a newer selection. Strict Cortex protocol markers
are grouped into a collapsed audit disclosure instead of being rendered as
ordinary chat messages.

### `console/`

Loopback FastAPI service with HTTP APIs, WebSocket pairing, settings, ChatGPT
chat, attachments, missions, health, pipeline status, and diagnostics.

### `transport/`

Structured Chrome-extension driver, legacy compatibility driver, Playwright
development driver, and deterministic fixtures. Selection shares one
monotonic 10-second deadline across navigation and state reads.

### `orchestration/` and `executor/`

The mission state machine stores `cortex.v1` decisions and evidence in SQLite.
Workspace-confined file and process tools execute only after policy and
preflight checks. Ollama is optional and is reported active only after a real
model call.

## Pairing protocol

1. Cortex issues a 256-bit token that expires after 60 seconds.
2. The Cortex page passes it to the localhost content script.
3. The extension presents it over its outbound WebSocket.
4. The backend consumes it once and enables the command channel.
5. Every command has a random request ID, session ID, allowlisted action, and
   structured payload.
6. One serialized writer sends commands over the WebSocket; the command
   deadline covers both the send and correlated result.
7. Disconnects, timeouts, unknown actions, oversized payloads, and replays fail
   closed.

## Conversation isolation

Each writer owns a lease tied to a conversation identity, logical session, and
Chrome tab. Two leases may be active. A third is rejected with HTTP 409 before
a tab opens or a message sends, while the client keeps its draft and file.

## Data and media

Mutable data lives under `CORTEX_HOME`, default
`~/.local/share/cortex-bridge`. Attachments resolve from opaque tokens to
validated managed paths. The extension transfer limit is 25 MiB in v0.5.
Screenshots must come from the visible bound ChatGPT tab and are written
atomically under `CORTEX_HOME`.

## Process ownership and release boundary

Lifecycle records include PID, start time, executable, argument hash, instance
token, and port. Stop signals only an exact match.

CI uses synthetic pages and never an authenticated account. Real Chrome,
ChatGPT, file, screenshot, dual-conversation, and mini-site gates require
explicit owner approval and redacted evidence.
