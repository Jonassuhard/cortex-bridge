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

## Fix round 1

Date: 2026-07-26
Starting commit: `38403edaf9dcf414d1daae63ab928ba2345c4249`

### Combined unit and runtime contract

The original `npm test` ran Vitest only. A temporary deliberately failing
`node:test` case proved the gap:

- old `npm test`: exit `0`, two Vitest tests passed while the runtime failure
  was ignored;
- after adding `test:unit`, `test:runtime`, and chaining them from `test`:
  exit `1`, the temporary runtime failure was reported after 18 runtime passes;
- after removing the temporary case: exit `0`, two Vitest tests and all 18
  runtime tests passed.

`test:coverage` now runs V8 coverage for the Vitest suite and then runs the
runtime suite explicitly. Runtime tests are not misrepresented as V8-covered
Vitest tests. Coverage includes application source only and excludes tests,
generated output, and `.next` artifacts.

### Committed browser coverage

Two browser specs now import the deterministic fixture:

- `e2e/smoke.spec.ts` verifies the named main region, synthetic conversation
  data, and loopback page origin;
- `e2e/accessibility.spec.ts` is tagged `@a11y`, verifies the named main
  landmark, and runs the axe `landmark-one-main` rule.

All fixture requests remain limited to `127.0.0.1:3420` and
`127.0.0.1:8420`. Every other origin is aborted. Traces, screenshots, and
videos remain disabled.

```text
npm run test:e2e   # 2 passed
npm run test:a11y  # 1 passed
```

### Node 20 dependency correction

The harness is pinned to versions whose published engines support Node 20:

- Vitest and coverage `3.2.4`: `^18.0.0 || ^20.0.0 || >=22.0.0`
- Vite `6.4.1`: `^18.0.0 || ^20.0.0 || >=22.0.0`
- jsdom `26.1.0`: `>=18`
- jest-dom `6.9.1`: `>=14`
- Testing Library React `16.3.0`: `>=18`
- Testing Library User Event `14.6.1`: `>=12`
- Playwright `1.62.0`: `>=20`
- tsx `4.20.6`: `>=18.0.0`
- axe-core and its Playwright integration `4.12.1`

The package declares `engines.node: >=20.9.0`, matching Next `16.2.9` rather
than claiming compatibility with every earlier Node 20 release. Vite is pinned directly so the
Vitest dependency range cannot resolve back to Vite 8 and its Node 20.19
minimum.

The historical runtime command used `--experimental-strip-types`, which does
not exist in early Node 20. It now uses `tsx --test`. Declaring the package as
ESM keeps `.mts`, `.ts`, and the existing VM-loaded component checks on one
module model.

Compatibility proof used the minimum Node 20 revision declared by the current
Next dependency:

```text
Node 20.9.0 + npm 10.9.4: npm test
```

Result: two Vitest tests and 18 runtime tests passed. The same combined command
also passed under Node `20.19.5`.

### Privacy correction

The sidebar now renders the neutral labels `CL`, `Compte local`, and
`Session locale`. A component test failed before the change because the
neutral identity was absent, then passed after the three-label replacement.

A case-insensitive exact-name repository scan returned no matches in committed
frontend source or the synthetic fixture. The broader fixture scan also found
no personal home path, unrelated project name, or non-loopback URL.

### Lockfile review

The lockfile was regenerated from the pre-harness `ecd28e8` lock plus the
corrected package manifest, rather than accepting npm's first-round full
normalization.

- existing package version changes: `0`;
- removed package entries: only `@vercel/analytics`;
- `@vercel/analytics` was absent from direct dependencies and had no frontend
  source import, so it was an orphaned lock entry rather than a removed product
  dependency;
- `nanoid` remains `3.3.12`;
- `@napi-rs/wasm-runtime` remains `1.1.5`;
- `@tybys/wasm-util` remains `0.10.2`;
- platform-specific WASM entries were preserved at their historical versions.

`npm ci --ignore-scripts --no-audit --no-fund` completed from the regenerated
lock. npm emitted deprecation notices for transitive `glob@10.5.0` and
`whatwg-encoding@3.1.1`; neither is a direct production dependency.

### Fresh verification

```text
npm test
```

