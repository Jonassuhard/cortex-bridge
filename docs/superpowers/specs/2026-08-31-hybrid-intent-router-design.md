# Cortex Bridge Hybrid Intent Router Design

**Status:** Proposed — concept approved by the owner; written specification pending review
**Date:** 2026-08-31
**Target:** v0.5.4 candidate

## Decision

Cortex Bridge will keep one composer and add a hybrid intent-routing boundary
before the existing ChatGPT send and local-mission paths.

The router has three layers:

1. high-precision deterministic rules for obvious chat or local-work intent;
2. one local Ollama classification call for genuinely ambiguous candidates;
3. one local clarification question when required information remains missing.

The router may prepare an execution preflight. It must never start a mission,
grant a capability, approve an action, call a local tool, or authorize an
external ChatGPT send solely from a model result.

This document supersedes the v0.5.0 rule that pressing Enter always sends the
exact draft to ChatGPT. The unchanged safety invariant is stronger: no local
action starts before an explicit execution preflight and confirmation.

## Problem and verified evidence

The current empty-state copy tells the user to write a complete mission, while
the composer sends every Enter submission through `/api/chat/send`. Only the
separate `Exécuter…` button can open the mission preflight.

During the owner test on 2026-08-30, two drafts matching these anonymized forms
were delivered to ChatGPT as ordinary chat messages. The private personal folder
name is replaced with `cortex-live-test` in this public document:

- `cree moi un dossier cortex-live-test sur mon bureau`;
- `je veux que ce soit toi qui le cree`.

Both chat runs reached `COMPLETED`, but the same time window contained zero
missions, approvals, tool executions, mission transport events, or filesystem
changes. ChatGPT correctly explained that a normal web conversation could not
create the folder. Cortex incorrectly presented message delivery as the end of
the requested work.

The transport, Chrome extension, ChatGPT session, local service, SQLite store,
and executor health were all operational. The failure boundary was the composer
routing decision before either execution pipeline began.

## Goals

- Let obvious local-action requests open a useful preflight without requiring a
  remembered Chat/Mission mode or a second composer button.
- Keep normal chat exact, fast, and unchanged.
- Resolve ambiguous intent locally without adding a paid API or leaking the
  draft to a cloud classifier.
- Ask at most one clear question at a time inside Cortex, not inside ChatGPT.
- Show the original draft and Cortex interpretation before confirmation.
- Make workspace and capability authority server-owned and fail-closed.
- Preserve draft, attachment, conversation isolation, and the two-writer limit.
- Produce reproducible evidence that classification alone performs no send,
  mission creation, approval, or filesystem mutation.

## Non-goals

- No automatic local execution from a classifier result.
- No model-generated shell command, tool call, path permission, or approval.
- No cloud classifier and no OpenAI API integration.
- No automatic Ollama model download, model switch, or terms acceptance.
- No hidden system-message injection into ChatGPT Web.
- No network, deletion, or process capability for intent-routed v0.5.4
  missions. Manual process missions remain outside this guarantee and must
  disclose that reviewed commands are not OS-sandboxed.
- No semantic rewriting of normal chat messages.
- No attachment-only intent inference.
- No replacement of the deterministic policy engine or existing per-action
  approvals.
- No process capability for intent-routed missions in v0.5.4. The existing
  manual process path remains separate and must keep its truthful warning that
  reviewed commands are not OS-sandboxed.

## Product contract

### One composer, four routing outcomes

Submitting text through Enter or `Continuer` calls the same routing function and
produces exactly one of these outcomes:

| Outcome | User-visible result | External effect |
| --- | --- | --- |
| Exact chat | The draft enters the existing send lifecycle | One exact ChatGPT send |
| Local execution proposal | The execution preflight opens | None before confirmation |
| Clarification | Cortex asks one local question | None |
| Local notice | Cortex explains an unsupported capability | None |

`Shift+Enter` continues to insert a line. Input surfaces follow this normative
matrix:

| Input | Route |
| --- | --- |
| Enter or `Continuer`, text only | `POST /api/intent/route` |
| Enter or `Continuer`, text plus staged file | Route the text; retain the browser file until the explicit final choice |
| Enter or `Continuer`, staged file only | Existing exact ChatGPT attachment send; no intent route |
| `Exécuter…`, no staged file | Existing manual preflight; no classifier |
| `Exécuter…`, staged file | Local unsupported notice; no filename-only mission handoff |
| ChatGPT capture action | Existing capture send; no classifier |
| Router unavailable | Local `Réessayer / Envoyer à ChatGPT / Exécuter…` panel; no implicit action |
| Automatic routing disabled | Existing exact ChatGPT send |

For v0.5.4, a routed local-action candidate with a staged file receives a local
notice: routed missions do not consume attachment bytes yet. The file stays
staged and can still be sent through the explicit ChatGPT choice. A staged
attachment never starts a mission by itself.

### Obvious chat

Only deterministic high-precision chat rules or an explicit user selection may
produce an exact ChatGPT send. Questions and explanatory requests that match
those rules bypass Ollama and retain the current exact-send behavior. Examples
include:

- `Quelle est la capitale du Japon ?`
- `Explique-moi comment créer un dossier sur macOS.`
- `Donne-moi un exemple de commande mkdir sans l'exécuter.`

The router must not treat quoted instructions, tutorials, hypothetical actions,
or requests for explanation as local execution.

Exact means byte-preserving for the user-visible draft. The server may inspect
`draft.strip()` only to reject an empty message; it stores, digests, and
transmits the original `draft` unchanged, including leading or trailing spaces
and newlines at the Cortex-to-extension payload boundary. ChatGPT's editor may
normalize presentation whitespace; its normalized delivery confirmation is not
claimed as byte-level proof. A deterministic `send_exact_chat` result causes
the frontend to call the separate authoritative finalization endpoint
immediately with the submission idempotency key; it does not require a second
click.

### Obvious local action

High-precision rules recognize a local action only when an action verb and a
local object or target are both present and no explanatory exclusion applies.

Example:

`cree moi un dossier cortex-live-test sur mon bureau`

This opens a preflight with:

- original request preserved;
- structured interpretation visible and non-editable;
- workspace alias `desktop`, resolved by the server;
- exact operation scope limited to `file_exists("cortex-live-test")` and
  `create_directory("cortex-live-test")`;
- write required with an explicit later action approval;
- process, network, and deletion disabled;
- no chat send and no mission before confirmation.

Rules are deliberately conservative. A false negative can fall back to the
manual execution action. A false positive must still stop at a reversible
preflight with an explicit `Envoyer seulement à ChatGPT` alternative.

### Ambiguous action

Ambiguous candidates such as `Range tout ça proprement` are sent once to the
local intent model. Any Ollama result classified as chat still becomes a local
route-choice question: model confidence is never authority for an irreversible
external send. An incomplete, unsupported, or non-high-confidence result also
becomes a deterministic local question or notice generated from bounded codes.

Example:

`Où dois-je ranger ces éléments ?`

Suggested answers are server-known workspace aliases. The question and answer
remain inside Cortex. They do not create a chat run or mission.

### Follow-up clarification

The local clarification panel exposes `Ajouter une précision`. Its answer is
bound to the active opaque route identifier and never enters the ChatGPT
composer. A standalone composer message such as `Je veux que ce soit toi qui le
crées` does not inherit hidden conversational intent; without an active local
panel Cortex asks what must be created.

## Architecture

```text
Composer draft
      |
      v
Frontend routing state + request epoch
      |
      v
POST /api/intent/route
      |
      +--> deterministic high-precision rules
      |        | exact chat ----------> authoritative route finalization
      |        | local action --------> preflight only
      |        ` ambiguous
      |              |
      |              v
      |       local Ollama classifier
      |              |
      |              +--> chat -------> explicit local route choice
      |              +--> local ------> preflight only
      |              +--> missing ----> local clarification
      |              `--> unsupported -> local notice
      |
      `--> safe fallback -------------> explicit manual choice

Explicit chat choice -----------------> authoritative route finalization
Explicit final choice ----------------> POST /api/intent/routes/{route_id}/finalize
                                         | exact chat -> existing send internals
                                         ` mission ----> existing mission internals
Mission action ------------------------> policy + per-action approval + tool
```

Classification and durable final-action creation do not acquire a conversation
writer slot. Finalization creates the resource with
`writer_state=WAITING_FOR_WRITER` and an ineligible outbox. In the same explicit
user request, Cortex may attempt the separate CAS admission
`WAITING_FOR_WRITER -> ACTIVE`; only that CAS creates the
`ConversationWriterLease` and makes the outbox eligible. An exact chat begins at
successful admission, and a confirmed mission is not considered started before
successful admission. Capacity refusal leaves the resource waiting, and a later
free slot never starts it without an explicit retry.

`POST /api/intent/route` has no external or persistent product effect for every
outcome. It never creates a chat run, mission, upload lease, writer lease,
browser command, or tool call. Only the final-action boundary can do so: the
JSON finalization endpoint, or the attachment-reserve phase after an explicit
ChatGPT choice. If the client is interrupted between routing and automatic chat
finalization, the intact draft remains in Cortex.

## Global safety gates

The existing transport-consent requirement, `STOP EVERYTHING` latch, and
classic-Chat-only invariant remain authoritative across every new path.

- `TransportConsent` is durable and versioned. `SafetyState` stores a durable
  monotonic `authorization_epoch`, a state version, and a `stop_everything`
  latch that survives restart. Every consent grant, consent withdrawal, STOP,
  and STOP reset advances the same authorization epoch.
- Finalization records the consent version and authorization epoch, then rechecks fresh
  consent and `stop_everything == false` at upload reservation, before opening
  an upload file, upload claim, finalization, writer claim,
  `READY -> PREPARING_DISPATCH`, `PREPARING_DISPATCH -> DISPATCHING`, before
  every extension/browser command, mission
  resume, approval, and local tool transition. Streaming compares both the
  recorded authorization epoch and consent version at each heartbeat and aborts
  safely when either changes.
- Every dispatch/tool transition takes a shared in-process safety gate, then
  reloads authorization epoch, consent version, consent-active state, STOP,
  account, and surface while holding that gate. For an external dispatch, the
  gate remains held from the final check through the first possible browser
  effect. For a local tool, it remains held from the final check through the
  first filesystem effect and until the tool's durable terminal result or
  operation-specific uncertain result is committed. For `create_directory`,
  the first effect is `CREATE_PRIVATE`; STOP cannot return between that private
  mkdir, exclusive publication, inode verification, and the durable
  `CREATED`/`CREATE_OUTCOME_UNCLEAR` commit. STOP and consent withdrawal take
  the same exclusive gate. Each first commits its new state and authorization
  epoch durably, cancels all work that is proven not to have crossed the first-
  effect boundary, and returns only after that cancellation is durable.
  Whichever side acquires the gate first wins the race. If a browser effect may
  already have begun or the process crashed, the message becomes
  `DELIVERY_UNCERTAIN`; if a local effect may have begun without a durable
  outcome, the operation becomes its explicit uncertain state. Neither is
  replayed automatically.
- STOP also pauses missions and cancels every pre-tool state. Consent withdrawal
  cancels every external pre-dispatch state and prevents new external approval
  or dispatch; it does not claim that a local filesystem effect already begun
  was reversed. Restart recovery loads authorization and STOP before restoring
  writers, outboxes, approvals, uploads, or tools.
- `WAITING_FOR_WRITER`, `CLAIMED`, `READY`, `PREPARING_DISPATCH`, and proven
  pre-delivery failures become `CANCELLED_BY_STOP` before execute after the
  backend preparation/proof/attempt is authoritatively invalidated; an
  applicable provisional extension-ledger tombstone synchronizes before future
  prepare but does not block STOP while offline. Attachment ownership is
  released under the normal tombstone rules. No retry can clear STOP or restore
  consent.

The existing bodyless STOP-reset endpoint is removed. Reset is a separate,
explicit local UI action and is unavailable through general CORS. A bounded UI
session is bootstrapped for the exact configured Cortex frontend Origin and
held in browser memory; credentials remain disabled. Preparing reset returns a
two-minute, single-use 256-bit confirmation nonce bound to that UI session,
displayed STOP state version, and authorization epoch. The strict JSON reset
request carries `reset_attempt_id`, `expected_state_version`,
`expected_authorization_epoch`, and the nonce, plus the session token in a
dedicated non-simple header. The server does not pretend that this proves a
physical gesture: the gesture is an independently tested UI requirement.

Under the exclusive safety gate, reset CAS-clears only a currently latched STOP,
advances the authorization epoch, and atomically persists session ID,
`reset_attempt_id`, request digest, nonce digest, and canonical response. A
matching attempt/digest lookup happens before consumed-nonce validation, so a
lost response or restart returns the durable operation result; the response
envelope also includes a fresh current `SafetyState`, so a later STOP is never
misrepresented by the older `stop=false` result. A changed digest, reused
nonce under another attempt, stale version/epoch, missing session header, or
non-exact Origin returns a closed error. Reset never restores consent or
resurrects a cancelled, uncertain, paused, expired, or pre-STOP resource; every
later route, approval, resume, upload, or dispatch is a fresh explicit action
bound to the new epoch.

Before handle issuance and before every composer preparation, upload, text
insertion, or click, the extension must provide a fresh positive proof (at most
five seconds old) that `surface == classic_chat`, the extension instance and
storage generation match, and the signed-in account/workspace fingerprint
matches. A positively identified work surface fails with
`WORK_SURFACE_REJECTED`; `unknown`, missing/localized DOM, or expired proof fails
with `SURFACE_UNVERIFIED`; an unavailable fingerprint fails with
`ACCOUNT_UNVERIFIED`; a changed fingerprint fails with `ACCOUNT_CHANGED`. A
stable account/workspace fingerprint is required for every mutation-capable
handle; if unavailable, Cortex permits read-only status but no send, new
conversation, deferred dispatch, or resume.

## Backend boundary

### New module and endpoint

Create an isolated `console/intent_router.py` and include its router from the
console application.

`POST /api/intent/route`

Before routing, the server returns an opaque `conversation_handle` with each
conversation view. It resolves server-side to the canonical or provisional
conversation key, current generation, human title, extension instance/storage
generation, pairing session, positive classic-surface proof, and stable
account/workspace fingerprint. It is not a ChatGPT URL or ID, cannot be minted
by the client, and is never sent to Ollama. A changed or unavailable identity
revokes mutation authority immediately.

`POST /api/conversations/provisional` creates no browser tab or ChatGPT action.
It allocates a unique server-side provisional key, generation, and conversation
handle only from the latest fully verified extension/account/surface identity.
`Nouvelle conversation` calls it before enabling that conversation's composer.
Two provisional conversations never share the ChatGPT root URL as
identity. On first confirmed delivery, the server atomically rekeys each
provisional binding to the distinct canonical conversation returned by the
transport. A service restart invalidates unfinalized provisional handles; the
frontend preserves their drafts and requests fresh handles before rerouting.

Request:

```json
{
  "conversation_handle": "server-issued-conversation-handle",
  "request_epoch": 42,
  "draft": "cree moi un dossier cortex-live-test sur mon bureau",
  "locale": "fr",
  "has_attachment": false,
  "attachment_descriptor": null
}
```

A clarification is a separate discriminated request:

```json
{
  "route_id": "opaque-single-use-route-id",
  "clarification": {
    "field": "target",
    "value": "desktop"
  }
}
```

Constraints:

- `draft`: non-empty UTF-8 string, at most 8,000 characters;
- `conversation_handle`: opaque server-issued handle with 256 bits of entropy,
  encoded as exactly 43 unpadded base64url characters;
- `request_epoch`: non-negative frontend sequence used only to discard stale
  responses; it grants no authority;
- `locale`: `fr` or `en`;
- `has_attachment`: boolean only;
- `attachment_descriptor`: required only when `has_attachment` is true and
  forbidden when false. Its basename is 1–255 UTF-8 bytes with no control,
  separator, `.` or `..`; size is an integer from zero through the configured
  hard attachment limit; MIME is empty or 1–127 visible ASCII characters
  matching MIME type/subtype token grammar; modified time is an integer from
  zero through JavaScript's safe-integer maximum; and SHA-256 is exactly 64
  lowercase hexadecimal characters. It contains no path or file bytes and is
  never sent to Ollama;
- `route_id`: opaque, single-use, 256-bit value encoded as exactly 43 unpadded
  base64url characters and bound server-side to
  the conversation handle, conversation generation, original draft digest,
  request epoch, and accepted decision;
- `clarification`: one bounded structured answer allowed by the pending
  missing-field code; target answers are enums, artifact names are at most 255
  UTF-8 bytes, and one optional free-text precision is at most 512 characters;
- extra request fields are rejected;
- no conversation URL, title, account identifier, browser target, history,
  absolute path field, or file content is accepted.

Response:

```json
{
  "schema_version": 1,
  "route_id": "opaque-single-use-route-id",
  "expires_at": "2026-08-31T00:05:00Z",
  "decision_digest": "server-digest",
  "action": "open_execution_preflight",
  "source": "rules",
  "execution_intent": {
    "intent": "local_change",
    "confidence": "high",
    "operation": "create_directory",
    "artifact_name": "cortex-live-test",
    "target": "desktop",
    "missing": [],
    "operation_scope": {
      "tools": ["file_exists", "create_directory"],
      "relative_paths": ["cortex-live-test"],
      "allow_read": false,
      "allow_write": true,
      "allow_processes": false
    }
  },
  "preflight": {
    "conversation_title": "Conversation title",
    "workspace_candidate": {
      "catalog_entry_id": "server-issued-catalog-entry",
      "catalog_revision": 7,
      "alias": "desktop",
      "label": "Bureau",
      "display_path": "~/Desktop"
    },
    "mission_id": "preallocated-mission-id",
    "cloud_payload_preview": "server-built immutable contract bytes"
  },
  "model_used": null,
  "latency_ms": 2,
  "degraded_reason": "none"
}
```

