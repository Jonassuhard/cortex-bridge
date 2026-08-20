# Diagnostic fallback

When `frontend/out` is unavailable, the console serves `frontend/fallback/index.html`.

The fallback is deliberately limited to:

- backend health;
- doctor command;
- UI rebuild command;
- log-location guidance.

It cannot browse conversations, send ChatGPT messages, upload files or start local execution. This prevents an old emergency interface from silently bypassing the v0.5 conversation and preflight contracts.

Rebuild the primary interface with:

```bash
./scripts/build-ui.sh
```