Result: exit `0`; two Vitest tests and 18 runtime tests passed.

```text
npm run test:coverage
```

Result: exit `0`; two Vitest tests plus 18 runtime tests passed. Application
coverage: 48.23% statements/lines, 38.21% branches, and 29.41% functions.

```text
npm run test:e2e
npm run test:a11y
npm run typecheck
npm run lint
```

Results: E2E `2/2`, a11y `1/1`, TypeScript exit `0`, ESLint exit `0`.

No frontend build or export was run. Generated `frontend/out/**` and
`frontend/tsconfig.tsbuildinfo` remain outside the staged scope.

### Audit status and concerns

`npm audit --json --registry=https://registry.npmjs.org` was rerun with an
explicit clean cache. The official endpoint again returned gzip bytes that npm
treated as invalid JSON (`Unexpected token '\u001f'`). Audit status remains
`[UNCLEAR]`; no vulnerability count or safety claim is available, and no
forced remediation was applied.

Open concerns are limited to the unavailable registry audit result and the two
transitive deprecation notices reported during clean installation.

## Fix round 2

Date: 2026-07-26
Starting commit: `56bbc715b9921845b5299c4a145d2420e32d47fa`

### Node minimum aligned with Next

The package and lockfile now declare `engines.node: >=20.9.0`. This is the
actual minimum published by Next `16.2.9`; the harness no longer implies that
Node `20.0.0` through `20.8.x` are supported.

Compatibility was rerun with Node `20.9.0` and npm `10.9.4`. The complete
`npm test` command passed two Vitest component tests, 18 historical runtime
tests, and the new privacy test.

### Frontend-wide privacy gate

A new Node test enumerates tracked and non-ignored frontend source, fixture,
and configuration files through `git ls-files`. It scans CSS, HTML, JSON,
Markdown, MJS, MTS, TS, and TSX while explicitly excluding generated output,
`.next`, dependency directories, coverage, browser reports, caches, the lockfile,
and `tsconfig.tsbuildinfo`.

The scanner rejects encoded markers for personal names, personal workspaces,
mounted personal volumes, unrelated project names, and personal macOS home or
volume paths. Encoding the markers prevents the privacy test from matching its
own source.

RED result:

- one privacy test failed;
- 22 findings were reported across seven frontend files;
- findings covered the README, CSS, application components, development
  fixtures, and standalone fallback.

GREEN result:

- neutral labels replace every finding;
- all demo storage and workspace paths use
  `/tmp/cortex-demo-workspace` or its `models` subdirectory;
- the fallback storage state keeps the same behavior under a neutral internal
  identifier;
- the privacy test passes with zero findings.

The sidebar component test now asserts `CL`, `Compte local`, and
`Session locale`. It also reconstructs the three former labels at runtime and
asserts that none is rendered, without embedding banned personal strings in
the committed test source.

`test:runtime` explicitly runs both `lib/runtimeTruth.test.mts` and
`test/privacy.test.mts`, so the privacy gate is part of `npm test` and
`test:coverage`.

### fsevents lockfile accounting

The previous statement of zero changes referred only to versions that already
existed in the pre-harness lock; it did not mean that the test harness added no
packages.

`fsevents@2.3.2` is an optional macOS transitive dependency with `os: darwin`.
The installed graph proves two paths:

- `@playwright/test` -> `playwright` -> optional `fsevents@2.3.2`;
- Vitest/Vite -> Rollup -> optional `fsevents@~2.3.2`.

The lock also contains development-optional `fsevents@2.3.3` entries beneath
Vite and tsx. These entries are required by the selected tooling's declared
cross-platform graph and were not removed. Round 2 changes no fsevents version;
the only lockfile change is the root Node engine floor.

### Fresh verification

```text
npm test
```

Result: exit `0`; two Vitest tests and 19 runtime tests passed.

```text
npm run test:coverage
```

Result: exit `0`; the same 21 tests passed. Application coverage remained
48.23% statements/lines, 38.21% branches, and 29.41% functions.

```text
npm run test:e2e
npm run test:a11y
npm run typecheck
npm run lint
```

Results: E2E `2/2`, a11y `1/1`, TypeScript exit `0`, ESLint exit `0`.

