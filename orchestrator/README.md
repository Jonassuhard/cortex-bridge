# Orchestrator — the cloud half of Cortex Bridge

The orchestrator is the strong cloud model that plans, decomposes, reviews the
executor's reports, and decides the next step. Two delivery paths exist:

| Module | How it reaches the cloud model | Terms-of-service status |
|---|---|---|
| [`api/`](api/) | Official OpenAI API (pay-per-token) | ✅ Compliant — **recommended** |
| [`browser-bridge/`](browser-bridge/) | Automates the ChatGPT web/desktop app of an existing subscription | ⚠️ Violates OpenAI's ToS — at your own risk |

**Read [../docs/legal-notes.md](../docs/legal-notes.md) before choosing.**

## Loop contract (shared by both paths)

Whatever the transport, each iteration exchanges two messages:

**Task (orchestrator → executor)**

```json
{
  "goal": "what must be achieved, in one sentence",
  "constraints": ["stay inside the workspace", "do not install system packages"],
  "workspace": "/absolute/path",
  "context": "anything the executor needs from previous iterations"
}
```

**Report (executor → orchestrator)**

```json
{
  "status": "done | blocked | failed",
  "summary": "what was actually done",
  "commands_run": ["..."],
  "files_changed": ["..."],
  "blockers": ["..."],
  "suggested_next_step": "..."
}
```

The structured report is what makes the loop robust: the orchestrator always
gets status, evidence and blockers — never just prose.

## Status

Both modules are at **design stage**. The executor half (`../executor/`) is
functional today; contributions on the loop transport are very welcome.
