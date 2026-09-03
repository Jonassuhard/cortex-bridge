# Cortex Bridge Local Alias Action Architecture Addendum

**Status:** Approach A approved by the owner; written addendum pending owner review
**Date:** 2026-09-03
**Target:** v0.5.4 candidate
**Normative scope:** This addendum resolves the local-folder authority conflict
between the approved storage and hybrid-intent designs. Where those documents
conflict on Desktop, Documents or Downloads, this addendum takes precedence.

## Decision

Cortex Bridge separates two execution classes:

1. `general_mission` uses ChatGPT, writer leases, mission outboxes and the
   generic `ToolExecutor`. Its workspace remains the verified encrypted vault's
   `20_WORKSPACES` root or a descriptor-opened descendant on the same APFS
   volume.
2. `local_alias_action` performs one deterministic local operation against one
   server-owned standard alias. In v0.5.4 the only operation is
   `create_directory` for one validated leaf below `desktop`, `documents` or
   `downloads`.

A local alias action is not a mission. It does not send anything to ChatGPT,
claim either of the two conversation writers, create a mission/outbox, invoke
the generic executor, or acquire read, listing, move, deletion, process or
network capability. It is persisted, displayed and approved as a separate
local action.

This keeps the external vault mandatory for general agent work without making
it a disguised preference that arbitrary missions can escape. It also preserves
the owner's required product behavior: an obvious request such as
`cree moi un dossier cortex-live-test sur mon bureau` can create that exact
folder after a visible one-shot approval.

## Superseded clauses

The following meanings are narrowed, not deleted:

- In `2026-09-02-storage-cutover-and-qa-design.md`, “every mission” continues to
  mean every `general_mission`. The `20_WORKSPACES` confinement, APFS identity,
  `WorkspaceHandle`, generic executor and process rules remain unchanged.
- In `2026-08-31-hybrid-intent-router-design.md`, `desktop`, `documents` and
  `downloads` are no longer general-mission workspace grants. They are
  `local_alias_action` targets only. `default_workspace` remains a vault-backed
  general-mission target.
- The earlier live Desktop acceptance remains required, but it proves a local
  alias action and explicitly proves zero ChatGPT, writer, mission, outbox and
  extension effects.
- Additional registered project folders are not local alias targets in v0.5.4.
  They may be used only as vault-backed general-mission descendants. Expanding
  local alias actions requires a new design and owner approval.

No other storage, intent, approval, STOP, browser, privacy or release rule is
weakened by this addendum.

## Goals

- Permit one obvious, explicitly approved folder creation in Desktop,
  Documents or Downloads while required external storage is healthy.
- Preserve the vault as the only authority for general missions and generic
  tools.
- Keep local alias selection server-owned and immune to client path injection.
- Bind every local effect to one alias, one catalog revision, one leaf, one
  action, one payload digest, one nonce and one STOP/authorization epoch.
- Use descriptor-relative, no-follow filesystem operations with deterministic
  crash and race outcomes.
- Refuse safely when macOS privacy controls, identity changes or storage state
  prevent proof.
- Never open a TCC-protected standard alias during startup, routing or
  finalization. A separate user-triggered access check is the only pre-write
  action allowed to cause a macOS privacy prompt.
- Make the UI say “Action locale” rather than pretending that ChatGPT executed
  or verified the filesystem change.

## Non-goals

- No general mission outside `20_WORKSPACES`.
- No arbitrary local path, user-provided absolute path, home-directory grant,
  filesystem-root grant or client-created allowlist.
- No local alias registration beyond `desktop`, `documents` and `downloads`.
- No nested path, wildcard, glob, regular expression or multi-entry request.
- No local file read, directory listing, search, write-file, move, copy,
  rename, overwrite, delete, user/model process, shell, network, attachment or
  capture operation. The fixed, attested local-alias worker described below is
  an internal implementation boundary, never an exposed process capability.
- No ChatGPT message, browser command, writer lease, mission, mission report or
  outbox for a local alias action.
- No automatic macOS permission change, Full Disk Access grant, Accessibility
  grant or implicit TCC prompt. Cortex may display and observe the result of a
  separately confirmed per-alias access check; it never clicks or accepts the
  system prompt.
- No automatic cleanup or deletion of a created or uncertain directory.
- No weakening of required-storage startup, transition, managed-start or STOP
  gates.

## Authority partition

```text
one composer
  |
  +-- exact/ordinary chat -----------------> ChatGPT chat path
  |
  +-- general agent work ------------------> GeneralMission
  |                                           |
  |                                           +-- VaultWorkspaceHandle
  |                                           +-- MissionLoop
  |                                           +-- ToolExecutor
  |                                           +-- writer/outbox/extension
  |
  +-- exact standard-folder mkdir ---------> LocalAliasAction
                                              |
                                              +-- LocalAliasHandle
                                              +-- EffectGate
                                              +-- mkdirat only
                                              +-- no ChatGPT/browser/writer
```

The server, never the frontend or classifier, selects the execution class.
The route token freezes that class before finalization.

