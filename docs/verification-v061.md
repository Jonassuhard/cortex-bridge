# 0.6.1 candidate verification

Checked on 2026-09-10. **Not release-ready.** This document distinguishes
source verification from installation, live provider acceptance and publication.

Subsequent real-interface preflight and its failures are recorded separately in
[live acceptance](live-acceptance-v061.md). Earlier green fixtures must not be
interpreted as completed real missions.

## Current execution addendum (2026-09-10)

The candidate now includes the full-screen terminal slice described in
`docs/PLAN_WEB_TUI_LUNA.md`:

| Check | Result | Evidence and limit |
| --- | --- | --- |
| Terminal/TUI focused slice | PASS, 81 tests | Textual headless smoke, CLI dispatch and PTY compatibility against synthetic HTTP fixtures |
| Real `cortex` launch and quit | PASS | Fresh isolated `CORTEX_HOME`; full-screen UI rendered, `Ctrl-Q` returned exit code 0 and left no owned backend process running |
| Complete Python suite | PASS, 724 tests in 198.742 s after the synchronized PTY acceptance fix | Local isolated fixtures; no signed-in ChatGPT delivery |
| Frontend unit/runtime | PASS, 207 unit + 36 runtime/privacy tests | Synthetic React/runtime data |
| Frontend typecheck/lint/build | PASS | `corepack npm@11.18.0`, static Next.js build |
| Frontend browser/a11y | PASS, 26 E2E + 4 accessibility; 1 optional guide skipped | Static synthetic export, no authenticated account |
| TUI wheel packaging | PASS | Disposable wheel install imports `tui` and exposes version 0.6.1 |
| Global command convenience | PASS locally | `~/.local/bin/cortex` points to this candidate only; not a portable release installer |

The TUI intentionally exposes deterministic local tools as the only verified
executor. No model-backed or Freebuff adapter is claimed. A healthy Ollama/model
pair is shown as a candidate until a real run records the executor kind and
model used. Live Chrome pairing, one text round-trip and one screenshot transfer
were observed after this table was written. Arbitrary file delivery, missions,
clean installation lifecycle and main integration remain open gates.

## Historical source baseline (dd4ad55)

The following block is retained for audit history only. It describes the older
published candidate, not the final 0.6.1 candidate or its current evidence.
Use the execution addendum above and `docs/live-acceptance-v061.md` for the
current result and remaining manual gates.

| Check | Result | Scope |
| --- | --- | --- |
| Terminal | PASS, 72 tests | Local client, controller, isolated FastAPI and actual subprocess PTY |
| Full Python suite | PASS, 707 tests in 165.645 s | Final run with isolated CORTEX_HOME; earlier failures documented below |
| Chrome extension | PASS, 130 tests | Node fixtures, not the user's Chrome account |
| Frontend unit | PASS, 207 tests | React component fixtures |
| Runtime/privacy/optimizer | PASS, 36 tests | Includes the overlapping 33-test standard test command |
| Typecheck and lint | PASS | Updated locked frontend environment |
| Static build | PASS | Next.js static export, not a deployment |
| Browser fixtures | PASS, 26; 1 skipped | Responsive, keyboard, accessibility and UI states; optional gallery generation skipped |
| Documentation diagrams | PASS | Three 32-frame, 1000×390 GIFs, static SVGs, visual inspection; controls/reduced motion at 375 and 1000 px |
| npm security audit | PASS | Zero findings after the approved dependency update; previous six findings recorded below |
| Release manifest | PASS, blocked verdict | `docs/verification/v0.6.1.json` validates as `RELEASE_BLOCKED_BY_PROVIDER_TERMS`; clean install remains not run |
| Static runtime layout | PASS | 4 checks from scripts/verify-runtime.py --json |
| Public privacy | PASS | 408 files and 90 images after the rebuilt export; internal notes excluded |
| Documentation links | PASS | 127 offline checks rerun; 48 external links checked in the preceding publication run |
| Secrets | PASS | Three unpublished ancestor commits and staged diff scanned with Gitleaks |
| Live ChatGPT and provider mission | UNCLEAR | Not run for these bytes |
| Clean user installation and native Windows | UNCLEAR | Not run |

The 72 terminal tests are included in the Python suite, not additional cases.
Likewise the 33 Node checks overlap the 36-check runtime command. Do not add
overlapping counts or test durations into a product benchmark.

## Failures found and corrective work

1. The first complete Python run had 2 failures out of 707: installer/doctor
   assertions still expected 0.5.4. They now compare with the canonical VERSION
   file; both original tests pass. Installer behavior was not changed.
2. A second complete run exposed an environment-dependent task/pipeline test.
   It replaced the task file but not the mission store, so unrelated active
   missions could override the expected task view. The test now uses a fresh
   SQLite mission store and restores it after completion. Its original
   assertions pass; no production status logic or readiness threshold changed.
   The complete 707-test suite subsequently passed with an isolated runtime home.
3. Terminal review found missing selected history, missing replies/delivery
   text and stale activity selection. These were corrected before publication
   preparation and covered by the 72-test terminal suite.

## Dependency update and verification

On 2026-09-10 the pre-update audit reproduced six findings: four moderate,
one high and one critical. After explicit local installation approval:

| Package | Before | After |
| --- | --- | --- |
| Next.js | 16.2.12 | 16.3.4 |
| Sharp (Next override) | 0.35.0 | 0.35.4 |
| Vitest and coverage-v8 | 4.1.10 | 4.1.11 |
| baseline-browser-mapping | 2.10.37 | 2.11.21 |

The lock was regenerated with pinned npm 11.18.0, then installed using
`../scripts/npmw ci --ignore-scripts --no-fund`. A fresh
`../scripts/npmw audit --audit-level=low` returned zero findings (exit 0).
No force fix, audit suppression or lowered severity threshold was used.
Original checkout and installed runtime were not modified.

The first runtime test run failed on the old strict Sharp 0.35.0 assertion;
the expected pin was updated to 0.35.4. Typecheck then identified Next's new
required `operationCache` argument; the test passes `undefined` to preserve
default behavior. All three image conversion and dimension assertions remain.
The final 36 runtime tests and typecheck pass with that exact test change.

The 207 unit tests, lint and static build were rerun against the new lock.
Browser fixtures on the rebuilt static export: 26 passed in 29.5 s, one
optional guide-generation test skipped; no authenticated account was used.
Coverage command passed: statements 76.39%, branches 73.75%, functions 71.34%,
lines 80.38% on the configured coverage scope. These are not whole-product
coverage or live-provider results. Python and extension results above belong
to the preceding publication run; those unchanged suites were not rerun for
this frontend-only update. Primary-branch integration remains blocked by the
missing release evidence and live/clean-install acceptance.

## Reproduce

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:console .venv/bin/python -m unittest discover -s tests
node --test chrome-extension/tests/extension.test.mjs
cd frontend
../scripts/npmw run test
../scripts/npmw run test:runtime
../scripts/npmw run typecheck
../scripts/npmw run lint
../scripts/npmw run build
../scripts/npmw run test:e2e
../scripts/npmw audit --audit-level=high
```

The canonical full release gate remains `scripts/test-all.sh`. The v0.6.1
manifest is a truthful technical-preview record, not a READY claim. The
existing backend suite emitted an unclosed-SQLite
ResourceWarning; it was not counted as a passing security or cleanup check.

## Fresh live observation — 2026-09-10

Using the candidate UI in the same Chrome profile as the signed-in ChatGPT tab:

- Extension WebSocket pairing: **PASS** — status returned `paired`, protocol
  version 2 compatible with the backend, no pairing token exposed.
- Classic ChatGPT readiness probe: **PASS** — the selected `chatgpt.com/c/...`
  tab exposed a composer and no Settings/Work blocker.
- Text delivery: **PASS** — the message `Réponds uniquement CORTEX-LIVE-01`
  was entered through Cortex, remained visible as pending, then changed to
  confirmed delivery with the response `CORTEX-LIVE-01` and a measured 9.6 s
  response. This is a single real conversation check, not a provider benchmark.
- Screenshot transfer: **PASS, one real check** — clicking Cortex's capture
  button produced run `8fb810edbea04d32b6889045563d319f` with state
  `COMPLETED` and attachment `cortex-screenshot-2a2313ca.png`. The UI showed
  `Réponse terminée`; the bound ChatGPT tab exposed the new image message and
  its response. The observed UI latency was 7.7 s. This is one signed-in
  browser check, not a throughput benchmark.
- Executor verification: **UNCLEAR** — the runtime reports an available
  Ollama candidate but no completed executor-backed mission, so the UI correctly
  keeps the executor unverified.

The live observation does not authorize a READY verdict. It does not cover
arbitrary file uploads, two-conversation isolation in a signed-in browser,
third-conversation refusal, missions, or a clean-machine lifecycle.

The screenshot gate required a focused macOS AX correction. ChatGPT exposes the
French empty composer as an AX value (`Demander à ChatGPT`) rather than as a
placeholder attribute; the native helper now recognizes only the known empty
labels after normalizing accents. It also scopes controls to the focused
ChatGPT web area and accepts the passive image group only when its frame is
visible. The targeted driver tests (9) and Swift permission check pass. The
earlier failed screenshot runs remain recorded in the live acceptance table.

The fresh `./scripts/test-all.sh` gate also completed all functional, browser,
runtime, privacy and link checks, then stopped at the release-evidence step with
`invalid_json manifest` because `docs/verification/v0.6.1.json` is intentionally
absent. This is a release blocker, not a test failure to be hidden.

## Evidence not produced

No authenticated account, private message, file upload to ChatGPT, provider
benchmark, clean-machine installation, new model benchmark or signed release
was run in this publication task. Diagram animation is explanatory, not
telemetry. Historical executor data is separately described in
[benchmarks](benchmarks.md).

The screenshot gallery from the UI work uses synthetic fixtures. Its older
overview captures predate the geometric card; `celestial.html` demonstrates
that direction separately. A documentation screenshot is not backend proof.

## Publication boundary

Candidate source and documentation may be shared as a development branch with
these failures visible. Merge and release readiness are separate decisions.
Internal handoff notes, local filesystem paths and review diffs are retained
locally but excluded from the public candidate.
