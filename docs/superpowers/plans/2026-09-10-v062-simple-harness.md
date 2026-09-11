# Cortex Bridge 0.6.2 Simple Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reduce Cortex Bridge to a clear conversation-first workflow and ship a bounded ChatGPT supervisor harness for approved files, documents, screenshots and links.

**Architecture:** Keep the existing FastAPI/WebBridge transport and React conversation controller. Add only the missing identity/idempotency boundary around context approvals, keep the technical inspector collapsed by default, and use deterministic fixtures for browser verification. The desktop ChatGPT app remains an explicit external capability gate.

**Tech Stack:** Python 3.11+, FastAPI/Pydantic, React 19, Next 16, TypeScript, CSS, Vitest, Testing Library, Playwright, unittest.

**Spec:** `docs/superpowers/specs/2026-09-10-v062-simple-harness-spec.md`

## Global Constraints

- Work only in the selected candidate checkout; do not modify the original checkout.
- Preserve existing uncommitted 0.6.1 changes and use one writer per file.
- No OpenAI API client, cookie export, silent full-disk read, automatic resend, or fabricated attachment delivery.
- Keep the two-writer conversation lease and explicit approvals.
- Use synthetic fixtures for automated UI evidence; real ChatGPT attachment delivery remains `UNCLEAR` until the desktop capability is exposed.
- Do not commit, push, tag, merge or publish during this plan without a separate explicit release approval.

### Task 1: Freeze the 0.6.2 contract

**Files:**
- Create: `docs/superpowers/specs/2026-09-10-v062-simple-harness-spec.md`
- Create: `docs/superpowers/plans/2026-09-10-v062-simple-harness.md`
- Modify: `primer.md`

- [x] Record the product contract, limits, external gates and acceptance criteria.
- [x] Record the current branch, sealed commit and uncommitted scope in `primer.md`.

### Task 2: Make context approvals identity-bound and idempotent

**Files:**
- Modify: `console/chat.py`
- Modify: `frontend/components/CortexApp.tsx`
- Modify: `frontend/lib/contextRequest.ts`
- Test: `tests/test_context_approval.py`
- Test: `frontend/lib/contextRequest.test.ts`

**Interfaces:**
- Request body fields: `request_id: string`, `item_id: string`, existing `item`.
- Backend response: `{id: string, state: string, context_request_id: string, context_item_id: string}`.
- Duplicate `(conversation_url, request_id, item_id)` approvals return the original run and do not call a transport twice.

- [x] Write tests for missing identity, duplicate approval and valid identity.
- [x] Run the focused tests and confirm the new cases fail before implementation.
- [x] Add bounded identity validation and an in-memory idempotency registry scoped to the process.
- [x] Pass the identities from the card callback to the backend and expose them in the response.
- [x] Run focused backend/frontend tests and confirm they pass.

### Task 3: Keep the default interface simple

**Files:**
- Modify: `frontend/components/CortexApp.tsx`
- Modify: `frontend/components/ChatWorkspace.tsx`
- Modify: `frontend/app/globals.css`
- Test: `frontend/components/ChatWorkspace.test.tsx`

- [x] Add a small `Détails techniques` control to the status area when the inspector is closed.
- [x] Keep the inspector closed by default and preserve keyboard/ARIA state.
- [x] Keep the composer actions limited to `Envoyer à ChatGPT`, attachment, capture and the explicit execution preflight.
- [x] Add a test proving the technical panel is not visible until the control is activated.
- [x] Run frontend tests, typecheck, lint and a production build.

### Task 4: Make the supervisor loop reusable without a hidden transport

**Files:**
- Modify: `orchestration/context.py`
- Modify: `orchestration/runner.py`
- Modify: `docs/CHATGPT_SUPERVISOR_PROTOCOL.md`
- Test: `tests/test_supervisor_context.py`

- [x] Add a small `render_supervisor_prompt(packet, decision_contract)` helper that emits the existing desktop-supervisor prompt and never reads/sends files.
- [x] Add a `render_supervisor_report(...)` helper whose output distinguishes executed actions, evidence, unknowns and the next safe action.
- [x] Test that secrets are redacted, paths stay relative and the prompt contains the desktop capability limitation.
- [x] Run the focused orchestration tests and the complete Python suite.

### Task 5: Verify the real user-visible flow with synthetic fixtures

**Files:**
- Modify: `frontend/e2e/hydration-console.spec.ts` only if a stable regression assertion is missing.
- Create: `docs/verification/v0.6.2-simple-harness.md`
- Create: `docs/screenshots/v0.6.2/context-request.png`
- Create: `docs/screenshots/v0.6.2/context-request-states.png`

- [x] Start the local fixture server on a free loopback port.
- [x] Assert one valid marker renders as three approval rows, then approve one and reject one.
- [x] Assert invalid or duplicated markers remain visible text and do not create a card.
- [x] Assert the console has no hydration error; record intentional fixture 503s separately.
- [x] Stop the server and save screenshots without personal paths or account data.

### Task 6: Documentation and release evidence

**Files:**
- Modify: `README.md`
- Modify: `docs/verification-v061.md`
- Create: `docs/verification/v0.6.2-simple-harness.md`
- Modify: `primer.md`

- [x] Explain the one-screen workflow, context approvals, file/document distinction, screenshot scope and supervisor loop.
- [x] State that no OpenAI API is used and that native desktop attachments are an external gate.
- [x] Record exact test counts, build/lint commands, screenshot paths, branch and unresolved gates.
- [x] Run `git diff --check` and inspect `git status`.

### Task 7: Final local gate

**Files:**
- No source changes unless a gate exposes a real defect.

- [x] Run Python suite, frontend suite, typecheck, lint, production build and link/privacy checks.
- [x] Re-run the synthetic browser flow after all source changes.
- [x] Confirm no generated output or secrets are left in the working tree.
- [x] Stop at a truthful local verdict; do not claim 0.6.2 is published or desktop-attachment complete.
