# Task 4 Report — Distributable Playwright browser driver

## Scope

- Added the `BrowserDriver` protocol and the single runtime factory in
  `transport/browser.py`.
- Added a shared persistent Playwright Chromium runtime in
  `transport/browser_playwright/`.
- Kept WebBridge as the explicit `webbridge` compatibility backend.
- Routed chat, missions, settings, diagnostics and onboarding through injectable
  factories.
- Added the dedicated-profile onboarding action and visible frontend button.
- Added only `playwright>=1.52,<2`; the local launcher now ensures both Python
  requirements and the matching Chromium binary.

## TDD evidence

### Initial RED

Command:

```bash
.venv/bin/python -m unittest tests.test_playwright_driver \
  tests.test_chat_settings_api.ChatSettingsApiTestCase.test_06_settings_persist_and_never_delete_is_forced \
  tests.test_chat_settings_api.ChatSettingsApiTestCase.test_09_pipeline_status_has_required_components \
  tests.test_chat_settings_api.ChatSettingsApiTestCase.test_10_onboarding_opens_dedicated_login_profile -v
```

Result: exit 1, two expected errors:

- `ModuleNotFoundError: No module named 'transport.browser'`
- `AttributeError: module 'settings' has no attribute 'browser_driver_factory'`

This established that the browser contract and injectable console factory did
not exist.

### Lifecycle REDs

```bash
.venv/bin/python -m unittest \
  tests.test_playwright_driver.PlaywrightDriverTest.test_health_does_not_launch_profile_before_explicit_browser_use -v
```

Result: exit 1; health reported `connected=True` because driver construction
started Chromium before the explicit onboarding action.

```bash
.venv/bin/python -m unittest \
  tests.test_playwright_driver.WebBridgeLifecycleCompatibilityTest.test_close_is_idempotent -v
```

Result: exit 1; two `close()` calls caused two close operations.

### GREEN

```bash
.venv/bin/python -m unittest tests.test_playwright_driver -v
```

Result: 7 tests passed. Coverage includes:

- loopback-only navigation and evaluation;
- persistent-profile isolation and same-session reopen after close;
- file input and screenshot;
- tab listing and generic driver health;
- one serialized dedicated worker thread;
- event-loop-safe and idempotent Playwright close;
- lazy startup until an explicit browser operation;
- factory selection/cache for `playwright` and `webbridge`;
- public `evaluate` attachment fallback (no private `_command`);
- idempotent WebBridge compatibility close.

## Regression evidence

Baseline before implementation:

```bash
.venv/bin/python -m unittest tests.test_transport_fixture tests.test_probe \
  tests.test_chat_settings_api tests.test_transport_session_isolation -v
```

Result: 64 tests passed in 111.944 s. Existing `ResourceWarning` noise was
present before Task 4.

Required transport suite:

```bash
.venv/bin/python -m unittest tests.test_playwright_driver \
  tests.test_transport_fixture tests.test_probe -v
```

Final result: 36 tests passed in 107.811 s.

Directly affected API/session suite:

```bash
.venv/bin/python -m unittest tests.test_chat_settings_api \
  tests.test_transport_session_isolation tests.test_missions_api \
  tests.test_write_slots -v
```

Result: 54 tests passed in 52.122 s.

Full backend suite:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The first full run exposed an order-dependent test-harness leak:
`tests/test_missions_api.py` left `missions_api._store` closed for the later
session suite. The production driver was not involved. The test harness now
restores the exact prior store, opt-in path and injectable transport factory.

Proof in the previously failing order:

```bash
.venv/bin/python -m unittest \
  tests.test_missions_api tests.test_transport_session_isolation -v
```

Result: 36 tests passed in 44.355 s.

Fresh full-suite result after that correction: 180 tests passed in 178.132 s.
Pre-existing `ResourceWarning` noise remains, with zero failures/errors.

Frontend:

```bash
npm run typecheck -- --incremental false
npm run lint
```

