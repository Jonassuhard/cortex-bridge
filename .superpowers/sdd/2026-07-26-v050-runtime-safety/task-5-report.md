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

## Fix round 1/5

### Review findings resolved

- Modern frontend API failures now use a pure neutral state boundary. Without
  `NEXT_PUBLIC_CORTEX_DEVELOPMENT_FIXTURES=1`, pipeline/settings/runtime
  refreshes expose no demo mission, model list, activity, active mission id, or
  fabricated executor. The initial render is neutral for the same reason.
- Mode A truth is durable SQLite evidence. The additive `missions` migration
  stores `executor_kind`, `executor_model_used`, `runtime_mode`,
  `release_eligible`, and `runtime_observed_at`; completed missions retain
  `deterministic` / `null` / `live` across a store close and reopen. API reads
  no longer hard-code those values.
- Pipeline executor truth comes from the persisted `/api/tasks` report (or the
  persisted active Mode A mission), not Ollama availability. It includes the
  task id, execution state, active flag, observation timestamp, and release
  eligibility, so terminal history is not rendered as a current execution.
- `/api/tasks` now drives the real `_run_live` boundary in tests with only
  `_chat_sync` patched. The exact called model is persisted to JSON, returned
  by the task API, and surfaced by the pipeline. A failed call remains
  `unavailable` / `null`.
- `TaskIn.development_fixture` defaults false. Real loopback HTTP tests cover
  all four request/environment combinations: only request true plus
  `CORTEX_ALLOW_DEVELOPMENT_FIXTURES=1` activates the blocked,
  non-release-eligible fixture; request true without the environment gate is a
  structured HTTP 403; the other two combinations remain live.
- Local reports and mission API/report boundaries expose `release_eligible`.
  Development fixtures and non-success terminal states remain false.
- `_build_runtime` accepts legacy executor arguments both positionally and as
  `primary_executor=` / `fallback_executor=` keywords, and explicitly ignores
  them.
- The fallback settings save path no longer dereferences the removed
  `#setFallback` element; a Node VM regression executes the real function.
- Shared frontend helpers ensure idle never reads as deterministic,
  `available` is recognized as availability, Ollama structured-tool wording
  appears only after actual Ollama execution, and failed/blocked/cancelled are
  never labelled complete.

### TDD evidence

RED backend command:

```text
.venv/bin/python -m unittest tests.test_executor_runtime_truth -v
```

Observed: `Ran 9 tests`; `failures=2, errors=5`. The failures were specific to
the missing keyword compatibility, durable/release fields, task-store pipeline
truth, HTTP fixture rejection, and fallback DOM dereference.

RED frontend command:

```text
node --experimental-strip-types --test frontend/lib/runtimeTruth.test.ts
```

Observed: failed because the neutral/runtime presentation boundary did not
exist. A second focused RED run proved terminal presentation had no exported
helper before implementation.

GREEN focused commands:

```text
.venv/bin/python -m unittest tests.test_executor_runtime_truth -v
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON \
  --experimental-strip-types --test frontend/lib/runtimeTruth.test.mts
```

Result: backend `Ran 9 tests in 8.584s ... OK`; frontend `4 tests`, all pass.

GREEN affected command under a 240-second process-group watchdog:

```text
.venv/bin/python -m unittest \
  tests.test_executor_runtime_truth tests.test_chat_settings_api \
  tests.test_missions_api tests.test_runner_mode_a \
  tests.test_protocol_state_store tests.test_process_policy \
  tests.test_transport_session_isolation -q
```

Result: `Ran 106 tests in 69.836s ... OK`, watchdog exit 0.

### Full and static verification

The exact requested discovery command ran inside a 300-second process-group
watchdog:

```text
.venv/bin/python -m unittest discover -s tests -v
```

Result: `Ran 214 tests in 198.624s ... OK`, watchdog exit 0. No Ollama or
external network dependency was used; HTTP/browser tests were loopback
fixtures.

