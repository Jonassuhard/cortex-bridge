# Chrome Tab Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Cortex Bridge open, verify, and drive the user's real ChatGPT tab in the same Google Chrome window through a secure local MV3 extension.

**Architecture:** A packaged Chrome extension connects outbound to a FastAPI WebSocket on loopback. A single-use token pairs the Cortex browser tab with the extension, after which an allowlisted command protocol binds logical Cortex sessions to ChatGPT tabs in the same window. The normal user path never launches the existing Playwright profile; Playwright remains an explicit development transport.

**Tech Stack:** Python 3.11+, FastAPI WebSockets, Pydantic, Chrome Manifest V3 (Chrome 116+), plain JavaScript content scripts, React 19, TypeScript, Vitest, Playwright test fixtures, `unittest`.

## Global Constraints

- No OpenAI or private ChatGPT API.
- No separate browser window in the normal user flow.
- No silent fallback to Playwright.
- No cookie, password, history, or cross-site access.
- No automatic login, CAPTCHA, terms, or security-check handling.
- The extension protocol accepts structured allowlisted commands, never raw JavaScript.
- Maximum two concurrent writing conversation sessions; reject the third before opening a tab.
- At most 50 conversations are loaded.
- Every switch completes or reports a recoverable error within 10 seconds.
- Repository documentation remains English; product UI remains French.
- Live evidence is redacted and remains pending until it was actually observed.

---

### Task 1: Pairing protocol and backend bridge manager

**Files:**
- Create: `console/chrome_extension.py`
- Modify: `console/server.py`
- Test: `tests/test_chrome_extension_bridge.py`

**Interfaces:**
- Produces: `chrome_extension_manager`, `ChromeExtensionManager.issue_pairing_token()`, `ChromeExtensionManager.command(session, action, payload, timeout)`, and router endpoints under `/api/chrome-extension`.
- Consumes: FastAPI application lifecycle and loopback request middleware already defined in `console/server.py`.

- [ ] **Step 1: Write failing pairing and protocol tests**

Cover 32-byte URL-safe tokens, 60-second expiry, single-use pairing, replay rejection, pre-pair command rejection, unknown action rejection, correlated response delivery, command timeout, disconnect cleanup, and status projection.

```python
token = manager.issue_pairing_token()
assert len(token.value) >= 43
assert manager.consume_pairing_token(token.value, connection) is True
assert manager.consume_pairing_token(token.value, connection) is False
with self.assertRaises(BridgeProtocolError):
    await manager.command("session", "raw_evaluate", {}, timeout=0.01)
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_chrome_extension_bridge -v`  
Expected: import failure for `console.chrome_extension`.

- [ ] **Step 3: Implement the manager and router**

Use `secrets.token_urlsafe(32)`, monotonic expiry, one active paired connection, `asyncio.Future` request correlation, a strict `ALLOWED_ACTIONS` set, maximum JSON message size, and stable public state codes. Add:

```python
@router.websocket("/chrome-extension/ws")
async def extension_socket(websocket: WebSocket) -> None:
    await chrome_extension_manager.handle_socket(websocket)

@router.post("/chrome-extension/pairing")
async def create_pairing() -> PairingResponse:
    return chrome_extension_manager.issue_pairing_response()

@router.get("/chrome-extension/status")
async def extension_status() -> BridgeStatus:
    return chrome_extension_manager.public_status()
```

Include the router in `console/server.py` without weakening loopback checks.

- [ ] **Step 4: Run focused tests and confirm GREEN**

