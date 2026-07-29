# Testing

## Complete local gate

```bash
PYTHON=.venv/bin/python ./scripts/test-all.sh
```

The gate runs:

- backend and release unit tests;
- Python compilation;
- fallback JavaScript syntax;
- npm dependency audit;
- frontend unit and runtime tests;
- coverage, typecheck and lint;
- deterministic static build and normalization;
- Playwright E2E and accessibility;
- runtime verification;
- public privacy verification when release marker and URL controls are supplied.

## Focused commands

```bash
.venv/bin/python -m unittest discover -s tests -v
cd frontend
../scripts/npmw run test:unit
../scripts/npmw run test:coverage
../scripts/npmw run typecheck
../scripts/npmw run lint
../scripts/npmw run build
../scripts/npmw run test:e2e
../scripts/npmw run test:a11y
```

## What fixtures prove

- exact composer send behavior;
- explicit execution preflight;
- two writer isolation and third-writer preservation;
- delayed A/B response rejection;
- 10-second selection deadline and explicit reload;
- attachment, screenshot and restart boundaries;
- 375, 768 and 1440 pixel layouts;
- keyboard, Axe and reduced-motion behavior;
- zero unexpected browser, console and hydration errors.

Fixtures do not prove current compatibility with the live ChatGPT website.

## Live gates

Live tests require explicit approval for:

- the dedicated ChatGPT profile;
- a disposable workspace root;
- each mini-site mission.

They must never use a personal conversation or important workspace. A live result records commands, hashes, HTTP checks, browser traces, screenshots and process cleanup. Failed attempts remain in the evidence; retries cannot erase them.

## Release evidence

`docs/verification/v0.5.0.json` records the final commit, environment, suite counts, performance, recovery, dual writers, mini-site runs, privacy/link results and artifact hashes. Validate it with:

```bash
./scripts/verify-release-evidence.py docs/verification/v0.5.0.json
```
