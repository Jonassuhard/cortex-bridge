# Cortex Bridge v0.5.0 Runtime Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make mission completion, process execution, browser transport, and two-conversation concurrency truthful, fail-closed, distributable, and independently testable.

**Architecture:** Keep the existing `MissionLoop` and transport adapter boundaries, but move unsafe defaults behind explicit capabilities. Add a durable conversation-session registry and a Playwright-backed browser driver so a clean install no longer depends on the private Kimi WebBridge binary. Preserve the current WebBridge driver as an optional compatibility backend.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, `unittest`, Playwright Python, existing `cortex.v1` protocol.

## Global Constraints

- No production change is written before its failing test is observed.
- `COMPLETED` requires a named validator and stored evidence.
- A non-zero process exit or timeout is never reported as success.
- Arbitrary process execution is disabled by default and always reviewed when enabled.
- No shell command strings or `shell=True` remain in release paths.
- Two active writer conversations use distinct browser sessions.
- A third writer receives HTTP 409 without losing its draft or attachment.
- Simulation never produces a release-pass result.
- The compatibility WebBridge backend remains optional and clearly labelled.

---

### Task 1: Fail-closed action and final validation

**Files:**
- Modify: `orchestration/loop.py`
- Modify: `orchestration/runner.py`
- Modify: `tests/test_loop_mock.py`
- Modify: `tests/test_runner_mode_a.py`
- Modify: `tests/test_missions_api.py`

**Interfaces:**
- Produces: `normalize_validation_result(value: object, *, validator_name: str) -> dict`
- Produces: `default_trace_validator(decision: dict, tools: ToolExecutor, store: AuditStore, mission_id: str) -> dict`
- Consumes: tool results with `exitCode`, `timedOut`, and `truncated`

- [ ] **Step 1: Add failing action-result tests**

Add tests that execute fixture decisions for `run_process` returning exit code
3 and a timeout result. Assert that the report status is `FAILED`, validation
contains `process_exit_code` or `process_timeout`, and the action is not noted
as successful.

```python
async def test_process_exit_nonzero_is_failed(self):
    loop, transport = self.make_loop([
        execute("run_process", {"argv": ["python3", "fail.py"]}),
        blocked("stop after the failed command"),
    ])
    await loop.run()
    report = protocol.extract_report(transport.sent_messages[1])
    self.assertEqual(report["status"], "FAILED")
    self.assertFalse(report["validation"]["passed"])
    self.assertEqual(report["toolResult"]["exitCode"], 3)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_loop_mock.LoopTests.test_process_exit_nonzero_is_failed \
  tests.test_loop_mock.LoopTests.test_process_timeout_is_failed -v
```

Expected: both fail because `_validate_action` currently checks only for a
Python exception.

- [ ] **Step 3: Implement action-result validation**

In `_validate_action`, require:

```python
exit_code_ok = result is None or result.get("exitCode", 0) == 0
not_timed_out = result is None or result.get("timedOut") is not True
passed = tool_error is None and exit_code_ok and not_timed_out
```

Return separate checks for execution, exit code, and timeout. Preserve custom
validators, but combine their result with these mandatory checks.

- [ ] **Step 4: Add failing final-validation tests**

Cover:

- no validator;
- validator exception;
- malformed validator output;
- explicit validator failure;
- named validator success with stored evidence.

No-validator must never become `COMPLETED`.

- [ ] **Step 5: Run the final-validation tests and verify RED**

Expected: the no-validator case currently reaches `COMPLETED`.

- [ ] **Step 6: Implement a named default trace validator**

The default validator must verify:

- at least one validated action or an explicitly permitted read-only result;
- no unresolved failed action;
- all process results have exit code zero and no timeout;
- every reported changed file still exists inside the workspace;
- the validation record includes `validator: "execution-trace-v1"`.

Malformed or exceptional validators produce a stored failed validation and a
terminal `FAILED` state. Never treat validator text supplied by ChatGPT as
evidence.

- [ ] **Step 7: Update API expectations**

Adjust mission API fixtures to supply deterministic actions that the trace
validator can prove. Add an API test proving an empty `COMPLETE` decision
fails closed.

- [ ] **Step 8: Run the affected suite**

