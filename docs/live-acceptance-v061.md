# 0.6.1 real-interface acceptance

Date: 2026-09-10. Base source: dd4ad55, followed by uncommitted startup and
detector corrections. **Not release-ready. No completed multi-model mission.**

## Fixed scenarios, not benchmark claims

| Scenario | Input interface | Requested artifact checks | Repetitions |
| --- | --- | --- | --- |
| G: synthetic file organization | Cortex Atelier only | Three originals preserved, classified copies, inventory with matching sizes and SHA-256 | Two distinct observed planner models |
| T: Orbital Notes mini-site | Cortex terminal only | HTML/CSS/JS/README, increment/reset interaction, actual passing Node test, no external requests | At least three runs across two distinct observed planner models |

The tests use isolated synthetic workspaces. Setup and diagnostic reads must
not implement the mission artifacts. No prompt is typed directly in ChatGPT.
The current mission executor is deterministic; planner diversity must not be
reported as executor-model diversity. Freebuff is not an integrated executor.

## Actual observations

| Check | Verdict | Observed evidence / limitation |
| --- | --- | --- |
| Terminal starts offline | PASS | CORTEX banner, unavailable backend message and interactive prompt |
| Terminal `/demarrer`, first attempt | FAIL | Launcher selected another Python; FastAPI import failed |
| Terminal `/demarrer`, after correction | PASS | Same command in a restarted Cortex terminal started the isolated candidate on loopback |
| Terminal regression suite | PASS | 73 tests in 10.815 s using the project virtualenv |
| Full backend suite, initial run | FAIL | 708 tests, three uninstall failures: fixture tests collided with the active QA listener |
| Installer fixture correction | PASS | Tests now use an allocated loopback port; original three cases and all 37 installer tests pass while the QA app remains running; no production guard changed |
| Full backend suite, after corrections | PASS | 710 tests in 165.449 s; includes terminal/driver/onboarding/installer tests, not additional independent cases |
| Cortex GUI opens | PASS | Real Chrome, candidate static UI and isolated backend |
| Extension pairing | PASS, real replay | Candidate extension paired in the same Chrome window; backend reported protocol version 2 compatible |
| GUI connection check | PASS, real replay | Classic `/c/...` ChatGPT tab exposed a composer; the probe returned no blocker |
| GUI text delivery | PASS, one real check | Cortex sent `Réponds uniquement CORTEX-LIVE-01`; the UI showed pending, then confirmed delivery and `CORTEX-LIVE-01` in 9.6 s |
| GUI screenshot delivery | PASS, one real check | The Cortex capture button produced run `8fb810edbea04d32b6889045563d319f`, state `COMPLETED`, attachment `cortex-screenshot-2a2313ca.png`; Cortex showed `Réponse terminée` and the bound ChatGPT tab exposed the new image message and its response |
| Planner model discovery | UNCLEAR | Terminal showed only “current visible model”; no two model identities established |
| Scenario G | UNCLEAR, not executed | Composer disabled during connection preflight |
| Scenario T | UNCLEAR, not executed | No ready conversation or verified planner selection |
| Freebuff participation | UNCLEAR, no mission test | GLM 5.3 Flash session opened; capability inquiry only, interrupted without running Cortex |
| Fresh macOS installation | UNCLEAR, not executed | An isolated runtime on an existing Mac is not a fresh OS/account |

The screenshot replay initially failed because the macOS AX helper interpreted
ChatGPT's French empty-composer value (`Demander à ChatGPT`) as user text. The
fix is deliberately narrow: native discovery stays scoped to the focused
ChatGPT web area, the passive image group remains geometry/visibility checked,
and only known localized empty-composer labels are treated as empty. The
focused helper, factory/static checks (9 tests) and Swift permission check pass.
The three earlier failed screenshot runs remain historical failures; they are
not rewritten as passes.

The earlier GUI rate-limit screenshot remains historical diagnostic evidence. It
documents Cortex's message, not a verified provider quota. The later replay used
the classic conversation route after reloading the paired extension; no limit,
challenge or login screen was bypassed.

The first detector correction passed 135 extension fixtures and 10 onboarding
tests. Independent review then found missing immediate handling of `ui_blocker`
and explicit non-chat routes. Follow-up corrections passed 138 extension tests,
40 Chrome-driver tests and 10 onboarding tests. They preserve the classic new
chat page and reject explicit Settings/Work surfaces. This is fixture evidence,
not a successful replay in the user's Chrome. Browser
automation cannot access extension management in this environment. Loading or
reloading the candidate extension requires a manual user action; no alternative
automation path is used to bypass that restriction.

Documentation checks: 128 link checks passed, including all 48 external URLs.
The public-tree privacy scan passed on 409 files and 90 images. Gitleaks found
no secrets in the current tracked diff or this new report. The mission diagram
was regenerated and visually inspected; no new model benchmark was invented.
Independent read-only review accepted the final connection and installer
corrections. A SQLite ResourceWarning appeared in the full passing run; no claim
of warning-free execution is made. The release manifest validator still fails
because the 0.6.1 live/installation evidence manifest is absent.

One worker run using system Python timed out in the PTY Ctrl-C test. A fresh
project-virtualenv run passed all 12 CLI tests, followed by all 73 terminal
tests. The earlier timeout is not erased or labelled pre-existing without proof.

## Remaining release evidence

Unresolved: replay the corrected extension in the actual browser, obtain a
ready classic ChatGPT conversation, execute the scenarios with observed model
identities and independently verified artifacts, complete live conversation
isolation/attachment gates and the clean installation lifecycle, then seal
evidence against the final source commit. Do not mark READY or merge on the
basis of this preflight report.
