# Terminal acceptance matrix

No fixture result below proves live ChatGPT or an installed 0.6 release.

| Requirement | Required evidence | Current verdict |
| --- | --- | --- |
| Loopback API boundary | Real temporary HTTP server, hostile URLs/paths, no redirects/proxy | PASS — Task1, 15 tests and independent re-review |
| No duplicate send after ambiguity | One observed POST after timeout, explicit uncertainty | PASS — Task1 |
| CORTEX startup / help / version | Actual CLI subprocess and PTY | PASS — fresh combined 82-test run, including PTY |
| Full-screen TUI launch | Textual headless layout, draft/escape/new-chat and default dispatch tests | PASS — 82-test terminal/TUI slice; real Terminal.app visual inspection remains open |
| Shared conversation selection/history | Selected snapshot/messages and canonical URL adoption | PASS — selected snapshot, provisional refusal, invalid indices and PTY reading assertions; final re-review |
| Two writing conversations / third refused | Actual backend writer registry exercised through client | PASS — isolated Task2 real-API test |
| Exact messages and preserved drafts | Controller send/error tests | PASS — Task2 fix2, per-submission drafts and independent acknowledgements |
| Mission preflight / once approval | Payload, confirmation, action match, actual backend scoped acceptance | PASS — Task2, expected action identity gate; fixture-only |
| Follow / stop selected task only | Polling/cancellation and context-switch tests | PASS — exclusive activity, navigation resets targets, Ctrl-C, PTY response and explicit delivery confirmation |
| Shared settings without privilege reset | Real settings PUT regression + controller merge confirmation | PASS — Task2 settings/real API tests |
| ChatGPT / executor honest states | Backend-shaped fixtures, unavailable state remains usable | PASS for covered fixture states; live availability UNCLEAR |
| Chrome onboarding | Correct endpoint delegation; no silent consent or token output | PASS — consent/API and opening-failure tests; actual Chrome pairing UNCLEAR |
| Packaged launcher | Temporary wheel entrypoint works outside checkout | PASS — disposable wheel inspection/import reported in Task3; no user installation |
| Geometric UI card | Current browser demo + integrated screenshots, separate component review | PASS for targeted local review/observation; two minor followups recorded |
| Live provider mission | Authorized real browser/executor run | UNCLEAR — outside current authorization |
| Clean user installation | Separate explicit authorization and live validation | UNCLEAR — not performed in this task |
| Branch publication / main integration | User-authorized, conditional on relevant checks | Candidate published in draft PR 16; main integration remains blocked by release-evidence and live-acceptance gates |

## Scope controls
Original repository/runtime remains untouched. Work stays in the independent candidate.
The local dependency update was separately approved; its fresh npm audit has zero
findings. See `verification-v061.md` for the measured scope and remaining gates.
