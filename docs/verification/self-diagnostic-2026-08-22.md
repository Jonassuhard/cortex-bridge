# Self-diagnostic mission — 2026-08-22

Release-close gate for v0.5.2: the documented lifecycle commands were
executed for real in a **disposable detached worktree** on `main@7d90c34`
with an isolated `CORTEX_HOME`. The worktree was removed afterwards and
never merged anything, per the release checklist.

All paths below use neutral markers; no personal path, account or volume
name is recorded.

## Environment

- Source: detached worktree of `main` at `7d90c34` (post-0.5.2 bump).
- Runtime state: isolated `CORTEX_HOME` at `$HOME/cortex-selfcheck-home`
  (removed after the run).
- Python: 3.12.14 (managed), fresh venv from `requirements.lock`
  (`--require-hashes`).

## Executed commands and observed results

| # | Command | Result |
|---|---------|--------|
| 1 | `install.sh --dry-run --json` | Immutable plan, `version: 0.5.2`, plan hash `52f7692eb8144e91d40e53bcab2b4ad8420b47bd0a413dc919292a26a687ff3c` |
| 2 | `install.sh --approve-plan 52f7692e… --json` | Install applied: venv (164 MB, locked deps) + `install/owned.json` recording the same plan hash and version 0.5.2 |
| 3 | `install.sh --approve-plan 52f7692e… --json` (replay) | Refused: `approved plan hash does not match the current plan` — an already-consumed plan cannot be replayed; a fresh dry-run then reports `already_installed` with the new plan hash `fb9e1c4269809cb3abab5c680287f71e0d84fc90e8d85c71ee26286327bc57df` |
| 4 | `cortex.sh doctor` | 5 ✅ / 1 ⚠️ (console stopped, with repair hint) — actionable French checklist as designed |
| 5 | `cortex.sh start` | `Cortex Bridge ready: http://127.0.0.1:8420`, owned pid recorded |
| 6 | `cortex.sh status` | Reports the real listener pid in French, consistent with the owned record |
| 7 | `GET /api/status` (loopback self-query) | HTTP 200, `"version": "0.5.2"`, `"runtime_mode": "live"`, executor section consistent |
| 8 | `GET /api/tasks` | HTTP 200, empty list on a fresh home |
| 9 | `cortex.sh stop` | Clean stop; port 8420 verified free afterwards |

## Notes

- The replay refusal in row 3 is the intended consent behavior: an approval
  hash is single-purpose and a mutated state produces a different plan hash.
- Ollama was reachable on the configured external volume during the run
  (`ollama_status: healthy`); the deterministic executor remains the
  always-available default and needs no model.
- Earlier in the session a first attempt targeted a `/private/tmp`-based
  `CORTEX_HOME`; that state was wiped and the full sequence above was
  re-executed cleanly against the `$HOME`-based home.

## Verdict

Self-diagnostic mission: **PASS** — executed in a disposable worktree that
was deleted without merging, covering install → approve → replay-guard →
doctor → start → status → API self-query → stop.
