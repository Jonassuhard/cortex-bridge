# Task 1 report: frontend test harness

Date: 2026-07-26  
Scope: frontend test dependencies, Vitest/jsdom setup, one semantic smoke test,
Playwright/axe tooling, and deterministic local browser fixtures.

## Installed tooling

- Vitest `4.1.10` with V8 coverage
- jsdom `29.1.1`
- Testing Library React `16.3.2`
- Testing Library User Event `14.6.1`
- jest-dom `7.0.0`
- Playwright Test `1.62.0`
- Chromium `151.0.7922.34`, Playwright build `1234`
- axe-core and `@axe-core/playwright` `4.12.1`

Chromium was installed with the package-local command:

```text
cd frontend
npx playwright install chromium
```

## TDD evidence

The smoke test renders the real `CortexApp`. The mutation it protects against
is removing the accessible name from the main conversation region.

### RED

```text
cd frontend
npm test -- components/CortexApp.test.tsx
```

Result: exit `1`; one test failed for the expected contract violation:

```text
Unable to find an accessible element with the role "main" and name `/conversation/i`
main: Name ""
Test Files  1 failed (1)
Tests       1 failed (1)
```

The initial jsdom run also exposed its missing `Element.scrollTo` browser API.
A setup-only polyfill removed that unrelated harness error, after which RED was
re-run and contained only the expected assertion failure.

### GREEN

The minimum production change was an accessible French label on the existing
`main` element: `Conversation principale`.

```text
cd frontend
npm test -- components/CortexApp.test.tsx
```

Result: exit `0`; one test passed, zero errors.

## Deterministic browser fixture

- UI server: `http://127.0.0.1:3420`
- intercepted API origin: `http://127.0.0.1:8420`
- every non-loopback request is aborted
- account: `Demo User`
- project: `Atlas`
- conversations: `Release checklist`, `Local site prototype`, `Research`
- workspace: `/tmp/cortex-demo-workspace`
- responses and timestamps are fixed; no live service or external site is used

A temporary Playwright smoke spec was used to exercise the committed fixture,
then removed so Task 7 retains ownership of browser scenarios:

```text
cd frontend
npx playwright test e2e/task1-smoke.spec.ts
```

Result: exit `0`; one Chromium test passed in 3.6 seconds. It verified the named
main region and the `Release checklist` fixture content through the local dev
server.

Browser traces, screenshots, and video are disabled in the base configuration.
The current pre-Task-3 sidebar still contains a legacy non-synthetic account
row, so retaining browser artifacts would not yet satisfy the privacy gate.
Playwright output is directed to the operating-system temporary directory.

## Verification

```text
cd frontend
npm test
```

Result: exit `0`; one Vitest file and one test passed.

```text
cd frontend
npm run test:coverage
```

Result: exit `0`; one test passed. Initial harness coverage was 30.02% statements,
18.83% branches, 27.49% functions, and 33.29% lines. Generated coverage output
was removed after verification.

```text
cd frontend
npm run typecheck
npm run lint
```

Result: both exited `0`; zero TypeScript or ESLint errors. The pre-existing Node
suite was also run before implementation: 18 tests passed, zero failed.

No frontend build or static export was run. Generated `frontend/out/**` and
`frontend/tsconfig.tsbuildinfo` changes were not staged or modified intentionally.

## Dependency audit

`npm audit --json` was run repeatedly, including with a clean temporary cache
and npm `11.18.0`. The registry audit endpoint returned a gzip stream that the
CLI treated as invalid JSON:

```text
audit endpoint returned an error
Unexpected token '\u001f' ... is not valid JSON
```

Audit result: `[UNCLEAR]`; no vulnerability counts were available. No dependency
upgrade, forced remediation, or lockfile rewrite was applied in response.

## Self-review and concerns

- The component test uses the real application and asserts user-visible
  semantics, not an implementation mock.
- The fixture allows only two explicit loopback origins and contains no live
  conversation, external URL, personal path, or personal identity.
- `test:e2e` and `test:a11y` are wired but have no committed specs in Task 1;
  Task 7 owns those suites. The temporary local fixture smoke passed.
- Traces and screenshots must remain disabled until the legacy account identity
  is removed or replaced by a synthetic fixture in the later navigation task.
- The only unresolved Task 1 concern is the unavailable npm audit summary.
