# Testing

## Automated suite

```bash
cd cortex-bridge
python3 -m unittest discover -s tests
```

**114 tests, all passing** (2026-07-25). They cover:

- `test_protocol_state_store.py` — cortex.v1 extraction/validation, state
  machine adjacency, budgets, fingerprints, SQLite store
- `test_loop_mock.py` — the full mission loop against a mock orchestrator:
  execution, violations, duplicates, approvals, recovery
- `test_runner_mode_a.py` — ModeARunner end-to-end against the fixture
- `test_transport_fixture.py` — transport behaviors: lock, mismatch, tab
  closure, blockers, streaming, browser-restart re-attach, stop
- `test_missions_api.py` — the console API over HTTP (uvicorn thread +
  fixture): opt-in gate, full mission, approval flow, pause/resume/cancel,
  crash-safety (missions can always reach FAILED), stop-everything
- `test_probe.py` — DOM probe summary semantics, transport delegation,
  console endpoint
- `test_empty_reply_grace.py` — thinking-model empty-shell grace window,
  code-block stability signature, streaming resets

No test touches the network, a real browser, or the real chatgpt.com.

## Live verification matrix (real chatgpt.com, 2026-07-24)

Missions run against the production UI through WebBridge, workspace
`e2e-sandbox`, policy `workspace-write-with-approvals` unless noted.

| Test | Scenario | Expected | Result |
|---|---|---|---|
| A | Transport echo: contract in, one terminal BLOCKED decision out | 1 send, 0 tool execs, 1 valid decision | ✅ PASS (after send-mechanics fixes) |
| B | Read-only "list the workspace files" | list_directory executed, COMPLETED | ✅ PASS |
| C | Write `witness-c.txt` with human approval | WAITING_FOR_APPROVAL → approve → write → COMPLETED | ✅ PASS |
| D | Multi-iteration repair of `broken.py` | run → read → write → run → COMPLETE, prints `CORTEX_REPAIR_OK` | ✅ PASS (5 valid decisions) |
| E | "Read /etc/passwd" | Refusal: terminal BLOCKED, 0 tool execs | ✅ PASS (refused at layer 1) |
| F | Tab/conversation switch mid-mission | CONVERSATION_MISMATCH pause | ✅ Covered: fixture `test_16` + live identity checks in A–E |
| G | Browser refresh after a report | No duplicate execution (fingerprints) | ✅ Covered: duplicate-response tests + REPORT_RESEND_IGNORED paths |
| H | STOP EVERYTHING mid-mission | Mission CANCELLED (`STOP_EVERYTHING`), writes stop immediately | ✅ PASS (h3.txt never written) |
| **Final acceptance** | scan.py mission, zero copy-paste | scan.py created, run, rapport.txt non-empty, COMPLETED | ✅ PASS (4 valid decisions) |
| F (organic) | Human yanked the tab to another chat mid-mission | CONVERSATION_MISMATCH pause, no leak into the wrong chat; fast detection while awaiting | ✅ PASS (happened for real, twice) |
| I | Reuse an existing conversation (attach, no new chat) | Contract into the locked chat, self-heal after 2 context-confusion violations, COMPLETED | ✅ PASS |
| J | Harder task: zip `cortex-bridge` via `run_process`, verify contents + size | cortex-backup.zip (551 files) created and verified, COMPLETED | ✅ PASS (4 valid decisions) |
| K (2026-07-25) | Echo on a **thinking model** (gpt-5.6-thinking slug) | First run FAILED: empty assistant shell extracted during the paint gap → 3 false NO_DECISION_BLOCK (replies were perfect, verified by screenshot + later DOM read). After the empty-reply-grace fix: **COMPLETED, valid decision `ECHO-GRACE-OK`, terminal** | ✅ PASS after fix |
| L (2026-07-25) | Live DOM probe `GET /api/transport/probe` | composer `#prompt-textarea` ok, messages `[data-message-author-role]` ok (8 nodes), send/stop warnings only (idle page) | ✅ PASS |
| M (2026-07-25) | v0.2.0 console UI: sidebar conversations + UI-driven simple chat | 31 conversations listed (pinned/unread/preview); message sent by driving the real Next.js UI via WebBridge, run COMPLETED (`UI-DRIVE-OK`), latency tracked | ✅ PASS |
| N (2026-07-25) | Full autonomous mission launched from the real UI ("Nouvelle mission") | WAITING_FOR_CHATGPT → WAITING_FOR_APPROVAL → approve → COMPLETED, `ui-acceptance.txt` (`ACCEPTANCE-OK`) created in 2 iterations | ✅ PASS ([screenshots](screenshots/)) |
| O (2026-07-25) | ChatGPT model switch via `GET/PUT /api/models/chatgpt` | 6 models detected (FR Radix pill), round-trip Pro → Instantanée → Pro confirmed against the live switcher | ✅ PASS (after switcher fix) |

Notable real-world defects found by this matrix and fixed the same day:

1. ProseMirror requires `execCommand('insertText')` (silent no-op otherwise).
2. Voice-mode button matched the old send fallback selector.
3. Post-send verification raced the SPA render (false DELIVERY_UNCERTAIN).
4. Markdown consumes report fences — delivery markers must skip them.
5. Transient `/c/WEB:<uuid>` URLs broke resume re-attach.
6. `REQUEST_CONTEXT` with a null action crashed the loop.
7. ChatGPT guessed tool argument names — the contract now embeds schemas.
8. (2026-07-25) Thinking models paint an empty assistant shell before the
   reply: empty == empty was read as "stable" and extracted. Fix: 45 s
   empty-reply grace + stability signature covering code blocks.
9. (2026-07-25) The FR Radix model switcher (`button.__composer-pill`, label
   "Pro"/"Instantanée", no testid) was invisible to the old selector; plain
   `.click()` does not open Radix menus; React detaches the pill node after
   selection (stale-ref confirmation). Fix: pill selector + full pointer
   sequence + post-navigation polling + re-query after selection.

## Reproducing the live tests

1. Chrome with WebBridge connected to a ChatGPT session; Ollama running.
2. `cd console && python3 server.py`, open `http://127.0.0.1:8420`, opt in.
3. Launch missions per scenario above; approve writes when prompted.
4. Audit: `sqlite3 console/data/cortex.db` — tables `missions`,
   `orchestrator_decisions`, `tool_executions`, `approvals`,
   `transport_events`, `validation_results`.
