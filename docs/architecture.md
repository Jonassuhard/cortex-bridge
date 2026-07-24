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

## The autonomous mission loop (Mode A)

Since Phase 6/7 the loop runs **without any human copy-paste**. Components:

```
console/server.py + console/missions.py     FastAPI cockpit (loopback only)
orchestration/runner.py                     ModeARunner — wires everything
orchestration/loop.py                       MissionLoop — one decision per cycle
orchestration/state.py                      State machine + budgets + fingerprints
orchestration/protocol.py                   cortex.v1 fences, validation, reports
orchestration/store.py                      SQLite audit (11 tables, WAL)
transport/chatgpt_web/adapter.py            ChatGPTWebTransport + drivers
transport/chatgpt_web/fixture.py            In-process fake chatgpt.com (tests)
executor/tools.py + executor/policy.py      Sandboxed tools + approval policy
```

One cycle:

```
1. The console sends the mission contract (objective, workspace, cortex.v1
   rules, per-tool argument schemas) into the chosen ChatGPT conversation.
2. ChatGPT answers with exactly one ```cortex-decision fenced block:
   EXECUTE (one tool call) | REQUEST_CONTEXT | COMPLETE | BLOCKED.
3. The loop validates the decision (protocol, iteration, UUID actionId,
   argument schema, path safety), evaluates it against the policy engine,
   asks the human when the policy requires approval, and executes the tool
   against the workspace.
4. The validated result goes back into the same conversation as exactly one
   ```cortex-report fenced block.
5. Repeat until COMPLETE/BLOCKED, budget exhaustion, pause or failure.
```

Guarantees enforced by the state machine and store (§14):

- one pending message at a time — the loop never overlaps sends;
- duplicate responses and duplicate reports are detected by content
  fingerprints and ignored, never re-executed;
- every delivery is proven (the sent message must appear in the DOM) before
  the next step — uncertain delivery pauses the mission for human resolution;
- pause/resume is exact: resume re-attaches the locked conversation and
  either re-sends the undelivered payload or waits for the reply, never both.

## Conversation lock

A mission locks exactly one conversation identity (`/c/<uuid>`) before the
first send. Every state read verifies the page still shows that identity —
a mismatch pauses with CONVERSATION_MISMATCH instead of leaking a mission
into the wrong chat. New conversations are locked as soon as ChatGPT assigns
their canonical `/c/<uuid>` URL (the transient `/c/WEB:<uuid>` shown right
after the first send is waited out).

## Trust boundaries

- The console binds to 127.0.0.1 only; there is no remote access to missions.
- The transport talks to chatgpt.com through the user's own Chrome via the
  local WebBridge daemon (127.0.0.1:10086) — DOM only, never `/backend-api/`.
- Tools are confined to the mission workspace: relative paths only, no `..`,
  no symlink escapes, an allowlist of executables for `run_process`.
- Write tools run under a policy: automatic, per-action approval, or denied.
- The orchestrator never receives raw credentials; it only sees task results.
- API keys live in environment variables or `~/.codex-cortex-bridge/auth.json`,
  never in this repo (see `.gitignore`).
