# Cortex Bridge v0.5 Release QA Plan

**Goal:** Publish a truthful v0.5 technical-preview pull request with reproducible fixture evidence and a real clean macOS lifecycle. Never label the candidate `READY` until a compliant provider transport passes every live gate.

**Evidence rule:** Authenticated details stay local. The repository stores only aggregate counters, reviewed plan hashes and explicit blocker states. Failed attempts remain counted.

## Constraints

- Use synthetic prompts, files and workspaces only.
- Never record conversation identifiers, cookies, account data or personal content.
- Never use private endpoints, credential automation, CAPTCHA bypass or automatic terms acceptance.
- Never convert fixture results into live results.
- Push only `codex/v050-release-qa`; do not create a tag or GitHub release.

## 1. Machine-enforced evidence contract

- [x] Require one live conversation for `READY`.
- [x] Require two isolated live writers, zero crossover and refusal of the third writer.
- [x] Require one file upload and one screenshot upload.
- [x] Require three consecutive disposable mini-site passes.
- [x] Require a real clean macOS install, browser launch, service lifecycle, doctor, reinstall and uninstall.
- [x] Accept an honest zero-count `BLOCKED_BY_PROVIDER_TERMS` state only with the pending verdict.
- [x] Reject any pending live gate that claims unobserved success.

## 2. Real clean macOS lifecycle

- [x] Review the dry-run commands, official URLs, disk estimate, rollback and plan hash.
- [x] Run real package and Playwright downloads with a fresh `HOME` and `CORTEX_HOME`.
- [x] Launch the installed Chromium runtime.
- [x] Start Cortex Bridge, query its status, run doctor, stop it and prove the listener is gone.
- [x] Reinstall and require zero commands plus `already_installed`.
- [x] Uninstall every manifest-owned resource while preserving a foreign sentinel.
- [x] Retain the first failed attempt that exposed the unowned browser-cache defect.
- [x] Fix the missing clean-environment `PYTHONPATH` and add regression tests.

## 3. Provider-policy gate

- [x] Review the current OpenAI Europe Terms of Use before authenticated automation.
- [x] Record that the terms effective January 16, 2026 prohibit automatically or programmatically extracting data or Output.
- [x] Stop before opening an authenticated profile or sending a consumer ChatGPT message.
- [x] Keep live conversation, attachment and ChatGPT-planned mission counters at zero.
- [ ] Implement an officially supported provider transport before retrying the live gates.

The official transport is a separate architecture decision: it requires provider configuration and billing and does not automatically mirror consumer ChatGPT conversations. It is not silently substituted into v0.5.

## 4. Final regression and evidence commit

- [x] Run the full backend, frontend, runtime, E2E and accessibility suites.
- [x] Run release-evidence, artifact, privacy, link, secret, dependency and shell gates.
- [x] Commit the audited source changes.
- [x] Update the evidence source commit, timestamp and final observed suite counts.
- [x] Commit the evidence and require a clean worktree.

## 5. GitHub publication

- [x] Confirm GitHub authentication, repository, remote and `main` base branch.
- [ ] Push `codex/v050-release-qa` without force.
- [ ] Open a technical-preview PR that states the blocked live boundary.
- [ ] Verify the remote SHA and PR URL.

## Release decision

- Current verdict: `PENDING_OWNER_APPROVAL_FOR_LIVE_GATES`.
- `READY` is prohibited until an officially supported transport produces all required live evidence.
- A pull request may still be published as a technical preview because the blocked boundary is explicit and machine-enforced.
