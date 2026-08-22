# Contributing

Cortex Bridge is a personal open-source project published as an opt-in
technical preview. Issues and well-scoped pull requests are welcome.

## Ground rules

- **Human approval is a feature, not a bug.** PRs that remove or weaken the
  approval gates will not be merged.
- **Classic chat only.** Nothing may target ChatGPT Work/business surfaces.
- **Privacy gates are mandatory.** The public tree is scanned for personal
  markers, fingerprints, non-allowlisted URLs, image EXIF and OCR content.
  Run before committing:

  ```bash
  scripts/check-public-privacy.sh \
    --markers tests/fixtures/privacy/ci-markers.txt \
    --fingerprints scripts/privacy-fingerprints.json \
    --url-allowlist scripts/public-url-allowlist.txt
  ```

- **Tests must pass locally as in CI:** `scripts/test-all.sh` (backend +
  extension), then the frontend gates in `frontend/` (`test:unit`,
  `test:coverage`, `typecheck`, `lint`, `test:e2e`, `test:a11y`).

## Commit identity

Commits must use your real GitHub identity. Early history contains commits
signed `Cortex Bridge <cortex-bridge@localhost>` from an automated session;
that identity is retired and documented here for transparency.

## Style

- Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, …).
- Public docs in English; application labels stay French.
- Update `CHANGELOG.md` (Unreleased) and, when behavior changes, the release
  checklist and evidence under `docs/verification/`.
