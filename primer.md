# Cortex Bridge session primer

Current state as of 2026-08-22. This file is rewritten at each release close
so any new session starts from facts, not from memory.

## Repository

- Public repo `cortex-bridge`, default branch `main`, version **0.5.2**
  (`VERSION` is the canonical source; pyproject, npm package + lock, Chrome
  manifest and installer metadata must match — enforced by
  `tests/test_version_consistency.py`).
- Release line: v0.3.0 (first public) → v0.5.0 (release candidate, merged PR
  #1) → v0.5.1 (classic-chat guard + click-free CDP capture, PR #2) → v0.5.2
  (simple onboarding, unified history, clear UI states, PR #3).
- Merged topic branches are deleted after merge; only `main` lives on the
  remote. Work happens in short-lived branches or disposable worktrees.
- Commits are signed with the owner's GitHub identity. Older commits signed
  `Cortex Bridge <cortex-bridge@localhost>` are historical; see
  CONTRIBUTING.md.

## Product rules (unchanged)

- The intended product uses the real signed-in Chrome profile through the
  local unpacked extension. It never substitutes the OpenAI API or a separate
  browser profile without an explicit product decision.
- Cortex writes **only** on the ChatGPT classic-chat surface. The Work
  surface is refused closed (`WORK_SURFACE_REJECTED`).
- Every local action requires explicit human approval; nothing executes
  silently.

## Provider conflict (standing, documented, owner-assumed)

- The OpenAI Terms of Use prohibit automatic or programmatic extraction. The
  consumer-site transport conflicts with that text. The project is published
  as an **opt-in technical preview**: the UI states the non-authorization and
  the account-suspension risk in French before activation, and the README
  carries the same notice. Owner approval does not lift the conflict; it is
  assumed personally by the owner.
- A compliant path would be an official transport (developer-mode plugin →
  public HTTPS MCP endpoint or Secure MCP Tunnel). Both require Platform
  permissions and credentials; adopting one is an explicit architecture
  change tracked in ROADMAP.md, not a fallback.

## Privacy rule (unchanged)

- Any technical observation uses neutral synthetic markers. Never publish
  account details, sidebar titles, conversation contents, conversation IDs,
  cookies, logs, or unredacted live captures.
- The public tree is gated by `scripts/check-public-privacy.sh` (markers,
  fingerprints, URL allowlist, image EXIF + OCR). Personal names, local
  usernames, external-drive names and the repo's own URL (it embeds a
  personal handle) must never enter the tree — that is why README badges are
  username-free and llms.txt uses relative links only.

## Quality gates (all green on main)

- 431 backend tests, 127 frontend unit tests, 56 extension tests, 12 E2E + 1
  documented skip, 4 accessibility tests, typecheck, lint, deterministic build, privacy,
  release-evidence and secret scans.
- CI: `.github/workflows/ci.yml` (backend, frontend, release-gates) plus the
  Public documentation workflow. Release evidence:
  `docs/verification/v0.5.2.json` (validated in CI by
  `scripts/verify-release-evidence.py`; the validator reads the canonical
  `VERSION`).
- Known honest gap: the real screenshot capture was validated live through a
  temporary broadened-permission debug build; the production
  click → activeTab → pendingCapture path is covered by unit/E2E tests, not
  by that same live run. Recorded in the release evidence notes.

## Local runtime state

- Console: `scripts/cortex.sh start|status|doctor|stop`; UI on
  `http://127.0.0.1:8420`. Default workspace: `~/cortex-workspaces`
  (auto-created, stable).
- Runtime state lives under `CORTEX_HOME`, not in the repo.
- Ollama is optional and lives on an external volume; the deterministic
  executor is the always-available default.
