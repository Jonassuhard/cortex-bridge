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

## Fix round 1 — external review findings

**Starting commit:** `990bdcb283d08961a2fe2938a5b6640384eb534b`

### Corrections

1. Recovery GET now receives an `AbortSignal`, one absolute deadline and the
   remaining budget. Each suspended attempt is aborted within its share of the
   same 10-second budget; close, replacement and unmount abort in-flight work.
   Exhaustion transitions the exact keyed run to `DELIVERY_UNCERTAIN` instead
   of leaving an indefinite active spinner.
2. Chat cancellation closes and invalidates the keyed stream/recovery before
   awaiting the cancel POST. The reducer applies cancellation by current run
   identity, independently of a reconnect-advanced stream epoch.
3. A chat POST acceptance stores an immutable submitted draft and exact `File`
   reference without clearing the composer. Only delivery proof clears matching
   values; newer edits survive, and failures/exhaustion preserve the original
   payload without automatic resend.
4. Canonical mission bindings rekey provisional entries atomically. Canonical
   collisions render a blocking French state, disable send/mission execution,
   select the existing canonical entry deterministically and discard only an
   empty safe provisional entry.
5. Pipeline controls and mission status now use only the selected
   conversation's mission. Global mission A cannot activate controls while B
   is selected.
6. Summary reconciliation retains omitted POST-pending, active-run and
   non-terminal-mission entries, while purging truly absent terminal/idle
   entries and selecting a valid remaining entry.
7. Removed the unused mission-list state and 3.5-second polling. Terminal A/B
   events share one deduplicated refresh timeout, cancelled on unmount.

### TDD evidence

- Initial focused RED: 20 failures out of 44 tests, covering all seven review
  findings before production corrections.
- Focused GREEN: 44/44.
- Added four `CortexApp` API → reducer/hook → rendered UI integrations for
  reconnect/cancel, provisional mission rekey, terminal refresh coalescing,
  unmount cleanup and absence of mission-list polling.
- A scheduler audit exposed a second-attempt timeout being cleared by the
  previous attempt's `finally`. A dedicated regression failed with a frozen
  `QUEUED` run, then passed after attempt-local timeout ownership.
- The first final review then found stale manual retry A1 → active A2, missing
  canonical rekey on terminal recovery, stale-mission rekey risk, premature
  uncertain-payload release and provisional-terminal retention. All five were
  reproduced with focused regressions before fixes. Manual retry and terminal
  canonical recovery are also exercised through real `CortexApp` API → state
  → rendered UI integrations.
- Final Vitest suite: 67/67.

### Fix round 1 verification

| Gate | Result |
|---|---|
| `corepack npm test` | 67/67 Vitest + 32/32 runtime/privacy/image |
| `corepack npm run test:coverage` | 67/67 + 32/32; reducer 88.72%, stream hook 90.86%, controller 89.06% statements |
| `corepack npm run lint` | Green; zero warnings, 6/6 lint-contract families rejected |
| `corepack npm run typecheck` | Green |
| `corepack npm run build` | Green; static `/` and `/_not-found` generated |
| `corepack npm run test:e2e` | 2/2 |
| `corepack npm run test:a11y` | 1/1, zero automated violations |
| Full and production dependency audits | 0 vulnerabilities |

### Fix round 1 independent review

The first read-only pass returned two Critical, two Important and one Minor
finding. Each was converted to a failing regression and corrected. The second
read-only pass found no remaining Critical, Important or Minor issue on the
five corrected paths and returned **Ready to merge: Yes**. `git diff --check`
is clean.

Generated `frontend/out/**`, `frontend/coverage/**` and
`frontend/tsconfig.tsbuildinfo` changes remain intentionally unstaged.

## Fix round 2 — lifecycle ownership and collision recovery

**Starting commit:** `fc4bf045cadd1957bf1361301474c4a736366abb`

### Corrections

1. Every initial send path now has one keyed owner, an abort signal and one
   absolute 10-second deadline. Message, attachment, screenshot and mission
   POSTs reject duplicate execution while a send, non-terminal chat run or
   non-terminal mission already exists. Attachment upload and delivery share
   the same signal; a late descriptor cannot trigger a second POST. Timeout
   preserves the exact draft and `File` and reports the deadline in French.
