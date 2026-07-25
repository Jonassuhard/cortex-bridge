# Cortex Bridge v0.5.0 Conversation UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the global, mode-based frontend with an accessible conversation-first interface that preserves state per conversation and makes sending versus local execution explicit.

**Architecture:** Introduce a pure per-conversation state reducer and controller hooks, then rebuild the workspace around one composer, an execution preflight, exclusive sidebar groups, and independent status sources. Add component tests before each behavior and Playwright E2E before generating the static export.

**Tech Stack:** Next.js 16, React 19, TypeScript, Vitest, Testing Library, Playwright, axe-core, CSS.

## Global Constraints

- The application interface is French by default.
- The public source, test names, and documentation are English.
- Enter always sends to ChatGPT; it never starts an execution.
- A local execution starts only after preflight confirmation.
- Draft, attachment, run, mission, and stream state are keyed by conversation.
- Unknown message counts are hidden.
- Statuses remain visible at 375, 768, and 1440 pixels.
- Minimum body text is 14 px; metadata is 12 px.
- Icon-only controls have accessible names, keyboard tooltips, and 44 px mobile targets.
- Closed drawers and dialogs cannot receive focus.
- `frontend/out` is generated only after all source tests pass.

---

### Task 1: Frontend test harness

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/test/setup.ts`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/fixtures/app.ts`

**Interfaces:**
- Produces scripts: `test`, `test:coverage`, `test:e2e`, `test:a11y`
- Produces deterministic API fixture routes for browser tests

- [ ] **Step 1: Add the test dependencies**

Install Vitest, jsdom, Testing Library, User Event, jest-dom, Playwright, and
axe-core as development dependencies.

- [ ] **Step 2: Add a failing smoke component test**

Render the current application and assert that it exposes a named main
conversation region. Run it once to prove the harness catches the missing
contract.

- [ ] **Step 3: Configure deterministic fixtures**

Fixture data uses only:

- account: `Demo User`;
- project: `Atlas`;
- conversations: `Release checklist`, `Local site prototype`, `Research`;
- workspace: `/tmp/cortex-demo-workspace`.

- [ ] **Step 4: Run the harness**

```bash
cd frontend
npm run test
npx playwright install chromium
```

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json \
  frontend/vitest.config.ts frontend/test frontend/playwright.config.ts \
  frontend/e2e/fixtures
git commit -m "test(ui): add component and browser test harnesses"
```

### Task 2: Per-conversation state model

**Files:**
- Modify: `frontend/lib/types.ts`
- Create: `frontend/lib/conversation-state.ts`
- Create: `frontend/lib/conversation-state.test.ts`
- Create: `frontend/hooks/useConversationController.ts`
- Create: `frontend/hooks/useChatRunStream.ts`
- Modify: `frontend/components/CortexApp.tsx`

**Interfaces:**
- Produces: `ConversationKey = string`
- Produces: `ConversationEntry`
- Produces: `conversationReducer(state, event)`
- Produces events: `SELECT`, `DRAFT_CHANGED`, `ATTACHMENT_STAGED`,
  `SWITCH_STARTED`, `SNAPSHOT_RECEIVED`, `RUN_EVENT`, `MISSION_EVENT`,
  `REKEY_CANONICAL`, `REQUEST_FAILED`

- [ ] **Step 1: Write reducer tests**

Cover:

- A and B retain independent drafts and attachments;
- an event for A cannot alter selected B;
- stale request epochs are ignored;
- provisional UUID rekeys atomically;
- HTTP 409 preserves draft and attachment;
- terminal run cleanup affects one conversation only.

- [ ] **Step 2: Verify RED**

```bash
cd frontend
npm run test -- lib/conversation-state.test.ts
```

- [ ] **Step 3: Implement the pure reducer**

Use immutable records keyed by `ConversationKey`. Store request epoch and run
ID with every asynchronous event.

- [ ] **Step 4: Move orchestration out of `CortexApp`**

The controller owns API requests, aborts obsolete conversation loads, enforces
the 10-second client budget, and filters SSE events by conversation and run.
`CortexApp` becomes layout and routing composition.

- [ ] **Step 5: Run reducer and type tests**

```bash
cd frontend
npm run test -- lib/conversation-state.test.ts
npm run typecheck
```

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/conversation-state.ts \
  frontend/lib/conversation-state.test.ts frontend/hooks \
  frontend/components/CortexApp.tsx
git commit -m "refactor(ui): isolate state by conversation"
```

### Task 3: Exclusive conversation navigation

