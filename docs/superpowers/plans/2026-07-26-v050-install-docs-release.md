# Cortex Bridge v0.5.0 Installation, Documentation, and Release Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Cortex Bridge reproducibly installable by a person or an agentic LLM, publish an English-only and privacy-clean repository, and prepare verifiable v0.5.0 release artifacts.

**Architecture:** Use a versioned dependency manifest as the source of truth for the human installer, agent protocol, doctor command, and documentation. Ship the static frontend for end users so Node remains optional, and verify every external link plus every release claim automatically.

**Tech Stack:** Bash, Python 3.11+, JSON, GitHub Actions, Markdown, gitleaks, shellcheck, lychee, Playwright-generated media.

## Global Constraints

- Every third-party installation requires named user consent.
- No installer uses `sudo`, logs in, accepts terms, or installs a browser extension for the user.
- The final-user path uses an isolated `.venv`.
- Node is optional unless rebuilding the frontend.
- WebBridge is compatibility-only; the distributable Playwright driver is the default.
- All public repository prose is English.
- No emoji is used unless it carries unique status meaning and has a text equivalent.
- No personal data, home path, external-volume name, unrelated client/project name, or secret remains in HEAD.
- Existing personal screenshots are replaced, not blurred in place.
- Link checks run against current official sources.
- Push, tag, release publication, and history rewriting require an explicit final approval after the target and impact are shown.

---

### Task 1: Version and reproducible Python package

**Files:**
- Create: `VERSION`
- Create: `pyproject.toml`
- Create: `requirements.lock`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `tests/test_version_consistency.py`

**Interfaces:**
- Canonical version: `0.5.0`
- Python extra groups: runtime, browser, development

- [ ] **Step 1: Write a failing version-consistency test**

Assert that `VERSION`, Python metadata, frontend package metadata, API status,
and release file all expose `0.5.0`.

- [ ] **Step 2: Verify RED**

```bash
python3 -m unittest tests.test_version_consistency -v
```

- [ ] **Step 3: Add package metadata and lock**

Declare FastAPI, uvicorn, and Playwright runtime dependencies. Keep frontend
tooling outside the Python environment.

- [ ] **Step 4: Update version surfaces and run the test**

```bash
.venv/bin/python -m unittest tests.test_version_consistency -v
```

- [ ] **Step 5: Commit**

```bash
git add VERSION pyproject.toml requirements.lock frontend/package*.json \
  tests/test_version_consistency.py
git commit -m "build: set the Cortex Bridge version to 0.5.0"
```

### Task 2: Dependency manifest and consent-aware installer

**Files:**
- Create: `install/dependencies.json`
- Create: `scripts/install.sh`
- Create: `scripts/uninstall.sh`
- Modify: `scripts/start-local.sh`
- Modify: `scripts/cortex.sh`
- Create: `tests/test_installer.py`

**Interfaces:**
- `./scripts/install.sh --dry-run`
- `./scripts/install.sh --approve python-runtime,browser-runtime`
- `./scripts/cortex.sh doctor`
- `./scripts/cortex.sh doctor --json`
- `./scripts/uninstall.sh --dry-run`

- [ ] **Step 1: Write installer behavior tests**

Run scripts in a temporary HOME and assert:

- dry-run changes nothing;
- unapproved dependencies are not installed;
- the exact command and official URL appear before consent;
- `.venv` is isolated;
- Node is skipped for the final-user path;
- doctor JSON uses stable component IDs;
- uninstall prints and removes only Cortex-owned paths.

- [ ] **Step 2: Verify RED**

```bash
python3 -m unittest tests.test_installer -v
```

- [ ] **Step 3: Create the manifest**

Components:

- Git;
- Python;
- Google Chrome or bundled Chromium;
- Playwright browser runtime;
- optional Ollama;
- optional local model;
- optional Node.js build toolchain;
- optional compatibility WebBridge with no public install command.

Each entry includes purpose, required status, official URL, commands, expected
disk impact when known, data paths, rollback, and interactive requirements.

- [ ] **Step 4: Implement install, doctor, and uninstall**

The installer performs inventory first, prints a consent plan, then executes
only approved entries. Browser login and model downloads always pause for the
user. `doctor --json` returns non-zero when a required component is unhealthy.

- [ ] **Step 5: Run script and installer gates**

```bash
bash -n scripts/*.sh executor/scripts/*.sh
shellcheck scripts/*.sh executor/scripts/*.sh
python3 -m json.tool install/dependencies.json >/dev/null
python3 -m unittest tests.test_installer -v
```

- [ ] **Step 6: Commit**

```bash
git add install/dependencies.json scripts/install.sh scripts/uninstall.sh \
  scripts/start-local.sh scripts/cortex.sh tests/test_installer.py
git commit -m "feat(install): add consent-aware setup and diagnostics"
```

### Task 3: Human and agentic installation guides