2. Cancellation is owned by `useChatRunStream` in a per-key task map. Duplicate
   clicks are rejected, the healthy SSE source remains followed while the
   bounded POST is pending, success terminalizes the matching run once, and
   terminal SSE truth aborts any late cancel request. Failure/timeout clears
   pending state and either keeps the healthy source or resumes bounded
   recovery when the source was lost. Unmount aborts every cancel request.
3. Manual recovery moved out of `CortexApp` into the same keyed recovery owner
   as automatic reconnect. It is deduplicated, visibly pending, abortable and
   deadline-bound; close, replacement and unmount invalidate it synchronously.
   A recovery response with a mismatched run ID consumes an attempt instead of
   freezing the old run.
4. Canonical collisions now expose two explicit choices. Resolution is allowed
   only when source and target own no active send, run, recovery, cancellation
   or mission. It atomically deletes the provisional key, selects the canonical
   key, preserves the exact chosen draft/`File`, and unions messages by ID
   without duplicates.
5. Mission inspection is selected-conversation scoped. If the global pipeline
   belongs to mission A while B is selected, the inspector receives neutral
   components, events, runtime execution, controls and mission identifiers;
   the global ChatGPT/executor availability rail remains visible. Selecting A
   restores its details.

### TDD evidence

- Initial `CortexApp` RED: 6/6 selected regressions failed with three execution
  POSTs for A1/A2, duplicate cancel POSTs, missing abort signals, duplicate
  manual recovery GETs, leaked mission-A inspector details and no bounded
  attachment request.
- Recovery RED: a mismatched recovery ID made only one GET and left the run
  queued instead of consuming both configured attempts and becoming uncertain.
- Collision RED: the reducer lacked `canResolveRekeyConflict` and the workspace
  lacked the two safe source/target actions.
- Additional RED regressions covered cancel timeout and manual A1 recovery
  invalidation when A2 starts.
- Focused GREEN command covering reducer, stream hook, workspace and real app
  integration: 68/68.

### Fix round 2 verification

| Gate | Result |
|---|---|
| `corepack npm test` | 79/79 Vitest + 32/32 runtime/privacy/image |
| `corepack npm run test:coverage` | 79/79 + 32/32; reducer 90.71%, stream hook 90.87%, controller 89.06% statements |
| `corepack npm run lint` | Green; zero warnings, 6/6 lint-contract families rejected |
| `corepack npm run typecheck` | Green |
| `corepack npm run build` | Green; static `/` and `/_not-found` generated |
| `corepack npm run test:e2e` | 2/2 |
| `corepack npm run test:a11y` | 1/1, zero automated violations |
| Full and production dependency audits | 0 vulnerabilities |
| `git diff --check` | Green |

### Scope and review handoff

- No dependency or lockfile changes.
- `frontend/next-env.d.ts` was restored after the build-generated route import
  changed it.
- `frontend/out/**`, `frontend/coverage/**` and
  `frontend/tsconfig.tsbuildinfo` remain intentionally unstaged.
- A fresh independent reviewer is delegated to the parent after this scoped
  commit; this report does not pre-empt that verdict.

## Fix round 3 — terminal truth, registry integrity and inspector isolation

**Starting commit:** `2482b657b6e693b89498b66f07940e16bb09b7fc`

### Corrections

1. Cancel success now validates and applies the returned backend `ChatRun`
   instead of manufacturing `CANCELLED`. Concurrent `COMPLETED`, `FAILED` and
   `CANCELLED` truth uses the normal reducer delivery/failure semantics,
   canonical rekeying and exact keyed source closure. A terminal SSE event,
   explicit close or replacement invalidates late cancel responses.
2. `subscribe` rejects a same-key replacement before constructing an
   `EventSource` while a live binding, recovery or cancellation still owns the
   previous non-terminal run. Different-conversation A/B streams remain
   concurrent; terminal or explicitly closed A1 permits A2.
3. Recovery and cancellation responses share structural `ChatRun` validation:
   known API state, matching ID, required string fields, valid ChatGPT
   conversation/canonical URL shapes, optional timestamp/error strings and
   finite non-negative latency values. Malformed same-ID payloads consume the
   bounded attempt budget and exhaust to `DELIVERY_UNCERTAIN` without opening a
   source.