```bash
.venv/bin/python -m unittest \
  tests.test_loop_mock \
  tests.test_runner_mode_a \
  tests.test_missions_api -v
```

- [ ] **Step 9: Commit**

```bash
git add orchestration/loop.py orchestration/runner.py \
  tests/test_loop_mock.py tests/test_runner_mode_a.py tests/test_missions_api.py
git commit -m "fix(runtime): fail closed on unverified mission results"
```

### Task 2: Explicit process capabilities and deletion policy

**Files:**
- Modify: `executor/tools.py`
- Modify: `executor/policy.py`
- Modify: `console/missions.py`
- Modify: `console/settings.py`
- Modify: `console/local_executor.py`
- Modify: `tests/test_executor_tools.py`
- Create: `tests/test_process_policy.py`
- Modify: `tests/test_chat_settings_api.py`

**Interfaces:**
- Produces: `ProcessCapabilities(allowed: bool, allow_network: bool, allow_deletions: bool)`
- Produces: `sanitized_process_environment(workspace: Path) -> dict[str, str]`
- Extends: `MissionIn` with `allow_processes: bool = False`

- [ ] **Step 1: Write failing policy tests**

Use literal command vectors and assert denial for:

```python
[
    ["rm", "file.txt"],
    ["find", ".", "-delete"],
    ["git", "clean", "-fd"],
    ["python3", "-c", "open('../escape', 'w').write('x')"],
    ["node", "-e", "require('fs').unlinkSync('file')"],
    ["sh", "-c", "echo x"],
    ["bash", "script.sh"],
]
```

