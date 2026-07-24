# Architecture

## The two halves

Cortex Bridge splits an agentic workflow across two models with different
strengths:

| Role | Runs where | Model | Does |
|---|---|---|---|
| **Orchestrator** | Cloud | Frontier model (ChatGPT / API) | Plans, decomposes, reviews, decides next steps |
| **Executor** | Your machine | Local Ollama model (gpt-oss:20b by default) | Runs code, edits files, executes shell commands, reports results |

## One loop iteration

```
1. Orchestrator writes a task message (goal + constraints + workspace)
2. Bridge delivers it to the executor on the local machine
3. Executor (Codex CLI profile → Ollama OpenAI-compatible API) acts locally:
   shell commands, file edits, builds, tests
4. Executor produces a structured report: what was done, what failed, logs
5. Bridge posts the report back into the orchestrator conversation
6. Orchestrator reads the report and either continues, corrects, or finishes
```

## Why Ollama as the executor backend

- OpenAI-compatible API out of the box (`http://127.0.0.1:11434/v1`) — any
  agent harness that can point at a custom `base_url` can drive it.
- Native tool calling on recent models (gpt-oss, qwen3, glm-4.x flash).
- Zero per-token cost; fully offline; code never leaves the machine.

## Memory budget (Apple Silicon)

Unified memory is the real constraint — not disk. Tested reference: M1 Pro
16 GB.

| Model | Download | RAM behavior | Verdict for 16 GB |
|---|---|---|---|
| `gpt-oss:20b` | ~13 GB | MoE + MXFP4, fits 16 GB | ✅ Default choice |
| `glm-4.7-flash` | ~8 GB | Light, fast, strong tool calling | ✅ Best speed |
| `qwen3:14b` | ~10 GB | Dense, good tool calling | ✅ Solid |
| `devstral:24b` | ~14 GB | Benchmarked agentic (46.8% SWE-Bench) | ⚠️ Very tight |
| `qwen3-coder:30b` | ~19 GB | Best local coder — needs 24–32 GB | ❌ Swaps on 16 GB |

**Context tuning matters**: advertised 128K contexts are unusable on 16 GB.
The executor ships a Modelfile capping context at 16K tokens, which leaves
headroom for macOS, the browser and the Ollama runtime.

## Storage on an external drive

Models can live on an external SSD via a symlink:

```bash
ln -sfn /Volumes/YOUR_DRIVE/ollama/models ~/.ollama/models
```

Disk speed only affects model *load* time — once weights are in RAM,
generation speed is identical to internal storage.

## Trust boundaries

- The executor runs with `sandbox_mode = "workspace-write"` and
  `approval_policy = "never"` inside an isolated Codex profile
  (`~/.codex-cortex-bridge`) so it cannot touch your main Codex config.
- The orchestrator never receives raw credentials; it only sees task results.
- API keys live in environment variables or `~/.codex-cortex-bridge/auth.json`,
  never in this repo (see `.gitignore`).
