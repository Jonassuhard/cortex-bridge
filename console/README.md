# Cortex Bridge Console

A local web console — the **cockpit** for the Cortex Bridge loop. It lets you
hand a task (goal + constraints + workspace) to the local executor, watch it
work live, get a structured JSON report back, and paste that report into your
cloud orchestrator (ChatGPT) to continue the conversation.

Dark ink UI, one signal blue, no build step: a FastAPI backend serving a
single-page vanilla HTML/CSS/JS frontend.

## Install

```bash
cd console
pip install -r requirements.txt
```

## Run

```bash
python server.py
```

Then open **http://127.0.0.1:8420**.

## Simulation vs live mode

The console picks the mode automatically per task:

- **LIVE** — only when the full executor stack is present:
  `~/.codex-cortex-bridge/config.toml` exists, Ollama answers on
  `127.0.0.1:11434`, **and** the `codex` binary is on PATH. The console runs
  `CODEX_HOME=~/.codex-cortex-bridge codex exec "<goal + constraints>"` with
  the task workspace as cwd, streams stdout into the live view, and marks the
  task `done` when the exit code is 0.
- **SIMULATION** — the default while the executor model is not installed.
  The console emits a realistic fake execution (a handful of log lines with
  small delays) and returns a complete structured report tagged
  `"mode": "simulation"`. Simulation reports are clearly flagged in the UI —
  nothing real is executed on your machine.

The current mode is always visible as a chip in the top-right status bar,
next to the Ollama up/down dot and the active model name.

## Local runtime panel

Above the Composer, the **Local runtime** card shows the state of the local
execution stack, refreshed every 10 seconds from `GET /api/status`:

- Ollama endpoint and health (`healthy` / `unhealthy`, from the `/api/tags` probe)
- Model storage path and whether the external **DJO volume is mounted**
- Primary executor `orchestra-executor` and fallback
  `orchestra-executor-fallback`, each with a state chip:
  `installed` (in `ollama list`), `loaded` (in `ollama ps`, accent blue) or
  `missing` (muted red)

The models live on an external drive (`/Volumes/DJO/AI/Ollama/models`, symlinked
to `~/.ollama/models`). When that volume is not mounted, the API reports
`storage_status: "LOCAL_MODEL_STORAGE_UNAVAILABLE"`, the panel shows a warning
banner, the *Run task* button is disabled, and `POST /api/tasks` refuses new
tasks with **HTTP 409** and the same code in the JSON body — local executors
cannot run without their weights. The remote fallback (Kimi/OpenCodex) remains
available; the console surfaces this as information only and performs no
automatic re-routing.

Set `CORTEX_STORAGE_PATH` to test the disk-missing path without unplugging the
drive; set `PORT` to run on a port other than 8420:

```bash
CORTEX_STORAGE_PATH=/Volumes/DJO/definitely-not-here PORT=8421 python server.py
```

## The manual ChatGPT loop

Until the automated orchestrator bridge lands, the loop is manual:

1. **Run a task** in the Composer card — describe the goal, add optional
   constraints, pick a workspace, hit *Run task*.
2. **Watch the live view** — log lines stream in via Server-Sent Events
   (commands in blue, errors in red, file writes in white).
3. When the run finishes, the **report card** shows status, summary, files
   changed, blockers and a suggested next step.
4. Click **Copy report for orchestrator** — the JSON report is now on your
   clipboard. Paste it into your ChatGPT conversation.
5. ChatGPT replies with the next instruction. Click **Paste orchestrator
   reply** in the console and attach the reply to the iteration, so the
   history stays complete.
6. Repeat — each cycle is one iteration in the sidebar.

## API (for tinkering)

| Method | Path                              | Purpose                                  |
|--------|-----------------------------------|------------------------------------------|
| GET    | `/api/status`                     | Local runtime status: Ollama probe, storage, executors, mode |
| POST   | `/api/tasks`                      | Create + start an iteration              |
| GET    | `/api/tasks`                      | List iterations                          |
| GET    | `/api/tasks/{id}`                 | Full iteration detail incl. report       |
| GET    | `/api/tasks/{id}/stream`          | SSE stream of live log lines             |
| POST   | `/api/tasks/{id}/orchestrator-reply` | Attach a pasted ChatGPT reply         |

Iterations are persisted to `console/data/iterations.json` (git-ignored).
