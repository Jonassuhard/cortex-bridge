# Cortex Bridge v0.5.2 Proof Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the v0.5.2 release proof self-consistent and close the real-production-extension screenshot gap with fresh, privacy-safe evidence.

**Architecture:** `VERSION` remains the only release-version source. The release-evidence validator resolves the current manifest when no explicit historical manifest is supplied, so local and CI gates cannot silently validate an older release. Live QA uses the installed v0.5.2 Chrome extension and the signed-in Chrome profile with a neutral synthetic marker; evidence records aggregate facts only.

**Tech Stack:** Python 3.11+, `unittest`, Bash, MV3 Chrome extension, React/Vitest/Playwright, GitHub Actions.

**Spec:** `VERSION`, `ROADMAP.md`, `docs/testing.md`, `docs/verification/v0.5.2.json`, and `docs/release-checklist.md`.

## Global Constraints

- Keep the product version at exactly `0.5.2`; this closeout does not retag or replace the published asset.
- Use the real signed-in Chrome profile and the unpacked production extension; do not substitute the OpenAI API or a separate Playwright profile.
- Use neutral synthetic markers only. Do not store account details, conversation titles, conversation IDs, cookies, or unredacted ChatGPT screenshots.
- Keep public documentation in English and application labels in French.
- Do not claim the consumer-site transport is provider-authorized.
- Do not merge or modify Dependabot pull requests in this plan.

---

### Task 1: Establish a clean isolated baseline

**Files:**
- Inspect: `scripts/verify-release-evidence.py`
- Inspect: `tests/test_release_manifest.py`
- Inspect: `chrome-extension/service-worker-core.js`

**Interfaces:**
- Consumes: clean `main` at `edd8554730ae2928cc26d1af9159ccf5458ff700`.
- Produces: an isolated `codex/v052-proof-closeout` worktree with known-good targeted tests.

- [ ] **Step 1: Install locked dependencies in the worktree**

Run the locked Python and frontend installation procedures already documented by the repository.

- [ ] **Step 2: Run targeted baseline tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_release_manifest tests.test_version_consistency -v
node --test chrome-extension/tests/extension.test.mjs
```

Expected: all existing tests pass before implementation.

---

### Task 2: Resolve current release evidence from VERSION

**Files:**
- Modify: `tests/test_release_manifest.py`
- Modify: `scripts/verify-release-evidence.py`
- Modify: `scripts/test-all.sh`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: repository root containing `VERSION` and `docs/verification/v<version>.json`.
- Produces: `default_manifest_path(repo_root: Path) -> Path`; the CLI accepts an optional explicit historical manifest and otherwise validates the current manifest.

- [ ] **Step 1: Write the failing behavioral test**

Add a temporary-repository test that copies the validator, writes `VERSION=9.9.9`, places a valid manifest at `docs/verification/v9.9.9.json`, invokes the validator without a manifest argument, and expects exit code `0` plus `PASS release=9.9.9`.

- [ ] **Step 2: Run the new test and confirm RED**

Run:

```bash
.venv/bin/python -m unittest tests.test_release_manifest.ReleaseManifestTest.test_default_manifest_follows_canonical_version -v
```

Expected before implementation: failure because the positional `manifest` argument is required.

- [ ] **Step 3: Implement the minimal resolver**

Add:

```python
def default_manifest_path(repo_root: Path = REPO_ROOT) -> Path:
    version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    return repo_root / "docs" / "verification" / f"v{version}.json"
