# Task 2 Report — Per-conversation state model

**Date:** 2026-07-26

**Branch:** `feature/v0.5.0`

**Base:** `cf0bd664a1900af26027cb4dff292276a9c494d1`

**Commit message:** `refactor(ui): isolate state by conversation`

## Delivered architecture

- Added a pure immutable reducer keyed by `ConversationKey`. Each
  `ConversationEntry` owns its summary, snapshot, messages, exact draft,
  staged `File`, load epoch/phase/error/freshness, chat run/stream epoch, send
  error, and mission state.
- Kept `selectedKey` independent from entry data. Selecting another entry
  preserves every cached entry and renders the selected cache while its live
  refresh is pending.
- Added a conversation controller with keyed request epochs, immediate abort
  of obsolete selected reads, a real `AbortController`, and a hard 10-second
  `Promise.race` deadline. Background polling reuses an in-flight read instead
  of restarting the deadline.
- Added a run-stream hook owning a `Map<ConversationKey, binding>`. Each
  binding contains the run ID, stream epoch, and `EventSource`; concurrent
  conversations do not share cleanup or state. Disconnect recovery uses a
  bounded three-attempt exponential backoff for both SSE and recovery-GET
  failures, and explicit close invalidates pending recovery by epoch.
- Added atomic provisional UUID rekeying on a delivery `canonical_url`.
  Canonical collisions are retained as an explicit `rekeyConflict` and never
  overwrite either entry.
- Made `ChatWorkspace` draft and attachment fully controlled. Async send
  handlers capture the initiating key, so success clears only that entry and
  any refusal or transport failure preserves the exact draft and `File`.
  Send-pending state and attachment controls are keyed too, so A and B can
  submit concurrently without changing a `File` already being uploaded.
- Attached mission IDs/details to conversation entries. Stale mission details
  are rejected by mission ID, and mission-list failures no longer rewrite the
  independent executor/pipeline truth.
- Migrated `CortexApp` away from global messages, run, selected mission, draft,
  attachment, load controller, selection coordinator, and singleton SSE
  source. Legacy `runtimeTruth` helpers remain because their existing tests
  still consume them; they were not removed prematurely.

## TDD evidence

### Initial RED

Command:

```text
corepack npm run test:unit -- lib/conversation-state.test.ts \
  hooks/useConversationController.test.tsx \
  hooks/useChatRunStream.test.tsx \
  components/ChatWorkspace.test.tsx
```

Observed result: four failed suites, zero collected tests. Every failure was
the expected unresolved production module (`conversation-state`,
`useConversationController`, or `useChatRunStream`).

### GREEN progression

- Reducer: 10/10 after the initial implementation, later 11/11 after the stale
  mission regression was added.
- Controller: 3/3 after the initial implementation, later 5/5 after StrictMode
  lifecycle and non-resetting deadline coverage.
- Streams: 3/3.
- Controlled workspace: 3/3.
- Focused integration including `CortexApp`: initially 20/20.

### Additional RED/GREEN regressions

1. Repeated background polls restarted one hung read three times before its
   deadline. RED observed `expected 1 call, received 3`; GREEN reuses the
   active promise and aborts it exactly at 10 seconds.
2. A late detail for `mission-old` replaced accepted `mission-new`. RED showed
   `missionId: mission-old`; GREEN rejects the stale detail and keeps the newer
   mission.
3. Independent review regressions were reproduced before fixes: stale recovery
   GET overwriting a newer run, non-terminal SSE disconnect without resubscribe,
   global send-pending state, screenshot attachment loss, duplicate provisional
   selection, full-history polling, cross-conversation mission display,
   cancellation during recovery, unbounded reconnects, mutable uploading files,
   and swallowed recovery-GET failures. The final focused suite is 39/39.

## Requirement coverage

| Invariant | Evidence |
|---|---|
| Independent A/B draft and exact `File` | Reducer and controlled component tests |
| A event cannot alter selected B | Reducer keyed update test |
| Stale load epochs and 10-second abort | Reducer and real controller hook tests |
| External/list A→B, cache-first, one B fetch | Real controller hook lifecycle test |
| Concurrent A/B streams and stale source events | Real stream hook test |
| Terminal A leaves B open | Real stream hook test |
| State rerender does not close SSE | Real stream hook rerender test |
| Unmount closes all active sources once | Real stream hook unmount test |
| Disconnect recovery is stale-safe and bounded | Real stream hook GET/SSE failure, cancel-race, backoff tests |
| Provisional delivery rekeys state and live source | Reducer plus real stream hook tests |
| Collision never overwrites | Reducer collision test |
| Third HTTP 409/transport failure preserves C and A/B | Reducer test |
| Success clears one entry only | Reducer plus controlled component test |
| Mission state remains conversation-scoped | Reducer stale/current mission tests |
| A/B POSTs remain concurrent | Controlled workspace deferred-POST test |
| Polling remains delta-aware | Controller background fetch test plus `light=1` integration |

## Verification

| Gate | Result |
|---|---|
| Node/npm contract | Node `v25.8.2` satisfies `>=22.12.0`; Corepack npm `11.18.0` |
| Focused unit/integration | Green |
| `corepack npm test` | Vitest 39/39 and runtime/privacy/image 32/32 |
| Focused coverage | 39/39; reducer 86.86% statements, controller 85.15%, stream hook 82.08% |
| `corepack npm run lint` | Green; Oxlint zero warnings and 6/6 lint-contract families rejected |
| `corepack npm run typecheck` | Green |
| `corepack npm run build` | Green; static routes `/` and `/_not-found` generated |
| `corepack npm run test:e2e` | 2/2 |
| `corepack npm run test:a11y` | 1/1 |
| Focused privacy test | 10/10 |
| Full dependency audit | 0 vulnerabilities |
| Production dependency audit | 0 vulnerabilities |

## Independent review

Four read-only review passes were completed against the evolving diff. The
initial NO-GO findings were converted into failing lifecycle/concurrency tests
before fixes. The final reviewer verdict is **GO**, with no remaining Critical
or Important finding and a clean `git diff --check`.

## Scope and generated files

- No dependency or lockfile changes.
- `frontend/out/**`, `frontend/coverage/**`, and
  `frontend/tsconfig.tsbuildinfo` were generated/updated by required gates and
  are intentionally excluded from the commit.
- `frontend/next-env.d.ts` was restored after Next.js rewrote its generated
  route import.
