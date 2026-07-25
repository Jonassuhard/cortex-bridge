# Cortex Bridge 🌉🧠

**A cloud brain. Local hands. One conversation loop.**

Cortex Bridge connects a powerful cloud LLM orchestrator (ChatGPT, Claude, any
strong planner) to a **local agentic executor** running on your own machine via
Ollama. The orchestrator thinks and plans; the local model executes code,
touches your filesystem, runs commands — then reports back into the
conversation so the loop continues.

```
┌─────────────────────┐         ┌──────────────────────────────┐
│  Cloud orchestrator │  task   │  Your machine (e.g. a Mac)   │
│  (ChatGPT / API)    ├────────►│  ┌────────────────────────┐  │
│                     │         │  │ Cortex Bridge executor │  │
│  "plan, review,     │         │  │  → Ollama (gpt-oss,    │  │
│   decide next step" │◄────────┤  │     qwen3, glm...)     │  │
└─────────────────────┘  report │  │  → runs code locally   │  │
                                │  └────────────────────────┘  │
                                └──────────────────────────────┘
```

## Why?

- **Local execution is free and private** — no API cost per action, your code
  never leaves your disk.
- **Cloud planning is strong** — frontier models are better at decomposition,
  review and long-horizon reasoning than anything that fits in 16 GB of RAM.
- **Each model does what it's best at.**

## Project status

✅ **Working end-to-end.** Autonomous missions verified against the real
chatgpt.com web UI on 2026-07-24:

- ✅ Local executor stack: Ollama models + policy engine + tool executor
  (`executor/`)
- ✅ Mission loop: contract → decision → tool execution → report → next
  decision, all inside a single ChatGPT conversation (`orchestration/`)
- ✅ ChatGPT Web Transport through the user's own Chrome via WebBridge
  (`transport/chatgpt_web/`) — DOM-only, no OpenAI API key needed
- ✅ Local web console (FastAPI) to launch, watch, approve, pause and stop
  missions (`console/`) — loopback only
- ✅ Verified live: read-only missions, file writes with human approval,
  multi-iteration code repair, policy refusals, emergency stop
- ⚠️ The web transport automates a consumer product UI and may break when
  ChatGPT changes its frontend — read
  [docs/legal-notes.md](docs/legal-notes.md) and
  [docs/chatgpt-web-transport.md](docs/chatgpt-web-transport.md)

See [docs/testing.md](docs/testing.md) for the full verification matrix.

## Repository layout

```
cortex-bridge/
├── docs/            Architecture, security model, transport, testing — read these first
├── executor/        The local half: policy engine + tool executor (paths, processes)
├── orchestration/   The loop: state machine, cortex.v1 protocol, runner, SQLite store
├── transport/       ChatGPT Web Transport (WebBridge driver + local fixture)
├── console/         Local web cockpit: launch/watch/approve/stop missions
└── examples/        What a full loop looks like
```

## Quick start (missions)

Requirements: macOS, [Ollama](https://ollama.com) with the executor models,
Chrome with the WebBridge extension connected to your ChatGPT session.

```bash
./scripts/start-local.sh   # serves the console at http://127.0.0.1:8420
```

The console is a local web cockpit (Next.js UI + FastAPI, loopback only):

1. Read the experimental-transport warning and opt in (persisted once).
2. Pick a mode: **Message simple** (one-shot chat through ChatGPT) or
   **Mission autonome** (the full plan → execute → report loop). Paste an
   objective, pick a workspace, choose a new or existing ChatGPT conversation
   from the sidebar, launch.
3. Watch decisions, tool executions and reports stream in; approve writes
   when prompted; STOP EVERYTHING kills everything instantly. Settings also
   expose the ChatGPT model switcher (experimental).

To hack on the UI: `scripts/dev-ui.sh` (Next.js dev server) and
`scripts/build-ui.sh` (static export served by the console).

The executor never leaves the workspace, never installs packages, and every
write can require your explicit approval. Details:
[docs/security-model.md](docs/security-model.md).

**Prefer to build it by hand, step by step?** →
[docs/manual-setup.md](docs/manual-setup.md) explains every command and every
config line — no scripts required.

## Contributing

Ideas, issues and PRs welcome — especially on the orchestrator loop.

## License

MIT — see [LICENSE](LICENSE).