## Frozen types

Python uses snake case. HTTP and frontend JSON use camel case.

```python
ExecutionClass = Literal["general_mission", "local_alias_action"]
LocalAlias = Literal["desktop", "documents", "downloads"]
LocalAliasOperation = Literal["create_directory"]
LocalAliasState = Literal[
    "awaiting_approval",
    "active",
    "created",
    "failed_safe",
    "outcome_unclear",
    "cancelled_by_stop",
]

@dataclass(frozen=True, slots=True)
class VaultWorkspaceRef:
    kind: Literal["vault"]
    catalog_entry_id: str
    revision: int
    storage_transaction_id: str
    root: Literal["20_WORKSPACES"]

@dataclass(frozen=True, slots=True)
class LocalAliasRef:
    kind: Literal["local_alias"]
    alias: LocalAlias
    catalog_entry_id: str
    revision: int

WorkspaceRef = VaultWorkspaceRef | LocalAliasRef
```

`WorkspaceRef` is routing metadata, not an executable capability. A client
cannot construct authority by posting either shape.

```python
@dataclass(frozen=True, slots=True)
class LocalRootIdentity:
    device: int
    inode: int
    uid: int
    mode: int

@dataclass(frozen=True, slots=True)
class LocalDescriptorEdge:
    parent_fd: int
    child_fd: int
    child_name: bytes
    child_identity: LocalRootIdentity

@dataclass(frozen=True, slots=True)
class LocalAliasCatalogEntry:
    catalog_entry_id: str
    revision: int
    alias: LocalAlias
    label: str
    allowed_execution_classes: tuple[Literal["local_alias_action"], ...]

@dataclass(frozen=True, slots=True)
class LocalAliasAccessObservation:
    observation_id: str
    effect_id: str
    catalog_entry_id: str
    catalog_revision: int
    alias: LocalAlias
    root_identity: LocalRootIdentity
    authorization_epoch: int
    verified_at: float
    expires_at: float

@dataclass(frozen=True, slots=True)
class LocalAliasGrant:
    grant_id: str
    action_id: str
    catalog_entry_id: str
    catalog_revision: int
    access_observation_id: str
    alias: LocalAlias
    root_identity: LocalRootIdentity
    operation: LocalAliasOperation
    allowed_leaf: str
    route_digest: str
    stop_epoch: int
    authorization_epoch: int

@dataclass(frozen=True, slots=True, init=False)
class LocalAliasHandle:
    action_id: str
    alias: LocalAlias
    chain: tuple[LocalDescriptorEdge, ...]
    root_fd: int
    root_identity: LocalRootIdentity
    alias_leaf: str
    allowed_leaf: str
    _authority: object

    def revalidate_chain(self) -> LocalRootIdentity: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
```

Only the fixed local-alias worker can construct `LocalAliasHandle`, and the
handle never leaves that child process. Starting from an opened filesystem-root
FD, the worker walks the absolute `getpwuid_r()` home path and fixed alias leaf
with `openat(O_DIRECTORY | O_NOFOLLOW)`. It retains a
`F_DUPFD_CLOEXEC` FD and identity for every parent-to-child edge, including the
home and alias roots. It owns and closes every duplicate on each terminal/error
path and treats use-after-close as a closed error. `revalidate_chain()` uses
`fstatat(parent_fd, child_name, AT_SYMLINK_NOFOLLOW)` on every retained edge and
requires the named entry still resolves to the retained child identity.

`LocalAliasHandle` is not a subtype of `WorkspaceHandle`. It cannot be passed
to `ToolExecutor`, `MissionLoop`, process launch, browser transport or any
generic tool registry.

```python
@dataclass(frozen=True, slots=True)
class LocalAliasWorkerRequest:
    operation: Literal["verify_access", "create_directory"]
    alias: LocalAlias
    allowed_leaf: str | None
    catalog_entry_id: str
    catalog_revision: int
    expected_identity: LocalRootIdentity | None

@dataclass(frozen=True, slots=True)
class LocalAliasWorkerReceipt:
    operation: Literal["verify_access", "create_directory"]
    alias: LocalAlias
    root_identity: LocalRootIdentity | None
    created_inode: int | None
    code: str

class LocalAliasWorkerRunner:
    async def run(
        self,
        *,
        request: LocalAliasWorkerRequest,
        activation: EffectActivation,
        deadline_seconds: Literal[60] = 60,
    ) -> LocalAliasWorkerReceipt: ...
```

The manifest-owned `executor/local_alias_worker.py` is invoked only through
this runner using the equipped installed Python and a reviewed fixed script.
Operation data travels as bounded JSON over private stdin, never argv or a
shell. Before spawn the runner verifies the installed script's manifest hash,
device, inode, owner and mode. The child starts blocked on a private control FD;
the parent records PID, PGID and start identity durably, then releases it only
after effect activation and ownership are both durable. The child has a
sanitized environment, inherits no unrelated FD, cannot invoke another
program, and emits one bounded non-path receipt.

