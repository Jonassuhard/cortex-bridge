# Cortex Bridge service

`console/` is the local FastAPI service behind the Cortex Bridge interface. It serves the static frontend, owns runtime settings and exposes conversation, transport, attachment, execution and diagnostic APIs.

## Start it

From the repository root:

```bash
./scripts/cortex.sh start
./scripts/cortex.sh status --json
```

Open `http://127.0.0.1:8420`. The service binds to loopback only. Use `PORT` to select another loopback port and an absolute `CORTEX_HOME` to move mutable state.

## Runtime surfaces

- `/api/status`: version and local runtime truth
- `/api/conversations` and `/api/conversations/snapshot`: bounded conversation discovery and selected snapshots
- `/api/chat/*`: exact-message delivery, attachments and run events
- `/api/missions/*`: reviewed execution preflight and mission lifecycle
- `/api/transport/*`: browser state, probe, stop and capabilities
- `/api/settings` and `/api/pipeline/status`: configuration and compact status
- `/api/diagnostics/export`: redacted diagnostics

The service serves `frontend/out/` when the verified static build exists. `frontend/fallback/index.html` is diagnostic-only and cannot send a message or start execution.

## Safety contracts

- Login and third-party terms remain human actions.
- The Playwright profile is dedicated to Cortex Bridge.
- A message is never retried after uncertain delivery.
- Attachments are resolved from opaque, expiring tokens; client paths are not trusted.
- Runtime data lives under `CORTEX_HOME`, not in the repository.
- Lifecycle commands signal only a process whose stored identity still matches.

Run the complete release suite from the repository root:

```bash
PYTHON=.venv/bin/python ./scripts/test-all.sh
```
