# Task 5 report — truthful executor and simulation states

## Outcome

- Runtime contract is exact:
  - `executor_kind`: `deterministic | ollama | unavailable`
  - `executor_model_used`: `null` until `_chat_sync` returns successfully,
    then the exact model passed to that call
  - `runtime_mode`: `live | development_fixture`
- Mode A reports deterministic execution and never claims Ollama.
- Legacy mission `primary_executor` / `fallback_executor` fields remain
  accepted for compatibility but are ignored.
- An unavailable local executor fails with `EXECUTOR_UNAVAILABLE`; it never
  completes through a fallback.
- Development fixtures require both the request flag and
  `CORTEX_ALLOW_DEVELOPMENT_FIXTURES=1`. They return a blocked report and fail
  `release_runtime_eligible`.
- `/api/tasks` exposes `unavailable` / `null` while running, then copies the
  actual executor truth from the completed report.
- Pipeline/UI separates Ollama/model availability from the executor actually
  used. Error, blocked, and cancelled states no longer render as completed.
- The modern frontend fixture requires
  `NEXT_PUBLIC_CORTEX_DEVELOPMENT_FIXTURES=1`; the standalone fallback requires
  the explicit loopback query `?development_fixture=1`.
- The contradictory legacy `console/static` application is no longer served
  when release frontends are missing.

## TDD evidence

### RED

Command:

```text
.venv/bin/python -m unittest tests.test_executor_runtime_truth -v
```

Observed: 6 tests ran; 1 failure and 5 errors. Failures were contract-specific:
missing runtime fields, missing release gate, `/api/tasks` exposing no truthful
before/after fields, Mode A missing deterministic truth, and `_chat_sync`
having no model-bearing call boundary.

The pipeline observability test was also run before implementation and failed
because no distinct `executor` component existed.

### GREEN

```text
.venv/bin/python -m unittest \
  tests.test_executor_runtime_truth tests.test_chat_settings_api -v
```

Result: `Ran 21 tests ... OK`.

```text
.venv/bin/python -m unittest \
  tests.test_executor_runtime_truth tests.test_chat_settings_api \
  tests.test_process_policy tests.test_missions_api tests.test_runner_mode_a -v
```

Result: `Ran 47 tests ... OK`.

```text
.venv/bin/python -m unittest tests.test_transport_session_isolation -v
```

Result: `Ran 30 tests ... OK`, including all three legacy positional
`_build_runtime` compatibility cases.

## Full-backend evidence

First complete discovery run:

```text
.venv/bin/python -m unittest discover -s tests -v
```

Result: `Ran 206 tests`; 203 passed and 3 compatibility calls failed after the
initial removal of positional legacy model arguments. The arguments were
restored and explicitly ignored. The entire affected 30-test isolation suite
then passed.

A second complete discovery run was attempted. It progressed beyond the
runtime tests but stalled in an existing Playwright driver async teardown and
was interrupted; no Task 5 assertion failure was reported before interruption.
The Playwright suite had passed in the first complete run.

## Static checks

```text
.venv/bin/python -m py_compile $(rg --files -g '*.py' -g '!frontend/**')
git diff --check
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

Result: all exited 0. No frontend build/export was run.

## Preserved external dirt

Known pre-existing generated changes under `frontend/out/**` and
`frontend/tsconfig.tsbuildinfo` were not modified intentionally, staged, or
committed.

## Concern

- The monolithic backend discovery command has a pre-existing/intermittent
  Playwright worker teardown hang under repeated same-session runs. Runtime,
  settings, mission, process-policy, runner, and session-isolation suites are
  green after the final changes.
