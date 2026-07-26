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

## Runtime truth

The console reports what actually ran, not what merely looked available:

- **LIVE** — when Ollama answers on `127.0.0.1:11434`, the
  `orchestra-executor` model is installed/loaded, and the model storage
  volume is mounted. The console **is** the executor harness: it drives
  Ollama `/api/chat` directly with one `shell` tool and a strict JSON status
  schema (READY_FOR_TOOL / READY_FOR_VALIDATION / BLOCKED / FAILED), executes
  the requested commands itself, streams everything into the live view, and
  marks the task `done` only after the model reports READY_FOR_VALIDATION with
  real evidence (at least one executed command; `files_changed` is the actual
  workspace diff). No Codex CLI dependency.
  **Safety:** every command passes a workspace jail (workdir and absolute
  paths must resolve inside the task workspace) and a denylist (`sudo`,
  `git push`, package installs, `ssh`, `kill`, writes to `/etc`, …); limits
  are 8 tool executions and a 5-minute wall-clock guard per task.
- **UNAVAILABLE** — when the local executor cannot be called successfully.
  The task fails with `EXECUTOR_UNAVAILABLE`; no command is simulated and no
  model name is reported as used.
- **DEVELOPMENT FIXTURE** — available only when both the caller requests
  `development_fixture` and `CORTEX_ALLOW_DEVELOPMENT_FIXTURES=1` is set.
  Fixture reports are blocked and explicitly ineligible for release evidence.

Every task/report exposes `executor_kind`, `executor_model_used` and
`runtime_mode`. Daemon/model availability is shown separately.

## Local runtime panel

Above the Composer, the **Local runtime** card shows the state of the local
execution stack, refreshed every 10 seconds from `GET /api/status`:

- Ollama endpoint and health (`healthy` / `unhealthy`, from the `/api/tags` probe)
- Model storage path and whether the external **DJO volume is mounted**
- Candidate executor `orchestra-executor`, with an availability state:
  `installed` (in `ollama list`), `loaded` (in `ollama ps`, accent blue) or
  `missing` (muted red)

The models live on an external drive (`/Volumes/DJO/AI/Ollama/models`, symlinked
to `~/.ollama/models`). When that volume is not mounted, the API reports
`storage_status: "LOCAL_MODEL_STORAGE_UNAVAILABLE"`, the panel shows a warning
banner, the *Run task* button is disabled, and `POST /api/tasks` refuses new
tasks with **HTTP 409** and the same code in the JSON body — local executors
cannot run without their weights. The remote fallback (Kimi/OpenCodex) remains
No remote or local fallback is implied or performed automatically.

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
