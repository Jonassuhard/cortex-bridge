# Contributing to Cortex Bridge

Cortex Bridge touches browser sessions, local files and processes. Small diffs still need serious evidence.

## Before opening a change

1. Open an issue for behavior, protocol or security changes.
2. Work from a clean branch or worktree.
3. Keep real account data, browser profiles, screenshots, logs and local paths out of fixtures.
4. Write a failing test before changing behavior.
5. Preserve the existing safety defaults unless the issue explicitly changes the product contract.

## Local setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.lock
corepack enable
cd frontend && corepack npm ci && cd ..
```

## Required verification

```bash
PYTHON=.venv/bin/python ./scripts/test-all.sh
git diff --check
gitleaks detect --source . --no-banner --redact
```

Browser tests use synthetic fixtures only. Do not attach a contributor’s live ChatGPT session to CI or a pull-request test.

## Code expectations

- Fail closed on an unknown browser, workspace, token, process or delivery state.
- Never resend automatically after an uncertain send.
- Never signal a PID without proving process identity.
- Never accept client-provided filesystem paths for attachments.
- Keep the application interface French and public repository prose English.
- Keep action and dependency versions pinned.
- Avoid broad refactors inside a security fix.

## Pull request evidence

Include:

- the user-visible behavior changed;
- the RED test and why it failed;
- exact GREEN commands and counts;
- performance or responsive evidence when relevant;
- privacy and migration impact;
- any live gate intentionally left for a maintainer.

## Documentation and media

Documentation screenshots must come from synthetic fixtures. Remove metadata, run OCR in English and French, and verify all links before committing media.

## Security reports

Do not open a public issue for a vulnerability. Follow [SECURITY.md](SECURITY.md).
