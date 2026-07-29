# Architecture

## Runtime flow

```text
French local UI
    |
    | exact ChatGPT message
    v
FastAPI console ----> dedicated Playwright Chromium profile ----> ChatGPT
    |
    | confirmed execution preflight
    v
mission protocol ----> deterministic executor or optional Ollama ----> workspace
    |
    +---- scoped status, evidence and approvals ----> selected conversation UI
```

The default browser transport is Playwright with a dedicated headed profile. Login is manual. WebBridge is compatibility-only.

## Components

### `frontend/`

React and Next.js static UI. Conversation state is reduced per identity. Late responses carry an epoch and cannot overwrite a newer selection.

### `console/`

Loopback FastAPI service. It exposes settings, ChatGPT chat, attachments, mission control, health, pipeline status and lifecycle diagnostics.

### `transport/`

ChatGPT browser adapter, Playwright driver and deterministic fixture. Selection shares one monotonic deadline across navigation and state reads.

### `orchestration/`

Mission state machine, `cortex.v1` decision protocol and SQLite evidence store. Completion requires structured validation evidence.

### `executor/`

Workspace-confined file and process tools. The deterministic executor is always available. Ollama is optional and never inferred as active merely because a model is installed.

## Data layout

Mutable data lives under `CORTEX_HOME`, defaulting to `~/.local/share/cortex-bridge`:

```text
attachments/
browser/
data/
logs/
pids/
runs/
settings/
```

Legacy repository-local data is copied non-destructively when migration is required. Existing files are not overwritten or deleted.

## Conversation isolation

Each writer owns a lease tied to a conversation identity and browser session. Two distinct leases may be active. A third is rejected with HTTP 409 while preserving client draft state.

Provisional conversations receive unique identities and rekey when a canonical ChatGPT URL appears. Stale releases cannot free a successor’s slot.

## Attachments

The browser receives a validated server-side descriptor, never a client path. The descriptor includes owner, token, name, MIME, kind and size. Office formats are checked as ZIP containers. Screenshot paths must match the expected selected target.

## Process ownership

Lifecycle records include PID, start time, executable, argument hash, instance token and port. `stop` signals only an exact match. Foreign listeners, stale records and PID reuse fail closed.

## Release boundaries

CI uses fixtures and no authenticated browser. Live ChatGPT compatibility, account state and three disposable mini-site missions require explicit owner approval outside CI.