Allowed top-level values:

- `action`: `send_exact_chat | open_execution_preflight | ask_user |
  show_local_notice`;
- `source`: `rules | ollama | safe_fallback`;
- `degraded_reason`: `none | unavailable | model_not_loaded | timeout |
  invalid_response | busy | oversized | cold_race`.

Responses are a discriminated union. Every terminal route includes a
`decision_digest`; for a mission proposal it covers the complete preflight and
cloud preview. `ask_user` includes one server-generated
question kind and a bounded option list. `show_local_notice` includes one
localized reason code and only `Modifier la demande` and explicit
`Envoyer à ChatGPT` actions. Fields from another variant are forbidden.

All request and response models use strict schemas with extra fields forbidden.
Every JSON intent endpoint rejects a body larger than 32 KiB before parsing;
the separate raw upload endpoint enforces the confirmed descriptor and hard
attachment limit while streaming. The server keeps at
most 128 unconfirmed routes globally and eight per conversation handle in
bounded memory, with a five-minute TTL and oldest-unconfirmed eviction. An
expired, evicted, consumed, or post-restart route returns `410 ROUTE_EXPIRED`
without any side effect unless a durable final action already exists. Each
clarification consumes its current route ID and returns a fresh successor route
ID; replaying the old ID cannot create or progress a new action. A duplicate
finalization with the same idempotency key is the sole exception and returns
its durable prior result.

### Authoritative finalization endpoint

`POST /api/intent/routes/{route_id}/finalize`

The request carries an `Idempotency-Key` header and a strict discriminated
action. A mission finalization body contains only:

```json
{
  "action": "start_mission",
  "conversation_handle": "server-issued-conversation-handle",
  "catalog_entry_id": "server-issued-catalog-entry",
  "catalog_revision": 7,
  "decision_digest": "server-digest"
}
```

An exact-chat finalization contains `action`, `conversation_handle`,
`decision_digest`, and an `upload_id` only when the terminal route declared an
attachment. Finalization is JSON-only. It never accepts client-supplied message
text, file bytes, mission objective, operation scope, tools, policy,
capabilities, absolute workspace, or conversation URL.

```json
{
  "action": "send_exact_chat",
  "conversation_handle": "server-issued-conversation-handle",
  "decision_digest": "server-digest"
}
```

The server reloads the route record, resolves the conversation handle, and
verifies conversation generation, expiry, draft digest, workspace catalog
entry/revision, decision digest, selected action, attachment presence, and the
staged file's complete canonical descriptor plus recomputed content digest when
applicable. Mission finalization
then revalidates the root and creates its durable `WorkspaceGrant` atomically
with the mission resource; routing never creates a grant.
A different conversation returns `409 ROUTE_CONVERSATION_MISMATCH`; a changed
grant or preview returns `409 PREFLIGHT_CHANGED`. Only then does the server
construct the exact chat run or structured mission through existing internals.
Manual chat and `Exécuter…` endpoints remain separate flows and cannot consume
a route ID.

For `start_mission`, `has_attachment: true` returns
`422 ATTACHMENT_UNSUPPORTED_FOR_ROUTED_MISSION` before upload, token creation,
writer admission, or mission creation. Exact-chat file delivery uses two
server-ordered endpoints after the user has explicitly chosen ChatGPT:

1. `POST /api/intent/routes/{route_id}/uploads/reserve` validates consent, STOP,
   route, conversation identity, classic surface, decision digest, descriptor,
   and idempotency key. In one transaction it consumes the route, creates or
   returns the durable `final_action` plus `UPLOADING` chat resource containing
   exact draft and `DestinationBinding`, persists a `RESERVED` upload lease, and
   returns a non-secret opaque `upload_id`. Before reserve, the browser generates
   and retains a separate 256-bit, 43-character base64url upload authorization
   token and sends it in `X-Cortex-Upload-Authorization`; the lease stores only
   its HMAC. An idempotent reserve retry reuses that client-held token, so a lost
   response cannot orphan authority. The strict JSON body contains only
   `conversation_handle`, `decision_digest`, and the canonical
   `attachment_descriptor`. It creates no outbox or writer admission;
2. `PUT /api/intent/uploads/{upload_id}` accepts only the raw file body with the
   `application/octet-stream` media type, counts bytes against the confirmed
   size and hard limit without trusting `Content-Length`, streams under the
   upload state machine, and returns only after `FSYNCED` evidence is durable.
   `PUT`, status lookup, finalization, and cancel all require the token in
   `X-Cortex-Upload-Authorization` before opening or changing upload state. The
   token never appears in a URL, log, diagnostic, durable raw field, or error.

`GET /api/intent/uploads/{upload_id}` is a read-only, owner-bound result lookup
for the current final action. It exposes only the upload state and permitted
next action. It is the recovery path when the raw `PUT` response is lost: an
already `FSYNCED` upload proceeds to finalization without retransmitting bytes.
An interrupted upload that is not durably `FSYNCED` is terminalized and requires
a new route; Cortex never resumes or appends to a partial body. The pre-dispatch
cancel endpoint aborts the browser request, wins or loses by CAS against
finalization, waits for the server upload owner to stop, and may return `Aucun
message n'a été envoyé.` only after the action, resource, lease, and any READY
outbox are durably non-dispatchable.

Raw upload authority intentionally lives only in page memory. After a renderer
crash, reload, or tab close, Cortex may rediscover an aggregate `UPLOADING`
final action through the normal UI-session/action view but cannot use its upload
lease. `POST /api/intent/final-actions/{id}/abandon-lost-upload` is a monotonic
no-send recovery endpoint: strict JSON contains the freshly issued
`conversation_handle`, action `state_version`, and reason `TOKEN_LOST`, and the
request requires the current `X-Cortex-UI-Session`. It never accepts file bytes
or an upload token. Under the per-upload mutex it may only fence/stop a stream
and CAS-terminalize a resource still `UPLOADING` with no claim, outbox, writer,
or execute state. If finalization won, it returns the current send state and the
UI cannot claim that nothing was sent. Successful abandonment keeps a tombstone,
closes/quarantines bytes, and permits a wholly new route/file selection; doing
nothing leaves the non-dispatchable action to its normal expiry.

Finalization requires that exact `FSYNCED` upload, recomputes and compares every
route/lease metadata field, and compares independently observed byte count and
content digest; Cortex does not pretend to derive original basename,
last-modified time, or MIME from raw bytes. One transaction then claims the
lease, transitions the one preallocated chat resource from `UPLOADING` to
`QUEUED`, and creates its single `READY` `CHAT` outbox. A missing, replaced, or
different file returns `409 ATTACHMENT_CHANGED`, preserves the browser file,
and terminalizes the existing `UPLOADING` resource as a non-dispatchable
tombstone; it never creates an outbox or writer admission and requires a new
route.
The reserve/result lookup is durable, so route expiry or service restart during
upload cannot lose the confirmed action or create a second chat resource.

### Required integration changes

- add `"intent_router"` and `"rename_exclusive"` to the explicit `py-modules`
  list for `console/intent_router.py` and `console/rename_exclusive.py`; the raw
  upload design adds no multipart runtime dependency or lockfile package;
- teach the frontend API client to stream a raw `PUT` body without JSON encoding
  and to send `Idempotency-Key` on reserve/finalization;
- preserve the existing exact loopback CORS allowlist for `GET`, `POST`, `PUT`,
  `DELETE`, `OPTIONS`, `Content-Type`, and `Last-Event-ID`, then add only
  `Idempotency-Key`, `X-Cortex-UI-Session`, and
  `X-Cortex-Upload-Authorization`. Keep exact allowed origins and negative tests
  for every other origin/method/header; never use wildcards and never treat CORS
  as authentication;
- bump the extension protocol, pin the manifest key/expected extension ID,
  implement one-time public-key enrollment plus signed pairing challenges, and
  persist instance/storage generation separately from the non-exportable
  enrollment key. The content script supplies a single-use signed surface,
  account, destination, payload, and epoch proof immediately before mutation.
  Older or unenrolled protocol clients remain read-only;
- add the SQLite schema and migrations for `chat_runs_v2`, `final_actions`,
  durable attachment ownership, and the transport outbox;
- implement the macOS-only system `renameatx_np(..., RENAME_EXCL)` wrapper in
  `console/rename_exclusive.py`; if the module, symbol, or exclusive semantics
  are unavailable, intent-routed directory creation is disabled before
  preflight and the manual fallback remains;
- run a one-time, locked, transactional, idempotent, schema-version-aware
  migration from historical chat-run JSON before accepting writer traffic. It
  classifies by durable evidence, never by terminal state alone: a run with a
  durable delivery receipt or proven pre-delivery failure imports as history;
  `FAILED + DELIVERY_UNCERTAIN`, any crash around transport, and any run without
  definitive evidence import as uncertain and are never resent;
- every uncertain legacy run is `legacy_reconciliation_only` and strictly
  non-dispatchable. Current pairing, extension, account, or surface identity
  never upgrades historical evidence into a modern `DestinationBinding`;
- when an uncertain legacy run has a canonical `/c/` URL, create a synthetic
  migrated `final_action`, non-dispatchable `LegacyDestinationEvidence`,
  reconciliation ID, and tombstone. The evidence contains only historical
  schema version, canonical URL, source digest, timestamps, and observed status;
  it may block that canonical conversation but cannot produce an outbox;
- every legacy run with only the ChatGPT root URL becomes
  `UNBOUND_LEGACY_DELIVERY_UNCERTAIN`, even when it contains a `provisional:*`
  key. The provisional key distinguishes reconciliation records only and never
  becomes a destination. These records block only new-conversation writes until
  explicit reconciliation, while canonical conversations and global writer
  slots remain available;
- preserve unambiguous legacy attachment ownership. Every ambiguous file gets a
  durable `LegacyAttachmentQuarantine(REVIEW_REQUIRED)` record containing its
  verified owner-only quarantine-root ID plus root device/inode, parent-relative
  components plus parent device/inode, exact leaf bytes, file device/inode,
  size/digest, source record, state version, and reconciliation ID. Automated
  deletion is unavailable for a file outside that verified private root or
  filesystem. It is never dispatchable or collectable until an explicit CAS
  disposition enters the dedicated capture/delete state machine; no import
  guesses ownership or silently deletes it. Every legacy block has a distinct
  reconciliation ID and tombstone;
- malformed, truncated, or unsupported legacy input enters
  `MIGRATION_REVIEW_REQUIRED`; writer traffic stays disabled while the local UI
  exposes diagnostics and retry. A migration marker and source digest prevent
  duplicate import and make crash/second-start recovery idempotent;
- make an installed-wheel smoke test import the router, run its migrations, and
  exercise positive and negative JSON/raw-upload/reset CORS preflights from the
  configured frontend origins to `http://127.0.0.1:8420`. On macOS the installed
  wheel must also import `rename_exclusive`, detect capability, publish a private
  disposable directory with `RENAME_EXCL`, verify its inode, and prove a second
  publish returns `EEXIST` without replacement. Missing support disables the
  routed operation before its preflight can be shown.

Legacy evidence classification is a compiled, versioned policy rather than an
inference from status text. For each supported schema, `LegacyEvidencePolicy`
names required fields, allowed values, linkage rules, and precedence. A positive
delivery receipt is valid only when it carries a supported schema version,
`run_id`, `dispatch_attempt_id`, keyed payload digest and `key_id`, canonical
destination plus binding digest, command/receipt sequence, and timestamp, and
all links validate against the same source record and retained key. A proven
pre-delivery failure requires a supported receipt that fixes command phase
strictly before the first extension command and names an allowlisted terminal
reason. Terminal state, `delivered_at`, `completed_at`, canonical URL, and error
text alone never prove either outcome.

The historical unversioned chat-run JSON currently written by Cortex has no
attempt-linked receipt and therefore cannot become `PROVEN_DELIVERED` or
`PROVEN_PREDELIVERY_FAILURE`, even for `COMPLETED`. Its structurally valid rows
import as `legacy_reconciliation_only`; canonical rows block only their exact
conversation and root/provisional rows use the unbound blocks above. Per-row
unknown fields, missing links, contradictory state/timestamps/errors, digest or
destination conflicts, and unsupported receipt versions take the same uncertain
path. A malformed/truncated top-level envelope or unverifiable source digest
keeps migration in `MIGRATION_REVIEW_REQUIRED`. Every decision persists policy
version, observed schema, source digest, selected category, priority rule, and
machine-readable reason. Precedence is: invalid envelope; row contradiction;
fully linked delivery receipt; fully linked pre-delivery receipt; otherwise
legacy reconciliation. Current extension/account identity can never fill a
missing historical link.

### Intent decision schema

The local model may propose only:

```json
{
  "intent": "chat | local_change | unclear | unsupported",
  "confidence": "high | medium | low",
  "operation": "create_directory | other | unsupported",
  "artifact_name": "string | null",
  "target": "desktop | documents | downloads | default_workspace | unspecified",
  "missing": [
    "target | artifact_name"
  ]
}
```

Validation rules:

- additional properties are rejected;
- every producer of `artifact_name` yields 1–255 UTF-8 bytes, preserves user
  case, and contains no control character, slash, path separator, dot segment,
  code fence, or shell syntax;
- `artifact_name` must match a contiguous span of the original draft or an
  explicit structured clarification byte-for-byte; otherwise the server asks
  the user and never normalizes case silently;
- a target is an alias, never an arbitrary or absolute path;
- objective text, capabilities, commands, tools, approvals, operation scopes,
  paths, network, and deletion are not model fields;
- the server builds the localized display summary, mission objective,
  capabilities, and operation scope from reviewed templates and validated
  slots;
- `low`, `unclear`, contradictory, or incomplete output becomes `ask_user`;
- an Ollama `chat` result always becomes `ask_user`, regardless of confidence;
- in v0.5.4, `create_directory` is the only intent-routed operation;
- `other`, file creation, inspection, organization, process, network,
  destructive work, and every unregistered operation require the manual route
  choice or a local unsupported notice until they have a complete reviewed
  template, operation scope, target-exists behavior, and test matrix;
- only a complete high-confidence `create_directory` decision can open a
  routed preflight;
- `model_used` remains null unless a valid response was received and accepted.

### Deterministic rules

Rules execute before Ollama and return only high-confidence results or
`ambiguous`. They are implemented as a pure module with a table-driven corpus,
not scattered JSX regular expressions.

The corpus includes:

- French and English local action verbs;
- local objects such as folder, file, workspace, project, terminal, local site,
  Desktop, Documents, and Downloads;
- explanatory exclusions such as `explique`, `comment`, `exemple`, `sans
  exécuter`, quoted instructions, and hypothetical phrasing. A polite question
  such as `Peux-tu créer…` remains a local action when it asks for an effect,
  not information;
- negation and unsupported destructive/network requests. Negation yields chat
  only when it unambiguously denies every local action; mixed wording such as
  `Ne l'envoie pas à ChatGPT, crée le dossier` becomes `ask_user`;
- accent, punctuation, whitespace, and case variants.

Rules never infer a custom path or permission.

## Local Ollama classifier

### Model selection

The initial recommended raw model is `qwen3.5:9b`, which is already installed
on the owner's machine. The router does not use the `orchestra-executor` or
`orchestra-executor-fallback` aliases because their prompts and tool semantics
belong to execution, not classification.

The model is configurable as `intent_router_model`. Public installation keeps
it optional and never pulls it automatically. If the configured model is not
installed, the router uses the safe fallback.

An optional `intent_router_prewarm` setting may load the configured model in
the background after explicit user opt-in and after the application is usable.
The UI explains the local memory/energy impact. Cortex records whether the model
was already loaded and whether it started its own keepalive renewals. `Arrêter
le maintien actif` cancels only Cortex's future renewals; it never sends an
unload request or claims ownership of a model in the shared Ollama daemon. The
model may therefore remain loaded for another tool or until Ollama evicts it.
If `/api/tags` contains the model but `/api/ps` does not, the Enter path does not
call `/api/chat` and returns `model_not_loaded` within a 250 ms budget. Cortex
does not claim that a cold load was impossible: an already-loaded model may be
evicted between observation and use. Such a race is reported as `cold_race`,
which means only "timeout after a loaded-state observation"; it is not proof of
the daemon's internal state. Cortex falls back without retry.

### Call contract

- endpoint: loopback-only Ollama `/api/chat`;
- `stream: false`;
- JSON Schema format;
- no tools;
- temperature zero;
- context budget 2,048 tokens;
- short bounded output;
- one call per routing attempt;
- warm-model absolute deadline of two seconds;
- one in-flight classification and a bounded queue of two; further requests
  return `busy` immediately;
- no cloud fallback and no automatic retry;
- no intentional cold-load request from a composer submission.

The two-second deadline is the public response boundary. The local HTTP worker
retains the classifier slot until Cortex observes its own request future return,
raise, or connection close; Cortex never claims this proves that the Ollama
daemon stopped working. A timeout or `cold_race` opens a circuit breaker for at
least 30 seconds and until that local future has ended. A single half-open probe
may then run; failure reopens the breaker. While open, classification returns
the manual choice without contacting `/api/chat`.

