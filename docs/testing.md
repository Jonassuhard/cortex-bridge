# Testing

## Complete local gate

```bash
PYTHON=$HOME/.local/share/cortex-bridge/venv/bin/python ./scripts/test-all.sh
```

The gate runs backend tests, Python compilation, Manifest V3 protocol tests,
fallback syntax, dependency audit, frontend unit/runtime/coverage/type/lint,
static build, Playwright E2E and accessibility fixtures, runtime verification,
and public privacy checks.

Playwright is the synthetic browser test tool. It is not the product transport.

## Focused commands

```bash
python -m unittest tests.test_chrome_extension_bridge -v
python -m unittest tests.test_chrome_extension_driver -v
node --test chrome-extension/tests/extension.test.mjs
cd frontend
../scripts/npmw run test:unit
../scripts/npmw run typecheck
../scripts/npmw run lint
../scripts/npmw run build
../scripts/npmw run test:e2e
../scripts/npmw run test:a11y
```

## Fixture proof

Fixtures prove pairing expiry/replay, command allowlisting, same-window tab
creation logic, connection dialog states, exact send lifecycle, two writers and
third rejection, 10-second selection, attachments, screenshots, restart,
responsive layouts, keyboard behavior, Axe, reduced motion, and absence of
unexpected browser errors.

Fixtures do not prove current compatibility with a real authenticated ChatGPT
account.

## Owner-approved live gate

The live gate requires explicit approval and the owner's normal Chrome profile.
It checks one conversation, two isolated conversations, third rejection, a
small redacted file, a redacted screenshot, tab-close recovery, and three
disposable mini-site missions. Evidence stores aggregate results and hashes,
never account identity, cookies, conversation text, or unredacted media.

Any unrun item remains `PENDING_OWNER_APPROVAL`. Fixture success cannot change
that state.

## Release evidence

Validate `docs/verification/v0.5.0.json` with:

```bash
./scripts/verify-release-evidence.py docs/verification/v0.5.0.json
```