```python
@dataclass(frozen=True, slots=True)
class LocalAliasActionRecord:
    action_id: str
    route_digest: str
    grant_id: str
    alias: LocalAlias
    operation: LocalAliasOperation
    allowed_leaf: str
    payload_digest: str
    stop_epoch: int
    authorization_epoch: int
    state: LocalAliasState
    created_inode: int | None
    terminal_code: str | None

class LocalAliasActionService:
    def finalize(
        self,
        *,
        route_id: str,
        conversation_handle: str,
        catalog_entry_id: str,
        catalog_revision: int,
        decision_digest: str,
    ) -> LocalAliasActionRecord: ...

    def prepare_approval(self, action_id: str) -> ApprovalChallenge: ...

    def execute(
        self,
        *,
        action_id: str,
        approval: ApprovalReceipt,
    ) -> LocalAliasActionRecord: ...

    def reconcile_startup(self, action_id: str) -> LocalAliasActionRecord: ...
```

The durable-effect owner set adds `local_alias_action`. Its category is always
`filesystem`. This addendum also extends the durable effect category union
normatively:

```python
EffectOwner = Literal["mission", "direct_ui", "admin_ui", "local_alias_action"]
EffectCategory = Literal["filesystem", "process", "browser", "sensitive_read"]
```

`verify_local_alias_access` uses `owner_kind="direct_ui"` and
`category="sensitive_read"`. `create_directory` uses
`owner_kind="local_alias_action"` and `category="filesystem"`. The existing
backend screenshot operation is also `sensitive_read`; no other operation may
claim that category without entering the exact effect inventory. The client
never supplies owner kind or category.

## Standard alias resolution

The server knows exactly three standard alias definitions:

| Alias | Filesystem leaf below the verified user home | French label |
| --- | --- | --- |
| `desktop` | `Desktop` | `Bureau` |
| `documents` | `Documents` | `Documents` |
| `downloads` | `Downloads` | `Téléchargements` |

The effective user and home come from `getuid()` plus `getpwuid_r()`, never
from client JSON, route text, `$HOME`, a shell expansion or model output.
Startup records only the fixed definitions and reports their access state as
`unverified`; it does not open Desktop, Documents or Downloads.

The UI exposes one separate action per alias:

```text
Vérifier l’accès à Bureau
macOS peut demander votre autorisation. Cortex ne peut pas la valider à votre place.
```

Only an explicit click may start this two-step API:

```http
POST /api/local-aliases/{alias}/verify-access/prepare
POST /api/local-aliases/{alias}/verify-access
Origin: CORTEX_FRONTEND_ORIGIN
X-Cortex-UI-Session: runtime-bound-session-token
Content-Type: application/json

{
  "verificationId": "server-minted-verification-id",
  "effect": {
    "requestId": "server-minted-request-id",
    "epoch": 7,
    "operation": "verify_local_alias_access",
    "payloadDigest": "sha256-hex"
  }
}
```

Prepare requires healthy storage/runtime state, creates no product row and
does not open the alias. It returns the exact alias, warning, verification ID
and effect envelope. The prepared challenge lives only in bounded memory for
two minutes, is single-use, is capped at eight per UI session and 128 globally,
and is invalidated by restart, STOP, consent or authorization-epoch change.
Execute requires the same exact Origin/UI session and byte-identical envelope,
then persists and activates a `direct_ui`/`sensitive_read` effect, starts the
owned worker blocked, records its process identity, and releases it before the
first alias `openat`. The worker has a strict 60-second monotonic deadline. A
changed request, alias, digest, session or epoch fails closed. Before a local
write is approved, this explicit access check is the only operation allowed to
trigger a TCC prompt. Cortex never interacts with that prompt. A successful
result terminalizes the effect and
persists a 15-minute
`LocalAliasAccessObservation` bound to alias identity, catalog revision and
authorization epoch. STOP, consent change, process restart, expiry or catalog
change invalidates it.

STOP, timeout, EOF, malformed receipt, worker crash or cancellation terminates
and revalidates the exact owned process group, closes every pipe/FD, records a
terminal failed sensitive-read effect, and creates no access observation.
Explicit `EPERM`/`EACCES` is `LOCAL_ALIAS_PERMISSION_REQUIRED`; timeout, crash,
EOF, a dismissed/unobserved system decision, or any unknown result is
`LOCAL_ALIAS_ACCESS_UNCLEAR`. Because neither result authorizes a subsequent action
or may have changed a Cortex-managed resource, it does not block STOP reset.
Cortex does not claim it can close an orphaned macOS dialog; the UI may tell the
owner to close one, while the dead worker and absent observation make it
non-authorizing.

During that explicit check, and again after local-write approval during
execution, the resolver rejects `uid == 0` and verifies:

- every traversed component is a real directory and not a symlink;
- the alias root is owned by the effective user;
- device, inode, UID and file type match the catalog revision;
- the alias is not equal to `/`, the complete home, `CORTEX_HOME`, the vault,
  a browser profile, credential store, Keychain path or device path;
- the alias is readable enough to retain and revalidate its descriptor chain;
- a TCC denial is reported, never bypassed or converted into a different root.