Run: `.venv/bin/python -m unittest tests.test_chrome_extension_bridge -v`  
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add console/chrome_extension.py console/server.py tests/test_chrome_extension_bridge.py
git commit -m "feat(bridge): add secure Chrome extension channel"
```

### Task 2: Manifest V3 extension and same-window tab control

**Files:**
- Create: `chrome-extension/manifest.json`
- Create: `chrome-extension/service-worker.js`
- Create: `chrome-extension/cortex-content.js`
- Create: `chrome-extension/chatgpt-content.js`
- Create: `chrome-extension/protocol.js`
- Create: `chrome-extension/README.md`
- Create: `chrome-extension/tests/extension.test.mjs`
- Modify: `scripts/test-all.sh`

**Interfaces:**
- Consumes: `/api/chrome-extension/ws` and the JSON command envelope from Task 1.
- Produces: extension messages `cortex.pair`, `bridge.heartbeat`, `command.result`, and structured actions including `open_chatgpt`, `probe`, `get_state`, `send_text`, and `capture_screenshot`.

- [ ] **Step 1: Write failing pure-JavaScript extension tests**

Mock `chrome.tabs`, `chrome.runtime`, and `WebSocket`. Assert that `open_chatgpt` reuses a ChatGPT tab in the Cortex tab's `windowId`, otherwise calls:

```js
chrome.tabs.create({
  windowId: cortexTab.windowId,
  index: cortexTab.index + 1,
  url: "https://chatgpt.com/",
  active: true,
});
```

Assert there is no `chrome.windows.create` reference, the heartbeat interval is 20 seconds, commands are allowlisted, and a missing content script returns `TAB_UNAVAILABLE`.

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `node --test chrome-extension/tests/extension.test.mjs`  
Expected: missing extension modules.

- [ ] **Step 3: Implement manifest and pairing relay**

Set `manifest_version: 3`, `minimum_chrome_version: "116"`, a service worker,
and content scripts restricted to:

```json
[
  "http://127.0.0.1:8420/*",
  "https://chatgpt.com/*"
]
```

The Cortex content script accepts only same-origin `window.postMessage`
pairing messages with the exact source/type shape and forwards the one-time
token plus `sender.tab` metadata to the service worker.

- [ ] **Step 4: Implement same-window tab binding and WebSocket lifecycle**

Connect to loopback, reconnect with capped backoff, heartbeat every 20 seconds,
store the paired Cortex tab, bind logical sessions to tab IDs, route only known
commands, and discard connection state on WebSocket close.

- [ ] **Step 5: Implement packaged ChatGPT DOM operations**

Port the existing adaptive-selector behavior into named operations in
`chatgpt-content.js`: probe, full/light state, SPA navigation, up-to-50
conversation discovery, text send, stop, attachment observation, bare send,
and model list/select. Return stable blocker codes for login, CAPTCHA, rate
limit, loading, and missing composer.

- [ ] **Step 6: Implement attachment chunks and screenshot capture**

Accept bounded base64 chunks, reconstruct one `File`, assign it through
`DataTransfer` to `form input[type=file]`, then require a visible attachment
chip. Capture only the bound ChatGPT tab and return PNG data; reject capture
when the tab is not active instead of capturing a different tab.

- [ ] **Step 7: Run extension tests and confirm GREEN**

Run: `node --test chrome-extension/tests/extension.test.mjs`  
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add chrome-extension scripts/test-all.sh
git commit -m "feat(extension): control ChatGPT in the Cortex Chrome window"
```

### Task 3: Chrome extension browser driver

**Files:**
- Create: `transport/browser_chrome_extension.py`
- Modify: `transport/browser.py`
- Modify: `transport/chatgpt_web/adapter.py`
- Modify: `console/settings.py`
- Test: `tests/test_chrome_extension_driver.py`
- Modify: `tests/test_playwright_driver.py`
- Modify: `tests/test_chat_settings_api.py`
- Modify: `tests/test_transport_session_isolation.py`

**Interfaces:**
- Consumes: `chrome_extension_manager.command(session, action, payload, timeout)`.
- Produces: `ChromeExtensionBrowserDriver`, implementing the existing `BrowserDriver` protocol with `driver_name = "chrome_extension"`.

- [ ] **Step 1: Write failing driver contract tests**

Test health truthfulness, open/focus, probe mapping, navigation, state reads,
send, two session-to-tab bindings, third writer rejection in existing lease
tests, file chunking, screenshot persistence beneath `CORTEX_HOME`, timeout
normalization, tab-closed errors, and no fallback.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_chrome_extension_driver -v`  
Expected: missing driver module.

- [ ] **Step 3: Implement the structured driver**

Map each protocol method to one allowlisted command. `evaluate()` must raise
`DriverError("raw evaluation is unavailable on the Chrome extension transport")`.
Upload validated staged files as 256 KiB chunks with a 25 MiB v0.5 bridge
limit. Decode screenshots, validate PNG bytes, and atomically write only to the
requested validated `CORTEX_HOME` path.

- [ ] **Step 4: Make Chrome extension the product default**

Use:

```python
DEFAULT_BROWSER_SETTINGS = {
    "browser_transport": "chrome_extension",
    "browser_profile_root": str(RUNTIME_PATHS.browser_profiles),
}
```

Allow `chrome_extension`, `playwright`, and legacy `webbridge`. Label
Playwright development-only. Do not auto-select it when the extension is
offline.

- [ ] **Step 5: Remove raw-evaluate attachment fallback for structured drivers**

When `upload_files` exists and reports a structured failure, surface
`ATTACHMENT_FAILED`; only legacy drivers explicitly declaring raw evaluation
support may use the old injection fallback.

- [ ] **Step 6: Run backend transport and isolation tests**

Run:

```bash
.venv/bin/python -m unittest \
  tests.test_chrome_extension_driver \
  tests.test_playwright_driver \
  tests.test_chat_settings_api \
  tests.test_transport_session_isolation -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add transport console/settings.py tests
