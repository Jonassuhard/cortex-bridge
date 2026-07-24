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

🚧 **Early stage.** What works today:

- ✅ Local executor stack: Ollama + OpenAI-compatible endpoint + Codex CLI
  profile, tuned for a 16 GB Apple Silicon Mac (`executor/`)
- ✅ Model tuning for agentic tool-calling on limited RAM
- 🔜 Orchestrator loop via the **official OpenAI API** (`orchestrator/api/` —
  design stage)
- ⚠️ Unofficial browser/desktop bridge to a ChatGPT Pro subscription
  (`orchestrator/browser-bridge/` — design stage, **read the legal notes
  first**: [docs/legal-notes.md](docs/legal-notes.md))

## Repository layout

```
cortex-bridge/
├── docs/            Architecture and legal notes — read these first
├── executor/        The local half: Ollama setup, model tuning, Codex profile
├── orchestrator/    The cloud half: API orchestrator (official) and
│                    browser bridge (unofficial, at your own risk)
└── examples/        What a full loop looks like
```

## Quick start (local executor)

Requirements: macOS on Apple Silicon (tested on M1 Pro 16 GB), [Ollama](https://ollama.com).

```bash
./executor/scripts/setup-executor.sh
```

This downloads `gpt-oss:20b`, creates a 16K-context alias tuned for 16 GB RAM,
and runs smoke tests (chat + tool calling). See
[executor/README.md](executor/README.md) for details and alternative models.

**Prefer to build it by hand, step by step?** →
[docs/manual-setup.md](docs/manual-setup.md) explains every command and every
config line — no scripts required.

## Contributing

Ideas, issues and PRs welcome — especially on the orchestrator loop.

## License

MIT — see [LICENSE](LICENSE).