An absent standard directory returns `LOCAL_ALIAS_UNAVAILABLE`. A changed
device, inode, owner, type, symlink state or catalog revision returns
`LOCAL_ALIAS_CHANGED`. `EPERM` and `EACCES` return
`LOCAL_ALIAS_PERMISSION_REQUIRED`. None has a path fallback.

The catalog and access observation store identity and provenance, not an open
FD. Startup, routing and finalization never open the alias. The approved write
worker reopens the complete chain and compares it with both records. If macOS
revoked access since verification, this post-approval open may display a new
system prompt; the preflight warns about that possibility, the same 60-second
deadline/owned-worker cancellation applies, and Cortex never controls the
prompt.

## Leaf validation

The server derives the candidate leaf from deterministic routing or a locally
clarified answer. The client echoes it only through the route decision digest.
It never posts a free path.

A valid v0.5.4 leaf:

- is NFC-normalized UTF-8;
- is exactly one non-empty path component;
- is at most 120 UTF-8 bytes;
- contains no `/`, NUL, ASCII control character or bidi override/control;
- is not `.` or `..`;
- does not begin with `.`;
- has no leading or trailing whitespace;
- is returned byte-for-byte in the visible interpretation before approval.

Case folding is not used. The exact requested lowercase
`cortex-live-test` remains lowercase. If normalization would change the user's
visible value, Cortex shows the normalized candidate and requires explicit
confirmation before finalization.

## Routing contract

The four top-level router outcomes remain unchanged. An obvious supported
local request returns `open_execution_preflight`, with this additional payload:

```json
{
  "executionClass": "local_alias_action",
  "operation": "create_directory",
  "alias": "desktop",
  "label": "Bureau",
  "leaf": "cortex-live-test",
  "catalogEntryId": "server-minted-opaque-id",
  "catalogRevision": 7,
  "accessState": "verified",
  "accessObservationId": "server-minted-observation-id",
  "decisionDigest": "sha256-hex",
  "requires": {
    "writeApproval": true,
    "chatgpt": false,
    "writer": false,
    "read": false,
    "process": false,
    "network": false,
    "deletion": false
  }
}
```

The opaque ID above illustrates the field and is not a valid test fixture.
Tests use a generated UUID and exact digest.

With no fresh access observation, the same preflight returns
`accessState="verification_required"` and no observation ID. Its execution
button remains disabled until the user explicitly runs the per-alias access
check. Routing never opens the protected alias in the background.

Deterministic rules own the frozen obvious phrase. Ollama is not called for it.
For a genuinely ambiguous local target or operation, Ollama may suggest
`ask_user`, but its result never creates the class, alias, leaf, grant,
approval or effect. Unsupported local operations return a local notice or
clarification; they never fall through to a general mission silently.

Selecting “Envoyer seulement à ChatGPT” is a new explicit finalization choice.
It follows exact-chat rules and does not reuse the local-action route token.

## Finalization API

The existing route-finalization endpoint adds one exact action:

```http
POST /api/intent/routes/{route_id}/finalize
Origin: CORTEX_FRONTEND_ORIGIN
Content-Type: application/json
X-Cortex-UI-Session: runtime-bound-session-token

{
  "action": "start_local_alias_action",
  "conversationHandle": "server-minted-handle",
  "catalogEntryId": "server-minted-opaque-id",
  "catalogRevision": 7,
  "decisionDigest": "sha256-hex"
}
```

The URL route ID, session token, conversation handle, catalog ID and digest are
server-minted runtime values. `CORTEX_FRONTEND_ORIGIN` means the one exact
scheme/host/effective-port origin published by this runtime; a hostname alias,
different port, missing Origin or generic loopback range is rejected.

Under one immediate SQLite transaction, finalization:

1. consumes the single-use route token;
2. verifies conversation handle/generation, exact Origin/UI session, route
   digest, action kind, catalog ID/revision, alias, operation and leaf;
3. reloads fresh consent, STOP, authorization epoch and storage readiness;
4. requires one unexpired access observation matching catalog ID/revision,
   alias, authorization epoch and recorded root identity, without opening the
   protected alias;
5. creates one `local_alias_grants` row and one `local_alias_actions` row in
   `awaiting_approval`;
6. creates no mission, outbox, writer, upload, browser command or extension
   ledger row.

A byte-identical idempotent retry returns the canonical action record. A
different action/digest under the same finalization key returns a conflict.

## Storage-required behavior

`StorageContract` remains the sole vault authority. It gains no local-root
constructor and `WorkspaceHandle` retains its `20_WORKSPACES` invariant.

The local action calls a read-only
`StorageContract.assert_runtime_ready() -> StorageStatus` gate before
finalization and again immediately before effect activation. Behavior is:

- no required-storage marker: the managed local runtime may admit a verified
  local alias action;
- required storage healthy and committed: a local alias action may proceed;
- host missing, vault detached, ownership ignored, image/APFS identity changed,
  transition active, rollback active, managed-start lease absent or runtime
  status contradictory: reject before grant, approval or filesystem effect;