git commit -m "feat(transport): use the paired Chrome tab by default"
```

### Task 4: Connection API and truthful onboarding checks

**Files:**
- Modify: `console/onboarding.py`
- Modify: `console/missions.py`
- Test: `tests/test_chat_settings_api.py`
- Test: `tests/test_probe.py`

**Interfaces:**
- Consumes: bridge manager status and `ChromeExtensionBrowserDriver.open_login()`.
- Produces: stable `ConnectionResult` payload with `code`, `state`, `title`,
  `message`, `recoverable`, `driver`, `tab_id`, and `url`.

- [ ] **Step 1: Write failing state-mapping tests**

Cover `EXTENSION_MISSING`, `EXTENSION_UNPAIRED`, `CHATGPT_LOADING`,
`LOGIN_REQUIRED`, `CAPTCHA`, `CONNECTED`, and `TAB_CLOSED`. Assert a false
health result never becomes `CONNECTED` and `open` never calls Playwright when
the configured default is `chrome_extension`.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_chat_settings_api tests.test_probe -v`  
Expected: assertions fail on the legacy profile-opening response.

- [ ] **Step 3: Implement open/retry/status state mapping**

Replace profile-oriented copy and route behavior. Pairing remains a separate
first step initiated by the UI; open/retry invoke the paired driver and return
the structured result without hiding errors inside an HTTP 500 string.

- [ ] **Step 4: Update onboarding checks**

Check extension presence/pairing first, then ChatGPT DOM readiness. Update hints
to say `Install or enable the Chrome extension`, `Sign in in the ChatGPT tab`,
or `Complete the verification`, according to the actual state.

- [ ] **Step 5: Run focused tests and confirm GREEN**

Run: `.venv/bin/python -m unittest tests.test_chat_settings_api tests.test_probe -v`  
Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add console/onboarding.py console/missions.py tests/test_chat_settings_api.py tests/test_probe.py
git commit -m "fix(onboarding): report real Chrome connection states"
```

### Task 5: French connection dialog and status rail

**Files:**
- Create: `frontend/components/ChatGPTConnectionDialog.tsx`
- Create: `frontend/components/ChatGPTConnectionDialog.test.tsx`
- Modify: `frontend/components/StatusRail.tsx`
- Modify: `frontend/components/StatusRail.test.tsx`
- Modify: `frontend/components/CortexApp.tsx`
- Modify: `frontend/components/CortexApp.test.tsx`
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/app/globals.css`
- Modify: `frontend/e2e/smoke.spec.ts`
- Modify: `frontend/e2e/accessibility.spec.ts`

**Interfaces:**
- Consumes: `POST /api/chrome-extension/pairing`, window pairing message, and
  structured open/retry/status payloads.
- Produces: a visible `Ouvrir et connecter ChatGPT` action and accessible
  connection dialog.

- [ ] **Step 1: Write failing component tests**

Assert the primary label, checking state, exact French login copy, retry call,
close behavior, Escape, focus return, extension-missing copy, connected status,
and absence of `profil ChatGPT` language.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `cd frontend && npm test -- --run components/ChatGPTConnectionDialog.test.tsx components/StatusRail.test.tsx components/CortexApp.test.tsx`  
Expected: missing dialog and legacy copy failures.

- [ ] **Step 3: Implement pairing and connection state machine**

On click: request pairing, post the token to the same page for the extension
relay, poll status for at most two seconds, call open, then show the mapped
dialog when action is required. Retry never creates a new browser window and
Close only dismisses UI state.

- [ ] **Step 4: Implement accessible dialog and status rail copy**

Use the existing accessible-dialog hook, `role="dialog"`, labelled title,
described body, French buttons `Réessayer` and `Fermer`, and a visible progress
state. Keep ChatGPT and local-agent statuses adjacent at all supported widths.

- [ ] **Step 5: Add E2E state coverage and run tests**

Run:

```bash
cd frontend
npm test
npm run typecheck
npm run lint
npm run test:e2e -- --grep "Chrome connection"
npm run test:a11y
```

Expected: all commands pass.

- [ ] **Step 6: Commit**

```bash
git add frontend
git commit -m "feat(ui): add clear ChatGPT Chrome connection flow"
```

### Task 6: Installer, Doctor, settings, and English documentation

**Files:**
- Modify: `scripts/install.sh`
- Modify: `scripts/cortex.sh`
- Modify: `scripts/uninstall.sh`
- Modify: `console/installer.py`
- Modify: `install/dependencies.json`
- Modify: `frontend/components/SettingsPanel.tsx`
- Modify: `README.md`
- Modify: `INSTALL.md`
- Modify: `docs/agent-installation.md`
- Modify: `docs/chatgpt-web-transport.md`
- Modify: `docs/security-model.md`
- Modify: `docs/testing.md`
- Modify: `docs/troubleshooting.md`
- Modify: `docs/user-guide.md`
- Modify: `orchestrator/browser-bridge/README.md`
- Test: `tests/test_installer.py`
- Test: `tests/test_start_local.py`
- Test: `tests/test_release_manifest.py`

