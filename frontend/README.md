# Cortex Bridge UI

This directory contains the conversation-first frontend for Cortex Bridge.

## Two delivery formats

### Modular application

- Next.js 16
- React 19
- TypeScript strict mode
- Tailwind CSS 4 / PostCSS
- static export consumed by FastAPI from `frontend/out/`

Required toolchain:

- Node `20.19.0` (the `.node-version` baseline), or Node `>=22.12.0`
- npm `11.18.0` exactly

Corepack can run the npm version declared by `packageManager` without relying
on a globally installed npm:

```bash
corepack npm --version # must print 11.18.0
corepack npm ci
corepack npm run typecheck
corepack npm run lint
corepack npm run build
```

The repository rejects unsupported Node/npm versions and unreviewed dependency
install scripts before installation. Do not bypass these checks with `--force`.

### Standalone fallback

`fallback/index.html` is a dependency-free, single-file version of the same
product surface. FastAPI serves it automatically when `frontend/out/` is not
available. It talks to the real Cortex Bridge API and enters an explicit demo
mode only when the backend cannot be reached.

## Visual direction

The interface uses a dark technical design language for a desktop execution
client:

- ink-black surface
- subtle animated grid
- restrained blue glow
- fine borders and softly rounded cards
- conversation-first hierarchy
- reduced-motion support

The reference application layout is documented in
[`../docs/interface.md`](../docs/interface.md).

## API dependencies

The UI uses:

- `/api/conversations`
- `/api/conversations/snapshot`
- `/api/chat/send`
- `/api/chat/runs/*`
- `/api/missions/*`
- `/api/pipeline/status`
- `/api/settings`
- `/api/models/chatgpt`
- `/api/models/ollama`
- `/api/transport/*`

No OpenAI API key is read by the frontend.