The server measures the complete serialized system instruction, schema, input,
and reserved output before calling Ollama. An oversized draft is never silently
truncated; it receives the safe manual choice. The client ignores proxy
environment variables and connects only to the configured loopback endpoint.

The existing executor `_chat_sync()` must not be reused: it exposes a process
tool and has a 180-second mission timeout.

The system instruction treats the draft as untrusted data and permits only the
intent schema. Backend validation remains authoritative even when Ollama claims
that its output follows the schema.

### Safe fallback

When Ollama is missing, not loaded, caught in a cold race, busy, timed out,
oversized, or invalid, Cortex keeps the draft and asks:

`Veux-tu envoyer ce texte à ChatGPT ou préparer une exécution sur ce Mac ?`

No request is sent elsewhere while this choice is pending.

## Clarification state

Clarification state is isolated by the server-resolved canonical or provisional
conversation key and includes:

- opaque `route_id` and server-issued `conversation_handle`;
- immutable original draft;
- accepted structured decision so far;
- missing-field code;
- current request epoch;
- at most one visible question at a time;
- at most two resolution calls before mandatory manual choice.

Changing conversation, editing the draft after submission, closing the dialog,
or cancelling the request invalidates the epoch. Late responses are ignored.
Clarification and finalization both resolve the handle again; a handle for
another conversation fails with `409 ROUTE_CONVERSATION_MISMATCH`.

Deterministic option answers update the structured decision without another
model call. A bounded free-text answer may trigger one additional local
resolution call. Clarification text is not persisted to chat runs, missions, or
the SQLite mission store before confirmation.

The question appears in a non-persistent panel directly above the composer,
never in the conversation message list:

```text
Question locale de Cortex
Où veux-tu créer ce dossier ?
[Bureau] [Documents] [Téléchargements] [Espace par défaut]
[Ajouter une précision] [Modifier la demande]
```

Focus moves to the first valid option. Escape closes the panel, invalidates the
route, and returns focus to the intact draft.

## Execution preflight

The preflight must display:

- `Ta demande`: the immutable original draft;
- `Cortex a compris`: a non-editable structured summary built by the server,
  preserving names exactly as typed;
- human conversation title, never an internal key;
- server-resolved workspace label and exact path;
- exact operation scope, required capability, and tools that may be proposed;
- executor and limits;
- a separate list of data that will be sent to ChatGPT after confirmation;
- the exact server-built cloud payload preview for a routed mission;
- disclosure that later bounded iteration reports will be sent through the same
  selected conversation as the mission progresses;
- explicit statement that no action has started.

Actions:

- `Démarrer la mission sur ce Mac`: confirms the preflight and creates one
  mission, but does not approve a later write action;
- `Envoyer seulement à ChatGPT`: sends the original draft and retained browser
  file, when present, exactly once;
- `Modifier la demande`: invalidates the route, returns focus to the exact
  draft, and requires a complete reroute after editing;
- `Annuler`: closes the proposal without any send or mission.

A local-change intent displays `Écriture requise, chaque modification sera
approuvée`. The required write capability is not an optional checkbox that can
be disabled while leaving an impossible mission. Existing per-action write
approvals remain mandatory, with specific copy such as `Autoriser la création
de « cortex-live-test » dans Bureau`.

Intent-routed v0.5.4 missions force process, network, and deletion off. The
manual execution path remains separate and must disclose that reviewed process
commands are not OS-confined and may affect paths outside the workspace, access
the network, or perform destructive actions after approval.

The authoritative mission payload is constructed from the confirmed
server-owned `ExecutionIntent` fields and route digest, never from display copy
or a stale draft. A routed mission does not send the raw draft to ChatGPT.
When producing `open_execution_preflight`, the server preallocates the mission
ID and renders one immutable routed-contract byte string from that ID, the
registered operation template, human workspace label, exact tool list, and
relative operation scope. It contains no absolute workspace path. The route
record stores those bytes and the response previews them verbatim.

Finalization persists the same bytes with the pending mission. The runner
receives `routed_contract_bytes` and bypasses its general contract renderer; it
must never regenerate the routed payload from the absolute workspace or a wider
tool registry. The raw draft stays local. An explicit exact-chat choice still
sends the raw draft unchanged at the Cortex-to-extension payload boundary.

Later mission reports are rendered once from server templates and already
sanitized evidence. They contain only relative paths, workspace aliases,
bounded tool results, and protocol state; never canonical local paths, account
identity, grants, secrets, or raw diagnostics. Each report is persisted as
immutable bytes in its own outbox before dispatch. The preflight discloses these
future categories even though their exact bytes do not yet exist.

Before an exact-chat choice, an attachment remains only a browser `File` plus
local UI metadata; no server upload lease is created. After the explicit choice,
reserve and raw upload run before finalization. Reservation creates the one
non-dispatchable `UPLOADING` chat resource. Validation failure terminalizes
that resource and closes or quarantines its lease for cleanup before claim,
`QUEUED`, outbox creation, or writer admission. Failure during the atomic claim
and queue transaction rolls it back; it never exposes a claimed upload without
its one queued resource and one outbox. A retry with the same idempotency key
resolves to at most one upload record and one chat resource. Mission
finalization rejects attachments before upload in
v0.5.4; neither routed nor manual mission UI may claim to consume a file when
only its name would reach the executor.

The attachment path is singular: when text plus a staged file resolves to local
intent, `/api/intent/route` returns `show_local_notice` and no mission preflight
is rendered. The routed HTTP 422 remains defense in depth. In v0.5.4 every
mission-creation endpoint, including the legacy/manual endpoint, rejects any
file-bearing attachment field and requires legacy `attachment_tokens` to be
absent or empty. A non-empty list returns HTTP 422 before token resolution,
writer admission, mission creation, or ChatGPT transport. UI notices are not
the security boundary.

## Server-owned workspace authority

The current mission API accepts a client-provided absolute workspace and then
uses that same path as its allowlist. The intent router must not build on that
trust boundary.

Add a server-owned workspace catalog with stable aliases:

- `default_workspace`;
- `desktop`;
- `documents`;
- `downloads`.

Additional project folders require a separate explicit local registration
action. They receive an opaque catalog identifier; a client can never register
or authorize a path merely by including it in a mission request.

Only roots that exist, are owned by the current user, are not symlinks, and pass
a new dedicated sensitive-workspace validator are returned. The model sees
aliases only.

A durable `WorkspaceCatalogEntry` is provisioned during startup for standard
aliases or by the separate registration action. It contains the opaque catalog
entry ID, revision, canonical path, label, expected owner/type/device/inode, and
registration provenance. `/api/intent/route` reads this entry and returns only
the candidate ID, revision, label, alias, and local display path. It does not
mutate SQLite or create authority.

A durable mission-scoped `WorkspaceGrant` is created only during finalization
after fresh validation. It records:

- opaque grant ID, catalog entry ID, and catalog revision;
- canonical path and user-facing label;
- UID, type, device, and inode observed at grant time;
- whether descendants may be selected;
- grant creation source and timestamp.

The validator rejects candidates equal to `/` or the whole home directory. For
protected subtrees such as `CORTEX_HOME`, browser profiles, credential/keychain
locations, secret stores, and device paths, it rejects a candidate that is
equal to, descends from, or is an authority-bearing ancestor of that protected
subtree. It does not reject Desktop, Documents, Downloads, or another approved
candidate merely because that candidate is a descendant of home.

The new frontend echoes the candidate `catalog_entry_id` and revision. At
mission finalization the server resolves it again, verifies path identity,
ownership, type, symlink status, and catalog revision, and atomically writes the
grant with the mission. A changed root returns `WORKSPACE_CHANGED` and requires
a new preflight.

`PolicyEngine.workspace_allowed()` is corrected globally: it accepts the exact
granted root, or a descendant only when the grant explicitly permits it. It
never accepts an ancestor of a granted root. Regression tests prove that `/`
and the home directory remain denied when Desktop is granted.

The legacy raw `workspace` field remains temporarily accepted only when it
matches a server-catalog root exactly. Arbitrary paths, `/`, home, sensitive
directories, path traversal, and client-created allowlists are rejected.

All tool paths remain workspace-relative and retain resolved-symlink checks.
For every action, the executor opens the granted root with
`O_DIRECTORY | O_NOFOLLOW`, compares `fstat` UID, type, device, and inode to the
durable grant, and performs relative operations through that directory file
descriptor. A root replacement after approval therefore fails closed or leaves
the action bound to the already-verified directory; it never follows a new
symlink or inode.

## Server-owned operation scope

Workspace selection does not imply permission to inspect the whole workspace.
Every routed proposal receives an `OperationScope` built by the server from the
validated operation slots.

For `create_directory("cortex-live-test")` on Desktop the only allowed calls are:

- `file_exists("cortex-live-test")`, revealing only existence of that exact relative path;
- `create_directory("cortex-live-test")`, after its write approval.

`list_directory`, `read_file`, `search_text`, arbitrary paths, and every other
tool are denied for that mission. Broader inspection or organization requests
require a separate preflight that names the read scope visibly. The policy
engine checks workspace grant, capability, tool allowlist, and relative-path
allowlist for every action.

If the exact target already exists, the mission stops before write approval and
reports `TARGET_ALREADY_EXISTS`; it never reports `created: true`, overwrites,
renames, deletes, or changes the existing entry. No other operation is
registered for intent-routed v0.5.4 missions.

The registered operation is a server-owned state machine:

```text
PROBE_TARGET -> AWAIT_WRITE_APPROVAL -> CREATE_PRIVATE -> PUBLISH_EXCLUSIVE
             -> VERIFY_PUBLISHED_INODE
```

ChatGPT output may propose the next allowed transition but cannot skip or
reorder states. `PROBE_TARGET` uses `lstat` relative to the verified root fd.
After the exact approval, Cortex creates a server-generated one-component
private directory name bound to the action ID using
`os.mkdir(private_name, 0o755, dir_fd=root_fd)`, then opens and holds its fd.
The mode and private name are server-only fields. On macOS, a small tested native
helper publishes it to the final name with dirfd-bound
`renameatx_np(..., RENAME_EXCL)`, so an existing final target is never replaced.

`FileExistsError`/`EEXIST` at publication yields `TARGET_ALREADY_EXISTS` and
`created:false`; Cortex removes only its own empty private directory after
matching action ID, device, and inode. After successful publication,
`VERIFY_PUBLISHED_INODE` compares `fstat(held_private_fd)` with non-following
`stat(final_name, dir_fd=root_fd)`. It requires the same directory device/inode
and fsyncs the root fd before reporting `created:true`. A concurrent rename,
removal, or replacement between publication and verification yields an unclear
outcome, never ownership of the replacement inode.

Deleting user content remains unavailable. The only internal cleanup exception
is Cortex's own empty private staging directory, after action ID, name, device,
inode, emptiness, and unpublished state all match. A restart before publication
may perform that cleanup and close the attempt as not published; it never
replays publication. Missing or contradictory staging evidence becomes
`CREATE_OUTCOME_UNCLEAR`.

Before each transition, the mission store persists operation state, action ID,
private and final target, transition version, grant identity, approval
reference, consent version, authorization epoch, and known fd/inode evidence.
`PUBLISH_EXCLUSIVE` is committed before
the native publication call. A restart from that state without committed final
inode evidence becomes `CREATE_OUTCOME_UNCLEAR / PAUSED_RECOVERY_REQUIRED`.
Cortex never republishes or replays the operation and never reports the target
as created or pre-existing until authoritative reconciliation records durable
evidence.

`POST /api/missions/{id}/reconcile-create` accepts only
`{"action":"inspect_current_target","state_version":N}` from
`CREATE_OUTCOME_UNCLEAR`. The server reopens and verifies the persisted grant,
then performs non-following `lstat` through its root fd. It atomically records
observed type, device, inode, timestamp, and reconciliation provenance:

- absent: `TARGET_NOT_PRESENT_AFTER_UNCERTAIN_CREATE`; no replay;
- directory present: `OUTCOME_PRESENT_PROVENANCE_UNCLEAR`, never
  `created:true`;
- file, symlink, or other type: `TARGET_CONFLICT`.

Any new creation attempt requires a new route and approval. Reconciliation uses
state-version CAS: replaying the same request returns its prior result, while a
conflicting or stale decision returns HTTP 409. The final-action reconciliation
endpoint uses the same CAS and idempotent replay rule.

## Capability authority

The backend must consume and validate the user-confirmed capability set instead
of trusting `approval_policy` alone.

Required invariants:

- `allow_read: false` denies generic read tools; an exact existence probe is
  permitted only when named in `OperationScope`;
- `allow_write: false` produces read-only policy server-side;
- a write policy combined with `allow_write: false` is rejected as
  contradictory;
- routed missions require `allow_processes: false` and reject every process
  action;
- `allow_network` remains false for intent-routed v0.5.4 missions;
- deletion remains unavailable to intent-routed structured tools;
- turning write and process toggles off resets the frontend policy to
  read-only;
- the model cannot expand any capability;
- preflight confirmation does not count as global write approval.

The confirmed contract is persisted atomically with the mission:

- `allow_read`, `allow_write`, and `allow_processes`;
- approval policy;
- serialized operation scope;
- workspace grant ID and revision;
- route and decision digests.

Mission restart or resume reconstructs only those persisted values after a
fresh workspace revalidation. A legacy or incomplete contract fails closed and
requires a new preflight; it never resumes with the current default write
policy.

## Frontend state and concurrency

Add an intent-routing state per conversation:

`idle | classifying | clarifying | preflight | notice | uploading |
preparing_dispatch | sending_chat | starting_mission | failed`

Rules:

- avoid a progress flash for deterministic decisions completed within 150 ms;
- after 150 ms show `Analyse locale en cours…` with `role="status"`;
- preserve the draft and staged attachment in all non-terminal states;
- compute the staged-file descriptor and content digest in a browser worker;
  text-plus-file routing waits for that local digest without blocking the UI;
- generate one finalization idempotency key before the route request, keep it in
  the per-conversation pending state, and reuse it for every finalization retry;
  editing or rerouting after an invalidation generates a new key;
- on explicit ChatGPT attachment choice, generate a separate upload
  authorization token in browser memory, reuse it for reserve/PUT/status/
  finalization/cancel retries of that one action, and erase it at terminal state;
  never persist or log the raw token. If page memory is lost while the durable
  action remains `UPLOADING`, do not guess or resume: enter the documented
  lost-upload recovery flow;
- use a synchronous per-conversation submission guard before any network call,
  so double Enter or double `Continuer` cannot create two routes or keys;
- disable duplicate submission while one route decision is pending;
- use the route and final-action idempotency contract defined below;
- abort or invalidate stale requests on conversation switch or draft edit;
- adding, removing, or replacing a staged file increments `request_epoch`,
  invalidates any route, notice, or preflight, preserves the new staged state,
  and requires a complete reroute before any final action;
- once attachment reservation starts, editing the draft, adding/removing/
  replacing the file, or changing conversation aborts the browser upload and
  invokes the pre-dispatch cancel endpoint for the old final action. The new
  draft/file/conversation state is preserved, but it cannot consume or finalize
  the old upload. Loss of the cancel response is resolved from durable server
  state before the old action can disappear from the UI;
- never copy router state across conversations;
- `notice` receives focus, Escape returns to the intact draft, and it never
  enters the conversation message list;
- classification does not consume a writer slot;
- two conversations may hold independent classification requests concurrently;
  the server still serializes Ollama through its one active slot and bounded
  queue;
- the existing two-writer limit is enforced at explicit writer admission, not
  classification or durable resource creation;
- a refused third writer keeps its draft, attachment, and route decision.

### Rare-state user flows

- `WAITING_FOR_WRITER` shows `En attente d'une place d'envoi. Rien n'a encore
  été envoyé.` with `Réessayer` and `Annuler`. Both keep the browser draft and
  `File`; retry reuses the existing key, while cancel releases only server
  resources and the next send uses a new route/key.
- After its 15-minute expiry, show `Cet envoi en attente a expiré. Rien n'a été
  envoyé.` with `Préparer un nouvel envoi`. Once outbox state is
  `DISPATCHING`, `Annuler` disappears and the UI makes no cancellation promise.
- After 150 ms in `PREPARING_DISPATCH`, show `Préparation de l'envoi… Rien n'a
  encore été envoyé.` with `role="status"` and `Annuler`. Mission variants name
  the payload: `Préparation du contrat…`, `Préparation du rapport d'itération
  n°N…`, or `Préparation du suivi…`, followed by the same no-send statement.
  Cancel waits for authoritative backend invalidation and only then announces
  `Aucun message n'a été envoyé.` After crash/lease recovery, focus `L'envoi n'a
  pas commencé.` with `Réessayer` and `Annuler`; retry creates one new
  attempt/proof and, when applicable, a new ledger entry only after old
  preparation invalidation/tombstoning. STOP, consent, account, surface, or
  extension failures show their dedicated copy instead of generic retry. At
  `DISPATCHING`, cancel and every no-send promise disappear.
