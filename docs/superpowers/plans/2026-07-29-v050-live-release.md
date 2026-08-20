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

## 2. Real clean macOS lifecycle for the current candidate

- [x] Review the dry-run commands, official URLs, disk estimate, rollback and plan hash.
- [ ] Apply the reviewed install plan after explicit approval of its exact hash.
- [ ] Run real package and Playwright downloads with a fresh `HOME` and `CORTEX_HOME`.
- [ ] Launch the installed Chromium runtime.
- [ ] Start Cortex Bridge, query its status, run doctor, stop it and prove the listener is gone.
- [ ] Reinstall and require zero commands plus `already_installed`.
- [ ] Uninstall every manifest-owned resource while preserving a foreign sentinel.

The automated lifecycle contracts pass, but they are not a substitute for this
real destructive/reversible lifecycle. The machine-readable evidence therefore
keeps `cleanMacosLifecycle.status` at `NOT_RUN`.

## 3. Provider-policy gate

- [x] Review the current OpenAI Europe Terms of Use before authenticated automation.
- [x] Record that the terms effective January 16, 2026 prohibit automatically or programmatically extracting data or Output.
- [x] Stop before opening an authenticated profile or sending a consumer ChatGPT message.
- [x] Keep live conversation, attachment and ChatGPT-planned mission counters at zero.
- [x] Verify the documented ChatGPT plugin and Secure MCP Tunnel routes.
- [ ] Implement an officially supported provider transport before retrying the live gates.

OpenAI documents a public HTTPS MCP endpoint for public plugins and Secure MCP
Tunnel for private developer-mode servers. Secure MCP Tunnel requires a
Platform organization, tunnel permissions and a runtime API key. It does not
preserve the current strict-local/no-API-credential product constraint or
automatically mirror consumer ChatGPT conversations. The official transport is
therefore a separate architecture decision and is not silently substituted into
v0.5.

## 4. Final regression and evidence commit

- [x] Run the full backend, frontend, runtime, E2E and accessibility suites.
- [x] Run release-evidence, artifact, privacy, link, secret, dependency and shell gates.
- [x] Commit the audited source changes.
- [x] Update the evidence source commit, timestamp and final observed suite counts.
- [x] Commit the evidence and require a clean worktree.

## 5. GitHub publication

- [x] Confirm GitHub authentication, repository, remote and `main` base branch.
- [ ] Push the current `codex/v050-release-qa` commits without force after the
  release boundary and clean lifecycle decision are explicit.
- [x] Keep the existing technical-preview PR explicit about the blocked live boundary.
- [ ] Verify the remote SHA and current PR checks after that push.

## Release decision

- Current verdict: `RELEASE_BLOCKED_BY_PROVIDER_TERMS`.
- `READY` is prohibited until an officially supported transport produces all required live evidence.
- A pull request may still be published as a technical preview because the blocked boundary is explicit and machine-enforced.