**Files:**
- Create: `frontend/lib/conversations.ts`
- Create: `frontend/lib/conversations.test.ts`
- Modify: `frontend/components/ConversationSidebar.tsx`
- Create: `frontend/components/ConversationSidebar.test.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- Produces: `groupConversations(items, limit = 50) -> ConversationGroups`
- Consumes: `project_id`, `project_title`, `pinned`, `message_count`

- [ ] **Step 1: Write grouping tests**

Use hand-written fixtures and assert:

- pinned items appear only under Pinned;
- project items appear only under their real project title;
- unpinned non-project items appear under Recent;
- results are newest-first and capped at 50;
- unknown count renders no count;
- removed conversations disappear after reconciliation.

- [ ] **Step 2: Verify RED**

```bash
cd frontend
npm run test -- lib/conversations.test.ts
```

- [ ] **Step 3: Implement sidebar groups**

Remove `New mission`, hard-coded account identity, duplicate pin labels,
`Not synchronized`, and dead controls. Keep one `Nouvelle conversation`
button at the top.

- [ ] **Step 4: Test expanded and collapsed navigation**

Assert all icon controls have names and collapsed mode exposes only expand,
new conversation, conversation navigation, and settings.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/conversations.ts frontend/lib/conversations.test.ts \
  frontend/components/ConversationSidebar.tsx \
  frontend/components/ConversationSidebar.test.tsx frontend/app/globals.css
git commit -m "feat(ui): group ChatGPT conversations by category"
```

### Task 4: Unified composer and execution preflight

**Files:**
- Create: `frontend/components/Composer.tsx`
- Create: `frontend/components/Composer.test.tsx`
- Create: `frontend/components/ExecutionPreflightDialog.tsx`
- Create: `frontend/components/ExecutionPreflightDialog.test.tsx`
- Modify: `frontend/components/ChatWorkspace.tsx`
- Modify: `frontend/components/ExecutionCard.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- `Composer.onSend(text, attachment)`
- `Composer.onPrepareExecution(text, attachment)`
- `ExecutionPreflightDialog.onConfirm(preflight)`
- `ExecutionPreflight` includes workspace, process capability, write policy,
  duration, iterations, executor kind, and attachments

- [ ] **Step 1: Write composer behavior tests**

Assert:

- Enter calls only `onSend`;
- Shift+Enter inserts a newline;
- `Exécuter sur cet ordinateur…` opens preflight and does not call the mission
  API;
- attachment and screenshot actions never start an execution;
- rejected send preserves all staged content.

- [ ] **Step 2: Verify RED**

```bash
cd frontend
npm run test -- components/Composer.test.tsx
```

- [ ] **Step 3: Implement the composer**

Remove persistent mode state and mode tabs. Use one visible Send button and a
text-labelled execution action. Keep workspace as a real button/select
control.

- [ ] **Step 4: Implement preflight**

The dialog names every capability and defaults processes to disabled. The
confirm action is the only code path that invokes `/api/missions`.

- [ ] **Step 5: Fix execution-card time rendering**

Remove `Date.now()` from render. Use API timestamps or stable text to eliminate
hydration mismatch. Collapse details by default.

- [ ] **Step 6: Run component, type, and lint checks**

```bash
cd frontend
npm run test -- components/Composer.test.tsx \
  components/ExecutionPreflightDialog.test.tsx
npm run typecheck
npm run lint
```

- [ ] **Step 7: Commit**

```bash
git add frontend/components/Composer* \
  frontend/components/ExecutionPreflightDialog* \
  frontend/components/ChatWorkspace.tsx \
  frontend/components/ExecutionCard.tsx frontend/app/globals.css
git commit -m "feat(ui): replace mission mode with explicit execution preflight"
```

### Task 5: Independent statuses and send lifecycle

**Files:**
- Create: `frontend/components/StatusRail.tsx`
- Create: `frontend/components/StatusRail.test.tsx`
- Modify: `frontend/components/ChatWorkspace.tsx`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- `StatusRail({ transport, executor, execution })`
- Humanized send states: queued, sending, visible, waiting, received,
  uncertain, failed

- [ ] **Step 1: Write status tests**

Assert that ChatGPT and local-agent statuses remain independent, raw enum
values never render, paused exposes only `Reprendre`, and latency is absent
when unknown.

- [ ] **Step 2: Verify RED**

```bash
cd frontend
npm run test -- components/StatusRail.test.tsx
```

- [ ] **Step 3: Implement the paired status rail**

Use text plus a non-color indicator. At medium/mobile widths, place a compact
second row under the title rather than hiding statuses.

- [ ] **Step 4: Implement explicit send feedback**

Keep the optimistic message block visible and update its status instead of
removing and recreating it after delivery.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/StatusRail* \
  frontend/components/ChatWorkspace.tsx frontend/lib/types.ts \
  frontend/app/globals.css
git commit -m "feat(ui): show independent transport and agent status"
```

### Task 6: Accessible drawers, dialogs, and visual tokens

**Files:**
- Create: `frontend/hooks/useAccessibleDialog.ts`
- Create: `frontend/hooks/useAccessibleDialog.test.tsx`
- Modify: `frontend/components/PipelineInspector.tsx`
- Modify: `frontend/components/SettingsPanel.tsx`
- Modify: `frontend/components/OnboardingPanel.tsx`
- Modify: `frontend/app/globals.css`