- storage administration never runs through `EffectGate`; local actions cannot
  mount, detach, repair, reconfigure or alter the vault.

Thus a Desktop action cannot be used as a recovery-mode escape when the
required vault is unavailable.

## Approval and effect ordering

The visible preflight says exactly:

```text
Action locale
Créer le dossier « cortex-live-test » dans Bureau.
Accès : créer uniquement ce dossier
ChatGPT : aucun message envoyé
Lecture, suppression, processus et réseau : désactivés
```

Finalization neither opens a protected alias nor causes a filesystem effect.
The one-shot approval challenge is bound to:

- local action ID and grant ID;
- catalog entry ID, revision and alias;
- operation `create_directory`;
- exact normalized leaf;
- canonical payload digest;
- single-use 256-bit nonce;
- scope `once`;
- STOP epoch and authorization epoch.

Approval mismatch, denial, expiry, reuse, changed digest, changed alias or
changed epoch executes nothing.

`LocalAliasActionService.execute` performs this order under the shared safety
gate and durable effect transaction:

1. reload STOP, consent and authorization epoch and validate the exact approval;
2. revalidate storage readiness and the unexpired access observation;
3. persist and fsync the local filesystem intent before spawning the fixed
   worker;
4. verify the installed worker identity, spawn it blocked on the private
   control FD, and durably record PID, PGID and start identity;
5. persist and fsync the filesystem effect as `active`, then release the worker;
6. inside the worker, open and retain the complete filesystem-root → home →
   alias descriptor chain, comparing every named edge and final identity to
   catalog, observation and grant;
7. probe the exact leaf with no-follow semantics;
8. reject an existing file, directory, symlink or dangling symlink as
   `TARGET_ALREADY_EXISTS`, terminalize the active effect without `mkdirat`,
   and exit;
9. revalidate the complete retained descriptor chain and effect activation;
10. call exactly `mkdirat(root_fd, leaf, 0o700)`;
11. revalidate every named descriptor-chain edge again with
    `fstatat(..., AT_SYMLINK_NOFOLLOW)`. If any home/alias entry no longer names
    the retained identity, persist `LOCAL_ALIAS_CHANGED` plus
    `outcome_unclear`; never report `created`;
12. open the created directory with `O_DIRECTORY | O_NOFOLLOW`, verify owner,
    device, inode and mode, fsync it and the retained alias root;
13. return one bounded worker receipt, persist `created` with the observed inode
    and terminal effect receipt, close/reap the owned process and every FD.

There is no shell call, absolute-path reopen, implicit parent creation,
overwrite, retry under a new name, copy/delete fallback or automatic cleanup.

## STOP, crash and race semantics

STOP and activation serialize through the same durable effect gate:

- access-check worker active: STOP cancels it immediately, revalidates and
  terminates its owned group with bounded TERM then KILL, records failed
  `LOCAL_ALIAS_ACCESS_UNCLEAR`, emits no observation and can settle/reset
  without waiting for a macOS prompt;
- write worker active: STOP performs the same bounded owned-process shutdown.
  A terminal worker receipt is committed normally; absence of a sufficient
  receipt becomes `LOCAL_ACTION_OUTCOME_UNCLEAR`, allowing STOP to settle but
  keeping reset disabled until explicit reconciliation;
- STOP first: the pending approval is invalidated, state becomes
  `cancelled_by_stop`, and `mkdirat` is never called;
- activation first: STOP waits for the active `mkdirat` plus terminal durable
  receipt or `outcome_unclear`; it does not invalidate the already-active
  capability merely because the epoch advances;
- process cancellation before `mkdirat`: `failed_safe` with proven absence;
- exception/cancellation after entering `mkdirat` and before durable terminal
  receipt: `outcome_unclear`, never replayed automatically;
- home or alias rename/replacement between the final pre-effect check,
  `mkdirat` and the post-effect chain check: `LOCAL_ALIAS_CHANGED` plus
  `outcome_unclear`, even if the retained old directory received the new leaf;
  the UI never says the requested alias contains the folder;
- restart with `active`: reopen the exact alias and target. An exact matching
  terminal receipt may restore `created`; proven absence may restore
  `failed_safe`; any existing target without sufficient creator/inode proof is
  `outcome_unclear`.

Reset never resumes, retries, approves or deletes a local alias action. A new
request needs a new route, finalization, action ID, grant, approval and current
epoch.

## Database changes

Add versioned tables under the same migration transaction as the intent/effect
schema:

