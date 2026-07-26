# Task 4 Report — Distributable Playwright browser driver

## Scope

- Added the `BrowserDriver` protocol and the single runtime factory in
  `transport/browser.py`.
- Added a persistent Playwright Chromium driver in
  `transport/browser_playwright/`.
- Kept WebBridge as the explicit `webbridge` compatibility backend.
- Routed chat, missions, settings, diagnostics and onboarding through injectable
  factories.
- Added the dedicated-profile onboarding action and visible frontend button.
- Added only `playwright>=1.52,<2`; Chromium remains an installer/runtime step.

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
  worker thread per driver. Async callers enqueue serialized operations and
  await `concurrent.futures.Future` instances without blocking the event loop.
- Persistent profiles resolve to `<browser_profile_root>/<session>`.
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

- No test or implementation navigated to `chatgpt.com`; all real browser tests
  used the loopback fixture server.
- No cookies or profiles are copied from another browser.
- Session names are validated before profile-path construction.
- The adapter no longer calls `driver._command` for upload fallback.
- The only dependency addition is Playwright with a minimum known-compatible
  release and a major-version breaking-change cap.
- Generated frontend export files and `tsconfig.tsbuildinfo` are intentionally
  excluded from this task's staging.

## Concerns / follow-up

- A distributable installer still needs to run
  `python -m playwright install chromium`; Python requirements install the
  package, not the browser binary. This worktree installed Chromium and ran the
  browser suite successfully.
- Live ChatGPT DOM compatibility is intentionally not exercised in Task 4.
  The existing local DOM fixture/probe regressions remain the release evidence.

## Final verification

- Required transport suite: 36/36 passed.
- Full Python suite: 180/180 passed.
- Directly affected API/session suite: 54/54 passed.
- Final Playwright contract rerun after removing every external URL literal:
  7/7 passed in 4.604 s.
- Frontend typecheck (`--incremental false`) and ESLint: exit 0.
- `py_compile` for every changed Python source/test: exit 0.
- `git diff --check`: exit 0.
- Staged-file audit and commit are recorded in the handoff.
