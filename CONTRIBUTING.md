# Contributing to Cortex Bridge

Thanks for your interest! Cortex Bridge is a small, local-first project and
contributions of every size are welcome.

## Ways to contribute

### 1. Suggest an improvement

Open an issue with the **Feature request / Improvement idea** template:
<https://github.com/Jonassuhard/cortex-bridge/issues/new?template=feature_request.md>

Ideas are tracked with the `enhancement` label. You can also browse existing
ideas and vote with a 👍 reaction — the most-upvoted ones get prioritized.

### 2. Report a bug

Use the **Bug report** template:
<https://github.com/Jonassuhard/cortex-bridge/issues/new?template=bug_report.md>

Please remove personal information (paths, conversation content) from logs
before pasting them.

### 3. Submit code

1. Fork the repository and create a branch from `main`.
2. Keep changes focused: one feature or one fix per pull request.
3. Run the test suite before opening the PR:

   ```bash
   python3 -m unittest discover -s tests
   ```

   All 120+ tests must pass. If you change the frontend, also run:

   ```bash
   cd frontend && npx tsc --noEmit && npm run lint && npm run build
   ```

4. Write commit messages in English. Documentation lives in English;
   the product UI is French — keep both as they are.
5. A pre-commit hook runs `gitleaks` on staged changes. Never commit
   tokens, cookies, or local paths with personal data.

### 4. Improve the documentation

Typos, clearer quickstarts, better diagrams — small doc PRs are merged fast.

## Ground rules

- **Local-first and loopback-only.** No code that phones home, no telemetry,
  no external API keys required to run the core loop.
- **No OpenAI API.** The whole point is driving the ChatGPT web UI through a
  real browser session. Do not add code paths that call OpenAI's API.
- **Be kind.** First-time contributors are welcome; ask questions in your PR
  or issue rather than staying stuck.