**Interfaces:**
- `useAccessibleDialog({ open, triggerRef, onClose })`
- Closed surfaces set `inert` and `aria-hidden`

- [ ] **Step 1: Write accessibility tests**

Cover Escape, focus trap, focus return, no off-screen tab stops, named close
buttons, keyboard tooltips, and settings tab semantics.

- [ ] **Step 2: Verify RED**

```bash
cd frontend
npm run test -- hooks/useAccessibleDialog.test.tsx
```

- [ ] **Step 3: Apply semantic tokens**

Define the v0.5 token set from `docs/v0.5.0-design.md`, temporarily alias
legacy `--text` and `--border`, then replace their uses. Raise body and
metadata sizes, ensure 44 px controls, and remove the light `--surface` from
dark onboarding cards.

- [ ] **Step 4: Make closed surfaces inert**

Add correct dialog/tab roles and focus behavior. Remove or wire every visible
dead control.

- [ ] **Step 5: Run accessibility component tests**

```bash
cd frontend
npm run test
npm run typecheck
npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/hooks/useAccessibleDialog* \
  frontend/components/PipelineInspector.tsx \
  frontend/components/SettingsPanel.tsx \
  frontend/components/OnboardingPanel.tsx frontend/app/globals.css
git commit -m "fix(ui): make Cortex readable and keyboard accessible"
```

### Task 7: Browser E2E and fallback removal

**Files:**
- Create: `frontend/e2e/dual-conversation.spec.ts`
- Create: `frontend/e2e/switch-timeout.spec.ts`
- Create: `frontend/e2e/send-lifecycle.spec.ts`
- Create: `frontend/e2e/execution-preflight.spec.ts`
- Create: `frontend/e2e/responsive-accessibility.spec.ts`
- Create: `frontend/e2e/hydration-console.spec.ts`
- Replace: `frontend/fallback/index.html`
- Modify: `scripts/test-all.sh`

**Interfaces:**
- E2E fixture runs the real static frontend against deterministic API routes
- Fallback becomes diagnostic-only and cannot simulate a mission

- [ ] **Step 1: Write failing E2E scenarios**

Cover dual conversations, third-writer rejection, cached switching, 10-second
recovery, send lifecycle, preflight, all three viewports, keyboard traversal,
and zero console errors.

- [ ] **Step 2: Replace the fallback**

The fallback page states that the UI build is unavailable and links to
installation diagnostics. It contains no chat, mission, demo, or generated
success state.

- [ ] **Step 3: Run E2E**

```bash
cd frontend
npm run test:e2e
npm run test:a11y
```

- [ ] **Step 4: Rebuild static output**

```bash
cd frontend
npm run build
```

- [ ] **Step 5: Run the full repository gate**

```bash
./scripts/test-all.sh
```

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e frontend/fallback/index.html frontend/out \
  scripts/test-all.sh
git commit -m "test(ui): cover the v0.5 conversation experience end to end"
```

### Task 8: Shared animated diagram and synthetic guide capture

**Files:**
- Create: `frontend/lib/bridge-diagram-model.ts`
- Create: `frontend/lib/bridge-diagram-model.test.ts`
- Modify: `frontend/components/BridgeDiagram.tsx`
- Create: `frontend/e2e/docs-guide.spec.ts`
- Create: `scripts/render-architecture-media.mjs`
- Create: `docs/media/architecture-flow.gif`
- Create: `docs/media/architecture-flow.png`
- Create: `docs/screenshots/v0.5.0/.gitkeep`

**Interfaces:**
- Shared states: user, ChatGPT, lock, policy, approval, executor, workspace,
  evidence, report
- French labels in app; English labels for docs render

- [ ] **Step 1: Write diagram-model tests**

Assert deterministic node order, optional Ollama branch, accessible
description, and reduced-motion state.

- [ ] **Step 2: Implement and render the diagram**

Use SVG/CSS for the app. Render README media from the same state model through
Playwright and ffmpeg; do not add Remotion to runtime dependencies.

- [ ] **Step 3: Capture synthetic guide screens**

Capture onboarding, grouped navigation, send lifecycle, preflight, approval,
execution details, dual conversations, attachments, recoverable error, and
Info diagram at required viewports.

- [ ] **Step 4: Run privacy checks**

```bash
exiftool -overwrite_original -all= docs/screenshots/v0.5.0/*.png docs/media/*
for f in docs/screenshots/v0.5.0/*.png; do
  tesseract "$f" stdout -l eng+fra 2>/dev/null
done | rg -i 'asterion|jonas|kimi|djo|cool.?bank|preuvia|/users/|/volumes/' \
  && exit 1 || true
```

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/bridge-diagram-model* frontend/components/BridgeDiagram.tsx \
  frontend/e2e/docs-guide.spec.ts scripts/render-architecture-media.mjs \
  docs/media docs/screenshots/v0.5.0
git commit -m "docs(ui): add the animated bridge guide"
```