**Files:**
- Create: `INSTALL.md`
- Create: `docs/agent-installation.md`
- Rewrite: `docs/manual-setup.md`
- Rewrite: `docs/troubleshooting.md`
- Create: `docs/user-guide.md`

**Interfaces:**
- Human quick path follows install, doctor, browser login, start, smoke test
- Agent protocol consumes `install/dependencies.json`

- [ ] **Step 1: Write `INSTALL.md`**

Include:

- supported platform;
- what is installed and where;
- dry-run;
- consent flow;
- dedicated ChatGPT browser profile and manual login;
- optional Ollama setup;
- doctor;
- start, stop, logs;
- rollback and uninstall.

- [ ] **Step 2: Write the agentic installation protocol**

The agent must:

1. inspect read-only;
2. parse the manifest;
3. verify official links;
4. show the user named products, commands, downloads, data paths, and
   rollback;
5. ask one explicit approval for the listed mutations;
6. install only approved components;
7. stop for login, terms, secrets, privilege escalation, extension
   installation, or large downloads;
8. run doctor and smoke tests;
9. report exact changes.

Include a copyable approval prompt that contains no assumed consent.

- [ ] **Step 3: Write the visual user guide**

Reference only synthetic screenshots from `docs/screenshots/v0.5.0`. Cover
installation, onboarding, conversations, send, execution preflight,
approvals, two active conversations, attachments, recovery, and shutdown.

- [ ] **Step 4: Pressure-test every command**

Execute every non-destructive command from a clean temporary HOME or dry-run
fixture. Correct the guide when observed output differs.

- [ ] **Step 5: Commit**

```bash
git add INSTALL.md docs/agent-installation.md docs/manual-setup.md \
  docs/troubleshooting.md docs/user-guide.md
git commit -m "docs: add human and agent-assisted installation guides"
```

### Task 4: Rewrite public documentation and remove false claims

**Files:**
- Rewrite: `README.md`
- Rewrite: `CONTRIBUTING.md`
- Rewrite: `docs/architecture.md`
- Rewrite: `docs/security-model.md`
- Rewrite: `docs/testing.md`
- Rewrite: `docs/chatgpt-web-transport.md`
- Rewrite: `docs/interface.md`
- Rewrite: `frontend/README.md`
- Rewrite: `console/README.md`
- Rewrite: `executor/README.md`
- Rewrite: `orchestrator/README.md`
- Create: `CHANGELOG.md`
- Create: `SECURITY.md`
- Create: `docs/release-checklist.md`
- Archive or remove from public navigation: internal phase reports and stale plans

**Interfaces:**
- README links to install, architecture, security, tests, user guide, and
  contribution docs
- Testing claims are generated from the verification report

- [ ] **Step 1: Rewrite the README around verified behavior**

Remove decorative emoji and claims that:

- local code never leaves the disk;
- Ollama executes Mode A when it does not;
- tools are OS-sandboxed when they are only reviewed;
- current live checks are equivalent to automated release acceptance.

Explain the two explicit composer actions, transport choices, local data
boundaries, and experimental ChatGPT UI dependency.

- [ ] **Step 2: Rewrite architecture and security**

Document trust boundaries, process limitations, browser profiles, exact
executor truth fields, approval model, and recovery behavior.

- [ ] **Step 3: Generate test counts from the verifier**

Remove hand-maintained conflicting totals. Embed or link the machine-readable
v0.5 verification report.

- [ ] **Step 4: Add contribution, security, changelog, and release policy**

Document responsible disclosure, supported versions, reproducible tests,
release gates, and Web UI breakage policy.

- [ ] **Step 5: Commit**

```bash
git add README.md CONTRIBUTING.md CHANGELOG.md SECURITY.md docs \
  frontend/README.md console/README.md executor/README.md \
  orchestrator/README.md
git commit -m "docs: rewrite the public repository for v0.5"
```

### Task 5: Privacy cleanup and history decision

**Files:**
- Modify: source files returned by the privacy scan
- Replace: `docs/screenshots/*.png`
- Regenerate: `frontend/out`
- Create: `scripts/check-public-privacy.sh`
- Create: `tests/test_public_privacy.py`

**Interfaces:**
- Public scan exits zero only with no personal pattern in HEAD

- [ ] **Step 1: Write a failing privacy test**

Scan tracked text and OCR output for:

```text
/Users/
/Volumes/
asterion
Jonas
Kimi
DJO
Cool Bank
Preuvia
OpenCodex
```

Allow the repository owner name only inside the canonical GitHub URL and
copyright metadata.

- [ ] **Step 2: Verify RED**

```bash
python3 -m unittest tests.test_public_privacy -v
```

- [ ] **Step 3: Replace personal defaults and screenshots**

Use neutral workspaces, model-storage paths, fixture conversations, and the
synthetic v0.5 screenshot set. Remove metadata and regenerate `frontend/out`.

- [ ] **Step 4: Decide history handling**

Run a history scan. If personal content exists in published history, prepare
two written choices:

- keep history and disclose that deleted screenshots remain retrievable;
- rewrite history with `git filter-repo`, requiring a force push and fresh
  clones.

