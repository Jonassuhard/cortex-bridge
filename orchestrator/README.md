# Orchestrator notes

This directory keeps design notes for two orchestration paths. It is not a separate v0.5 runtime package.

| Path | Role in v0.5 |
|---|---|
| [`api/`](api/) | Reference architecture for a future official-API transport |
| [`browser-bridge/`](browser-bridge/) | Compatibility notes for the experimental consumer-web transport |

The implemented v0.5 browser path lives in `transport/`, is selected through `transport/browser.py`, and uses a dedicated Playwright profile by default. The execution state machine lives in `orchestration/`.

No orchestrator path receives execution authority directly. Chat messages remain messages; local actions require a separate preflight and policy decision.