Result: both exited 0. No frontend export/build was run; existing
`frontend/out/**` and `frontend/tsconfig.tsbuildinfo` changes were preserved.

## Implementation notes

- Playwright sync objects are created, used and closed only on one dedicated
  worker thread per authenticated runtime. Async callers enqueue serialized
  operations and await protected `concurrent.futures.Future` instances without
  blocking the event loop.
- All logical sessions share
  `<browser_profile_root>/cortex-bridge-ui`; each session owns an isolated,
  bounded page inside that one authenticated persistent context.
- Driver construction is lazy. Health checks do not open Chromium; the
  onboarding button calls `open_login()` and starts the visible dedicated
  profile.
- The Playwright factory reuses a live `(profile root, session, headless)`
  driver and replaces closed instances, avoiding duplicate locked contexts.
- Settings accept exactly `playwright` or `webbridge`; the default is
  `playwright`.
- Diagnostics and pipeline status expose the selected driver name rather than a
  hard-coded WebBridge label.
- Chat and mission writer session IDs still flow through the Task 3 lease
  registry; only driver construction moved behind the central factory.

## Self-review

- No test navigated to `chatgpt.com`; all browser and WebBridge contract tests
  used loopback fixture servers. Production `open_login()` and conversation
  discovery intentionally default to `https://chatgpt.com/`.
- No cookies or profiles are copied from another browser.
- Session names are validated before profile-path construction.
- The adapter no longer calls `driver._command` for upload fallback.
- The only dependency addition is Playwright with a minimum known-compatible
  release and a major-version breaking-change cap.
- Generated frontend export files and `tsconfig.tsbuildinfo` are intentionally
  excluded from this task's staging.

## Concerns / follow-up

- `scripts/start-local.sh` now runs both requirements installation and
  `python -m playwright install chromium` before starting the console.
- Live ChatGPT DOM compatibility is intentionally not exercised in Task 4.
  The existing local DOM fixture/probe regressions remain the release evidence.

## Final verification

- Required transport suite: 36/36 passed.
- Full Python suite: 180/180 passed.
- Directly affected API/session suite: 54/54 passed.
- Final Playwright contract rerun used loopback URLs only; production external
  defaults remain explicit and intentional.
- Frontend typecheck (`--incremental false`) and ESLint: exit 0.
- `py_compile` for every changed Python source/test: exit 0.
- `git diff --check`: exit 0.
- Staged-file audit and commit are recorded in the handoff.

## Fix round 1/5 — runtime safety review

### RED evidence

The new regression suite was written before the fixes. The first targeted run
failed the shared-authentication assertion, then hung after cancelling a queued
evaluation. The captured stack showed the cancelled asyncio wrapper cancelling
the underlying `concurrent.futures.Future`; the worker subsequently attempted
to settle that cancelled future and became unusable.

The additional REDs covered:

- atomic admission versus shutdown;
- bounded `evaluate(timeout)` with a never-resolving Promise;
- raw Playwright exception normalization and delivery uncertainty after click;
- startup failure eviction and recovery;
- bounded logical-page/profile lifecycle;
- concurrent WebBridge close;
- meaningful adapter flows through Playwright and WebBridge loopback fixtures;
- unconditional requirements/Chromium bootstrap;
- structured onboarding failure;
- traversal/symlink profile-root rejection and external-path anonymization.

### Corrective architecture

- One runtime is shared per `(profile_root, headless)` and owns the sole
  persistent Chromium context at `cortex-bridge-ui`.
- Logical chat, mission, diagnostics and onboarding sessions use isolated pages
  in that context, with an eight-page LRU bound and a short bounded idle
  shutdown window.
- Admission, page release and the terminal sentinel are serialized under the
  runtime state lock.
- Cross-thread futures are shielded from caller cancellation; worker settlement
  is defensive and every queued call is settled when the worker exits.
- JavaScript evaluation uses an in-page `Promise.race` timeout and remains
  usable after a timeout.
- Playwright failures cross the public driver boundary as `DriverError`, so the
  adapter's fallback and `DELIVERY_UNCERTAIN` rules apply consistently.