- Attachment reservation shows `Préparation du fichier…`; the raw body state
  shows `Envoi du fichier…`. Both use `role="status"` and an accessible
  indeterminate progress indicator; a numeric percentage appears only when
  computed from bytes acknowledged by the active request. Before
  `DISPATCHING`, `Annuler l'envoi` aborts locally, calls server cancellation,
  and announces `Aucun message n'a été envoyé.` only after durable
  acknowledgement. A lost response after `FSYNCED` is recovered through the
  upload result lookup and continues without reupload. Any interruption not
  proven `FSYNCED` shows `L'envoi du fichier doit être préparé de nouveau. Aucun
  message n'a été envoyé.` with `Préparer un nouvel envoi`; partial bytes are
  never resumed. Expiry uses `L'envoi du fichier a expiré. Aucun message n'a
  été envoyé.` A changed file uses `Le fichier a changé. Vérifie de nouveau cet
  envoi.` Once `DISPATCHING`, cancellation and every no-send promise disappear.
- After page reload/crash, if the server proves the action is still
  `UPLOADING`, has no outbox/writer, and the page no longer has its upload token,
  show `Cet envoi ne peut plus être repris. Aucun message n'a été envoyé.` with
  `Sélectionner de nouveau le fichier` and `Fermer`. The first action explicitly
  abandons the old upload; only after durable acknowledgement does it open a new
  file selection and route. Closing leaves the old upload non-dispatchable until
  expiry. If abandonment loses a race to finalization, replace the no-send copy
  with the authoritative send state and never open a duplicate route
  automatically.
- A new conversation shows `Préparation de la nouvelle conversation…` with a
  disabled composer. On timeout/failure, show `Cortex ne peut pas préparer cette
  conversation.` with `Réessayer` and `Retour aux conversations`; no route is
  permitted and other conversations remain usable.
- `DESTINATION_COLLISION_DETACHED` focuses `Conversation déjà liée` and shows
  `Cette nouvelle conversation correspond déjà à « <titre> » dans Cortex. Aucun
  autre message ne sera envoyé depuis ce doublon.` Actions are `Ouvrir la
  conversation déjà liée` and `Retour aux conversations`. The first action uses
  only the exact server-recorded Cortex conversation ID; it never merges records
  or opens the active browser tab. If the duplicate's first delivery is still
  uncertain, its delivery reconciliation runs first, but the duplicate remains
  non-writable in every outcome.
- `DELIVERY_UNCERTAIN` opens a message-specific view showing destination,
  message kind and sequence, timestamp, a readable preview of the exact
  immutable sanitized payload bytes, digest, and available non-secret transport
  evidence. `CHAT` shows `Message à vérifier. Cortex ne le renverra pas
  automatiquement.` with `Marquer comme livré` and `Marquer comme non livré`.
  The latter offers `Préparer un nouvel envoi`, restores the exact text with a
  new route/key, and states that any old attachment must be selected again.
  Mission copies are kind-specific: `Contrat de mission à vérifier`, `Rapport
  d'itération n°N à vérifier`, or `Suivi de mission à vérifier`. Each mission
  kind explicitly exposes `Marquer comme livré` and `Marquer comme non livré`
  with distinct accessible names. Either decision keeps the mission paused.
  After delivered, `Reprendre la mission` reacquires a writer before progress.
  After non-delivered, the only resume action is kind-specific: `Reprendre la
  mission et préparer le contrat`, `Reprendre la mission et préparer de nouveau
  le rapport`, or `Reprendre la mission et préparer de nouveau le suivi`. The UI
  states that a new authorization will be requested and that the replacement
  keeps the same message type and content.
- A changed destination proven before any extension command shows a definitive
  local error, preserves input, and requires an explicit new route/binding; it
  does not open delivery reconciliation. Separate copies are `Le compte ChatGPT
  a changé. Rien n'a été renvoyé.` and `La conversation ChatGPT a changé. Rien
  n'a été renvoyé.` If a browser command may have begun, the message instead
  enters `DELIVERY_UNCERTAIN` with the corresponding reason. Cortex never
  chooses the current tab. Both definitive errors receive title focus and show
  `Réessayer` and `Retour aux conversations`; `Réessayer` first obtains fresh
  account/surface proof, then creates a new route/binding. It never reuses the
  failed binding or auto-resumes.
- Surface `work` shows `Cette page ChatGPT n'est pas une conversation classique.
  Aucun message n'a été envoyé.`; surface `unknown` or unverifiable DOM shows
  `Cortex ne peut pas vérifier cette page ChatGPT. Aucun message n'a été
  envoyé.`; unavailable account fingerprint shows `Cortex ne peut pas vérifier
  le compte ChatGPT. Aucun message n'a été envoyé.` Each receives focus and
  offers `Réessayer` and `Retour aux conversations`. No recovery auto-resumes a
  route. `Ouvrir une conversation ChatGPT classique` appears only where the
  extension can implement and freshly verify that action.
- `EXTENSION_IDENTITY_REJECTED`, missing enrollment key, or storage reset opens
  a focused `Reconnecter l'extension Cortex` view: `Cortex ne peut pas vérifier
  l'extension Chrome. Les conversations restent visibles, mais aucun message ni
  mission ne peut être envoyé.` Actions are `Reconnecter l'extension` and
  `Rester en lecture seule`; the latter closes without mutation. Reconnect shows
  `Connexion sécurisée à l'extension…`, targets only the expected extension ID,
  and on success announces `Extension Cortex reconnectée. Vérifie de nouveau ta
  demande.` Missing/wrong extension uses `L'extension Cortex attendue n'est pas
  disponible dans Chrome.`; expired enrollment uses `La demande de connexion a
  expiré.` Both offer `Réessayer` and `Rester en lecture seule`. Draft/file are
  preserved, prior mutation handles/routes remain revoked, and success never
  resumes or sends before a new route.
- Missing transport consent before preparation focuses `Autorisation d'envoi
  requise` with `Cortex n'est pas autorisé à envoyer vers ChatGPT. Rien n'a été
  envoyé.` Withdrawal during `PREPARING_DISPATCH` focuses `Autorisation d'envoi
  retirée` with `Cortex n'est plus autorisé à envoyer vers ChatGPT. Rien n'a été
  envoyé.` Both preserve draft/file and offer only `Gérer l'autorisation` and
  `Retour aux conversations`. Managing consent opens the existing local consent
  view; a fresh grant never resumes automatically and a later explicit retry
  creates a new attempt. Withdrawal after `DISPATCHING` uses
  `DELIVERY_UNCERTAIN(reason=CONSENT_CHANGED)` and never displays a no-send
  promise.
- When STOP is latched, `Réactiver les actions` opens a focused confirmation
  view titled `Réactiver les actions ?` with: `L'arrêt global sera désactivé.
  Les envois et missions annulés ou en pause ne reprendront pas. Le consentement
  ne sera pas rétabli.` Actions are `Réactiver les actions` and `Garder l'arrêt
  global`; closing or choosing the latter preserves STOP. Success announces
  `L'arrêt global est désactivé. Aucune action n'a repris.` A stale epoch,
  concurrent STOP, expired nonce, or session error refreshes the visible safety
  state and requires a new explicit confirmation; no reset auto-retries.
- `CREATE_OUTCOME_UNCLEAR` shows `Création à vérifier`, `Cortex ne sait pas si
  le dossier « cortex-live-test » a été créé.`, and only `Vérifier l'état du dossier`.
  Cortex performs the authoritative fd-bound inspection; the user does not
  attest success.
- During legacy import show `Mise à niveau des messages locaux…`. Failure keeps
  writer traffic disabled and shows `La mise à niveau a échoué.` with
  `Réessayer` and `Ouvrir les diagnostics`. Imported uncertain or unbound runs
  open in their reconciliation view before affected writes are enabled.
- `LegacyAttachmentQuarantine(REVIEW_REQUIRED)` opens a focused `Fichier ancien
  à vérifier` view with human filename, size, shortened digest, and historical
  source. `Conserver en quarantaine` records `KEEP_QUARANTINED` and announces
  `Le fichier reste en quarantaine. Il ne sera envoyé ni supprimé
  automatiquement.` `Supprimer définitivement…` appears only when the durable
  record is inside the verified private quarantine root; otherwise show `Cortex
  ne peut pas supprimer automatiquement ce fichier ancien.` and keep is the only
  disposition. The delete action opens a second focused
  confirmation: `Supprimer définitivement « X » ?` and `Cette action est
  irréversible. Le fichier ne sera associé à aucun message.`, with `Supprimer le
  fichier` and `Annuler`. Escape/close/cancel preserves review-required state.
  After CAS approval, show `Suppression autorisée. Le fichier sera supprimé
  après les vérifications de sécurité.`; say `Le fichier ancien a été supprimé.`
  only after the dedicated deletion worker records exact captured-object
  deletion. Stale/opposite
  CAS refreshes the durable choice. Identity change shows `Le fichier a changé.
  Rien n'a été supprimé.` and returns to review; it never silently follows the
  replacement inode. `LEGACY_DELETE_OUTCOME_UNCLEAR` shows `Suppression à
  vérifier` and `Cortex ne peut pas confirmer l'état du fichier ancien. Aucun
  nouvel essai ne sera lancé.` with only `Vérifier l'état du fichier`; the
  authoritative read-only root/parent/staging inspection never asks the user to
  attest deletion. It focuses exactly one result: `Le fichier ancien est
  conservé en sécurité. Aucun nouvel essai ne sera lancé.`, `Le fichier est
  revenu en quarantaine. Il ne sera pas supprimé automatiquement.`, `Le fichier
  est absent, mais Cortex ne peut pas prouver qui l'a supprimé.`, or `L'état du
  fichier reste indéterminé.`

### Idempotency

Each final choice carries a client-generated `Idempotency-Key`: exactly 32
random bytes encoded as a 43-character unpadded base64url string. It is bound
server-side to `route_id`, the chosen action, and a digest of the exact confirmed
payload. The server checks it before writer admission or side effects:

- same key and digest returns the already-created chat run or mission;
- same key and different digest returns `409 IDEMPOTENCY_CONFLICT`;
- one route can produce only one final action;
- attachment reserve, raw upload, claim, and exact-chat finalization share the
  same route/idempotency binding; the chat resource is preallocated at reserve,
  while claim, `UPLOADING -> QUEUED`, and outbox creation are one later SQLite
  transaction.

SQLite becomes authoritative for routed finalization. New `final_actions`,
`chat_runs_v2`, durable attachment ownership, and outbox records share the same
database as missions. Existing chat-run JSON is a derived compatibility cache,
never recovery authority.

The transaction contract is normative:

| Boundary | Atomic durable result | Forbidden result |
| --- | --- | --- |
| exact chat without file finalization | one `final_action`, one `QUEUED` chat resource with `writer_state=WAITING_FOR_WRITER`, and one ineligible `READY` `CHAT` outbox | upload lease, second outbox, writer lease, or browser scheduling |
| attachment reserve | one `final_action`, one non-dispatchable `UPLOADING` chat resource, and one `RESERVED` upload lease | outbox, writer admission, or browser scheduling |
| raw attachment `PUT` | the same lease reaches at most `FSYNCED` with observed descriptor evidence | chat queue transition, outbox, writer admission, or browser scheduling |
| attachment finalization | exact lease `FSYNCED -> CLAIMED`, chat resource `UPLOADING -> QUEUED` with `writer_state=WAITING_FOR_WRITER`, and one ineligible `READY` `CHAT` outbox | partial commit, writer lease, or a second resource/outbox |
| mission finalization | one `final_action`, one pending mission with `writer_state=WAITING_FOR_WRITER` containing canonical `ExecutionIntent`, grant, scope, preallocated ID and immutable contract bytes, plus one ineligible `READY` `CONTRACT` outbox | attachment ownership, writer lease, or direct transport |
| explicit writer admission | CAS `WAITING_FOR_WRITER -> ACTIVE`, one active `ConversationWriterLease`, and eligibility of the existing first outbox | automatic admission when a slot later frees, duplicate destination lease, or browser command in the same transaction |
| upload failure, expiry, STOP, withdrawal, or descriptor mismatch | existing `UPLOADING` resource and action terminalized as a non-dispatchable tombstone; lease closed or quarantined by its exact state | `QUEUED`, outbox, writer admission, or deletion without identity proof |

Every chat/mission resource stores a server-resolved `DestinationBinding`
containing the canonical conversation key/URL or explicit new-conversation
sentinel, generation, provisional key, and transport/account identity needed to
reselect and verify the destination. Every later mission iteration report or
follow-up receives its own durable message outbox before transport. Browser
transport may be scheduled only from an eligible message outbox after writer
admission.

Each message outbox record owns a unique `message_id`, resource ID, monotonic
sequence, kind (`CHAT`, `CONTRACT`, `ITERATION_REPORT`, or `FOLLOW_UP`), immutable
payload bytes, `DestinationBinding`, consent version, authorization epoch, state
version, dispatch attempt, durable receipt, and reconciliation source/outcome/
timestamp/response fields, plus nullable `supersedes_message_id` and
`causal_predecessor_message_id`. Uniqueness on resource/sequence
prevents duplicate report creation. The mission loop never calls transport
directly and never regenerates a persisted report. It waits for the preceding
message's durable outcome before advancing. On restart, a `READY` message may be
claimed only when its resource was already `ACTIVE`, recovery renews the exact
destination writer under fresh safety/identity proof, and the outbox was already
eligible before the crash; a waiting resource is never auto-admitted. A
`DISPATCHING` contract or report becomes `DELIVERY_UNCERTAIN` and is never
automatically sent again.

`DestinationBinding` is a strict versioned record:

- `kind`: `canonical` or `new_conversation`;
- canonical conversation key/URL, or the unique server provisional key and
  new-conversation sentinel;
- conversation generation;
- pinned Chrome extension ID, enrolled extension public-key fingerprint,
  extension instance ID, and extension-storage generation;
- positive classic-surface proof version and last consumed proof nonce;
- required account fingerprint version and value derived from a stable signed-in
  account/workspace identifier;
- creation time and binding version.

The packaged manifest contains a fixed public `key`, producing one expected
Chrome extension ID that is embedded in the backend build. The WebSocket
accepts only loopback plus the exact `chrome-extension://<expected-id>` Origin;
the generic `chrome-extension://` prefix is rejected, and Origin is treated as
routing evidence rather than authentication.

Initial enrollment is an explicit local UI action. Cortex generates a 256-bit
single-use enrollment token and sends it only to the expected extension ID. The
extension creates an Ed25519 enrollment keypair; its private key is
non-exportable and stored in extension-owned IndexedDB, while public identity,
instance ID, and storage generation live in `chrome.storage.local`. The backend
atomically binds the token, expected extension ID, public key, instance, and
generation. Storage reset or key loss revokes the enrollment and requires a new
explicit pairing; an extension cannot self-declare a replacement identity.
Every later WebSocket session proves possession by signing a fresh backend
challenge before it receives commands. Durable enrollment identity and the
short-lived pairing session are separate records.

During enrollment, the extension also creates a separate non-exportable 256-bit
fingerprint key in extension-owned storage. During pairing it sends a versioned
HMAC fingerprint of a stable ChatGPT account/workspace identifier; the raw
identifier and fingerprint key never leave the extension. Each mutation
consumes a single-use signed `SurfaceProof` bound
to pairing session, command and dispatch-attempt IDs, tab/window, exact observed
URL or provisional sentinel, payload digest, account fingerprint, surface,
authorization epoch, consent version, nonce, and timestamp. The extension
reobserves these values immediately before insertion/click and signs the proof;
the backend rejects replay or field mismatch. If no stable fingerprint or fresh
positive classic-surface proof is available, no mutation-capable handle,
binding, or command is issued. Backend restart, service-worker restart,
extension reload, same-session account switch, missing fingerprint, and
fingerprint-source version change are separate tested cases.

Mutation is a two-phase extension protocol. `command.prepare` carries the
backend nonce, intended payload digest, destination, epoch/version, and fencing
tokens; the extension observes without DOM mutation and returns the signed
`SurfaceProof`. After verification, `command.execute` references that exact
proof and tuple. The extension reobserves immediately before DOM access,
rejects any changed field, consumes the proof once, performs at most the named
mutation, and returns a signed receipt. A crash or lost result after execute is
delivery-uncertain; the prepare phase alone is a definitive no-effect state.

`DestinationBinding` contains only durable destination identity. Ephemeral
pairing ID, challenge, connection identity, and heartbeat live in a separate
`LiveTransportSession` record and are never serialized into the durable binding.
After backend or service-worker restart, a new signed challenge may CAS-attach a
new live session to the unchanged binding only when expected extension ID,
enrolled public key, instance/storage generation, account fingerprint,
destination, and conversation generation all still match. Old-session commands
remain invalid. Any durable-identity change revokes mutation authority and
requires the explicit rebind or enrollment path.

For the first message to a provisional conversation, the extension also keeps a
bounded durable dispatch ledger in `chrome.storage.local`. Before the first
browser command it records `dispatch_attempt_id`, extension instance/storage
generation, account fingerprint, provisional key, and selected tab identity.
After ChatGPT navigates to `/c/...`, it appends the freshly observed canonical
URL, conversation fingerprint, surface proof, and receipt evidence under the
same attempt ID before acknowledging delivery. Backend and extension rekey the
provisional conversation only from that exact record, never from the active
tab. A lost HTTP/WebSocket receipt is recovered by querying the same attempt ID
after service-worker or backend restart. If the canonical target cannot be
proven, the message becomes `DELIVERY_UNCERTAIN` with reason
`DESTINATION_UNBOUND`; a human
may mark it definitively not delivered, but `DELIVERED` and every later mission
message remain forbidden until the canonical binding is recovered. The ledger
is authenticated by the enrolled extension key and contains no raw account
identifier or message bytes. Entries remain pinned until backend receipt or
human reconciliation is durable; unresolved entries are never evicted to meet
the bound. While the outbox is `PREPARING_DISPATCH`, the extension reserves
entry/byte capacity and durably writes the attempt before the backend may commit
`PREPARING_DISPATCH -> DISPATCHING`; capacity or storage-write failure is a
definitive pre-delivery failure and no execute command is attempted. Only
acknowledged/reconciled tombstones may be evicted.

