# Routing policy — local executors

How the orchestrator routes work to the local Ollama executors, and how
failures escalate. The local models are **execution workers** — they never
replace the cloud orchestrator (Kimi K3 / ChatGPT), which stays in charge of
planning, routing and final judgment. The console (`console/executor.py`)
implements the bridge loop directly against Ollama `/api/chat` — the model
only requests actions, the bridge validates and executes them; there is no
Codex CLI dependency.

## Chain

1. **Primary attempt** — an atomic, explicit, low-ambiguity task is routed to
   `orchestra-executor` (granite4.1:8b), the deterministic primary executor.
2. **Fallback attempt** — on exactly one `BLOCKED` or `FAILED` result from the
   primary: collect the evidence (logs, report, blockers) and retry the same
   action on `orchestra-executor-fallback` (qwen3.5:9b).
3. **Return to the cloud** — if the fallback also fails, package the full
   evidence and return it to the cloud orchestrator (Kimi K3 / ChatGPT).
   There is **no infinite retry**: the loop ends here and a human or the cloud
   orchestrator decides what happens next.

## Limits

- **One loaded local model at a time** — never keep both executors warm in
  memory simultaneously.
- **One retry max per model** — a model gets its single attempt, no loops.
- **Two local attempts max per action** — primary once, fallback once, then
  escalate.
- **No silent success** — every result is reported with evidence.
- **No silent cloud fallback** — any escalation to the cloud is explicit and
  carries the collected evidence.
- **No silent model substitution** — the model that ran is always named in the
  report; routing never swaps models without saying so.

## Storage dependency

Local executors depend on the external model storage (DJO volume). When it is
unavailable, the console reports `LOCAL_MODEL_STORAGE_UNAVAILABLE` and refuses
new local tasks (HTTP 409); the remote Kimi/OpenCodex fallback remains
available. This is surfaced as information only — no automatic re-routing is
performed.
