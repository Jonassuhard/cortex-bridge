# Executor — the local half of Cortex Bridge

> **Want to do this manually instead of running scripts?**
> Every step below is explained command by command, with each config line
> broken down, in [../docs/manual-setup.md](../docs/manual-setup.md).

The executor is an isolated [Codex CLI](https://github.com/openai/codex)
profile whose model backend is a **local Ollama server** instead of a cloud
API. It receives a task, acts on your machine (shell, files, builds, tests),
and produces a report for the orchestrator.

## What you need

- macOS on Apple Silicon (tested: M1 Pro, 16 GB unified memory)
- [Ollama](https://ollama.com) installed and running
- Codex CLI installed (`npm i -g @openai/codex` or via your package manager)
- ~13 GB of free disk for the default model

## Quick start

```bash
./scripts/setup-executor.sh
```

The script will:

1. Verify Ollama is running
2. Pull `granite4.1:8b` and `qwen3.5:9b` (primary + fallback bases)
3. Create the `orchestra-executor` and `orchestra-executor-fallback` profiles
   (see below)
4. Smoke-test chat **and tool calling** (the critical capability)
5. Create an isolated Codex profile at `~/.codex-cortex-bridge`

Then run a task:

```bash
CODEX_HOME=~/.codex-cortex-bridge codex exec "list the files in my Downloads folder and summarize what's there"
```

If Codex asks for an API key: `export OPENAI_API_KEY=ollama` (Ollama ignores
the value, but the client requires one to be set).

## Executor profiles

The default executor is **`orchestra-executor`** (based on `granite4.1:8b`) —
the deterministic primary for atomic, low-ambiguity tasks. When it returns
BLOCKED or FAILED, the run escalates once to **`orchestra-executor-fallback`**
(based on `qwen3.5:9b`), the adaptive recovery executor. The full routing
policy is in [../docs/routing-policy.md](../docs/routing-policy.md).

Both profiles are built from `configs/Modelfile.orchestra-executor` and
`configs/Modelfile.orchestra-executor-fallback`:

```bash
ollama create orchestra-executor -f configs/Modelfile.orchestra-executor
ollama create orchestra-executor-fallback -f configs/Modelfile.orchestra-executor-fallback
```

## Alternative models (16 GB RAM)

| Model | Pull | Why |
|---|---|---|
| `glm-4.7-flash` | `ollama pull glm-4.7-flash` | Fastest, strong tool calling, 8 GB |
| `qwen3:14b` | `ollama pull qwen3:14b` | Solid all-round, Qwen family |
| `devstral:24b` | `ollama pull devstral:24b` | Benchmarked agentic (46.8% SWE-Bench), very tight on RAM |

On 24–32 GB machines, prefer `qwen3-coder:30b` (the best local coder today).
Alternatives are drop-in base models — rebuild the Modelfiles with a different
`FROM` line to experiment; the routing policy stays the same.

## Optional: store models on an external drive

```bash
mkdir -p /Volumes/YOUR_DRIVE/ollama/models
mv ~/.ollama/models /Volumes/YOUR_DRIVE/ollama/models 2>/dev/null || true
ln -sfn /Volumes/YOUR_DRIVE/ollama/models ~/.ollama/models
```

Then run the setup script. Disk speed only affects model load time, not
generation speed.

## Switching back to a cloud backend

`scripts/switch-executor.sh` toggles the profile between the Ollama config and
a backup of your previous config, so experiments are always reversible.
