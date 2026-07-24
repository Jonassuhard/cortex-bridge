# Example: one full Cortex Bridge loop

Goal: *"Add input validation to the signup form in my web app and make sure
the tests pass."*

---

**Iteration 1 — orchestrator → executor**

```json
{
  "goal": "Add email and password validation to the signup form",
  "constraints": [
    "stay inside ~/projects/myapp",
    "use the existing validation helpers in src/lib if present",
    "do not add new dependencies"
  ],
  "workspace": "/Users/me/projects/myapp",
  "context": "Signup form lives in src/components/SignupForm.tsx. Tests run with `npm test`."
}
```

**Iteration 1 — executor → orchestrator**

```json
{
  "status": "done",
  "summary": "Added validateEmail/validatePassword to SignupForm.tsx using src/lib/validators. 2 of 14 tests still fail.",
  "commands_run": ["npm test"],
  "files_changed": ["src/components/SignupForm.tsx", "src/lib/validators.ts"],
  "blockers": ["test 'rejects weak password' expects a specific error message format I could not infer"],
  "suggested_next_step": "Tell me the expected error message format, or let me read the failing test file."
}
```

**Iteration 2 — orchestrator → executor**

```json
{
  "goal": "Read the failing test and align the error messages with its expectations",
  "constraints": ["do not modify the test file"],
  "workspace": "/Users/me/projects/myapp",
  "context": "Previous iteration: validation added, 2 tests fail on error message format."
}
```

**Iteration 2 — executor → orchestrator**

```json
{
  "status": "done",
  "summary": "Aligned error messages with the test expectations. All 14 tests pass.",
  "commands_run": ["npm test"],
  "files_changed": ["src/lib/validators.ts"],
  "blockers": [],
  "suggested_next_step": "None — goal achieved."
}
```

Loop ends. Total orchestrator tokens consumed: two short structured exchanges
— this is why the loop contract keeps reports terse.