- Terminal chat and mission transports release their logical pages; WebBridge
  close is concurrently idempotent.
- Settings validate profile roots both when loaded and when updated. Relative
  traversal and configured symlink roots fail closed; diagnostics redact
  non-home absolute paths.

### GREEN evidence

Focused fix-round suite:

```bash
.venv/bin/python -m unittest tests.test_playwright_driver tests.test_start_local \
  tests.test_chat_settings_api.ChatSettingsApiTestCase.test_10b_onboarding_browser_failure_is_structured_non_2xx \
  tests.test_chat_settings_api.ChatSettingsApiTestCase.test_10c_browser_profile_root_rejects_traversal_and_symlinks \
  tests.test_chat_settings_api.ChatSettingsApiTestCase.test_10d_loaded_invalid_browser_settings_fail_closed_and_external_paths_are_anonymized -v
```

Result: 21 tests passed in 10.972 s.

Fresh full backend regression:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Result: 194 tests passed in 184.856 s. Existing `ResourceWarning` noise remains,
with zero failures/errors.

Frontend:

```bash
npm run typecheck -- --incremental false
npm run lint
```

Result: both exited 0.

Final strict-timeout Playwright rerun:

```bash
.venv/bin/python -m unittest tests.test_playwright_driver -v
```

Result: 17 tests passed in 17.020 s, followed by successful `py_compile` and
`git diff --check`.

## Fix round 2/5 — configuration-boundary compensation

### RED evidence

Two tests were added before production changes:

```bash
.venv/bin/python -m unittest \
  tests.test_chat_settings_api.ChatSettingsApiTestCase.test_10e_onboarding_invalid_persisted_browser_settings_are_structured \
  tests.test_transport_session_isolation.ChatRouteSessionIsolationTest.test_invalid_settings_fail_run_and_release_exact_writer_capacity -v
```

Initial result: 2 failures.

- Invalid persisted browser settings escaped onboarding as an unstructured
  HTTP 500 instead of the documented `BROWSER_LOGIN_FAILED` 503 payload.
- Transport construction failed after writer acquisition but before the chat
  `try/finally`; the run remained `QUEUED` and retained the writer lease.

### Correction

- Onboarding now resolves settings, constructs the driver and opens the login
  page inside one error boundary. Configuration and construction failures use
  the same structured 503 payload as launch failures; when no driver can be
  resolved, `driver` is truthfully reported as `unknown`.
- Chat transport construction now occurs inside the run lifecycle boundary.
  Every post-acquisition failure records `FAILED`, persists the error, releases
  the exact lease and restores normal two-writer capacity.
- The analogous mission-create path was inspected and not changed in round 2:
  acquisition appeared to be followed by a compensating block covering
  persistence and `_build_runtime()`. The existing
  `test_synchronous_binding_failure_fails_mission_and_releases_lease`
  exercised only a SQLite binding failure; it did **not** directly prove
  runtime construction or mission resume. Those distinct boundaries are
  covered in round 3 below.

### GREEN evidence

Focused regression: 2 tests passed in 1.256 s.

Affected API/session/mission suites:

```bash
.venv/bin/python -m unittest tests.test_chat_settings_api \
  tests.test_transport_session_isolation tests.test_missions_api \
  tests.test_write_slots -v
```

Result: 59 tests passed in 56.605 s.

Fresh full backend regression:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Result: 196 tests passed in 188.442 s. Existing `ResourceWarning` noise remains
unchanged, with zero failures/errors.

Targeted `py_compile` and `git diff --check` both exited 0. No frontend source
changed in this round, so frontend checks were not rerun.

## Fix round 3/5 — direct factory proofs and resume compensation

### Three distinct boundaries

The new tests deliberately avoid treating one failure as evidence for another:

1. `test_selected_transport_constructor_failure_is_persisted_and_releases_writer`
   injects a direct chat transport-constructor failure after acquisition. It
   asserts no task exception escapes, in-memory and JSON-persisted `FAILED`
   state/error match, the exact observed lease is released, and capacity again
   admits two writers while refusing a third.
