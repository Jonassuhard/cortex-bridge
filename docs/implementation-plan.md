# Cortex Bridge — Implementation Plan (Automated Loop)

Mission source: `../MISSION-BUILD-AN.txt` (build and verify the fully automated
ChatGPT Web ↔ local executor loop). Reformulated and planned 2026-07-24.

## Phase 0 — Audit results

**Verified infrastructure (live checks, 2026-07-24):**

| Component | State | Evidence |
|---|---|---|
| Console FastAPI (127.0.0.1:8420) | running, live mode | `GET /api/status` → healthy |
| Ollama (127.0.0.1:11434) | healthy | `/api/status` |
| Model storage `/Volumes/DJO/AI/Ollama/models` | mounted | `/api/status` |
| orchestra-executor (granite4.1:8b) | installed, benchmark 10/10 | executor/benchmark/ |
| orchestra-executor-fallback (qwen3.5:9b) | installed | `/api/status` |
| WebBridge daemon (127.0.0.1:10086) | running, read+navigate proven | live extraction from chatgpt.com |
| Git | clean, 6 commits, gitleaks hook | `git status` |

**Unsafe paths identified:**

1. `console/executor.py::_run_live` — free-form model shell via
   `asyncio.create_subprocess_shell`. Jail + denylist mitigate but do not
   eliminate quoting failures (observed twice live: heredoc/echo escaping
   broke valid Python). → replace with structured Python tools.
2. No persistence: task history is `console/data/iterations.json` (in-memory
   list + JSON dump). → SQLite per mission spec.
3. No tests directory at all.
4. ChatGPT transport is manual copy-paste. → WebBridge adapter.
5. Orchestrator contract is an unversioned raw-JSON prompt → markdown
   rendering mangles escapes (observed live). → `cortex.v1` fenced blocks.

**Reusable components:** FastAPI app + Preuvia-style static UI, Ollama
health/model probes, workspace snapshot + `_files_changed`, bridge-side
auto-validation (`_auto_validate`), denylist/jail concepts, WebBridge daemon.

## Phase plan (per mission §26)

- **P1 Protocol+persistence**: `cortex.v1` decision/report schemas, mission
  state machine, SQLite (tables per §18), duplicate/idempotency protection,
  restart→PAUSED_RECOVERY_REQUIRED. Unit tests §20.
- **P2 Structured tools**: `orchestration/tools.py` implementing the 11 tools
  of §10 in Python, path confinement + symlink protection, checkpoints,
  `run_process` via `create_subprocess_exec` (never shell=True), denylist §15.
  Tests §21.
- **P3 Mock loop**: mock orchestrator driving multi-iteration missions through
  the real state machine; pause/resume/cancel/final validation.
- **P4 Browser fixture**: local HTML fixture imitating ChatGPT surface;
  transport adapter passes §22 tests before touching real ChatGPT.
- **P5 Real transport**: WebBridge adapter (`transport/chatgpt_web/`):
  conversation select+lock, identity verify per message, generation-complete
  detection (multi-signal §13), blocker detection (login/CAPTCHA/rate-limit),
  send message, extract latest ```cortex-decision fenced block only.
- **P6 UI**: mission composer, conversation selector, timeline (§17),
  approvals, STOP EVERYTHING, experimental-transport warning + explicit opt-in.
- **P7 Controlled real tests A–H** (§23) on a dedicated disposable conversation.
- **P8 Final acceptance** (§24): scan.py mission on e2e-sandbox, zero
  copy-paste.
- **P9 Docs** per §1481-1493.

## Hard constraints (never violate)

No OpenAI API / API key, no Codex CLI, no OpenCodex, no sudo, loopback only,
no push without explicit approval, no cookie/credential access, no CAPTCHA or
anti-bot bypass, manual mode preserved as fallback.