**Interfaces:**
- Consumes: packaged `chrome-extension/` and connection status endpoint.
- Produces: a one-time manual extension installation flow and Doctor checks
  that distinguish installation, pairing, login, and ready states.

- [ ] **Step 1: Write failing install and documentation contract tests**

Assert the extension directory exists, manifest minimum version is 116,
installer prints the absolute load-unpacked path, agent guide requires explicit
approval, Doctor checks the bridge, all product links use HTTPS and are
allowlisted, and default docs no longer describe Playwright as the user path.

- [ ] **Step 2: Run focused tests and confirm RED**

Run: `.venv/bin/python -m unittest tests.test_installer tests.test_start_local tests.test_release_manifest -v`  
Expected: legacy WebBridge/Playwright assertions fail.

- [ ] **Step 3: Update install, Doctor, uninstall, and settings**

Do not try to silently install the extension. Print/copy its absolute path,
optionally open `chrome://extensions` only after user confirmation, validate
manifest files in Doctor, and remove only Cortex-managed runtime files during
uninstall. Settings shows `Chrome extension — recommended`; Playwright appears
under Advanced as `development only`.

- [ ] **Step 4: Rewrite public docs in English**

Document architecture, exact install steps, user/agent consent, permissions,
pairing, retry states, attachment/screenshot limits, troubleshooting, two-tab
writer behavior, and the honest live-test boundary. Link only official Chrome,
Python, Node, Ollama, and project pages.

- [ ] **Step 5: Run install and link verification tests**

Run:

```bash
.venv/bin/python -m unittest tests.test_installer tests.test_start_local tests.test_release_manifest -v
./scripts/verify-links.sh
```

Expected: all tests and link checks pass.

- [ ] **Step 6: Commit**

```bash
git add scripts console/installer.py install frontend/components/SettingsPanel.tsx README.md INSTALL.md docs orchestrator/browser-bridge tests
git commit -m "docs(install): ship the Chrome extension setup flow"
```

### Task 7: Full regression, live Chrome acceptance, and PR update

**Files:**
- Modify: `docs/verification/v0.5.0.json`
- Modify: `docs/verification/v0.5.0.md`
- Modify: `docs/release-checklist.md`
- Modify: `.github/RELEASE-v0.5.0.md`
- Modify: `primer.md`

**Interfaces:**
- Consumes: all prior tasks and the owner's authenticated Chrome session.
- Produces: redacted machine-readable and human-readable release evidence.

- [ ] **Step 1: Run the complete automated suite**

Run:

```bash
./scripts/test-all.sh
cd frontend && npm audit --audit-level=high
cd .. && gitleaks detect --no-banner
./scripts/check-public-privacy.sh
```

Expected: zero failed tests, zero high/critical npm vulnerabilities, zero
secrets, and zero privacy findings.

- [ ] **Step 2: Rehearse install, Doctor, and uninstall in an isolated home**

Use a temporary `HOME` and `CORTEX_HOME`. Prove installation prepares the
extension, Doctor reports `extension not paired` before pairing, and uninstall
removes only managed files. Preserve command output in the verification record.

- [ ] **Step 3: Perform the live same-window acceptance**

In the owner's normal Chrome profile:

1. install/load the unpacked extension with explicit approval;
2. open Cortex and press `Open and connect ChatGPT`;
3. prove the ChatGPT tab has the same `windowId` and no Chrome window was created;
4. prove the logged-out/retry dialog using a safe fixture or logged-out profile;
5. open one real conversation and send a harmless test message;
6. bind and send in two real conversations independently;
7. prove the third writer is rejected before send;
8. attach one small redacted file;
9. capture and attach one redacted screenshot;
10. close a bound tab and prove `TAB_CLOSED` recovery.

Do not store conversation text, account identity, cookies, or unredacted images.

- [ ] **Step 4: Update release evidence truthfully**

Set each gate to `passed` only when its fresh output exists. Keep any unrun live
gate `pending_owner_approval`; do not convert fixture success into live proof.

- [ ] **Step 5: Verify Git state and push the existing branch**

Run:

```bash
git status --short --branch
git log --oneline -8
git push origin codex/v050-release-qa
gh pr checks 1 --watch
```

Expected: clean worktree, pushed commits visible on PR 1, and all required
checks green.

- [ ] **Step 6: Final verification and goal completion**

Re-run the narrow connection tests plus release-evidence verifier. Mark the
goal complete only if no required implementation, automated gate, or approved
live gate remains.