4. The stream controller now exposes an explicit collision rekey contract.
   Source choice transfers the canonical epoch/registry so an uncertain run is
   retryable; target choice drops the provisional epoch and owned resources.
   Invalid stale retries are rejected before creating timerless tasks, and
   unmount aborts the transferred manual recovery.
5. Selected-conversation pipeline projection now neutralizes overall mission
   truth, components, events, queue, all runtime-execution identity/truth fields
   and all latency values. `ChatWorkspace` receives only this projection plus a
   separate global availability projection for ChatGPT connectivity and local
   executor readiness; it never receives the raw mission-A pipeline while B is
   selected.

### TDD evidence

- Initial selected RED: 10 expected failures across hook and app integration.
  They showed A2 epoch `2` instead of rejection, cancel response truth replaced
  by `CANCELLED`, one malformed recovery attempt followed by resubscription,
  missing registry `rekey`, missing neutral projection and mission-A values
  rendered in B.
- Registry audit RED: A2 was also accepted during an owned A1 recovery because
  the temporarily absent socket was mistaken for absent work. The dedicated
  regression failed with epoch `2`, then passed after the pre-source guard was
  extended to recovery/cancellation owners.
- Focused GREEN: reducer, stream hook, workspace and real app integration
  79/79.
- The first full gate exposed two historical static-render fixtures missing
  the new explicit availability prop. After updating those fixtures, the full
  command was rerun from the start and passed.

### Fix round 3 verification

| Gate | Result |
|---|---|
| `corepack npm test` | 90/90 Vitest + 32/32 runtime/privacy/image |
| `corepack npm run test:coverage` | 90/90 + 32/32; reducer 90.29%, stream hook 88.42%, controller 89.06% statements |
| `corepack npm run lint` | Green; zero warnings, 6/6 lint-contract families rejected |
| `corepack npm run typecheck` | Green |
| `corepack npm run build` | Green; static `/` and `/_not-found` generated |
| `corepack npm run test:e2e` | 2/2 |
| `corepack npm run test:a11y` | 1/1, zero automated violations |
| Full and production dependency audits | 0 vulnerabilities |

### Scope and review handoff

- No dependency or lockfile changes.
- `frontend/next-env.d.ts` was restored after the generated route import changed.
- `frontend/out/**`, `frontend/coverage/**` and
  `frontend/tsconfig.tsbuildinfo` remain intentionally unstaged.
- The parent will assign the fresh independent review after this commit.

## Fix round 4 — pending-operation guards and rekeyed owners

**Starting commit:** `751ca8aae6f9c378d194b45a1a28892ed246a9f4`

### Corrections

1. Recovery and cancellation pending state now blocks every new chat,
   attachment, screenshot and mission execution in both the workspace UI and
   the defensive `beginExecution` boundary. Draft editing remains available;
   Enter cannot abandon A1 or create an A2 POST.
2. A delivery canonical rekey transfers the in-flight cancellation map entry
   and mutable task key with the stream binding. Terminal cancel responses use
   that current canonical identity for validation, reducer dispatch, binding
   lookup, cleanup and terminal callback. `COMPLETED`, `FAILED` and `CANCELLED`
   each apply once under the canonical key; unmount still aborts the owner.
3. Synchronous `EventSource` construction failure returns a rejected
   subscription without mutating run state. Recovery then creates the next
   bounded owner with the same absolute deadline and incremented attempt; one
   factory failure can recover, while repeated failures exhaust truthfully to
   `DELIVERY_UNCERTAIN` with no source or phantom pending flag.

### TDD and verification evidence

- Initial selected RED: 6/7 failed for the expected causes: A2 send remained
  enabled, three canonical cancel responses left `VISIBLE_IN_CHATGPT`, and
  factory throws stopped recovery after one GET.
- Selected GREEN for the new regressions: 7/7.
- Final focused reducer/hook/workspace/app suite: 85/85.
- `corepack npm run lint`: green, zero warnings and 6/6 contract families.
- `corepack npm run typecheck`: green.
- `git diff --check`: green.
- Full release gates were not rerun under the explicit 16:30 hard cutoff; the
  immediately preceding round-3 full gates remain recorded above.

### Scope

- No dependency or lockfile changes.
- Generated `frontend/out/**`, `frontend/coverage/**` and
  `frontend/tsconfig.tsbuildinfo` remain intentionally unstaged.
- Fresh independent review remains delegated to the parent.