Upload leases use a durable state machine:

```text
RESERVED -> STREAMING(device, inode, heartbeat) -> FSYNCED(observed descriptor)
         -> CLAIMED -> RELEASED(reason)
```

Reservation chooses an unpredictable one-component basename in a private upload
root and persists expected descriptor, opaque internal stream-owner fence,
route/idempotency binding,
consent version, authorization epoch, surface/account binding digest, path, state
version, and expiry before any body is accepted. The raw `PUT`
opens that name relative to the verified upload-root fd with
`O_CREAT | O_EXCL | O_NOFOLLOW`, immediately captures `fstat` device/inode, and
CAS-transitions `RESERVED -> STREAMING`. Expected and observed descriptors are
separate fields. Streaming renews a durable heartbeat at bounded byte/time
intervals. Completion fsyncs file and parent, validates observed size and digest
plus the syntactic/allowlist rules for confirmed metadata, and CAS-transitions
to `FSYNCED`; finalization alone may transition it to `CLAIMED`.

A crash after exclusive file creation but before the inode receipt leaves a
`RESERVED` lease plus an unbound file at the exact reserved name. Recovery moves
it to `QUARANTINED_UNBOUND`, records observed identity, and never claims it as an
upload. Startup holds one recovery lock and runs strictly in this order: schema
migrations, legacy import, final-action/outbox recovery, upload-lease recovery,
then orphan collection. Import-time cleanup is removed. Per-upload mutexes and
state-version CAS make streaming, claim, recovery, and collection mutually
exclusive.

The pre-claim lease, `UPLOADING` resource, and final action share one coherent
30-minute inactivity expiry. `RESERVED` has no heartbeat; `STREAMING` renews the
deadline from its bounded durable heartbeat but has a two-hour absolute cap;
`FSYNCED` receives one final 30-minute deadline. Expiry, explicit cancel, STOP,
or consent withdrawal takes the per-upload mutex and CAS-terminalizes lease,
resource, and action together while retaining the idempotency tombstone. An
active stream cannot be collected; an expired stream is first stopped and its
owner fencing token invalidated. STOP uses `ABORTED_BY_STOP`; the other terminal
reason remains explicit. `CLAIMED` ownership follows its queued chat resource
and cannot expire independently while its message remains replay-eligible.
Delivery, definitive pre-delivery failure, delivery uncertainty, cancellation,
or expiry makes the old message non-replayable and atomically transitions its
attachment `CLAIMED -> RELEASED(reason)` while retaining descriptor/digest
evidence in the tombstone. A later send must reselect and reupload the browser
file; reconciliation never reclaims released bytes.

The ordinary collector deletes only terminal upload files older than one hour
whose lease is expired, heartbeat is stale, durable references are absent, and
path/device/inode all match. It may delete `RELEASED` bytes after the retention
floor but never directly deletes `STREAMING`, `FSYNCED`, `CLAIMED`, an
in-process upload, any legacy quarantine, or legacy delete-staging name. A
committed chat run owns exactly one attachment record. Mission resources cannot
own attachments in v0.5.4.

Legacy deletion uses a separate durable state machine:

```text
REVIEW_REQUIRED -> KEEP_QUARANTINED
REVIEW_REQUIRED -> DELETE_APPROVED -> CAPTURE_RESERVED -> CAPTURED_MATCHED
                                         |                    |-> DELETED
                                         |                    `-> LEGACY_DELETE_OUTCOME_UNCLEAR
                                         `-> IDENTITY_CHANGED_REVIEW_REQUIRED
```

After the retention floor, one interprocess lock covers the exact quarantine
record. The worker opens the persisted private root and parent with
`O_DIRECTORY | O_NOFOLLOW`, verifies root/parent device+inode, allocates and
persists an unpredictable component under a same-filesystem owner-only delete-
staging dirfd, then atomically captures the current leaf with
`renameatx_np(..., RENAME_EXCL)`. It opens the captured private name with
`O_NOFOLLOW`, verifies file device/inode/size/digest against the approved record,
and durably commits `CAPTURED_MATCHED` before any unlink. Still under the lock,
it unlinks only that private staging name, fsyncs the staging parent, verifies
absence, and then commits `DELETED`.

If captured identity differs, Cortex never deletes it. It attempts an exclusive
restore to the original parent/name. Successful restore enters
`IDENTITY_CHANGED_REVIEW_REQUIRED`; failed restore keeps the captured object in
private staging and enters `LEGACY_DELETE_OUTCOME_UNCLEAR`. Crash recovery uses
the persisted staging name and state: it may delete only from a durable
`CAPTURED_MATCHED`; any missing or contradictory post-capture evidence becomes
unclear rather than a deletion claim. The generic collector never handles these
states. This protocol protects legitimate Cortex concurrency; malicious
same-UID modification of the private 0700 staging root remains outside the
declared threat model.

`final_actions` enforces unique `route_digest` and `Idempotency-Key`. It records
action, payload digest, state, resource ID, HMAC of the route token,
conversation-handle digest, consent version, authorization epoch, surface/account
binding digest, `state_version`, `key_id`, and timestamps. Reconciliation also
persists `reconciled_from_version`, outcome, reconciliation timestamp, and the
canonical response body. The payload digest covers
action, conversation generation, exact draft HMAC and the complete canonical
attachment descriptor (basename, MIME, size, modified time, and content digest)
for chat, or execution intent, grant revision, operation scope, and cloud
contract bytes for a mission.

Writer ownership and message dispatch use distinct durable leases:

- `ConversationWriterLease` owns one of the two global conversation slots and
  serializes the whole chat or mission resource with a monotonically increasing
  destination fencing generation plus opaque token. A partial unique index
  permits at most one active writer lease per canonical or provisional
  destination, so chat and mission cannot consume two slots for the same
  conversation. Provisional-to-canonical rekey checks that index in the same
  transaction. Collision never merges resources: it records the exact already-
  linked Cortex conversation ID/canonical target, releases the losing
  provisional writer, and terminalizes that duplicate for future writes as
  `DESTINATION_COLLISION_DETACHED`. The first message keeps only its independently
  proven delivered/uncertain outcome, but no later outbox can originate from the
  detached duplicate. The UI may navigate only to the recorded existing Cortex
  conversation, never the active tab.
  A chat holds it through its terminal message outcome. An active mission
  renews it across contract delivery, ChatGPT response waits, approvals, local
  actions, iteration reports, and follow-ups. It releases only at a terminal
  state, STOP, delivery uncertainty, or an explicit pause that cannot resume
  automatically. Explicit mission resume must reacquire a writer slot before it
  creates or schedules another message;
- `DispatchAttemptLease` is separate and belongs to exactly one message outbox.
  Only its CAS claimant, while also presenting the current conversation-writer
  fencing token, may transition that message toward a browser command. A fresh
  dispatch lease is used for every `CONTRACT`, `ITERATION_REPORT`, and
  `FOLLOW_UP`.

Backend validates both fencing tokens before scheduling every extension
command. The extension also persists the highest accepted writer generation per
destination and rejects a stale generation, wrong dispatch token, reused proof,
or destination mismatch before DOM access on every insert/click command. Lease
expiry cannot make a stale worker safe by itself: if the outbox is already
`DISPATCHING`, recovery first records `DELIVERY_UNCERTAIN` and the destination
block durably, then releases the conversation slot. Only proven pre-command
expiry may return to waiting with fresh tokens.

Before any browser command, recovery may requeue a resource or message only
with durable proof that no effect boundary was crossed. Two concurrent
finalizations can never both claim the conversation slot or the same message.
A third-writer refusal leaves `writer_state=WAITING_FOR_WRITER`, keeps the
frontend draft/file state and ineligible outbox, and requires a later explicit
retry that performs the admission CAS; it never starts automatically when a
slot becomes free or after restart.

Every message, canonical or provisional, gets a backend-authoritative
`DispatchPreparation` record before prepare. It stores message/attempt IDs,
state version, authorization epoch/consent version, proof nonce/digest,
destination, writer/dispatch fencing generations, and
`ACTIVE|INVALIDATED|EXECUTING` state. A provisional message additionally owns
the extension dispatch-ledger record; canonical messages need no persistent
extension ledger before execute. Backend invalidation of the preparation record
and advance of its attempt generation is sufficient to revoke execute and to
acknowledge STOP even while the extension is offline. The extension rejects old
pairing sessions/attempt generations. When a provisional ledger exists, its
tombstone is synchronized before any later prepare after reconnect, but that
offline cleanup does not delay STOP acknowledgement.

The first-effect boundary is one SQLite transaction, not two writes. It verifies
the outbox is `PREPARING_DISPATCH`, preparation is `ACTIVE`, proof nonce/digest
and attempt match, writer/dispatch fences remain current, authorization and
destination remain valid, then atomically consumes the proof, transitions
`DispatchPreparation ACTIVE -> EXECUTING`, and transitions the outbox
`PREPARING_DISPATCH -> DISPATCHING`. `command.execute` is emitted only after
that commit. If any predicate or commit fails, execute is forbidden. Recovery
treats any impossible crossed pair — outbox `DISPATCHING` with preparation
`ACTIVE`, or preparation `EXECUTING` with outbox `PREPARING_DISPATCH` — as
`DELIVERY_UNCERTAIN`, never READY/cancelled. STOP/invalidation winning before
the transaction makes its CAS fail; the transaction winning first makes STOP
apply the post-effect uncertainty boundary.

Every durable message outbox uses this state machine:

```text
READY -> PREPARING_DISPATCH -> DISPATCHING -> DELIVERED
  ^       |                 |                -> DELIVERY_UNCERTAIN
  |       |                 `-> DEFINITIVE_PREDELIVERY_FAILURE
  |       `-> DEFINITIVE_PREDELIVERY_FAILURE / CANCELLED_BY_STOP
  `------- explicit retry CAS after authoritative invalidation
```

`READY -> PREPARING_DISPATCH` is committed before the first extension command
and stores a dispatch-attempt ID plus current dispatch/writer fencing tokens.
Only in `PREPARING_DISPATCH` may `command.prepare` reserve/persist the extension
ledger entry and return the signed no-DOM `SurfaceProof`. Backend then rechecks
safety, identity, destination, proof, and both fencing tokens through the single
atomic preparation/outbox transaction above immediately before the first
possible browser effect, `command.execute`.

A crash, STOP, withdrawal, or lease expiry in `PREPARING_DISPATCH` is a proven
no-effect boundary. Recovery first durably invalidates the backend
`DispatchPreparation`, proof nonce, and attempt generation. STOP may then return
even when the extension is offline. If a provisional extension ledger exists,
its tombstone is required before any future prepare after reconnect, but not for
the STOP response; canonical messages have no such ledger. Generic crash/lease
recovery may CAS-return the same outbox to `READY` only on a later explicit retry
with a new attempt/proof after authoritative invalidation. STOP, consent
withdrawal, and identity failures use their dedicated terminal/pause state and
never a generic retry. Recovery never calls execute from prepared state. Once
`DISPATCHING`, dispatch-lease expiry or restart never
returns the entry to `READY`; missing signed receipt becomes
`DELIVERY_UNCERTAIN`. Cortex never equates a process-local success or timeout
with a durable delivery receipt.

The outbox always uses its `DestinationBinding`. Restart recovery reselects and
verifies that exact canonical destination or the exact provisional sentinel. A
missing generation, changed account/transport identity, or mismatched canonical
conversation proven before any extension command becomes
`DEFINITIVE_PREDELIVERY_FAILURE` with a typed reason such as
`CONVERSATION_CHANGED`, `ACCOUNT_CHANGED`, `SURFACE_UNVERIFIED`, or
`WORK_SURFACE_REJECTED`; it never falls back to the active tab and requires a
new route/binding for chat. An existing mission instead enters
`PAUSED_REBIND_REQUIRED`: an explicit rebind validates a freshly selected
server-issued conversation handle and surface/account proof, retains the same
mission ID and immutable causal history, and never creates a second mission or
copies the active tab implicitly. The same mismatch after a command may have started becomes
`DELIVERY_UNCERTAIN` with that reason. First delivery to a provisional sentinel
records canonical identity only through the authenticated extension dispatch
ledger. An unproven canonical target uses
`DELIVERY_UNCERTAIN(reason=DESTINATION_UNBOUND)`. Any delivery uncertainty releases the
global writer slot but blocks further writes only to that conversation until
reconciliation; it is never auto-replayed.

The local reconciliation view shows the human destination, message kind,
monotonic sequence, timestamps, a readable preview of the exact immutable
sanitized payload bytes, payload digest, and available transport evidence
without exposing secrets. The
strict local endpoint
`POST /api/intent/final-actions/{id}/messages/{message_id}/reconcile` accepts only
`{"outcome":"DELIVERED|DEFINITIVE_NOT_DELIVERED","state_version":N}`
for that uncertain message. It uses state-version CAS: the same choice returns
the recorded result and a stale/conflicting choice returns HTTP 409 using
`UPDATE message_outbox ... WHERE state = 'DELIVERY_UNCERTAIN' AND
state_version = N`. Message and aggregate final-action reconciliation persist
the source version, outcome, timestamp, and canonical response. Two opposing
concurrent choices therefore have one winner, and replay before or after restart
creates no outbox. For a provisional first delivery, `DELIVERED` additionally
requires the canonical binding recovered from the same extension dispatch
attempt; otherwise the endpoint rejects it while allowing only
`DEFINITIVE_NOT_DELIVERED`.

For mission messages, either reconciliation outcome leaves the mission paused.
After `DELIVERED`, an explicit resume must reacquire a
`ConversationWriterLease` before the mission may advance or create another
outbox. `DEFINITIVE_NOT_DELIVERED` never changes message kind or payload. A
later explicit resume/rebind with fresh authorization, writer admission, and
per-message approval may create exactly one replacement outbox with a new
`message_id` and dispatch attempt, `supersedes_message_id` pointing to the
failed message, and the same immutable sanitized bytes: `CONTRACT` replaces a
contract, `ITERATION_REPORT` replaces that report, and `FOLLOW_UP` replaces that
follow-up. Replacement transport never repeats the local action that produced a
report. The causal predecessor must already have a definitive delivered outcome,
and the old attempt remains terminal/non-replayable.

Legacy reconciliation has a separate strict endpoint because migrated records
intentionally have no message outbox:
`POST /api/intent/legacy-final-actions/{id}/reconcile` accepts only
`{"outcome":"DELIVERED|DEFINITIVE_NOT_DELIVERED","state_version":N}` for one
`legacy_reconciliation_only` record. It CAS-updates only that exact uncertain
legacy state and persists source version, outcome, timestamp, and canonical
response. Identical replay returns the durable response; a stale or opposite
choice returns HTTP 409. It never creates an outbox, modern
`DestinationBinding`, current identity, or transport command. A canonical
record lifts only its conversation block. An unbound/root record lifts only its
own new-conversation block; remaining unbound records continue to block new-
conversation writes independently.

Ambiguous legacy attachments use
`POST /api/intent/legacy-attachments/{id}/dispose` with strict
`{"outcome":"KEEP_QUARANTINED|DELETE_APPROVED","state_version":N}` and the same
CAS/idempotent-response rules. `KEEP_QUARANTINED` remains non-collectable;
`DELETE_APPROVED` becomes eligible only for the dedicated atomic capture/delete
worker after the retention floor. The ordinary collector never deletes it.
v0.5.4 never reassigns a quarantined file to a message or mission. The UI
discloses the exact filename, size, digest, and historical source before the
separate deletion confirmation.

`POST /api/intent/legacy-attachments/{id}/inspect-delete-outcome` is the only
action behind `Vérifier l'état du fichier`. Its strict body is
`{"action":"inspect_current_state","state_version":N}` and it is accepted only
from `LEGACY_DELETE_OUTCOME_UNCLEAR`. Under the quarantine lock it opens and
verifies the persisted root, original parent, and staging dirfds, then observes
the original and reserved staging names with `fstatat(..., AT_SYMLINK_NOFOLLOW)`.
It never calls rename, restore, unlink, or the deletion worker. State-version
CAS persists source version, bounded result, evidence, timestamp, and canonical
response; identical replay returns that response and stale replay returns 409.

Allowed inspection results are exhaustive:

- exact approved object only in private staging -> `CAPTURED_PRESENT`, retained
  non-collectable, copy `Le fichier ancien est conservé en sécurité. Aucun
  nouvel essai ne sera lancé.`;
- exact approved object only at the original quarantine name ->
  `ORIGINAL_RESTORED`, terminal `KEEP_QUARANTINED`, copy `Le fichier est revenu
  en quarantaine. Il ne sera pas supprimé automatiquement.`;
- neither name present -> `ABSENT_UNATTRIBUTED`, copy `Le fichier est absent,
  mais Cortex ne peut pas prouver qui l'a supprimé.`;
- both names present, any identity mismatch, changed root/parent/staging, or
  observation error -> `STATE_INDETERMINATE`, copy `L'état du fichier reste
  indéterminé.`

No inspection result except an already durable post-unlink `DELETED` record may
say Cortex deleted the file. Inspection never retries deletion.

`DEFINITIVE_NOT_DELIVERED` never reuses the old attempt. Exact chat requires a
new route/key. A mission pauses as `PAUSED_RECONCILIATION_REQUIRED` and follows
the typed replacement rules above. Reconciliation itself never sends.

