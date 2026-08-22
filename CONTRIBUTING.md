# Contributing to Cortex Bridge

Cortex Bridge touches browser sessions, local files and processes. Small diffs still need serious evidence.

Cortex Bridge is a personal open-source project published as an opt-in
technical preview. Issues and well-scoped pull requests are welcome; see the
public [ROADMAP.md](ROADMAP.md) for where the project is heading.

## Ground rules

- **Human approval is a feature, not a bug.** PRs that remove or weaken the
  approval gates will not be merged.
- **Classic chat only.** Nothing may target ChatGPT Work/business surfaces.
- **Privacy gates are mandatory** (see Required verification below).

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
scripts/check-public-privacy.sh \
  --markers tests/fixtures/privacy/ci-markers.txt \
  --fingerprints scripts/privacy-fingerprints.json \
  --url-allowlist scripts/public-url-allowlist.txt
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

## Commit identity and style

- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, …).
- Commits must use your real GitHub identity. Early history contains commits
  signed `Cortex Bridge <cortex-bridge@localhost>` from an automated session;
  that identity is retired and documented here for transparency.
- Update `CHANGELOG.md` (Unreleased) and, when behavior changes, the release
  checklist and evidence under `docs/verification/`.

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