Assert that `run_process` is denied when `allow_processes` is false and always
requires per-command approval when true.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.test_process_policy -v
```

- [ ] **Step 3: Replace the denylist contract**

Introduce an explicit executable/subcommand policy. Deny shell interpreters,
inline interpreter execution, package installation, publish/push/login,
network clients other than approved loopback health checks, and every
deletion command.

Run subprocesses with:

```python
await asyncio.create_subprocess_exec(
    *argv,
    cwd=str(workdir),
    env=sanitized_process_environment(self.workspace),
    start_new_session=True,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

On timeout, terminate the process group, then kill it if it does not exit.

- [ ] **Step 4: Apply capabilities in `PolicyEngine`**

`run_process` and `run_tests` are rejected unless `allow_processes` is true.
When true, they require approval even under automatic write mode. Direct file
tools never expose deletion in v0.5.0.

- [ ] **Step 5: Remove the legacy shell path**

Replace `create_subprocess_shell` in `console/local_executor.py` with the
shared structured process executor. A missing executor returns
`EXECUTOR_UNAVAILABLE`, never simulated `done`.

- [ ] **Step 6: Verify environment and child cleanup**

Add tests that a marker secret from the parent environment is absent, a timed
out command leaves no child process, and the settings API reports the actual
capabilities rather than a hard-coded deletion promise.

- [ ] **Step 7: Run backend policy tests**

```bash
.venv/bin/python -m unittest \
  tests.test_executor_tools \
  tests.test_process_policy \
  tests.test_chat_settings_api -v
```

- [ ] **Step 8: Commit**

```bash
git add executor/tools.py executor/policy.py console/missions.py \
  console/settings.py console/local_executor.py \
  tests/test_executor_tools.py tests/test_process_policy.py \
  tests/test_chat_settings_api.py
git commit -m "fix(security): require reviewed structured process execution"
```

### Task 3: Durable conversation-session isolation

**Files:**
- Create: `console/conversation_sessions.py`
- Modify: `console/write_slots.py`
- Modify: `console/chat.py`
- Modify: `console/missions.py`
- Modify: `orchestration/store.py`
- Modify: `transport/chatgpt_web/adapter.py`
- Modify: `tests/test_write_slots.py`
- Create: `tests/test_transport_session_isolation.py`

**Interfaces:**
- Produces: `ConversationSessionRegistry`
- Produces: `acquire_writer(conversation_key: str) -> SessionLease`
- Produces: `rekey(provisional_key: str, canonical_key: str) -> SessionLease`
- Produces: `release_writer(conversation_key: str) -> None`
- Session IDs: `cortex-conv-<stable-token>`

- [ ] **Step 1: Write a session-aware fake daemon test**

The fake records the session ID and target URL for every command. Start A and
B concurrently, then assert:

- two session IDs;
- A receives only A messages;
- B receives only B messages;
- a read-only snapshot cannot navigate either writer session;
- a second writer on A is serialized or refused;
- C receives HTTP 409 while A and B are active.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.test_transport_session_isolation -v
```

- [ ] **Step 3: Implement the registry**

Use an async global capacity of two, a per-conversation lock, a unique
provisional UUID for new chats, and atomic rekeying. Persist session ID and
conversation target in `conversation_bindings`.

- [ ] **Step 4: Route every chat and mission through a lease**

Remove shared default session construction from `console/chat.py` and
`console/missions.py`. Create a separate read-only browser session that never
navigates a leased writer tab.

- [ ] **Step 5: Rebuild slots after restart**

Load non-terminal missions and chat runs from SQLite/JSON persistence, restore
their leases, and release exactly one slot on every terminal transition.

- [ ] **Step 6: Run concurrency tests ten times**

```bash
for i in $(seq 1 10); do
  .venv/bin/python -m unittest \
    tests.test_write_slots tests.test_transport_session_isolation || exit 1
done
```

- [ ] **Step 7: Commit**

```bash
git add console/conversation_sessions.py console/write_slots.py \
  console/chat.py console/missions.py orchestration/store.py \
  transport/chatgpt_web/adapter.py tests/test_write_slots.py \
  tests/test_transport_session_isolation.py
git commit -m "fix(transport): isolate two active conversation sessions"
```

### Task 4: Distributable Playwright browser driver

**Files:**
- Create: `transport/browser_playwright/__init__.py`
- Create: `transport/browser_playwright/driver.py`
- Create: `transport/browser.py`
- Modify: `transport/chatgpt_web/adapter.py`
- Modify: `console/settings.py`
- Modify: `console/onboarding.py`
- Modify: `console/requirements.txt`
- Create: `tests/test_playwright_driver.py`

**Interfaces:**
- Produces: `BrowserDriver` protocol with `navigate`, `evaluate`,
  `list_tabs`, `upload_files`, `take_screenshot`, `health`, and `close`
- Produces: `PlaywrightBrowserDriver(session: str, profile_root: Path)`
- Keeps: `WebBridgeDriver` as compatibility implementation

- [ ] **Step 1: Write driver-contract tests against a local fixture page**

Verify navigation, evaluation, isolated persistent contexts, file input,
screenshot, tab listing, health, and cleanup. No test uses chatgpt.com.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.test_playwright_driver -v
```

- [ ] **Step 3: Implement the browser-driver protocol**

Run Playwright in a dedicated worker thread. Each session owns a persistent
profile below `console/data/browser-profiles/<session>`. Launch visible
Chromium on first login and never copy cookies from another browser profile.

- [ ] **Step 4: Add transport selection**

Settings values:

```json
{
  "browser_transport": "playwright",
  "browser_profile_root": "console/data/browser-profiles"
}
```

Allowed values are `playwright` and `webbridge`. The onboarding screen gives
the user a button to open the dedicated browser profile and asks them to log
in manually.

- [ ] **Step 5: Exercise the existing adapter against both drivers**

All adapter fixture tests must pass unchanged through the protocol boundary.
Add a driver-name field to health and diagnostics.

- [ ] **Step 6: Run transport tests**

```bash
.venv/bin/python -m unittest \
  tests.test_playwright_driver \
  tests.test_transport_fixture \
  tests.test_probe -v
```

- [ ] **Step 7: Commit**

```bash
git add transport/browser.py transport/browser_playwright \
  transport/chatgpt_web/adapter.py console/settings.py console/onboarding.py \
  console/requirements.txt tests/test_playwright_driver.py
git commit -m "feat(transport): add distributable Playwright browser driver"
```

### Task 5: Truthful executor and simulation states

**Files:**
- Modify: `console/local_executor.py`
- Modify: `console/missions.py`
- Modify: `console/settings.py`
- Modify: `frontend/lib/types.ts`
- Modify: `tests/test_chat_settings_api.py`
- Create: `tests/test_executor_runtime_truth.py`

**Interfaces:**
- Produces: `executor_kind: "deterministic" | "ollama" | "unavailable"`
- Produces: `executor_model_used: str | None`
- Produces: `runtime_mode: "live" | "development_fixture"`

- [ ] **Step 1: Add failing truth tests**

Assert:

- a Mode A mission reports deterministic execution and no Ollama model;
- `/api/tasks` reports the exact Ollama model only after a real model call;
- unavailable Ollama never returns `done`;
- simulation requires an explicit development flag and is rejected by the
  release verifier.

- [ ] **Step 2: Verify RED**

```bash
.venv/bin/python -m unittest tests.test_executor_runtime_truth -v
```

- [ ] **Step 3: Implement truthful runtime fields**

Remove unused primary/fallback model claims from mission requests. Keep model
selection only on code paths that call Ollama. Replace automatic simulation
fallback with a structured unavailable state.

- [ ] **Step 4: Run settings and runtime tests**

```bash
.venv/bin/python -m unittest \
  tests.test_executor_runtime_truth tests.test_chat_settings_api -v
```

- [ ] **Step 5: Commit**

```bash
git add console/local_executor.py console/missions.py console/settings.py \
  frontend/lib/types.ts tests/test_chat_settings_api.py \
  tests/test_executor_runtime_truth.py
git commit -m "fix(runtime): report the executor that actually ran"
```

### Task 6: Backend metadata, switching budget, and attachment boundaries

**Files:**
- Modify: `transport/chatgpt_web/adapter.py`
- Modify: `transport/chatgpt_web/fixture.py`
- Modify: `console/chat.py`
- Modify: `console/attachments.py`
- Modify: `tests/test_transport_fixture.py`
- Create: `tests/test_attachment_boundaries.py`

**Interfaces:**
- Conversation metadata adds `project_id` and `project_title`
- Normal conversation switch budget: 10 seconds
- Explicit recovery: `reload_required: true`

- [ ] **Step 1: Add failing metadata and timeout tests**

Test real project titles, exclusive max-50 results, deletion reconciliation,
an obsolete switch cancellation, and a 10-second recoverable timeout.

- [ ] **Step 2: Add attachment-boundary tests**

Cover exact file/image limits, MIME mismatch, traversal filenames, symlink,
unregistered raw token, restart cleanup, and staged attachment preservation.

- [ ] **Step 3: Verify RED**

```bash
.venv/bin/python -m unittest \
  tests.test_transport_fixture tests.test_attachment_boundaries -v
```

- [ ] **Step 4: Implement metadata, budget, and attachment validation**

Return stable project fields, cap the normal navigation path, never perform a
silent full reload after the budget, and require explicit recovery. Detect
MIME from content where supported and neutralize filenames before registry
storage.

- [ ] **Step 5: Run affected tests**

```bash
.venv/bin/python -m unittest \
  tests.test_transport_fixture tests.test_attachment_boundaries \
  tests.test_chat_settings_api -v
```

- [ ] **Step 6: Commit**

```bash
git add transport/chatgpt_web/adapter.py transport/chatgpt_web/fixture.py \
  console/chat.py console/attachments.py tests/test_transport_fixture.py \
  tests/test_attachment_boundaries.py
git commit -m "fix(transport): bound switching and validate conversation data"
```

### Task 7: Runtime verification gate

**Files:**
- Create: `scripts/verify-runtime.py`
- Modify: `scripts/test-all.sh`
- Create: `docs/verification/runtime-schema.json`
- Create: `tests/test_verify_runtime.py`

**Interfaces:**
- Produces: machine-readable JSON with suite counts, failures, driver,
  executor, simulation flag, and security checks

- [ ] **Step 1: Write a failing verifier test**

The verifier must reject:

- fixture or simulation labelled as live;
- missing final-validator evidence;
- non-zero command results labelled successful;
- shared session IDs for active conversations.

- [ ] **Step 2: Implement and run the verifier**

```bash
.venv/bin/python -m unittest tests.test_verify_runtime -v
./scripts/test-all.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/verify-runtime.py scripts/test-all.sh \
  docs/verification/runtime-schema.json tests/test_verify_runtime.py
git commit -m "test(runtime): enforce the v0.5 safety gate"
```