Finalization first looks up the durable route-token HMAC and idempotency key. If
a record exists, matching data returns or resumes only that resource; a mismatch
returns `409 IDEMPOTENCY_CONFLICT`. Only when no durable record exists must the
memory route still be live. Therefore restart recovery never depends on a memory
route and never reclassifies or creates a second resource. An ambiguous browser
delivery keeps the existing no-auto-resend rule.

Route, decision, and payload digests are keyed HMACs, not recoverable raw hashes
of short drafts. Each record stores a `key_id`; the owner-only keyring retains
old keys until every corresponding route, final-action record, and tombstone has
been garbage-collected.

### Credential and record lifecycle

- A conversation handle is stable only for one conversation generation, expires
  after 30 minutes of inactivity, and is revoked on conversation deletion,
  generation change, or service restart. The server keeps at most 256 active
  handles and evicts only handles with no live route.
- A duplicate finalization for an already durable result is looked up first by
  route-token HMAC and idempotency key. It verifies the stored handle digest and
  does not require the pre-restart handle to resolve as a new live route.
- `WAITING_FOR_WRITER` expires 15 minutes after creation or the last explicit
  retry. `POST /api/intent/final-actions/{id}/cancel` may cancel only
  pre-dispatch states, including an active upload after its stream owner is
  fenced and stopped. Expiry or cancellation atomically marks the resource
  `EXPIRED` or `CANCELLED`, closes any READY outbox, releases attachment
  ownership, and keeps a tombstone; neither can touch `DISPATCHING`.
- `UPLOADING` action, resource, and pre-claim lease use the shared inactivity
  deadlines defined by the upload state machine. An expired/unrecoverable
  upload marks the action `UPLOAD_EXPIRED`, terminalizes the resource,
  releases/quarantines its lease under the upload rules, and requires a new
  route. Same-key lookups before expiry return the same resource/upload state.
- An expired conversation-writer or dispatch claim in `READY` or
  `PREPARING_DISPATCH` may return to waiting/READY only after prepared proof and
  ledger invalidation durably prove no first effect and fresh fencing tokens are
  issued. On restart, every `DISPATCHING` entry without a
  durable receipt becomes `DELIVERY_UNCERTAIN`; it is never garbage-collected as
  retryable work. An active mission renews its conversation-writer lease between
  messages; pause, STOP, or uncertainty releases it and requires explicit
  reacquisition.
- Terminal records and tombstones have a 24-hour minimum and 30-day maximum
  retention. The 10,000-record cap may prune the oldest terminal records older
  than 24 hours; it never prunes non-terminal or uncertain records. If those
  records alone reach the cap, new finalization fails closed with
  `503 FINAL_ACTION_CAPACITY` and a local retry message.
- Key rotation creates a new current `key_id`; it never deletes a key still
  referenced by a route, record, or tombstone. Owner-only file permissions and
  startup validation are mandatory.

## Privacy and audit

Ollama receives only:

- the draft as untrusted data;
- locale;
- attachment presence;
- structured clarification when applicable.

It never receives conversation history, title, URL, account data, browser
target, absolute filesystem path, file content, or another conversation's
state.

Intent routing does not persist raw drafts or clarification text. Diagnostics
may record only:

- timestamp;
- rotating local HMAC of the input, never a raw SHA digest recoverable by a
  dictionary attack;
- selected action;
- source (`rules`, `ollama`, or `safe_fallback`);
- `model_attempted`, observed model name/digest, and `decision_accepted` as
  separate truth fields;
- latency;
- confidence enum;
- reason and degradation codes.

No prompt, model response, free-form exception, draft, clarification, or
display summary is logged. Diagnostics are memory-only by default. If a
dedicated bounded audit journal is enabled, non-mutation tests explicitly
exclude that named journal while still proving that SQLite, chat runs, mission
records, attachments, and user workspaces remain unchanged.

After final choice, the exact chat message is persisted through authoritative
`chat_runs_v2`; the legacy JSON is only a derived cache. A confirmed mission
objective is persisted only through the mission resource created by
finalization.

## ChatGPT visibility limit

Classification prompts and clarification exchanges stay local and never appear
in ChatGPT.

After mission confirmation, the final mission contract still has to be sent to
ChatGPT Web through its visible composer. ChatGPT Web provides no hidden system
message channel to this extension. Cortex may collapse protocol messages in its
own interface, but the actual ChatGPT conversation can still display them.

The preflight lists the cloud disclosure separately and previews the exact
mission payload bytes. A routed mission never forwards the raw draft. The
contract sent to ChatGPT contains only the server-generated operation template,
human workspace label, and relative paths. The canonical absolute workspace
path, any absolute path embedded in the draft, home path, mount path, workspace
grant, UID, device, inode, and local audit fields remain inside Cortex. A
transport-payload test fails on any home or mounted-volume absolute path and
asserts that the preview equals the actual transport bytes. An explicit exact
chat choice is the separate path that sends the raw draft.

The product must state this limitation rather than imply an invisible ChatGPT
system prompt.

## Failure handling

| Failure | Required behavior |
| --- | --- |
| Ollama unavailable or model missing | Local manual choice, draft preserved |
| Two-second warm-model timeout, model not loaded, cold race, oversized input, or busy model | Same safe fallback, no retry |
| Invalid or extra JSON field | Reject output and use safe fallback |
| Consent absent/withdrawn or STOP latched | Exclusive authorization gate decides the first-effect race; cancel/pause proven pre-effect work, make possible delivery uncertain, never bypass or auto-resume |
| Surface positively identified as `work` | `WORK_SURFACE_REJECTED` before upload/composer mutation |
| Surface `unknown`, stale, missing, or DOM unverifiable | `SURFACE_UNVERIFIED` before upload/composer mutation |
| Account fingerprint unavailable | `ACCOUNT_UNVERIFIED` before upload/composer mutation |
| Account fingerprint changed | `ACCOUNT_CHANGED` before a command, or delivery uncertainty if a command may have begun |
| Extension ID, enrollment key, pairing signature, or one-time surface proof invalid | `EXTENSION_IDENTITY_REJECTED`; mutation disabled, read-only status only, never fall back to another extension |
| Unsupported process/destructive/network request | `show_local_notice`; no action |
| Workspace alias unavailable | Ask for an allowed workspace |
| Workspace changed after preflight | HTTP 409, reopen preflight |
| Decision, grant, or preview digest changed | HTTP 409 `PREFLIGHT_CHANGED`; preserve draft/file and require a new route |
| Staged file descriptor or digest changed | HTTP 409 `ATTACHMENT_CHANGED`; terminalize the old preallocated upload resource before queue/outbox/writer, preserve the new file, and require a new route |
| Upload interrupted before durable `FSYNCED` | Terminalize the partial upload; no send or resume, preserve browser input, require a new route |
| Upload lease expired or became quarantined | `UPLOAD_EXPIRED`; terminalize lease/resource/action atomically, no send, preserve browser input when available, require a new route |
| Draft or conversation changed | Ignore stale decision |
| Route expired, evicted, consumed, or service restarted | HTTP 410; preserve draft/file and offer `Vérifier de nouveau` |
| Duplicate click/retry | At most one final send or mission |
| Intent API unavailable | Local `Réessayer / Envoyer à ChatGPT / Exécuter…` panel; no implicit action |
| Any mission endpoint with attachment | HTTP 422 before token resolution; preserve file and offer exact ChatGPT send or removal |
| Exact directory target already exists | Neutral `TARGET_ALREADY_EXISTS`; no approval, mutation, or generic failure |
| Durable final-action capacity reached | HTTP 503; preserve state and offer retry, never bypass the registry |
| Third writer or duplicate active destination | Third writer stays `WAITING_FOR_WRITER`; a proven rekey collision becomes terminal `DESTINATION_COLLISION_DETACHED` linked to the exact existing Cortex conversation, never auto-admit, merge, or dispatch again |
| Browser command started but durable delivery receipt missing | `DELIVERY_UNCERTAIN`; block that conversation, never auto-resend, show reconciliation |
| Durable destination cannot be reverified before any browser command | `DEFINITIVE_PREDELIVERY_FAILURE` with typed reason; preserve input, require a new route/binding, never use the active tab |
| Durable destination changes after a browser command may have begun | `DELIVERY_UNCERTAIN` with typed reason; never use the active tab or auto-resend |
| Crash around exclusive directory creation without inode receipt | `CREATE_OUTCOME_UNCLEAR`; pause, never replay, require reconciliation |
| STOP reset state/epoch/session/nonce stale | Keep or refresh STOP state; require a new explicit confirmation, never retry implicitly |
| Ambiguous legacy attachment ownership | Durable review-required quarantine; no dispatch or collection before explicit CAS disposition |
| Legacy delete capture differs or cannot be restored/proven | Never unlink the mismatched object; restore exclusively or keep it in private staging as `LEGACY_DELETE_OUTCOME_UNCLEAR`, no automatic retry or deletion claim |
| Chat delivery uncertain | Existing no-auto-resend rule remains |

Failures never silently turn a local-action candidate into a ChatGPT send.

## Accessibility and copy

- Classification, clarification, preflight, and errors use text, not color
  alone.
- Focus moves to the clarification or preflight title and returns to the
  composer on close.
- Escape cancels safely without losing the draft.
- All alternatives are keyboard reachable and have explicit accessible names.
- Reduced motion changes no information.

Primary French copy:

- composer placeholder: `Écris une question ou demande une action sur ce Mac…`;
- composer help: `Entrée pour continuer · ⇧ Entrée pour une ligne`;
- composer action and accessible name: `Continuer`;
- progress: `Analyse locale en cours…`;
- interpretation label: `Cortex a compris`;
- exact create-directory interpretation template: `Créer le dossier « cortex-live-test » dans Bureau.`;
- preflight title: `Vérifier la mission locale`;
- preflight explanation: `Aucun fichier n'a été modifié. Après le démarrage, Cortex te demandera séparément d'autoriser la création du dossier.`;
- primary action: `Démarrer la mission sur ce Mac`;
- secondary action: `Envoyer seulement à ChatGPT`;
- fallback question: `Veux-tu envoyer ce texte à ChatGPT ou préparer une exécution sur ce Mac ?`;
- no-action statement: `Aucune mission n'a démarré et aucun fichier n'a été modifié.`;
- expired route: `Cette vérification a expiré. Vérifie de nouveau la demande.`;
- changed preflight: `Cette vérification n'est plus à jour. Vérifie de nouveau la demande.`;
- existing target: `Le dossier « cortex-live-test » existe déjà dans Bureau. Rien n'a été modifié.`;
- attachment mission notice: `Cette version ne peut pas utiliser un fichier dans une mission locale. Retire le fichier ou envoie-le à ChatGPT.`;
- upload preparation: `Préparation du fichier…`;
- upload streaming: `Envoi du fichier…`;
- upload cancellation: `Annuler l'envoi`, followed by `Aucun message n'a été envoyé.` only after durable cancellation;
- upload interrupted: `L'envoi du fichier doit être préparé de nouveau. Aucun message n'a été envoyé.` with `Préparer un nouvel envoi`;
- upload authority lost: `Cet envoi ne peut plus être repris. Aucun message n'a été envoyé.` with `Sélectionner de nouveau le fichier` and `Fermer`;
- attachment changed: `Le fichier a changé. Vérifie de nouveau cet envoi.`;
- upload expired: `L'envoi du fichier a expiré. Aucun message n'a été envoyé.` with `Préparer un nouvel envoi`;
- router unavailable: `Cortex ne peut pas vérifier l'intention pour le moment.` with `Réessayer`, `Envoyer à ChatGPT`, and `Exécuter…`;
- manual process warning: `Un script approuvé n'est pas isolé par macOS. Il peut agir hors de l'espace de travail, accéder au réseau ou effectuer des actions destructives.`;
- waiting writer: `En attente d'une place d'envoi. Rien n'a encore été envoyé.` with `Réessayer` and `Annuler`;
- expired waiting writer: `Cet envoi en attente a expiré. Rien n'a été envoyé.` with `Préparer un nouvel envoi`;
- dispatch preparation: `Préparation de l'envoi… Rien n'a encore été envoyé.` with `Annuler`;
- mission contract preparation: `Préparation du contrat… Rien n'a encore été envoyé.`;
- mission report preparation: `Préparation du rapport d'itération n°N… Rien n'a encore été envoyé.`;
- mission follow-up preparation: `Préparation du suivi… Rien n'a encore été envoyé.`;
- recovered preparation: `L'envoi n'a pas commencé.` with `Réessayer` and `Annuler`;
- provisional progress: `Préparation de la nouvelle conversation…`;
- provisional failure: `Cortex ne peut pas préparer cette conversation.` with `Réessayer` and `Retour aux conversations`;
- destination collision title: `Conversation déjà liée`;
- destination collision explanation: `Cette nouvelle conversation correspond déjà à « <titre> » dans Cortex. Aucun autre message ne sera envoyé depuis ce doublon.` with `Ouvrir la conversation déjà liée` and `Retour aux conversations`;
- uncertain chat delivery: `Message à vérifier. Cortex ne le renverra pas automatiquement.` with `Marquer comme livré` and `Marquer comme non livré`;
- uncertain mission contract: `Contrat de mission à vérifier. Cortex ne le renverra pas automatiquement.` with `Marquer comme livré` and `Marquer comme non livré`;
- uncertain mission report: `Rapport d'itération n°N à vérifier. Cortex ne le renverra pas automatiquement.` with `Marquer comme livré` and `Marquer comme non livré`;
- uncertain mission follow-up: `Suivi de mission à vérifier. Cortex ne le renverra pas automatiquement.` with `Marquer comme livré` and `Marquer comme non livré`;
- mission delivered: `La mission reste en pause.` with `Reprendre la mission`;
- mission contract not delivered: `La mission reste en pause.` with `Reprendre la mission et préparer le contrat` and `Une nouvelle autorisation sera demandée.`;
- mission report not delivered: `La mission reste en pause.` with `Reprendre la mission et préparer de nouveau le rapport` and `Une nouvelle autorisation sera demandée.`;
- mission follow-up not delivered: `La mission reste en pause.` with `Reprendre la mission et préparer de nouveau le suivi` and `Une nouvelle autorisation sera demandée.`;
- conversation changed: `La conversation ChatGPT a changé. Rien n'a été renvoyé.` with `Réessayer` and `Retour aux conversations`;
- account changed: `Le compte ChatGPT a changé. Rien n'a été renvoyé.` with `Réessayer` and `Retour aux conversations`;
- classic surface rejected: `Cette page ChatGPT n'est pas une conversation classique. Aucun message n'a été envoyé.`;
- surface unverifiable: `Cortex ne peut pas vérifier cette page ChatGPT. Aucun message n'a été envoyé.`;
- account unverifiable: `Cortex ne peut pas vérifier le compte ChatGPT. Aucun message n'a été envoyé.`;
- extension reconnect title: `Reconnecter l'extension Cortex`;
- extension reconnect explanation: `Cortex ne peut pas vérifier l'extension Chrome. Les conversations restent visibles, mais aucun message ni mission ne peut être envoyé.`;
- extension reconnect actions: `Reconnecter l'extension` and `Rester en lecture seule`;
- extension reconnect progress: `Connexion sécurisée à l'extension…`;
- extension reconnect success: `Extension Cortex reconnectée. Vérifie de nouveau ta demande.`;
- expected extension missing: `L'extension Cortex attendue n'est pas disponible dans Chrome.`;
- extension enrollment expired: `La demande de connexion a expiré.`;
- transport consent missing: `Autorisation d'envoi requise` and `Cortex n'est pas autorisé à envoyer vers ChatGPT. Rien n'a été envoyé.` with `Gérer l'autorisation` and `Retour aux conversations`;
- transport consent withdrawn: `Autorisation d'envoi retirée` and `Cortex n'est plus autorisé à envoyer vers ChatGPT. Rien n'a été envoyé.` with `Gérer l'autorisation` and `Retour aux conversations`;
- STOP reset title: `Réactiver les actions ?`;
- STOP reset explanation: `L'arrêt global sera désactivé. Les envois et missions annulés ou en pause ne reprendront pas. Le consentement ne sera pas rétabli.`;
- STOP reset actions: `Réactiver les actions` and `Garder l'arrêt global`;
- STOP reset success: `L'arrêt global est désactivé. Aucune action n'a repris.`;
- uncertain creation: `Création à vérifier` and `Cortex ne sait pas si le dossier « cortex-live-test » a été créé.` with `Vérifier l'état du dossier`;
- uncertain creation, target absent: `Aucun dossier « cortex-live-test » n'est présent dans Bureau. Cortex ne relance rien.`;
- uncertain creation, directory present: `Le dossier « cortex-live-test » est présent, mais Cortex ne peut pas prouver qui l'a créé.`;
- uncertain creation, conflict: `Un fichier ou un lien utilise déjà le nom « cortex-live-test ». Rien n'a été modifié.`;
- migration progress: `Mise à niveau des messages locaux…`;
- migration failure: `La mise à niveau a échoué.` with `Réessayer` and `Ouvrir les diagnostics`;
- unbound legacy delivery: `Ancien envoi à vérifier. Cortex ne peut pas déterminer sa conversation.`;
- legacy attachment title: `Fichier ancien à vérifier`;
- legacy attachment keep: `Conserver en quarantaine` with `Le fichier reste en quarantaine. Il ne sera envoyé ni supprimé automatiquement.`;
- legacy attachment delete unavailable: `Cortex ne peut pas supprimer automatiquement ce fichier ancien.`;
- legacy attachment delete prompt: `Supprimer définitivement « X » ?` with `Cette action est irréversible. Le fichier ne sera associé à aucun message.`, `Supprimer le fichier`, and `Annuler`;
- legacy attachment delete pending: `Suppression autorisée. Le fichier sera supprimé après les vérifications de sécurité.`;
- legacy attachment deleted: `Le fichier ancien a été supprimé.`;
- legacy attachment changed: `Le fichier a changé. Rien n'a été supprimé.`;
- legacy attachment deletion unclear: `Suppression à vérifier` and `Cortex ne peut pas confirmer l'état du fichier ancien. Aucun nouvel essai ne sera lancé.` with `Vérifier l'état du fichier`;
- legacy inspection captured: `Le fichier ancien est conservé en sécurité. Aucun nouvel essai ne sera lancé.`;
- legacy inspection restored: `Le fichier est revenu en quarantaine. Il ne sera pas supprimé automatiquement.`;
- legacy inspection absent: `Le fichier est absent, mais Cortex ne peut pas prouver qui l'a supprimé.`;
- legacy inspection indeterminate: `L'état du fichier reste indéterminé.`;
- prewarm stop: `Arrêter le maintien actif` with `Cortex ne déchargera pas le modèle partagé.`;
- unsupported deletion: `Cortex ne peut pas supprimer de fichiers dans cette version. Modifie la demande ou envoie-la à ChatGPT pour obtenir des instructions.`;
- disabled-setting explanation: `Détection automatique des actions locales désactivée : Entrée envoie à ChatGPT. Le bouton Exécuter… reste disponible.`

