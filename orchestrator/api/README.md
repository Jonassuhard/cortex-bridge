# Orchestrator via the official OpenAI API — ✅ compliant path

**Status: design stage. This is the recommended orchestrator path.**

## Concept

Use the official OpenAI API (Responses API) as the orchestrator brain.
Programmatic access is exactly what the API is for — fully compliant with
OpenAI's terms.

```
Your loop driver (Python) ──► OpenAI API (frontier model)
        │                            │
        │ task (JSON)                │ report (JSON)
        ▼                            │
   Local executor (Codex → Ollama) ──┘
```

## Sketched interface

```python
# orchestrator/api/driver.py  (to be implemented)
def run_loop(goal: str, workspace: str, max_iterations: int = 10):
    conversation = seed_conversation(goal, workspace)
    for i in range(max_iterations):
        task = ask_orchestrator(conversation)          # Responses API call
        report = run_executor(task, workspace)         # CODEX_HOME=~/.codex-cortex-bridge codex exec ...
        conversation = append_report(conversation, report)
        if report["status"] == "done":
            break
    return conversation
```

## Design decisions to make

- Model choice for the orchestrator (frontier vs. cheaper planning model)
- How the executor report is bounded (log truncation, diff caps)
- When to stop: status field, iteration cap, token budget
- Optional human-in-the-loop approval between iterations

## Cost note

Unlike a flat ChatGPT subscription, the API bills per token. The loop is
cheap to run *if* reports are kept structured and short — that is why the
[loop contract](../README.md#loop-contract-shared-by-both-paths) exists.