```text
.venv/bin/python -m py_compile $(rg --files -g '*.py' -g '!frontend/**')
git diff --check
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

Result: all exited 0.

### Preserved external dirt and concern

- Known generated changes under `frontend/out/**` and
  `frontend/tsconfig.tsbuildinfo` remain unstaged and uncommitted.
- The full suite exits 0 but still emits existing `ResourceWarning` lines for
  a few unclosed SQLite/HTTP test resources. They do not affect Task 5 runtime
  truth, but should be cleaned in a dedicated lifecycle pass rather than
  disguised here.

## Fix round 2/5

### Review findings resolved

- A failed conversation refresh keeps already synchronized content only as an
  explicit stale cache: both the selected conversation and list entries carry
  `sync_state=stale` plus the synchronization error. With no cache, the state
  is unavailable. Development conversations still require the explicit
  frontend fixture flag.
- A failed mission-list or mission-detail refresh clears the selected mission,
  detail, active mission id/state, events, current task, and current executor.
  The remaining transport component stays independent; the pipeline and local
  execution components become neutral instead of inheriting stale activity.
- `ChatWorkspace` now derives ChatGPT and executor status independently from
  their respective components. `PipelineInspector` uses the same presentation
  helper. `unknown` is rendered as `État inconnu` with neutral styling, never
  `Connecté` or `Live`; unavailable/error states render `Indisponible`.
- The standalone fallback executes the same truth rule for its pipeline label;
  a Node VM regression runs the real `renderPipeline` function and proves an
  unknown pipeline is not rendered online.
- Mode A coverage now starts from a genuine pre-v0.5 `missions` table. The
  additive migration preserves the legacy row and defaults, then persists and
  reloads updated runtime truth. A completed mission's non-empty
  `runtime_observed_at` is also proven stable across close/reopen.

### TDD evidence

Frontend RED command:

```text
node --disable-warning=MODULE_TYPELESS_PACKAGE_JSON \
  --experimental-strip-types --test frontend/lib/runtimeTruth.test.mts
```

Observed: `7 tests`; 4 passed and 3 failed because
`reduceConversationRefreshFailure`, `reduceMissionRefreshFailure`, and
`statusPresentation` did not exist. A focused follow-up RED proved `error` was
mislabelled as `État inconnu`. The fallback VM regression separately failed
with actual `En ligne` versus expected `État inconnu`.

Frontend GREEN result for the same Node command: `7 tests`, all pass in
`164.261ms`. These tests drive the pure reducers and presentation helper
imported by `CortexApp`, including the success-then-failure transition.

Backend focused command:

```text
.venv/bin/python -m unittest tests.test_executor_runtime_truth -v
```

Result: `Ran 11 tests in 7.390s ... OK`. The new genuine-schema migration and
timestamp-stability assertions passed against the existing additive persistence
implementation; no compensating backend production change was required.

Affected command under a 240-second process-group watchdog:

```text
.venv/bin/python -m unittest \
  tests.test_executor_runtime_truth tests.test_chat_settings_api \
  tests.test_missions_api tests.test_runner_mode_a \
  tests.test_protocol_state_store tests.test_process_policy \
  tests.test_transport_session_isolation -q
```

Result: `Ran 108 tests in 69.349s ... OK`, watchdog exit 0.

### Full and static verification

The exact discovery command ran inside a 300-second process-group watchdog:

```text
.venv/bin/python -m unittest discover -s tests -v
```

Result: `Ran 216 tests in 199.177s ... OK`, watchdog exit 0.

```text
.venv/bin/python -m py_compile $(rg --files -g '*.py' -g '!frontend/**')
git diff --check
npm --prefix frontend run typecheck
npm --prefix frontend run lint
```

Result: all exited 0 after the final source changes.

### Preserved external dirt and concern

- Known generated changes under `frontend/out/**` and
  `frontend/tsconfig.tsbuildinfo` remain unstaged and uncommitted.
- The green backend runs still emit existing `ResourceWarning` lines for a few
  unclosed SQLite/HTTP test resources. They remain a separate lifecycle debt.