## Test strategy

### Pure routing tests

- obvious chat bypasses Ollama and returns `send_exact_chat`;
- explanatory, quoted, hypothetical, and fully negated actions remain chat;
- polite action questions remain local and mixed negation becomes `ask_user`;
- the anonymized owner folder request returns `open_execution_preflight` without
  Ollama;
- ambiguous action invokes Ollama once;
- an Ollama `chat/high` result still returns `ask_user` and never sends;
- accents, case, punctuation, and whitespace do not alter intended results;
- an artifact span preserves exact case, including the distinction between
  `Sample` and `sample`;
- every operation except `create_directory` becomes a manual choice or notice
  in v0.5.4;
- hostile instructions cannot add schema fields, commands, paths, permissions,
  network, or deletion.

Each new behavior must be proven RED against the current implementation before
production code is written.

### Backend tests

- strict request and response validation;
- timeout, busy, absent model, malformed JSON, extra fields, and contradictory
  capabilities all fail closed;
- when `/api/tags` lists the model but `/api/ps` does not, `/api/chat` is never
  called, no prewarm starts from the submission, and `model_not_loaded` returns
  in under 250 ms; an observed eviction race returns `cold_race` without an
  untruthful no-load claim;
- no routing request changes SQLite, chat-runs, iteration files, missions,
  approvals, tool records, attachments, or user workspaces; a separately
  enabled named audit journal is tested independently;
- `model_attempted`, observed digest, and `decision_accepted` remain truthful;
- prewarming a model already loaded by another process, starting Cortex
  keepalive renewals, and stopping them never issues an unload; concurrent
  third-party use remains untouched;
- calling `/api/intent/route` alone creates no run, mission, token, writer,
  browser command, or tool call; interruption before finalization preserves the
  draft;
- missing/withdrawn consent and durable STOP are tested at reservation/upload,
  finalization, conversation-writer claim, each per-message
  `READY -> PREPARING_DISPATCH -> DISPATCHING`, immediately before browser command, mission resume,
  approval, and local tool. Barrier-controlled races run STOP versus first
  effect and consent withdrawal versus first effect in both winner orders. They
  prove the shared/exclusive gate, authorization epoch, consent version,
  pre-effect cancellation, post-effect uncertainty, restart persistence, and
  that retry cannot restore authority. For `create_directory`, STOP is blocked
  from `CREATE_PRIVATE` through durable `CREATED` or
  `CREATE_OUTCOME_UNCLEAR`; a STOP response can never precede a later unfenced
  publication;
- the legacy bodyless STOP-reset request is rejected. Reset tests cover exact
  configured Origin, JSON-only request, UI-session header and TTL, single-use
  nonce, reset-attempt ID, expected state version/authorization epoch,
  cross-origin simple POST, missing session/nonce, stale epoch, concurrent
  STOP/reset, and crash before/after commit. Exact attempt/digest replay returns
  the canonical operation result before nonce rejection plus fresh current
  safety state; a later STOP remains visibly latched, a changed replay returns
  409, and no old resource or consent is resurrected;
- server-issued conversation handles cannot be minted by the client; route IDs
  are opaque, expiring, single-use, conversation-bound, and reject
  cross-conversation clarification or finalization;
- two simultaneous provisional conversations receive different server keys and
  handles, rekey to different canonical URLs, survive generation changes
  without cross-talk, and reacquire handles safely after restart. Lost first-
  delivery receipts recover canonical identity only from the same durable
  extension dispatch-attempt record across backend and service-worker restarts;
  `DELIVERED` is rejected while that binding remains unproven;
- mutation-capable handles require the fixed extension ID, enrolled public key,
  signed live pairing challenge, matching instance/storage generation, stable
  account fingerprint, and fresh single-use payload/destination/epoch-bound
  `classic_chat` proof. Generic extension origins, self-declared replacement
  keys, proof replay, same-session account switch, missing/localized DOM,
  `unknown`, `work`, stale proof, canonical/new conversation, attachment,
  mission, and resume all fail before upload or composer mutation;
- 32 KiB request limits, 128 global routes, eight routes per conversation,
  oldest-route eviction, five-minute expiry, successor IDs, and
  `410 ROUTE_EXPIRED` are tested at their boundaries;
- expired finalization preserves the client draft and staged file and creates
  no token, run, mission, or writer admission;
- finalization rejects every client-supplied objective, message, path, scope,
  tool, policy, capability, URL, stale grant, and stale decision digest;
- text-plus-file routing requires a complete descriptor that never reaches
  Ollama; a raw upload/finalization descriptor mismatch returns
  `ATTACHMENT_CHANGED` before `CLAIMED`, `QUEUED`, outbox creation, or writer
  admission; the one preallocated `UPLOADING` resource becomes a terminal
  tombstone;
- preflight response includes the catalog candidate, French label `Bureau`, internal
  alias `desktop`, resolved display path, preallocated mission ID, and immutable
  cloud contract preview; routing reads a catalog entry but creates no
  `WorkspaceGrant`, while finalization persists exactly one grant;
- workspace catalog rejects arbitrary paths, symlinks, ownership changes, and
  stale revisions;
- workspace policy rejects candidates equal to `/` or home and any candidate
  equal to/inside/authority-bearing over a protected subtree, while accepting
  valid Desktop/Documents/Downloads descendants of home; it never accepts an
  ancestor of a granted root for tool access;
- replacing the workspace root with a symlink or different inode between
  approval and action fails the fd-bound grant check before mutation;
- the exact create-directory operation scope rejects list, read, search,
  alternate paths, and every unlisted tool;
- `allow_write: false` enforces read-only behavior server-side;
- confirmed capabilities, scope, and workspace grant persist and restore
  exactly; incomplete legacy state requires a new preflight;
- same idempotency key and digest returns the prior result across a simulated
  crash/restart, while a changed digest returns `409 IDEMPOTENCY_CONFLICT`
  before side effects; one route digest creates at most one durable result;
- failpoints before/after attachment reserve, raw `PUT` state commits, atomic
  claim/queue/outbox creation, no-file resource/outbox commit, writer refusal,
  outbox claim, and task scheduling recover the same durable resource; they
  prove reserve and raw upload create zero outboxes and zero writer admissions.
  Dispatch failpoints run after `READY -> PREPARING_DISPATCH`, after extension
  ledger reservation, after signed proof, before
  the atomic proof-consume/preparation-EXECUTING/outbox-DISPATCHING transaction,
  after that commit but before execute,
  after execute/click, after visible message, and before the SQLite receipt.
  They prove recovered preparation is no-effect and invalidated, while
  `DISPATCHING` never re-enters `READY`; two
  simultaneous HTTP finalizations prove the CAS permits one claimant and one
  dispatch only;
- transaction tests prove proof consumption,
  `DispatchPreparation ACTIVE -> EXECUTING`, and outbox
  `PREPARING_DISPATCH -> DISPATCHING` commit or roll back together. Injected/
  corrupted crossed pairs recover only as `DELIVERY_UNCERTAIN`; STOP winning
  before the transaction prevents execute, while STOP after commit observes the
  uncertain boundary;
- preparation recovery matrix covers canonical/provisional destination ×
  extension online/offline × crash/STOP/consent withdrawal/identity change/
  lease expiry. Every case durably invalidates backend attempt/proof before STOP
  acknowledgement; provisional ledger tombstones gate the next prepare after
  reconnect but do not block offline STOP. Only generic crash/lease plus explicit
  retry may CAS `PREPARING_DISPATCH -> READY` with one new attempt;
- finalization for chat, attachment, and mission creates
  `writer_state=WAITING_FOR_WRITER` plus an ineligible outbox and no writer
  lease. The explicit admission CAS alone creates one lease and makes that
  outbox eligible; capacity refusal, slot release, and restart never auto-admit.
  Partial unique-index tests reject chat/mission duplication on one destination,
  stale writer generations, and stale dispatch tokens before every extension
  command. Provisional rekey collision atomically records the exact existing
  Cortex conversation, releases the losing writer, creates one terminal
  `DESTINATION_COLLISION_DETACHED`, never merges history/outboxes, and preserves
  independent first-message delivered/uncertain evidence across restart;
- a multi-cycle mission creates one immutable outbox row per contract/report,
  with unique sequence and attempt; STOP between messages cancels later READY
  rows, and no `DISPATCHING` report is regenerated or resent after restart.
  Fake-clock tests take the mission beyond each lease TTL and prove the distinct
  conversation-writer lease stays fenced/renewed between messages, the third
  conversation remains refused, each message receives a distinct dispatch
  lease, and explicit pause/uncertainty releases then requires reacquisition;
- restart recovery from `WAITING_FOR_WRITER` reselects the exact durable
  `DestinationBinding` for existing and provisional conversations despite a
  different active tab. Account, generation, pairing, and conversation changes
  before any command produce typed `DEFINITIVE_PREDELIVERY_FAILURE`; the same
  changes after a possible command produce typed `DELIVERY_UNCERTAIN`;
- extension-instance persistence, backend restart, service-worker restart,
  extension reload, account switch, unavailable account fingerprint, and
  fingerprint-version change prove the binding either reselects exactly or
  fails closed;
- an effect created before a lost HTTP response is returned, not recreated, on
  retry; chat JSON is rebuilt from authoritative SQLite rather than used for
  recovery;
- handle expiry, record retention/capacity, tombstone GC, HMAC `key_id`
  rotation, old-key retention, 15-minute waiting expiry, pre-dispatch cancel,
  attachment release, and the rule that `DISPATCHING` cannot be cancelled or
  collected are tested at boundaries;
- opposing per-message reconciliation choices race through state-version CAS;
  one wins, identical replay before/after restart returns the same response,
  and reconciliation creates zero outbox rows. Later explicit mission resume/
  rebind reacquires the writer and may create one same-kind replacement with
  fresh ID/attempt, exact immutable bytes, and `supersedes_message_id`:
  `CONTRACT`, `ITERATION_REPORT`, and `FOLLOW_UP` never collapse into one generic
  follow-up, and no replacement repeats a local action. Separate fixtures for `CHAT`,
  `CONTRACT`, `ITERATION_REPORT`, and `FOLLOW_UP` verify exact sanitized preview,
  kind, sequence, destination, chat restoration, mission pause, and the rule
  that an unbound provisional first delivery cannot be marked delivered;
- legacy reconciliation endpoint tests cover canonical records, multiple root/
  unbound records, opposing CAS choices, identical replay, crash/restart,
  per-record unblocking, and zero outbox, current identity, binding, or transport;
- the ChatGPT mission payload contains no absolute home or mount path; a draft
  containing `/tmp/cortex-test-home/Desktop/cortex-live-test` stays local, and the preview exactly
  matches the sanitized transport bytes; SHA-256 of the preview returned before
  finalization equals the first payload passed to the extension, including the
  preallocated mission ID;
- every `CONTRACT`, `ITERATION_REPORT`, and `FOLLOW_UP` outbox payload rejects
  absolute paths, account/binding/grant data, secrets, and unbounded tool output;
- exact chat uses trimming only for emptiness and preserves leading/trailing
  spaces and newlines in storage, digest, and the Cortex-to-extension command;
  normalized ChatGPT confirmation is tested only as delivery evidence;
- every routed and manual mission endpoint rejects attachment fields before
  upload lookup; exact-chat attachment validation failure leaves the one
  `UPLOADING` resource terminal/non-dispatchable with no claim, queue, outbox, or
  writer; failure of the atomic claim/queue/outbox transaction rolls back all
  three transitions, and a same-key retry creates at most one upload record,
  resource, and outbox;
- upload reservation/raw PUT tests cover every CAS transition, byte overrun and
  underrun, wrong MIME/digest, crash between `O_EXCL` and inode receipt,
  heartbeat expiry, quarantine, claim, STOP/consent withdrawal, and mutual
  exclusion with recovery/collection. Missing/wrong upload authorization on
  PUT/GET/finalize/cancel fails before file open or state change; only the token
  HMAC is durable, lost reserve response reuses the browser-held token and same
  action, and raw token redaction is verified across logs/errors;
- lost-upload abandonment tests simulate renderer/page loss in
  `RESERVED`/`STREAMING`/`FSYNCED`: exact UI session, fresh conversation handle,
  state version, mutex/fencing, zero claim/outbox/writer/execute, expiry and
  cleanup are required. A concurrent finalization winner prevents the no-send
  result and exposes only its authoritative state; a successful abandonment
  permits one new route without duplicate resource or transport;
- same-key reserve, route expiry, response loss after `FSYNCED`, service restart
  in `RESERVED`/`STREAMING`/`FSYNCED`, shared 30-minute inactivity expiry,
  streaming absolute cap, and collector races return or atomically close the one
  durable lease/resource/action without creating an early outbox or duplicate;
- attachment lifecycle tests prove `CLAIMED -> RELEASED` is atomic with every
  non-replayable delivery/failure/uncertain/cancel/expiry outcome, retained
  evidence survives byte deletion, fd/device/inode-bound collection cannot
  delete an active claim, and `LegacyAttachmentQuarantine(REVIEW_REQUIRED)` is
  never handled by the generic collector. Opposing/replayed
  `KEEP_QUARANTINED`/`DELETE_APPROVED` decisions, restart, and retention are
  covered; files outside the verified private root cannot enter
  `DELETE_APPROVED`. Deletion barriers exercise verified root/parent dirfds, capture-name
  reservation, an exact replacement between resolution and atomic rename,
  replacement after capture but before fstat, durable `CAPTURED_MATCHED`, swap
  attempts before private-name unlink, parent fsync, and every crash boundary.
  Mismatch restores exclusively or enters `LEGACY_DELETE_OUTCOME_UNCLEAR`; only
  a matched captured private name can reach `DELETED`, and v0.5.4 never
  reassigns quarantined bytes;
- legacy delete-outcome inspection tests cover exact object only in staging,
  exact object restored at original name, neither present, both present, every
  identity mismatch, changed root/parent/staging, and observation failure. The
  strict state-version CAS is idempotent across restart, stale replay conflicts,
  copies/results are bounded, and syscall spies prove zero rename/restore/unlink/
  delete-worker invocation;
- a direct `create_directory("cortex-live-test")` mission uses `lstat` to prove the target
  absent, leaves it absent before confirmation and write approval, and creates
  one fresh inode only inside a disposable approved workspace;
- `create_directory` reports a pre-existing target truthfully instead of
  claiming a new creation;
- directory, regular file, valid symlink, dangling symlink, and a concurrent
  target appearing between probe and create all return `created:false`; the
  state machine rejects skipped/reordered cloud transitions, and only an
  exclusive private-name publication can reach `VERIFY_PUBLISHED_INODE`;
- a concurrent rename/replacement after publication but before verification
  yields an unclear outcome and never attributes the replacement inode to
  Cortex;
- crash failpoints immediately before/after private mkdir, publication, and
  before verified
  inode commit restore `CREATE_OUTCOME_UNCLEAR`, never replay or claim success,
  and require human reconciliation;
- create reconciliation proves absent, directory-present, file, and symlink
  outcomes via fd-bound `lstat`; same state-version replay is idempotent and a
  conflicting reconciliation returns 409;
- attachment descriptors reject every boundary violation and canonicalize all
  five identity fields; all artifact producers enforce 1–255 UTF-8 bytes and
  the directory mode cannot come from model or client input;
- the routed operation registry contains only `create_directory`; every other
  model operation fails closed to the documented manual outcome;
- installed-wheel smoke tests import the router and migrate SQLite; real CORS
  tests preserve positive `GET/POST/PUT/DELETE/OPTIONS`, `Content-Type`, and
  `Last-Event-ID`, add only `Idempotency-Key`/`X-Cortex-UI-Session`/
  `X-Cortex-Upload-Authorization`, reject every other origin/method/header, and
  separately prove application authentication. On macOS the installed wheel
  imports `rename_exclusive` and performs disposable capability, successful
  publish/inode, and `EEXIST` no-replacement checks; unsupported capability
  hides the routed preflight;