2. `test_runtime_construction_failure_fails_creation_and_releases_lease`
   injects `_build_runtime()` failure after mission persistence/binding. It
   asserts structured HTTP 503, persisted mission `FAILED` detail, exact lease
   release and recovered capacity.
3. `test_resume_transport_construction_failure_is_terminal_and_releases_restored_lease`
   restores a durable paused-mission lease, then injects transport construction
   failure during resume. It asserts structured HTTP 503, persisted terminal
   `FAILED` detail, runtime/lease cleanup and recovered capacity.

### RED/GREEN evidence

Initial focused result:

- direct chat constructor proof: passed immediately, confirming the round 2
  lifecycle boundary also covers arbitrary selected factories;
- mission create: failed because the HTTP/persisted detail incorrectly called
  every runtime failure a “binding” failure;
- mission resume: escaped a raw `RuntimeError` and retained ownership.

After the first resume compensation, the resume test correctly stopped the raw
exception but exposed a state-machine issue: `_fail_mission()` converted
`PAUSED` to `CANCELLED`, not `FAILED`. The final path explicitly resumes into
`TRANSPORT_ERROR`, then transitions to `FAILED`, closes any constructed
runtime, releases the exact restored lease and removes ownership maps.

Final focused command:

```bash
.venv/bin/python -m unittest \
  tests.test_transport_session_isolation.ChatRouteSessionIsolationTest.test_selected_transport_constructor_failure_is_persisted_and_releases_writer \
  tests.test_transport_session_isolation.MissionRouteSessionIsolationTest.test_runtime_construction_failure_fails_creation_and_releases_lease \
  tests.test_transport_session_isolation.MissionRouteSessionIsolationTest.test_resume_transport_construction_failure_is_terminal_and_releases_restored_lease -v
```

Result: 3 tests passed in 0.031 s.

Affected chat/mission/session/settings suites:

```bash
.venv/bin/python -m unittest tests.test_chat_settings_api \
  tests.test_transport_session_isolation tests.test_missions_api \
  tests.test_write_slots -v
```

Result: 62 tests passed in 52.337 s.

Fresh full backend regression:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Result: 199 tests passed in 185.761 s. Existing `ResourceWarning` noise remains,
with zero failures/errors.

Targeted `py_compile` and `git diff --check` both exited 0. No frontend source
changed in this round, so frontend checks were not rerun.

## Fix round 4/5 — post-construction resume cleanup proof

### Characterization

`test_resume_attach_failure_closes_inserted_runtime_and_clears_all_ownership`
injects failure from `transport.attach()` after `_build_runtime()` has
successfully constructed and inserted the runtime. During `attach()`, the test
observes the live `_runtimes`, `_mission_leases` and `_mission_write_urls`
entries, including the exact restored lease and conversation lock.

The existing production compensation passed this direct characterization
without modification. The regression asserts:

- structured HTTP 503 detail;
- legal persisted terminal `FAILED` state and exact failure detail;
- one awaited transport close and a quiescent, closed runtime;
- release of the exact restored lease;
- removal from all three ownership maps;
- empty active-lease state and restored capacity for exactly two writers.

Focused command:

```bash
.venv/bin/python -m unittest \
  tests.test_transport_session_isolation.MissionRouteSessionIsolationTest.test_resume_attach_failure_closes_inserted_runtime_and_clears_all_ownership -v
```

Result: 1 test passed in 0.022 s.

Affected mission/session suites:

```bash
.venv/bin/python -m unittest tests.test_transport_session_isolation \
  tests.test_missions_api tests.test_write_slots -v
```

Result: 48 tests passed in 45.191 s.

Fresh full backend regression:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Result: 200 tests passed in 188.209 s. Existing `ResourceWarning` noise remains,
with zero failures/errors. No frontend or production source changed in this
round, so frontend checks were not rerun.