Do not rewrite or force-push without explicit approval.

- [ ] **Step 5: Commit HEAD cleanup**

```bash
git add scripts/check-public-privacy.sh tests/test_public_privacy.py \
  docs/screenshots frontend/out console frontend executor docs
git commit -m "chore(privacy): remove personal data from the public tree"
```

### Task 6: CI, link verification, and release evidence

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/docs.yml`
- Create: `.github/RELEASE-v0.5.0.md`
- Create: `docs/verification/v0.5.0.json`
- Create: `scripts/verify-links.sh`
- Create: `tests/test_release_manifest.py`

**Interfaces:**
- CI runs Python, frontend unit, type, lint, build, browser E2E, privacy, and
  secret scans
- Docs workflow runs Markdown and external-link validation

- [ ] **Step 1: Write a failing release-manifest test**

Assert that evidence includes commit, OS, Python, Node, browser driver,
executor kind, suite counts, dual-conversation runs, mini-site runs, privacy
scan, link scan, and console-error count.

- [ ] **Step 2: Add CI workflows**

Use pinned action major versions, least permissions, no repository secrets for
fixture CI, and uploaded Playwright traces only on failure.

- [ ] **Step 3: Verify official links**

Check and record final URLs for:

- Cortex Bridge repository;
- Python;
- Node.js;
- Git;
- Google Chrome;
- Playwright;
- ChatGPT;
- Ollama;
- OpenAI Codex CLI only if still required.

Compatibility WebBridge is documented without an install link because no
public official distribution exists.

- [ ] **Step 4: Run release evidence tests**

```bash
gitleaks detect --source . --no-banner --redact
./scripts/verify-links.sh
./scripts/test-all.sh
.venv/bin/python -m unittest tests.test_release_manifest -v
```

- [ ] **Step 5: Commit**

```bash
git add .github scripts/verify-links.sh docs/verification/v0.5.0.json \
  tests/test_release_manifest.py
git commit -m "ci: enforce the Cortex Bridge v0.5 release gate"
```

### Task 7: Clean-install and acceptance evidence

**Files:**
- Create: `scripts/acceptance-mini-site.py`
- Create: `tests/test_acceptance_harness.py`
- Update: `docs/verification/v0.5.0.json`
- Update: `.github/RELEASE-v0.5.0.md`

**Interfaces:**
- Each run creates a fresh workspace and conversation
- Oracle lives outside the mission workspace

- [ ] **Step 1: Write the acceptance-harness tests**

Prove that the harness detects outside-workspace changes, non-zero commands,
external URLs, console errors, leftover processes, and fake completion.

- [ ] **Step 2: Run fixture acceptance**

Execute 20 consecutive deterministic fixture runs with no retry masking.

- [ ] **Step 3: Run dual-conversation acceptance**

Execute ten cold A/B runs and prove distinct sessions and zero crossover.

- [ ] **Step 4: Run three live mini-site missions**

Each run uses a fresh workspace and ChatGPT conversation, records hashes,
commands, HTTP checks, browser traces, screenshots, and process cleanup.

- [ ] **Step 5: Update release evidence**

Record every failed and passed attempt. The release stays blocked unless all
required consecutive runs pass.

- [ ] **Step 6: Commit evidence**

```bash
git add scripts/acceptance-mini-site.py tests/test_acceptance_harness.py \
  docs/verification/v0.5.0.json .github/RELEASE-v0.5.0.md
git commit -m "test: record the v0.5 acceptance evidence"
```

### Task 8: Release and launch recommendation

**Files:**
- Create: `docs/launch-strategy.md`
- Update: `CHANGELOG.md`
- Update: `.github/RELEASE-v0.5.0.md`

**Interfaces:**
- Produces channel recommendation, competitor comparison, roadmap, and
  open-source decision based on current evidence

- [ ] **Step 1: Research current adjacent projects**

Use primary project repositories and current product documentation. Compare
browser-use agents, local computer-use tools, ChatGPT browser extensions,
Open Interpreter-style runtimes, and agent orchestration bridges.

- [ ] **Step 2: Evaluate open-source options**

Compare:

- full MIT release;
- open core with a hardened runtime closed;
- source-available preview;
- private beta until the browser transport and security maintenance burden
  are proven.

Address credential exposure, malicious prompt execution, disclosure response,
maintenance load, and contributor value.

- [ ] **Step 3: Produce channel-specific launch assets**

Recommend one primary launch channel and supporting formats for LinkedIn,
GitHub, developer communities, Instagram, and TikTok. Avoid publishing a
security-sensitive autonomy claim that the evidence does not support.

- [ ] **Step 4: Prepare but do not publish the release**

Show:

- repository and branch;
- commits and diff;
- tests and acceptance evidence;
- privacy and link scans;
- tag and release text;
- history-cleanup decision;
- exact external impact.

Wait for explicit approval before push, tag, GitHub Release, or history
rewrite.