```sql
CREATE TABLE local_alias_catalog (
    catalog_entry_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    alias TEXT NOT NULL UNIQUE CHECK (alias IN ('desktop','documents','downloads')),
    label TEXT NOT NULL,
    provenance TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE local_alias_access_observations (
    observation_id TEXT PRIMARY KEY,
    effect_id TEXT NOT NULL UNIQUE,
    catalog_entry_id TEXT NOT NULL,
    catalog_revision INTEGER NOT NULL,
    alias TEXT NOT NULL CHECK (alias IN ('desktop','documents','downloads')),
    authorization_epoch INTEGER NOT NULL,
    device INTEGER NOT NULL,
    inode INTEGER NOT NULL,
    uid INTEGER NOT NULL,
    mode INTEGER NOT NULL,
    verified_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    FOREIGN KEY (catalog_entry_id) REFERENCES local_alias_catalog(catalog_entry_id)
);

CREATE TABLE local_alias_grants (
    grant_id TEXT PRIMARY KEY,
    action_id TEXT NOT NULL UNIQUE,
    catalog_entry_id TEXT NOT NULL,
    catalog_revision INTEGER NOT NULL,
    access_observation_id TEXT NOT NULL,
    alias TEXT NOT NULL CHECK (alias IN ('desktop','documents','downloads')),
    operation TEXT NOT NULL CHECK (operation = 'create_directory'),
    allowed_leaf TEXT NOT NULL,
    route_digest TEXT NOT NULL,
    stop_epoch INTEGER NOT NULL,
    authorization_epoch INTEGER NOT NULL,
    device INTEGER NOT NULL,
    inode INTEGER NOT NULL,
    uid INTEGER NOT NULL,
    mode INTEGER NOT NULL,
    FOREIGN KEY (catalog_entry_id) REFERENCES local_alias_catalog(catalog_entry_id),
    FOREIGN KEY (access_observation_id) REFERENCES local_alias_access_observations(observation_id)
);

CREATE TABLE local_alias_actions (
    action_id TEXT PRIMARY KEY,
    grant_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_digest TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'awaiting_approval','active','created','failed_safe',
        'outcome_unclear','cancelled_by_stop'
    )),
    created_inode INTEGER,
    terminal_code TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    FOREIGN KEY (grant_id) REFERENCES local_alias_grants(grant_id)
);
```

Foreign keys are enabled before migration. The explicit constraints bind
observations and grants to catalog entries and actions to grants. Effect
ownership adds the frozen literal
`local_alias_action`; schema migration fails closed on an unknown prior local
grant rather than promoting it.

The final durable-effect schema version is `3`. Its migration rebuilds the
SQLite effects table in one immediate transaction so the owner/category
constraints are exactly:

```sql
CHECK (owner_kind IN ('mission','direct_ui','admin_ui','local_alias_action'))
CHECK (category IN ('filesystem','process','browser','sensitive_read'))
```

It copies only rows whose existing literals are recognized, verifies source
and destination row counts plus canonical row digests, swaps tables, runs
`foreign_key_check` and `quick_check`, then commits. An unknown owner/category,
count/digest mismatch or interrupted migration fails closed before runtime
resume. The registered effect inventory contains exactly the access check,
local create, existing filesystem/process/browser effects and backend capture;
discovered and registered sets must be equal.

## UI contract

The composer remains singular. The preflight panel distinguishes:

- `Chat` for exact ChatGPT delivery;
- `Mission` for general vault-backed agent work;
- `Action locale` for the narrow deterministic operation in this addendum.

The user does not choose an internal mode before typing. Cortex derives the
candidate and makes the execution class visible before finalization.

For `Action locale`, the UI shows alias label, exact leaf, operation, disabled
capabilities, storage/runtime readiness and `ChatGPT : aucun message envoyé`.
It never shows an executor/model as active. When access is unverified, it shows
the per-alias access-check button and the exact warning that macOS may ask for
permission; finalization/execution remains disabled. Only the user's click may
start that check. Before write approval it also states that macOS may ask again
if access was revoked since verification. After access verification and write
approval it shows:

- `Création en cours…` while the durable effect is active;
- `Dossier créé` only with terminal inode/receipt evidence;
- a precise French refusal for unavailable permission, changed alias, existing
  target, STOP or stale approval;
- `Résultat incertain — ne relancez pas automatiquement` for
  `outcome_unclear`.

The original draft remains available until finalization succeeds. Failure or
denial never converts the draft into a ChatGPT message.

## Error contract

| Code | Meaning | Effect behavior |
| --- | --- | --- |
| `LOCAL_ALIAS_UNAVAILABLE` | Standard alias is absent or invalid | No grant, approval or effect |
| `LOCAL_ALIAS_CHANGED` | Catalog/root identity or revision changed | No new effect; active case reconciles |
| `LOCAL_ALIAS_PERMISSION_REQUIRED` | Access unverified, expired, revoked or denied | No implicit prompt or fallback; only confirmed access-check or approved-write workers may prompt |
| `LOCAL_ALIAS_ACCESS_UNCLEAR` | Access worker timed out, crashed, lost its receipt or met an unknown system decision | No observation, grant or automatic retry; STOP/reset remains available |
| `LOCAL_ACTION_UNSUPPORTED` | Operation/alias/shape outside v0.5.4 | No mission/chat fallback |
| `INVALID_LOCAL_LEAF` | Leaf violates the frozen validator | No finalization |
| `TARGET_ALREADY_EXISTS` | Exact leaf exists in any form | Active probe terminalizes without `mkdirat` or overwrite |
| `LOCAL_ACTION_APPROVAL_MISMATCH` | Approval tuple differs | No effect |
| `LOCAL_ACTION_CANCELLED_BY_STOP` | STOP won before activation | No effect |
| `LOCAL_ACTION_OUTCOME_UNCLEAR` | Effect may have occurred without proof | No replay |
| `STORAGE_NOT_READY` | Required storage/runtime gate failed | No local-action escape |

