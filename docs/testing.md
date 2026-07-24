# Testing

## Automated suite

```bash
cd cortex-bridge
python3 -m unittest discover -s tests
```

**89 tests, all passing** (2026-07-24). They cover:

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

Notable real-world defects found by this matrix and fixed the same day:

1. ProseMirror requires `execCommand('insertText')` (silent no-op otherwise).
2. Voice-mode button matched the old send fallback selector.
3. Post-send verification raced the SPA render (false DELIVERY_UNCERTAIN).
4. Markdown consumes report fences — delivery markers must skip them.
5. Transient `/c/WEB:<uuid>` URLs broke resume re-attach.
6. `REQUEST_CONTEXT` with a null action crashed the loop.
7. ChatGPT guessed tool argument names — the contract now embeds schemas.

## Reproducing the live tests

1. Chrome with WebBridge connected to a ChatGPT session; Ollama running.
2. `cd console && python3 server.py`, open `http://127.0.0.1:8420`, opt in.
3. Launch missions per scenario above; approve writes when prompted.
4. Audit: `sqlite3 console/data/cortex.db` — tables `missions`,
   `orchestrator_decisions`, `tool_executions`, `approvals`,
   `transport_events`, `validation_results`.
