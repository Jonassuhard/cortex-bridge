# Frontend dependency security remediation

Date: 2026-07-26
Scope: `frontend/` dependency graph and lint toolchain
Baseline commit: `e3f7a8c8146c3c4ea21a1251ae8b3c51e0b19cbb`

## Result

- `npm audit --json`: **0** vulnerabilities.
- `npm audit --omit=dev --json`: **0** vulnerabilities.
- The full graph fell from 632 to 296 packages.
- The supported runtime contract is Node `^20.19.0 || >=22.12.0`; every final gate below ran on exactly Node `20.19.0` with npm `11.18.0`.
- npm `11.18.0` is enforced by exact `engines.npm` and error-level `devEngines`, with `engine-strict=true`. `packageManager` supplies Corepack metadata; it does not enforce the version by itself.

## Fix round 1

- Added `.node-version`, `.npmrc`, exact README/Corepack commands, and hard Node/npm contracts. Node `20.19.0` with npm `10.9.2` now exits `EBADDEVENGINES` before creating `node_modules`; Node `20.19.0` with npm `11.18.0` completes a clean install.
- Enabled npm's `strict-allow-scripts` gate. The exact positive install reports `No packages with unreviewed install scripts.` A mutation that removed the Sharp override was independently rejected because `sharp@0.34.5` had an unapproved install script.
- Added a committed `lint:contract` gate with six neutral temporary fixtures and exact diagnostic-code assertions for conditional hooks, TypeScript correctness, bad imports, accessibility, raw Next images, and focused Vitest tests. Its `finally` cleanup is also asserted.
- Removed global accessibility disables. Valid custom semantics now use local, reasoned Oxlint suppressions; the composer tabs, page heading, status output, and SVG accessible name were fixed in markup.
- Expanded Playwright/Axe from one selected rule to the complete Axe ruleset. The first full run caught `aria-required-children` and `page-has-heading-one`; the corrected UI passes with zero violations.
- Deleted `eslint.config.mjs`. The privacy gate now skips tracked paths that were intentionally deleted and still scans the remaining committed/untracked source set.
- Kept the scoped Sharp override because the reviewed [GHSA-f88m-g3jw-g9cj](https://github.com/advisories/GHSA-f88m-g3jw-g9cj), published in 2026, affects Sharp `<0.35.0` through libvips vulnerabilities CVE-2026-33327, CVE-2026-33328, CVE-2026-35590, and CVE-2026-35591. A direct test imports Next's real `optimizeImage` module, verifies Sharp `0.35.0`, and converts/resizes PNG, JPEG, and WebP buffers. Without the override, Next resolves Sharp `0.34.5` and the regression test fails.

## Security-driven red/green evidence

### Red baseline

The preliminary non-major update was captured before further manifest edits:

| Audit | Info | Low | Moderate | High | Critical | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full | 0 | 0 | 0 | 12 | 0 | 12 |
| Production (`--omit=dev`) | 0 | 0 | 0 | 0 | 0 | 0 |

The vulnerable development paths were:

- ESLint 9 -> `@eslint/config-array` / `@eslint/eslintrc` -> `minimatch@3` -> vulnerable `brace-expansion`.
- `@vitest/coverage-v8@3` -> `test-exclude@7` -> `glob@10` / vulnerable `minimatch`.

The raw evidence was saved during the run as:

- `/tmp/cortex-bridge-frontend-audit-before.json`
- `/tmp/cortex-bridge-frontend-audit-prod-before.json`
- `/tmp/cortex-bridge-frontend-dependency-graph-before.json`

### Rejected partial remediation

ESLint `10.8.0` and Vitest/Coverage `4.1.10` reduced the full audit from 12 to 6 high findings, but could not make the ESLint graph sound:

- `eslint-config-next@16.2.12` still installs `eslint-plugin-import@2.32.0`, `eslint-plugin-jsx-a11y@6.10.2`, and `eslint-plugin-react@7.37.5`.
- Those stable plugins still declare ESLint peers ending at 9 and still depend on `minimatch@3`.
- `npm ls` therefore marked ESLint 10 invalid, while audit still reported six high findings.
- Next stable and canary package metadata exposed the same plugin set.

The following were explicitly rejected:

- npm's bogus `eslint-config-next@12.0.4` downgrade suggestion;
- a major `minimatch@10` override, because its CommonJS export is an object while these plugins call the v3 function API;
- a Next prerelease solely to obtain a newer Sharp range.

### Green remediation

ESLint and `eslint-config-next` were replaced with `oxlint@1.75.0`. The committed `.oxlintrc.json` enables built-in ESLint, TypeScript, import, React, JSX accessibility, Next.js, Vitest, Unicorn, and Oxc rules, with correctness diagnostics treated as errors. Hooks, unescaped entities, TypeScript correctness, import validity, accessibility, raw Next images, and focused Vitest tests are explicit error-level rules. `npm run lint` is deterministic, warning-intolerant, and includes `lint:contract`.

The lint contract writes fixtures under a temporary frontend directory, invokes the installed Oxlint binary with the committed config, and asserts these exact codes:

- `react-hooks(rules-of-hooks)`
- `typescript(no-duplicate-enum-values)`
- `import(default)`
- `jsx-a11y(anchor-has-content)`
- `next(no-img-element)`
- `vitest(no-focused-tests)`

There are no global accessibility rule disables. The few valid custom widgets that cannot use the suggested native tag have adjacent, reasoned suppressions. Full Axe analysis and TypeScript remain independent gates. The obsolete `eslint.config.mjs` compatibility stub was deleted; the privacy test intentionally tolerates tracked deletions.

## Dependency diff

| Package / contract | Before (`e3f7a8c`) | After |
| --- | --- | --- |
| Node engine | `>=20.9.0` | `^20.19.0 || >=22.12.0` |
| Package manager | unspecified | `npm@11.18.0` |
| Next | `16.2.9` | `16.2.12` |
| React / React DOM | `19.2.4` | `19.2.4` |
| ESLint | `^9` | removed |
| eslint-config-next | `16.2.9` | removed |
| Oxlint | absent | `1.75.0` |
| Vite | `6.4.1` | `6.4.3` |
| Vitest | `3.2.4` | `4.1.10` |
| Vitest V8 coverage | `3.2.4` | `4.1.10` |
| Tailwind PostCSS | `^4` | `4.3.3` |
| Resolved Tailwind | prior lock | `4.3.3` |
| Resolved PostCSS | prior lock | `8.5.23` |
| Resolved Sharp under Next | `0.34.x` | `0.35.0` |

Overrides are intentionally narrow:

- `postcss@8.5.23` keeps the shared PostCSS graph on the audited patch.
- `next > sharp@0.35.0` is scoped to Next. Next `16.2.12` declares `sharp ^0.34.5`, which cannot select the patched `0.35.x` line. The override is tied to the 2026 libvips advisory above and exercised through Next's actual image optimizer, not only by requiring Sharp directly.

npm install scripts are explicit: reviewed `esbuild@0.25.12` is allowed, while optional `fsevents` build scripts are denied. A clean install reports no unreviewed scripts.

## Final verification

All commands ran after the final clean install under Node `20.19.0` and npm `11.18.0`.

| Gate | Result |
| --- | --- |
| `npm ci --no-audit --no-fund` | exit 0; 176 packages installed |
| `npm install-scripts ls` | no unreviewed install scripts |
| Node `20.19.0` + npm `10.9.2` negative contract | exit 1 `EBADDEVENGINES`; no `node_modules` created |
| Node `20.19.0` + npm `11.18.0` positive contract | exit 0; clean install and install-script review passed |
| `npm audit --json` | 0 total |
| `npm audit --omit=dev --json` | 0 total |
| `npm ls --all --json` | exit 0; `problems=[]` |
| lock consistency | SHA-256 unchanged after `npm install --package-lock-only` |
| `npm test` | 2 Vitest tests + 32 Node/TAP tests passed |
| `npm run test:coverage` | passed; 30.03% statements, 19.5% branches, 27.64% functions, 33.21% lines |
| `npm run lint` | passed, including six-family fixture contract |
| Sharp optimizer integration | Sharp `0.35.0`; PNG/JPEG/WebP conversions and resize passed |
| Sharp override mutation | resolved `0.34.5`; optimizer regression test failed as required |
| `npm run typecheck` | passed |
| `npm run build` | Next `16.2.12` compiled; 3 static pages generated |
| `npm run test:e2e` | 2/2 passed |
| `npm run test:a11y` | 1/1 passed with the complete Axe ruleset |
| privacy gate only | 10/10 passed |
| source-only Gitleaks scan | no leaks found |
| external network in browser tests | blocked; loopback origins only |

Additional compatibility proof:

- compiled CSS: `out/_next/static/chunks/1ajr4ln32s4c4.css`, 57,379 bytes, contains `.cortex-app`, and no unresolved Tailwind import;
- Sharp runtime: `0.35.0`, libvips `8.18.3`;
- resolved toolchain: Oxlint `1.75.0`, Vite `6.4.3`, Vitest/Coverage `4.1.10`, Tailwind/PostCSS `4.3.3`/`8.5.23`.

## Compatibility notes and rollback

- Oxlint is not a byte-for-byte implementation of `eslint-config-next`; it replaces the vulnerable plugin graph with native TS/React/a11y/Next/Vitest correctness rules. The six-family lint contract and retained typecheck/full-Axe gates cover the intended contract.
- npm `11.18.0` is part of the reproducibility contract. `packageManager` lets Corepack select it, while exact `engines`, error-level `devEngines`, and `.npmrc` provide the actual install-time rejection. npm `11.11.1` previously installed stale optional Sharp nodes under the scoped override; `11.18.0` resolves the graph with `problems=[]`.
- The clean install still prints the upstream `whatwg-encoding@3.1.1` deprecation notice. It is not an audit finding.
- Coverage percentages are unchanged in intent and remain below comprehensive application coverage; no threshold existed before this remediation.

Rollback is one commit: revert the dependency-security commit, then run `npm ci` using the package manager declared by the restored manifest. This restores the previous ESLint config and dependency graph; it also restores the 12-high development audit baseline, so rollback is for compatibility diagnosis only, not release.