HTTP errors use the existing strict JSON envelope and do not expose absolute
paths, device names, user names or raw OS errors.

## Migration and compatibility

- `WorkspaceHandle` and `StorageContract.open_workspace` remain unchanged and
  vault-only.
- The durable-effect plan owns generic filesystem primitives and the new
  `local_alias_action` owner kind, the fixed worker, its installer/attestation
  records and owned-process runner. The intent plan owns routing/finalization
  and `LocalAliasActionService`; neither creates a second effect gate.
- Existing or planned standard-alias `WorkspaceGrant` rows are never promoted
  into local actions. If found, startup records `MIGRATION_REVIEW_REQUIRED` and
  disables the affected route.
- Non-finalized route tokens expire. Pending local alias actions created under
  an older schema become `failed_safe` only with proven zero effect; otherwise
  `outcome_unclear`.
- Access observations expire after 15 minutes and are invalidated by STOP,
  consent/authorization-epoch change, process restart or catalog revision.
- Older extension protocol clients remain read-only. Local alias actions issue
  no extension command, but finalization still requires the current Cortex UI
  session and authorization epoch.
- macOS is the only v0.5.4 target. Other platforms keep exact chat/manual
  behavior and return `LOCAL_ACTION_UNSUPPORTED` for this route.

## Test strategy

### Pure routing and schema

- The exact Desktop phrase routes through deterministic rules with
  `execution_class=local_alias_action`, `model_attempted=false` and no model
  result.
- Exact chat and general mission inputs remain byte-identical to their prior
  routes.
- Invalid leaf, unsupported verb, nested path, arbitrary path and additional
  project alias never produce a local action.
- Pydantic/TypeScript/SQLite literals and camel/snake conversion match exactly.
- A schema-v2 fixture migrates to v3 with identical rows/digest; unknown owner
  or category aborts. The final `CHECK` accepts the two new literals and no
  unregistered fifth category.

### Alias and filesystem integration

Automated integration uses an injected temporary alias root; it never writes to
the real Desktop, Documents or Downloads.

- Resolve the home from `getpwuid_r`, walk no-follow and reject hostile `$HOME`.
- Prove startup, routing and finalization perform zero open/probe against the
  protected alias; only the confirmed access-check action or an approved local
  write may open it.
- Prove each access check targets one fixed alias, records one expiring identity
  observation, may surface but never controls a TCC prompt, and fails closed on
  denial/revocation.
- Hold the fake TCC prompt open, then exercise STOP, 60-second timeout, EOF,
  malformed receipt, cancellation and worker crash/restart. Require bounded
  worker death, closed FDs, terminal failed effect, zero observation/grant and
  reset still available.
- Reject absent, symlinked, wrong-owner, wrong-type, replaced, cross-revision,
  TCC-denied and protected roots.
- Reject existing directory, file, symlink and dangling symlink before effect
  activation.
- Prove one `mkdirat`, exact mode/owner/inode, parent fsync and no unrelated
  entry change.
- Inject home/alias rename or replacement between route, finalization,
  approval, activation, the last pre-check, `mkdirat` and the post-check. Prove
  no `created` receipt or success UI when any named descriptor-chain edge
  changes.
- Inject cancellation/crash before, during and after `mkdirat`; prove the fixed
  terminal/reconciliation matrix and no replay.
- Revoke access between observation and approved write. A second system prompt
  is permitted only after write approval; denial/timeout produces no success,
  and an unknown post-release write outcome blocks reset until reconciliation.

### Authority and negative capability tests

- A local alias handle is rejected by `ToolExecutor`, `MissionLoop`, process
  launch and browser transport.
- Exact registry equality proves no local listing/read/search/write-file/move/
  delete/process/network/upload/capture operation exists.
- Effect inventory equality proves access verification is exactly
  `direct_ui/sensitive_read`, local creation is exactly
  `local_alias_action/filesystem`, and neither client payload can select those
  fields.
- Client-supplied execution class, owner kind, category, alias, leaf or path
  cannot alter the server-frozen route.
- Local action finalization creates exactly one grant/action and zero mission,
  writer, outbox, upload, browser command and extension ledger rows.
- Two active ChatGPT writers do not block the local action; the local action
  does not consume or release a writer slot.

### Storage, STOP and durability

- With healthy required storage, the local action can reach approval.
- With absent/replaced/detached storage, active transition/rollback or missing
  managed-start lease, it fails before grant/approval/effect.
- Test STOP-first and activation-first order, restart in every state, stale
  nonce/digest/epoch, reset without replay and exact idempotent finalization.
- Prove general missions still reject Desktop and accept only the vault root or
  a verified descendant.