The targeted case-insensitive privacy grep returned zero source, fixture, or
configuration matches outside the explicit generated/dependency exclusions.
No frontend build or export was run. Existing `frontend/out/**` and
`frontend/tsconfig.tsbuildinfo` changes remain outside the scoped commit.

### Audit status

The frontend audit was rerun from `frontend/` against the explicit official
registry with a clean dedicated cache. The endpoint again returned a gzip
stream that npm treated as invalid JSON (`Unexpected token '\u001f'`), exit
`1`. Audit status remains `[UNCLEAR]`; no forced remediation or safety claim
was applied.

## Fix round 3

Date: 2026-07-26
Starting commit: `c5262b77d3c86c876c942bb942519f4939816300`

### Non-reversible privacy fingerprints

The round 2 gate still embedded reversible byte-array reconstructions of the
values it was meant to ban. Those reconstructions and the corresponding
component-test assertions have been removed. The gate now commits only each
marker's SHA-256 digest, normalized Unicode code-point length, and a generic
finding category. It neither stores nor reconstructs the original marker.

The scanner normalizes input with NFKC and locale-stable lowercase conversion.
Before hashing candidate substrings, it decodes JavaScript Unicode escapes,
JavaScript hexadecimal escapes, and contiguous URL percent escapes. Synthetic
tests prove detection of raw, escaped, URL-encoded, JavaScript, and JSX forms.

### Anti-obfuscation gate

The source scan also rejects common dynamic string-assembly mechanisms:

- `String.fromCharCode` and `String.fromCodePoint`;
- `atob`;
- `Buffer.from` with `base64` or `hex` encoding;
- direct literal `split(...).join(...)` chains;
- literal arrays joined into strings.

The privacy test itself is excluded only from this anti-obfuscation rule so it
can define detector examples and decode literal escapes. It remains included in
the raw and fingerprint scans, preventing the test file from hiding a banned
marker. The sidebar component test now asserts neutral labels only.

The exact scanned extensions are `.cjs`, `.config`, `.css`, `.html`, `.js`,
`.json`, `.jsx`, `.md`, `.mjs`, `.mts`, `.toml`, `.ts`, `.tsx`, `.txt`,
`.yaml`, and `.yml`. Exact file exclusions are `package-lock.json` and
`tsconfig.tsbuildinfo`; directory exclusions are `.next/`, `coverage/`,
`node_modules/`, `out/`, `playwright-report/`, and `test-results/`.

### TDD evidence

First RED:

- the raw JavaScript and JavaScript/JSX extension cases passed;
- escaped and URL-encoded forms were not detected;
- `atob`, `Buffer.from`, and join-based assembly were not rejected;
- the real repository scan exposed the component test's dynamic reconstruction.

Second RED, after implementing normalization and anti-obfuscation:

- all synthetic detector cases passed;
- only the repository scan still failed on the sidebar test reconstruction.

GREEN, after reducing the component test to neutral labels:

- six privacy runtime tests passed;
- the sidebar component test passed;
- the real frontend source scan returned zero findings.

### Fresh verification

```text
npm test
```

Result: exit `0`; two Vitest tests and 24 runtime tests passed.

```text
npm run test:coverage
```

Result: exit `0`; the same 26 tests passed. Application coverage remained
48.23% statements/lines, 38.21% branches, and 29.41% functions.

```text
npm run test:e2e
npm run test:a11y
npm run typecheck
npm run lint
```

Results: E2E `2/2`, a11y `1/1`, TypeScript exit `0`, ESLint exit `0`.

The full `npm test` command also passed under Node `20.9.0` with npm `10.9.4`:
two Vitest tests and 24 runtime tests. Package and lockfile engine declarations
remain aligned at `>=20.9.0`; the optional Darwin `fsevents@2.3.2` metadata is
unchanged.

No frontend build or export was run. Generated `frontend/out/**` and
`frontend/tsconfig.tsbuildinfo` remain outside the scoped commit.

### Audit status

The frontend audit was rerun against the explicit official registry with a new
dedicated cache. The endpoint again returned gzip bytes that npm treated as
invalid JSON (`Unexpected token '\u001f'`), exit `1`. Audit status remains
`[UNCLEAR]`; no vulnerability count, safety claim, or forced remediation was
applied.