```

Make `manifest` optional and use this resolver only when it is absent. Change the local full gate and CI release gate to invoke the validator without a hard-coded path.

- [ ] **Step 4: Run the focused tests and confirm GREEN**

Run:

```bash
.venv/bin/python -m unittest tests.test_release_manifest tests.test_ci_contract -v
```

Expected: all tests pass and the current v0.5.2 manifest is selected.

- [ ] **Step 5: Commit the atomic fix**

Commit only the validator, its tests, the full gate and CI contract using `fix(release): derive evidence from VERSION`.

---

### Task 3: Correct stale public release facts

**Files:**
- Modify: `README.md`
- Modify: `docs/testing.md`
- Modify: `docs/release-checklist.md`
- Modify: `primer.md`

**Interfaces:**
- Consumes: current release facts from `VERSION` and `docs/verification/v0.5.2.json`.
- Produces: public instructions that call the version-derived validator and session context reporting 431 backend, 127 frontend, 56 extension, 12 E2E plus one skip, and 4 accessibility passes.

- [ ] **Step 1: Replace stale v0.5.0 current-release references**

Point README readers to the current v0.5.2 evidence, document the argument-free validator command, and correct the checklist source/package version to v0.5.2. Historical v0.5.0 evidence and screenshot directories remain unchanged.

- [ ] **Step 2: Update quality counts**

Update `primer.md` to the exact v0.5.2 evidence counts without changing the known live-capture caveat yet.

- [ ] **Step 3: Verify documentation gates**

Run:

```bash
scripts/verify-links.sh
scripts/check-public-privacy.sh --markers tests/fixtures/privacy/ci-markers.txt --fingerprints scripts/privacy-fingerprints.json --url-allowlist scripts/public-url-allowlist.txt
```

Expected: both gates pass.

- [ ] **Step 4: Commit the atomic documentation correction**

Commit only the four documentation/context files using `docs(release): align v0.5.2 proof references`.

---

### Task 4: Run the production-extension screenshot E2E

**Files:**
- Create: `.gstack/qa-reports/qa-report-127.0.0.1-2026-08-22.md`
- Create: `.gstack/qa-reports/baseline.json`
- Create: privacy-safe cropped or redacted screenshots under `.gstack/qa-reports/screenshots/`
- Modify after PASS only: `docs/verification/v0.5.2.json`
- Modify after PASS only: `ROADMAP.md`
- Modify after PASS only: `primer.md`

**Interfaces:**
- Consumes: loopback console at `http://127.0.0.1:8420`, paired Chrome extension version `0.5.2`, one neutral ChatGPT test conversation.
- Produces: a fresh run proving the production extension captures the selected visible ChatGPT tab, uploads the PNG, shows a visible attachment/send state, and records no personal data.

- [ ] **Step 1: Start and verify the local console**

Run `scripts/cortex.sh start`, then verify `scripts/cortex.sh status --json`, `scripts/cortex.sh doctor --json`, `/api/status`, and `/api/chrome-extension/status`.

- [ ] **Step 2: Verify the exact browser prerequisites**

In the user’s Chrome, confirm the extension reports version `0.5.2`, the Cortex page is paired, the selected ChatGPT tab is classic chat, and the composer is ready. If any prerequisite fails, fix that prerequisite rather than broadening permissions.

- [ ] **Step 3: Execute the synthetic capture flow**

Use a marker containing only the release and timestamp. Capture the selected visible ChatGPT tab through the production extension, attach the PNG to the same conversation, send it, and confirm the visible ChatGPT attachment/send lifecycle. Do not capture the sidebar or publish the raw image.

- [ ] **Step 4: Record evidence honestly**

If PASS, replace the debug-build caveat with the exact production-extension run facts, mark the v0.5.x roadmap item complete, and update the primer. If FAIL, keep the roadmap open, document the exact failure and add a regression test before any code fix.

- [ ] **Step 5: Stop the console and verify port release**

Run `scripts/cortex.sh stop` and confirm `scripts/cortex.sh status --json` reports `stopped`.

---

### Task 5: Run final gates and prepare integration

**Files:**
- Modify: `docs/verification/v0.5.2.json` hashes/counts only when supported by fresh output.
- Modify: `primer.md` final session state.
- Inspect: all branch changes.

**Interfaces:**
- Consumes: Tasks 2 through 4.
- Produces: a clean branch whose claims match fresh command output.

- [ ] **Step 1: Run the complete local gate**

Run:

```bash
scripts/test-all.sh
```

Expected: backend, extension, frontend unit/coverage/typecheck/lint/build, E2E, accessibility, runtime, privacy and current release evidence all pass.

- [ ] **Step 2: Validate generated artifacts and release evidence again**

Run:

```bash
.venv/bin/python scripts/verify-release-evidence.py
git diff --check
```

Expected: `PASS release=0.5.2` and no whitespace errors.

- [ ] **Step 3: Review repository state**

Inspect `git status`, `git diff main...HEAD`, and the commit list. Confirm no personal data, runtime files, raw ChatGPT captures, dependency changes or unrelated edits are present.

- [ ] **Step 4: Commit final evidence if it changed**

Use `test(release): record production extension capture` only when the live result supports the evidence update.

- [ ] **Step 5: Present the verified integration result**

Do not push or merge without explicit confirmation. Report exact tests, exact live result, commits and any remaining external-only items.