- Prove an access observation cannot cross STOP, consent change, epoch change,
  expiry or process restart.

### Frontend and accessibility

- The panel says `Action locale`, exposes the exact French interpretation and
  never says ChatGPT/model/executor performed the action.
- Keyboard/focus/live-region tests cover preflight, approval, active, created,
  denied, permission-required, STOP and uncertain states.
- Draft preservation and no implicit chat fallback are integration-tested.
- Mobile, tablet and desktop layouts have no overflow or hidden approval
  boundary.

### Live owner acceptance

The live test is manual, synthetic and action-time approved. It never runs in
CI and performs no automatic cleanup.

1. Confirm required storage/runtime is healthy and managed.
2. Click `Vérifier l’accès à Bureau`; if macOS presents a privacy prompt, the
   owner decides it directly. Require one fresh access observation and no
   ChatGPT, mission, writer, outbox or extension effect.
3. Prove by `lstat` that exact `~/Desktop/cortex-live-test` is absent. If it is
   present, verdict is `UNCLEAR`; do not delete or rename it.
4. Enter exactly `cree moi un dossier cortex-live-test sur mon bureau` in
   Cortex and press Enter without using `Exécuter…`.
5. Require rules source, no Ollama call, no ChatGPT send/refusal, no mission,
   no writer, no outbox and no extension command.
6. Verify the French `Action locale` preflight, exact alias/leaf and disabled
   capabilities.
7. Prove the folder remains absent after routing and finalization.
8. Approve only the displayed one-shot `create_directory` action.
9. If macOS asks again because access changed, the owner decides the system
   prompt directly; Cortex neither clicks it nor waits beyond 60 seconds.
10. Prove one new directory/inode, terminal receipt and no unrelated Desktop
   entry change.
11. Leave the folder in place. Any cleanup is a separate deletion decision.

## Implementation-plan ownership changes

After written-owner approval, the existing plan set changes as follows:

| Plan | Required change |
| --- | --- |
| Storage foundation | Keep `WorkspaceHandle` vault-only; expose read-only runtime-readiness assertion consumed by local actions |
| Durable effects/executor | Add `local_alias_action`, fixed attested worker, bounded owned-process runner and exact-leaf mkdir; keep generic executor vault-only |
| Runtime UI/browser | Render local-action runtime truth; no browser command or transport change for execution |
| Hybrid intent | Replace standard-alias mission grants with catalog, grants, action service and finalization defined here |
| Live QA | Run Desktop acceptance against the healthy required-storage product runtime and prove zero chat/mission/browser effects |
| Completion program | Reference this addendum hash and gate all five subordinate plans against it |

Only one plan may own each production file at a time. Shared files are changed
sequentially in storage → durable effects → UI → intent → live order.

## Acceptance gates

| Gate | `PASS` | `FAIL` | `UNCLEAR` |
| --- | --- | --- | --- |
| Authority separation | General missions are vault-only; local handle cannot enter generic executor | Any personal root reaches a general mission/tool | Registry or call graph cannot be proven |
| Server-owned target | Alias/revision/identity/leaf come from frozen server route | Client/model path changes authority | Provenance is incomplete |
| No ChatGPT side effect | Zero writer/mission/outbox/browser/extension rows or commands | Any implicit external/chat effect | Counters/ledger unavailable |
| Exact approval | One action/digest/nonce/epoch-bound approval | Broad, reused, mismatched or pre-effect approval | Durable tuple missing |
| Filesystem result | One exact directory, inode and receipt; no other entry changes | Wrong/extra/overwrite/replay effect | Creator/outcome cannot be proven |
| Storage health | Required storage and managed runtime pass before finalization and activation | Local action bypasses failed storage | Storage observation unavailable |
| macOS access | Before write approval only the confirmed access check may prompt; an approved write may prompt again after revocation; both workers are bounded and Cortex never controls the prompt | Background route/finalize opens the alias, worker outlives its deadline/STOP, or Cortex controls the prompt | Prompt/access/worker provenance unavailable |
| STOP/crash | Fixed winner/outcome matrix and no replay | Post-STOP effect or implicit retry | Effect boundary cannot be located |
| UI truth | `Action locale` and capabilities are explicit in French | UI calls it a mission or implies ChatGPT execution | Visible state cannot be captured |
| Privacy | No personal path/name/content in committed evidence | Secret/PII/private path committed | Scan/review missing |

## Completion definition

This addendum is implemented only when:

- every general mission remains confined to verified vault workspaces;
- the three standard aliases can produce only the one frozen local operation;
- the exact live Desktop request succeeds after one visible one-shot approval;
- no ChatGPT, writer, mission, outbox, extension or generic executor effect is
  created by that local action;
- storage, STOP, crash, TCC, path-race, negative capability, privacy and full
  release gates pass;
- the implementation and evidence receive independent zero-P0/P1/P2 reviews.

Approval of this written design does not authorize a real Desktop write,
Keychain operation, vault mutation, browser control, ChatGPT send, Git push,
merge, tag or release.