- upgrade tests import legacy JSON once under lock, restore non-terminal
  per-conversation or unbound blocks while keeping global writer slots free,
  recover from a migration crash, rebuild the JSON cache from SQLite, and make a
  second startup idempotent. Fixtures cover pre-identity schema, two root-URL
  runs, `FAILED + DELIVERY_UNCERTAIN`, generic transport crash, attachment,
  canonical `/c/`, root plus `provisional:*`, two simultaneous root runs,
  truncated JSON, and unknown fields. Migrated records are reconciliation-only,
  never acquire current identity, and never create outbox rows; each imported
  block is resolvable only through the dedicated legacy CAS endpoint. Policy-
  table tests prove state/timestamps alone never count as receipts, validate all
  receipt linkage fields and precedence, persist policy/reason, and send unknown,
  contradictory, unsupported, or unlinked rows to reconciliation;
- startup-order tests prove migration and recovery finish before orphan
  collection; durable upload leases survive crash, and a concurrent collector
  cannot delete an active or referenced upload;
- a fake Ollama server that keeps working after client disconnect proves the
  circuit breaker blocks new calls without claiming daemon termination.

### Chrome extension tests

`node --test chrome-extension/tests/extension.test.mjs` is a mandatory gate,
not replaceable by frontend fixtures or mocked browser E2E. RED-first tests
must prove:

- strict current protocol validation and read-only rejection of mutation
  commands from older protocol versions;
- fixed manifest key and expected extension ID, exact WebSocket Origin, generic
  extension-Origin rejection, one-time targeted enrollment, Ed25519 challenge
  possession, stable service-worker restart identity, and explicit re-enrollment
  after key/storage reset;
- account/workspace raw identifiers never leave the extension or appear in
  backend storage/logs, while a fingerprint change revokes every mutation;
- fresh single-use signed `SurfaceProof` bound to pairing, command/attempt,
  tab/window, exact URL, payload, fingerprint, epoch, consent version, nonce,
  and timestamp before each insertion/click; `command.prepare` performs no DOM
  mutation, `command.execute` reobserves/consumes exactly once, and replay or any
  changed field fails. Lost execute result becomes uncertain while lost prepare
  remains definitive no-effect.
  `work`, `unknown`, missing/localized DOM, stale proof, and account mismatch
  fail closed under their distinct codes;
- authorization epoch, consent version, and STOP rechecks before every command;
- monotonically fenced writer and dispatch tokens are checked on every command;
  stale owners and known duplicate destination leases fail before DOM access;
  a collision discovered only after provisional canonical navigation is durably
  detached before any second DOM command;
- bounded authenticated persistence and recovery of
  `dispatch_attempt_id -> selected tab -> canonical /c/... -> fingerprint`
  across service-worker restart, including two provisional conversations, lost
  receipts, changed account, pinned unresolved entries, storage-write failure,
  capacity reservation during `PREPARING_DISPATCH` before its transition to
  `DISPATCHING`, capacity exhaustion, eviction of acknowledged tombstones only,
  and absence of active-tab fallback.
- backend preparation invalidation revokes old attempt/proof even with the
  extension offline; on reconnect, provisional ledger tombstones synchronize
  before another prepare, canonical prepares require no ledger tombstone, and
  no prepared command can execute across pairing-session or attempt-generation
  change.

### Frontend tests

- Enter and `Continuer` call the same router on the exact folder request and do
  not call `onChatSend` directly;
- `Nouvelle conversation` keeps its composer unavailable until the provisional
  endpoint returns; success, timeout, retry, return, and two independent new
  conversations use the documented copies and controls;
- destination collision focuses the exact detached-duplicate notice, disables
  its composer permanently, and exposes only the server-recorded `Ouvrir la
  conversation déjà liée` and `Retour aux conversations` actions. Delivered and
  uncertain first-message variants, restart, keyboard, and active-tab mismatch
  never merge or create another outbox;
- the preflight shows original draft, exact `cortex-live-test`, structured French
  interpretation `Créer le dossier « cortex-live-test » dans Bureau.`, French label
  `Bureau`, alias `desktop`, resolved `~/Desktop` path, operation scope, and
  required write;
- `Modifier la demande` invalidates the route; a changed name or target can be
  confirmed only after a complete new decision;
- `Envoyer seulement à ChatGPT` sends the original draft once;
- clarification uses the local panel, adds no conversation message, and never
  calls chat or mission endpoints;
- closing, editing, or switching conversation keeps the draft and invalidates
  stale results;
- adding, removing, or replacing a staged file invalidates route, notice, and
  preflight; a changed file cannot reuse the previous finalization digest or
  idempotency key. During `uploading`, draft edit, file change, or conversation
  switch aborts and cancels the old action, preserves the new local state, and
  cannot later finalize the old upload;
- normal chat remains unchanged at the Cortex-to-extension payload boundary and
  finalizes automatically without a second gesture;
- the full input matrix is tested: Enter, `Continuer`, text plus file, file
  only, `Exécuter…`, capture, disabled routing, and unavailable router;
- attachment-only input and capture bypass classification;
- choosing ChatGPT with an attachment shows the preparation/streaming states,
  uses reserve then raw `PUT`, and creates no outbox before successful
  finalization; choosing a routed or manual mission with a staged file shows the
  unsupported notice and never performs a decorative filename-only handoff;
- upload UI tests cover failure before the first byte, mid-body interruption,
  lost reserve response, lost response after `FSYNCED`, restart in each lease
  state, cancellation, expiry, draft/file/conversation change, and result lookup.
  They verify one browser-held upload token is reused only for that action,
  accessible status/focus, reliable-or-indeterminate progress, preserved input,
  exactly one resource/upload, no involuntary send, safe `FSYNCED` continuation,
  and mandatory new preparation for every partial body;
- page reload, tab close/reopen, and renderer crash with token loss in
  `RESERVED`/`STREAMING`/`FSYNCED` show the exact unrecoverable-upload copy. Close
  waits for expiry; file reselection first receives durable abandonment. Tests
  prove zero old outbox/send, no raw-token persistence, authoritative handling
  when finalization won the race, and one fresh route only;
- an expired preflight closes, preserves draft/file, announces expiry, and
  offers `Vérifier de nouveau`;
- `PREFLIGHT_CHANGED` follows the same safe reroute flow with its dedicated
  copy;
- `TARGET_ALREADY_EXISTS` shows the exact neutral copy, requests no approval,
  and does not use a generic failure state;
- `DELIVERY_UNCERTAIN` fixtures for `CHAT`, `CONTRACT`, `ITERATION_REPORT`, and
  `FOLLOW_UP` show kind, sequence, destination, exact sanitized payload preview,
  evidence and kind-specific French copy; they never auto-retry and expose only
  their permitted chat or mission reconciliation actions.
  `CREATE_OUTCOME_UNCLEAR` independently exposes only authoritative inspection;
- create reconciliation renders the three authoritative inspection outcomes and
  never asks the user to claim authorship; a new attempt requires a new route;
- writer waiting shows `Réessayer/Annuler`, expiry shows `Préparer un nouvel
  envoi`, both preserve browser input, and cancellation disappears at
  `DISPATCHING`;
- dispatch preparation UI tests cover the 150 ms threshold, chat and each
  mission-kind copy, ledger capacity/write failure, crash after state entry/
  ledger/proof/before DISPATCHING, cancel, explicit retry and double retry.
  Focus/keyboard, zero DOM effect, zero extra outbox, authoritative invalidation,
  tombstoned old proof/ledger, one fresh attempt, dedicated STOP/consent/
  identity errors, and cancel disappearing at `DISPATCHING` are mandatory;
- missing consent and withdrawal in `PREPARING_DISPATCH` test the exact focused
  title/copy, `Gérer l'autorisation`/`Retour aux conversations`, preserved
  draft/file, close/keyboard, fresh grant without auto-resume, and one new
  attempt only after explicit retry. Withdrawal after `DISPATCHING` must render
  delivery uncertainty and never the no-send copy;
- marking uncertain delivery as non-delivered restores exact text with a new
  key and requires reselecting any attachment. Each mission kind exposes both
  `Marquer comme livré` and `Marquer comme non livré`; either stays paused, and
  non-delivery offers only its contract/report/follow-up replacement action with
  a new authorization. Labels, focus, delivered/non-delivered paths, immutable
  preview, and zero reconciliation outbox are tested for every kind;
- `WORK_SURFACE_REJECTED`, `SURFACE_UNVERIFIED`, `ACCOUNT_UNVERIFIED`,
  `ACCOUNT_CHANGED`, and `CONVERSATION_CHANGED` use distinct copies, focus the
  local error, preserve draft/file, expose the exact `Réessayer` and `Retour aux
  conversations` actions, create a new route/binding only after fresh proof,
  never auto-resume, and never fall back to the active tab;
- extension reconnect UI tests verify focus/keyboard, read-only exit, exact
  expected-ID targeting, missing/wrong ID, expired token, lost enrollment key,
  progress/success/failure copy, successful re-enrollment, preserved draft/file,
  revoked old handles/routes, and a mandatory new route before any mutation;
- STOP reset tests verify the focused title/explanation, `Réactiver les actions`
  and `Garder l'arrêt global`, keyboard/Escape/close behavior, preserved STOP on
  cancel, success copy, double gesture, stale epoch/nonce, concurrent STOP,
  refreshed state without auto-retry, no restored consent, and no resurrected
  message, mission, approval, upload, or tool;
- migration progress, failure/retry/diagnostics, unbound legacy state, and the
  reconciliation handoff are visible before affected composers become usable;
- legacy attachment UI tests verify focused details, keep copy and durable
  non-collectable state, two-step irreversible delete confirmation, keyboard/
  Escape/close, approval-versus-actual-deletion copy, opposing/replayed/stale
  CAS, restart, deletion unavailable outside the verified private root,
  deletion-worker completion, inode replacement, and that no bytes
  disappear before exact deletion evidence. Capture/restore failure shows the
  exact `Suppression à vérifier` flow with authoritative inspection only and no
  automatic second delete. Inspection tests cover captured/restored/absent/
  indeterminate copies, focus, replay/stale/restart, root/parent/staging
  replacement, present original, present staging, both, neither, and zero
  filesystem mutation;
- `notice` focus, Escape, and return to the intact draft are tested;
- double click produces one final action;
- double Enter or double `Continuer`, interruption between route/finalize, and a
  lost finalization response all preserve one final message/resource;
- two concurrent conversation classifiers do not share state;
- a third writer refusal preserves its complete state.

### Browser E2E

- before the user's final choice, spies prove zero chat, attachment, screenshot,
  task, mission, extension-command, store-mutation, approval, and tool calls;
- exactly one complete route decision and expected panel/preflight must appear,
  so swallowing the submission cannot pass;
- an obvious chat first completes a side-effect-free route, then one automatic
  finalization; network interception proves `/route` itself sent nothing;
- slow/recovered dispatch preparation shows the exact no-send status and
  cancel/retry actions. Failpoints after state entry, ledger, proof, and before
  DISPATCHING prove no DOM effect; retry creates one fresh attempt, double retry
  is fenced, dedicated STOP/consent/identity copy wins, and cancel disappears
  immediately at DISPATCHING;
- obvious local request opens a centered, accessible preflight at 375, 768, and
  1440 pixels;
- ambiguous request displays one local clarification;
- fallback remains usable with Ollama disabled;
- rule result at 50 ms shows no flash, 151 ms shows the live status, and a warm
  model timeout at two seconds enters fallback;
- a model installed but absent from `/api/ps` returns the manual choice without
  calling `/api/chat` or loading it from the composer;
- every row of the input matrix reaches its documented path, including the
  `Continuer` button and the router-unavailable panel;
- classic-surface proof is positive for each mutation; `work`, `unknown`,
  missing/localized DOM, same-session account switch, stale fingerprint, and old
  extension protocol all fail before upload/text insertion/click with distinct
  recovery copy, explicit retry, preserved input, and no auto-resume;
- missing/wrong extension identity and key loss open the exact read-only
  reconnect view; keyboard operation covers stay-read-only, expired token,
  expected-ID-only successful enrollment, preserved input, and new-route-before-
  mutation with no automatic resend;
- barrier-controlled consent-withdrawal and STOP races immediately before
  upload/open, click, mission report, approval, and local tool run both winner
  orders, preserve input/evidence, and prove either no effect or explicit
  uncertainty according to the first-effect boundary;
- consent absent/withdrawn before DISPATCHING shows the exact focused consent
  flow; keyboard/close and local consent management preserve input, a fresh grant
  does not resume, and explicit retry creates one new attempt. Withdrawal after
  DISPATCHING stays delivery-uncertain with no no-send promise;
- the complete STOP-reset confirmation is operated by keyboard: cancel/close
  retains STOP, success shows the exact no-resume/no-consent result, stale or
  concurrent state requires a new gesture, and neither lost-response retry nor
  successful reset restarts any prior work;
- legacy attachment quarantine is exercised through keep and two-step delete
  paths, including focus/Escape, restart, stale/opposing choice, delayed
  deletion-worker confirmation, and barriers that replace the leaf before
  capture, after capture, and before private-name unlink. Only matched capture
  reports deletion; restore failure shows the exact unclear/no-retry flow, and
  the read-only inspection button renders captured/restored/absent/indeterminate
  outcomes with no filesystem mutation;
- attachment add/remove/replace invalidates visible local state and cannot
  finalize an earlier decision. Network cuts before byte, mid-body, and after
  durable `FSYNCED`, plus cancel and service restart, exercise the exact upload
  copy/actions and prove one resource, zero early outbox, and no implicit send.
  Page reload/token loss exercises close/expiry and explicit abandon-before-
  reselect without persisting the raw token or creating a duplicate;
- two provisional conversations rekey to their own canonical ChatGPT
  conversations without following whichever tab is active; a lost first receipt
  and service-worker restart recover only through the matching dispatch-attempt
  ledger and cannot mark delivery while the canonical target is unproven;
- a forced provisional-to-canonical collision detaches the duplicate, releases
  its slot, shows the exact recorded existing Cortex conversation, and permits
  only navigation/return; delivered and uncertain variants survive restart with
  no merge, active-tab fallback, or later duplicate send;
- account/conversation change before any command shows definitive failure and a
  new-route path; the same change after a possible command opens typed delivery
  reconciliation. Neither path selects the current tab;
- expired and changed preflights preserve input, announce the exact French
  reason, and require a new route;
- the process toggle is absent from routed preflights; before the manual toggle
  can be enabled, its visible warning states that scripts are not OS-confined
  and may act outside the workspace, use the network, or be destructive;
- no console error, hydration error, horizontal overflow, or focus loss.

### Live owner acceptance

After automated gates pass, the owner runs the anonymized acceptance fixture
from Cortex only. The test stops at each real human approval boundary.

PASS requires:

1. prove with `lstat` that the exact Desktop entry `cortex-live-test` is absent; if it
   exists, verdict is `UNCLEAR` and nothing is deleted automatically;
2. type exactly `cree moi un dossier cortex-live-test sur mon bureau` in Cortex and press
   Enter without using `Exécuter…`;
3. observe no ordinary ChatGPT refusal and no external send before the
   preflight;
4. verify `source=rules`, `model_attempted=false`, and `model_used=null`;
5. verify the original draft, exact lowercase name `cortex-live-test`, French structured
   interpretation `Créer le dossier « cortex-live-test » dans Bureau.`, French label
   `Bureau`, internal alias `desktop`, resolved `~/Desktop` path, exact operation
   scope, required write, and no process/network/deletion;
6. prove the folder absent before and after starting the mission;
7. approve only `create_directory("cortex-live-test")` for the Desktop grant;
8. prove one new entry and inode after approval, terminal mission evidence, and
   no unrelated Desktop entry change;
9. prove only the server-bound selected conversation received the expected
   visible mission protocol and no other conversation changed.

## Documentation changes

Implementation must update:

- `docs/routing-policy.md`;
- `docs/interface.md`;
- `docs/user-guide.md`;
- the v0.5.0 design with a supersession note rather than rewriting history;
- French onboarding and composer help copy;
- architecture animation labels if the new router appears in the information
  diagram;
- testing and release evidence documentation.

Public repository prose remains English. Application copy remains French.

## Rollout and release gates

- Keep the existing manual `Exécuter…` action as a fallback.
- Add an `intent_routing_enabled` setting; default it on for the owner candidate
  and allow an immediate opt-out.
- Enable the intent-routed `create_directory` implementation on macOS first.
  Other operating systems keep exact chat and the manual fallback until an
  equivalent rooted-handle implementation passes the same identity, race, and
  symlink/reparse-point gates; existing non-routed platform support is not
  removed.
- Do not claim Ollama classification unless model name, digest, valid response,
  and latency were observed.
- Do not make the optional model an installation prerequisite.
- Run full backend tests under Python 3.11 and 3.14, the mandatory real
  `node --test chrome-extension/tests/extension.test.mjs` suite, frontend
  unit/contracts, typecheck, lint, build, E2E, accessibility, privacy, links,
  secrets, and live owner acceptance.
- No tag, merge, push, or release-ready claim follows from unit tests alone.

## Acceptance verdict

The feature is complete only when obvious local intent reaches a confirmed
mission without first producing a normal ChatGPT refusal, ambiguous intent is
resolved locally, exact chat stays exact, and no classifier result can cross
the policy, workspace, or approval boundaries.
