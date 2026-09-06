# Cortex Bridge v0.5.4 Durable Effects and Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Cortex filesystem, process, administrative, sensitive-capture, and browser mutation descriptor-confined, exactly authorized, durably ordered against STOP, crash-reconciled, and non-replayable when its outcome is uncertain.

**Architecture:** SQLite is the single serialization point for exact approvals, effect intents, activation, STOP epochs, reset, ownership, and terminal receipts. `console/effect_gate.py` exposes capability objects consumed by the mission loop, direct/admin routes, `ToolExecutor`, the fixed local-alias worker runner, and the Chrome-extension choke point; `ToolExecutor` consumes the storage plan's retained `WorkspaceHandle` and never reopens an absolute workspace path. The local-alias worker is a separate installed and attested execution class: it receives no `WorkspaceHandle`, builds and revalidates its own descriptor chain from filesystem root to the approved fixed alias, and may perform exactly one `mkdirat` leaf mutation. Browser, process, and file effects record intent before dispatch and reconcile active rows on restart; uncertain outcomes block reset and are never replayed.

**Tech Stack:** Python 3.11/3.14, SQLite 3 (`BEGIN IMMEDIATE`, `PRAGMA synchronous=FULL`), FastAPI/Pydantic v2, macOS `openat(2)`/`mkdirat(2)`/`renameatx_np(2)`/`posix_spawn(2)`, asyncio, Chrome Extension Manifest V3, Node test runner.

**Specs:** `docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md` frozen at SHA-256 `472ae88687f6df00be1aac7bb33af536b0456fdc7fd04b7bb5f95e637e4b38f5`; `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md` frozen at SHA-256 `2034280b1b4943c2b602eba888b58742e2d77b428bdc63dc5f93a4b59c72cb5f`; `docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md` frozen at SHA-256 `38dff2d114ddf3a8f2262f3ac2b37dcbec9fd33951934c5d5c03a9a0c4acc08b`

## Global Constraints

- Target is the v0.5.4 candidate; no release, merge, tag, push, deployment, or publication is part of this plan.
- `CORTEX_HOME` remains local; database, settings, chat-run state, iterations, attachments, runs, logs, process records, locks, virtual environment, native helpers, and private quarantine do not move to external storage.
- Required/release runtime accepts only `browser_transport = chrome_extension`; Playwright and WebBridge remain explicit development-fixture transports with required storage absent.
- The existing authenticated ChatGPT browser transport is the only external product network path; executor processes get no arbitrary outbound-network capability.
- Every T12-T18 local write has a distinct action-bound one-shot approval; broad scopes never satisfy `move_file` or acceptance-test writes.
- `move_file` is exclusive, same-filesystem, descriptor-relative, one source file to one absent destination, and has no overwrite or copy/delete fallback.
- STOP state is exactly `inactive | stopping | stopped | resetting`; effect state is exactly `intent | active | succeeded | failed | outcome_unclear`.
- STOP and activation serialize through the same `BEGIN IMMEDIATE` transaction; STOP increments the epoch, invalidates pending approvals, prevents new activation, and waits for already-active owned effects. An activation committed before STOP remains valid for that exact active effect until terminalization/reconciliation; STOP does not revoke it merely because the control epoch advanced.
- Reset is accepted only from `stopped` with zero active and zero `outcome_unclear` effects; reset increments the epoch again before returning to `inactive`.
- Direct/admin intent is durable and fsynced before any temporary open or first byte; activation is durable before temporary open, publication, or browser envelope emission.
- Browser delivery uncertainty and `MOVE_OUTCOME_UNCLEAR` are terminal non-replay states.
- `ToolExecutor` accepts only `executor.workspace_handle.WorkspaceHandle`, uses borrowed FDs only during calls, and never closes the handle it did not create.
- `local_alias_action` is a separate execution class. Its fixed worker and runner never import, accept, construct, or call `ToolExecutor` or `WorkspaceHandle`; mission tools never receive a local-alias descriptor or grant.
- The exact sensitive-read inventory is `verify_local_alias_access` and backend `capture_screenshot`. No other operation may use `sensitive_read` without an explicit inventory and source-oracle test change.
- A local-alias access check is `direct_ui/sensitive_read`; its directory creation is `local_alias_action/filesystem`. The worker may address only server-owned aliases `desktop | documents | downloads` and operation `create_directory` with one validated absent leaf.
- Local-alias access/read failure never blocks STOP reset because it changes no managed resource. After entry into the write worker's `mkdirat` boundary, any cancellation, exception, EOF, malformed receipt, timeout, crash, or unverifiable postcondition terminalizes `outcome_unclear`, is never replayed or deleted by reset, and blocks reset pending explicit reconciliation.
- `LocalAliasWorkerRunner` uses a strict 60-second deadline, owns the exact PID/PGID/start identity, and closes every pipe/descriptor and reaps or verifies disappearance of the exact group on STOP, timeout, EOF, crash, and cancellation.
- The two blocked-worker effects cannot activate by call-order convention alone: a fresh single-use `BlockedWorkerActivationPermit` bound to durable ownership, current STOP epoch, storage observation and server-only protected-root facts is mandatory in the activation transaction.
- Local-alias protected-root facts come only from `getuid/getpwuid_r`, the installed manifest/home, the opaque result of `StorageContract.assert_runtime_ready()`, the committed server local-runtime projection and fixed macOS credential/Keychain/device locations. The local runner receives no storage binding, mount/vault descriptor, vault identity or APFS UUID; client, model, request and environment values have zero authority.
- All workspace traversal and mutation is relative to retained descriptors with `O_NOFOLLOW`; absolute path resolution/reopen, `Path.resolve()`, `os.walk`, `rglob`, and a path-based process `cwd` are forbidden in executor operations.
- Process launch uses runtime-resolved `posix_spawn_file_actions_addfchdir_np` on macOS 14/15 or `posix_spawn_file_actions_addfchdir` on macOS 26+, with no path-based fallback.
- A process child cannot execute the requested program until PID/PGID/start identity is durable; timeout, STOP, and `CancelledError` terminate and verify the owned group.
- Toolbar capture and all `pendingCapture` state are removed; screenshots originate only from backend `capture_screenshot` with a durable sensitive-read activation.
- Legacy mutating POST routes return `410 LEGACY_TASK_ENDPOINT_DISABLED` for absent, malformed, unknown-ID, and valid bodies without parsing a Pydantic body and without side effects.
- Existing-session state/light-state/list-tabs/await-attachment reads and bridge heartbeat are the only ordinary browser exemptions; `press_stop` and `release_session` bypass activation only with a STOP-cleanup permit.
- No runtime service, Chrome session, vault, sparsebundle, Keychain item, or external storage is mutated while implementing this plan's tests; integration tests use isolated temporary databases/workspaces and mocked extension connections unless a separately authorized acceptance phase begins.
- Every Python test added or modified here is collected by stdlib `unittest`: synchronous cases live in `unittest.TestCase`, async cases in `unittest.IsolatedAsyncioTestCase`, and parameter matrices use `subTest`. Every new Python test file invoked directly must import `sys`/`unittest` and end with the exact guard below before its first RED run; `unittest.main()` is forbidden because an empty module can exit zero. The aggregate oracle verifies both a positive collected count and this byte-exact footer. No task depends on pytest or on module-level functions that a direct `"$PYTHON" tests/file.py` command would ignore.
- Each task starts RED, reaches GREEN, and ends in one atomic local commit during execution; this planning task itself creates no commit.

```python
if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    count = suite.countTestCases()
    if count <= 0:
        raise SystemExit(2)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
```

---

## File map and frozen cross-plan contracts

### Files created by the preceding storage plan and consumed read-only here

- `console/storage_contract.py` owns storage verification and workspace admission. Consume `StorageContract.open_workspace(binding, requested) -> WorkspaceHandle`; do not modify this file.
- `executor/workspace_handle.py` owns retained descriptor identity. Consume the following exact interface; do not modify this file:

```python
@dataclass(frozen=True, slots=True)
class WorkspaceIdentity:
    storage_transaction_id: str
    mount_dev: int
    mount_fsid: tuple[int, int]
    workspace_dev: int
    workspace_ino: int
    apfs_volume_uuid: str
    relative_path: PurePosixPath
```

Exact `WorkspaceHandle` members consumed here are `identity: WorkspaceIdentity`, borrowed `mount_fd: int`, borrowed `workspace_fd: int`, relative-only `display_path: str`, `revalidate() -> WorkspaceIdentity`, `duplicate_workspace_fd() -> int`, and `close() -> None`. `MountFacts` is imported from `executor.workspace_handle`; `console.storage_contract` re-exports the same class.

### New durable-effect interfaces owned by this plan

`console/effect_gate.py` is the only module allowed to construct capabilities or move an effect between durable states. JSON uses camelCase at HTTP boundaries; Python uses snake_case internally.

```python
JSONValue = None | bool | int | float | str | list["JSONValue"] | dict[str, "JSONValue"]
EffectOwner = Literal["mission", "direct_ui", "admin_ui", "local_alias_action"]
EffectCategory = Literal["filesystem", "process", "browser", "sensitive_read"]
EffectState = Literal["intent", "active", "succeeded", "failed", "outcome_unclear"]
StopState = Literal["inactive", "stopping", "stopped", "resetting"]

@dataclass(frozen=True, slots=True)
class DirectEffectRequest:
    request_id: str
    epoch: int
    operation: str
    payload_digest: str

ApprovalOwner = Literal["mission", "local_alias_action"]

@dataclass(frozen=True, slots=True)
class MissionApprovalChallenge:
    mission_id: str
    action_id: str
    epoch: int
    arguments_digest: str
    nonce: str
    tool: str
    scope: str

@dataclass(frozen=True, slots=True)
class LocalAliasApprovalChallenge:
    action_id: str
    grant_id: str
    catalog_entry_id: str
    catalog_revision: int
    alias: Literal["desktop", "documents", "downloads"]
    operation: Literal["create_directory"]
    allowed_leaf: str
    epoch: int
    authorization_epoch: int
    arguments_digest: str
    nonce: str
    scope: Literal["once"]

ApprovalChallenge = MissionApprovalChallenge | LocalAliasApprovalChallenge

@dataclass(frozen=True, slots=True)
class MissionApprovalResponse:
    mission_id: str
    action_id: str
    epoch: int
    arguments_digest: str
    nonce: str
    scope: str
    approve: bool

@dataclass(frozen=True, slots=True)
class LocalAliasApprovalResponse:
    action_id: str
    epoch: int
    arguments_digest: str
    nonce: str
    scope: Literal["once"]
    approve: bool

ApprovalResponse = MissionApprovalResponse | LocalAliasApprovalResponse

@dataclass(frozen=True, slots=True)
class MissionApprovalReceipt:
    approved: bool
    mission_id: str
    action_id: str
    epoch: int
    arguments_digest: str
    scope: str | None
    nonce_consumed: bool

@dataclass(frozen=True, slots=True)
class LocalAliasApprovalReceipt:
    approved: bool
    action_id: str
    grant_id: str
    epoch: int
    authorization_epoch: int
    arguments_digest: str
    scope: Literal["once"] | None
    nonce_consumed: bool

ApprovalReceipt = MissionApprovalReceipt | LocalAliasApprovalReceipt

@dataclass(frozen=True, slots=True)
class FileIdentity:
    dev: int
    ino: int
    size: int
    sha256: str

@dataclass(frozen=True, slots=True)
class StagingExpectation:
    directory_dev: int
    directory_ino: int
    temporary_basename: str
    final_basename: str
    prior_target: FileIdentity | None

@dataclass(frozen=True, slots=True)
class EffectIntent:
    effect_id: str
    owner_kind: EffectOwner
    epoch: int
    operation: str
    payload_digest: str
    category: EffectCategory
    parent_effect_id: str | None
    staging: StagingExpectation | None

@dataclass(frozen=True, slots=True)
class EffectReceipt:
    effect_id: str
    state: Literal["succeeded", "failed", "outcome_unclear"]
    epoch: int
    operation: str
    payload_digest: str
    result: Mapping[str, JSONValue]
    error_code: str | None

@dataclass(frozen=True, slots=True, init=False)
class ExistingSessionReadPermit:
    session: str
    operation: str
    epoch: int
    _authority: object

@dataclass(frozen=True, slots=True, init=False)
class StopCleanupPermit:
    operation: Literal["press_stop", "release_session", "terminate_owned_process"]
    epoch: int
    _authority: object

@dataclass(frozen=True, slots=True)
class ReconcileResult:
    state: Literal["succeeded", "failed", "outcome_unclear"]
    error_code: str | None
    receipt: Mapping[str, JSONValue]

EffectReconciler = Callable[[Mapping[str, JSONValue]], ReconcileResult]

class EffectGateConflict(RuntimeError):
    code: str

@dataclass(frozen=True, slots=True, init=False)
class EffectActivation:
    effect_id: str
    owner_kind: EffectOwner
    epoch: int
    operation: str
    payload_digest: str
    category: EffectCategory
    parent_effect_id: str | None
    _authority: object

@dataclass(frozen=True, slots=True, init=False)
class BlockedWorkerActivationPermit:
    effect_id: str
    owner_kind: Literal["direct_ui", "local_alias_action"]
    category: Literal["sensitive_read", "filesystem"]
    operation: Literal["verify_local_alias_access", "create_directory"]
    epoch: int
    ownership_digest: str
    storage_observation_digest: str
    protection_facts_digest: str
    _authority: object

@dataclass(frozen=True, slots=True)
class StopStatus:
    schema_version: Literal[1]
    state: StopState
    epoch: int
    accepting_effects: bool
    active_effect_count: int
    outcome_unclear_count: int
    reset_allowed: bool
    updated_at: float

ExecutionClass = Literal["general_mission", "local_alias_action"]
LocalAlias = Literal["desktop", "documents", "downloads"]
LocalAliasOperation = Literal["create_directory"]
LocalAliasState = Literal[
    "awaiting_approval", "active", "created", "failed_safe",
    "outcome_unclear", "cancelled_by_stop",
]

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

ProtectedRootKind = Literal[
    "cortex_home", "local_runtime_projection", "credential_store", "keychain",
    "device_tree",
]
ProtectionSource = Literal[
    "getuid_getpwuid_r", "installed_manifest", "storage_readiness",
    "server_local_runtime_projection", "fixed_os_paths",
]

@dataclass(frozen=True, slots=True)
class LocalAliasProtectedRoot:
    kind: ProtectedRootKind
    absolute_components: tuple[bytes, ...]
    identity_chain: tuple[LocalRootIdentity, ...]
    provenance_digest: str

@dataclass(frozen=True, slots=True)
class LocalAliasProtectionFacts:
    uid: int
    filesystem_root_identity: LocalRootIdentity
    home_components: tuple[bytes, ...]
    home_identity_chain: tuple[LocalRootIdentity, ...]
    alias_components: tuple[bytes, ...]
    catalog_entry_id: str
    catalog_revision: int
    readiness_digest: str
    provenance_sources: tuple[ProtectionSource, ...]
    protected_roots: tuple[LocalAliasProtectedRoot, ...]
    absent_protected_paths: tuple[tuple[ProtectedRootKind, tuple[bytes, ...]], ...]
    digest: str

PROTECTED_ROOT_KINDS: tuple[ProtectedRootKind, ...] = (
    "cortex_home", "local_runtime_projection", "credential_store", "keychain",
    "device_tree",
)
SERVER_ONLY_PROTECTION_SOURCES: tuple[ProtectionSource, ...] = (
    "getuid_getpwuid_r", "installed_manifest", "storage_readiness",
    "server_local_runtime_projection", "fixed_os_paths",
)
FIXED_HOME_CREDENTIAL_COMPONENTS: tuple[tuple[bytes, ...], ...] = (
    (b".ssh",), (b".gnupg",), (b".aws",),
    (b".config", b"gcloud"), (b"Library", b"Keychains"),
)
FIXED_ABSOLUTE_PROTECTED_COMPONENTS: tuple[tuple[bytes, ...], ...] = (
    (b"Library", b"Keychains"),
    (b"System", b"Library", b"Keychains"),
    (b"dev",),
)

class LocalAliasProtectionResolver:
    def __init__(self, *, installed_home: Path,
                 storage_contract: StorageContract,
                 local_projection_resolver: Callable[[StorageStatus],
                     tuple[LocalAliasProtectedRoot, ...]]) -> None: ...
    def resolve(self, *, alias: LocalAlias, catalog_entry_id: str,
                catalog_revision: int,
                readiness: StorageStatus) -> LocalAliasProtectionFacts: ...
    def revalidate(self, facts: LocalAliasProtectionFacts, *,
                   readiness: StorageStatus) -> LocalAliasProtectionFacts: ...

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

@dataclass(frozen=True, slots=True, init=False)
class BlockedLocalAliasWorker:
    effect_id: str
    pid: int
    pgid: int
    start_sec: int
    start_usec: int
    _authority: object

```

Exact `LocalAliasHandle` signatures are `revalidate_chain() -> LocalRootIdentity`, `close() -> None`, `__enter__() -> Self`, and `__exit__(exc_type, exc, tb) -> None`. Exact runner signatures are `LocalAliasWorkerRunner.__init__(effect_gate: EffectGate, installed_home: Path, storage_contract: StorageContract)`, `spawn_blocked(*, request: LocalAliasWorkerRequest, intent: EffectIntent) -> BlockedLocalAliasWorker`, `assert_pre_activation_ready(*, intent: EffectIntent) -> BlockedWorkerActivationPermit`, asynchronous `run(*, request: LocalAliasWorkerRequest, activation: EffectActivation, deadline_seconds: Literal[60] = 60) -> LocalAliasWorkerReceipt`, and asynchronous `abort_blocked(*, intent: EffectIntent, code: str) -> None`. The runner constructs its server-only `LocalAliasProtectionResolver(installed_home=installed_home, storage_contract=storage_contract, local_projection_resolver=server_local_runtime_projection_resolver(installed_home))`; neither constructor nor public worker request accepts client/model/environment protection facts. The resolver may call only `storage_contract.assert_runtime_ready()` and is forbidden from calling `open`, `open_workspace`, `revalidate`, or receiving a `StorageBinding`/`WorkspaceHandle`. `spawn_blocked` opens no descriptor for a filesystem root, user directory, or alias, and the returned opaque lease cannot release the child. `abort_blocked` is mandatory in the caller's `finally` when activation does not yield to `run`.

The exact `EffectGate` signatures are:

- `EffectGate.__init__(store: Store)`
- `status() -> StopStatus`
- `register_pending_approval(*, mission_id: str, action_id: str, tool: str, arguments: Mapping[str, JSONValue], scope: str) -> MissionApprovalChallenge`
- `register_local_alias_approval(*, action_id: str, grant_id: str, catalog_entry_id: str, catalog_revision: int, alias: LocalAlias, operation: Literal["create_directory"], allowed_leaf: str, payload_digest: str, authorization_epoch: int) -> LocalAliasApprovalChallenge`
- `decide_approval(response: ApprovalResponse) -> ApprovalReceipt`
- `approval_receipt(*, mission_id: str, action_id: str, epoch: int, arguments_digest: str) -> MissionApprovalReceipt`
- `local_alias_approval_receipt(*, action_id: str, epoch: int, arguments_digest: str) -> LocalAliasApprovalReceipt`
- `activate_mission_effect(*, mission_id: str, action_id: str | None, epoch: int, operation: str, payload_digest: str, category: EffectCategory, approval_required: bool, parent_effect_id: str | None = None) -> EffectActivation`
- `begin_direct_intent(request: DirectEffectRequest, *, owner_kind: Literal["direct_ui", "admin_ui"], category: EffectCategory, parent_effect_id: str | None = None, staging: StagingExpectation | None = None) -> EffectIntent`
- `activate_direct_intent(effect_id: str, *, blocked_worker_permit: BlockedWorkerActivationPermit | None = None) -> EffectActivation`; the permit is forbidden for ordinary direct/admin intents and mandatory for `direct_ui/sensitive_read/verify_local_alias_access`
- `begin_local_alias_intent(*, action_id: str, epoch: int, operation: Literal["create_directory"], payload_digest: str, grant_id: str) -> EffectIntent`
- `record_blocked_ownership(effect_id: str, ownership: Mapping[str, JSONValue]) -> None`
- `activate_local_alias_intent(effect_id: str, *, approval: LocalAliasApprovalReceipt, blocked_worker_permit: BlockedWorkerActivationPermit) -> EffectActivation`
- `assert_activation(activation: EffectActivation, *, owner_kind: EffectOwner, category: EffectCategory, operation: str) -> None`
- `record_ownership(activation: EffectActivation, ownership: Mapping[str, JSONValue]) -> None`
- `succeed(activation: EffectActivation, receipt: Mapping[str, JSONValue]) -> EffectReceipt`
- `fail(activation: EffectActivation, *, code: str, receipt: Mapping[str, JSONValue]) -> EffectReceipt`
- `outcome_unclear(activation: EffectActivation, *, code: str, receipt: Mapping[str, JSONValue]) -> EffectReceipt`
- `existing_session_read_permit(*, session: str, operation: str) -> ExistingSessionReadPermit`
- `stop_cleanup_permit(*, operation: str) -> StopCleanupPermit`
- `request_stop() -> StopStatus`
- `settle_stop() -> StopStatus`
- `reset_stop(*, expected_epoch: int) -> StopStatus`
- `reconcile_startup(reconcilers: Mapping[EffectCategory, EffectReconciler]) -> StopStatus`

The stable STOP JSON is:

```json
{"schemaVersion":1,"state":"inactive","epoch":0,"acceptingEffects":true,"activeEffectCount":0,"outcomeUnclearCount":0,"resetAllowed":false,"updatedAt":1788336000.0}
```

The exact approval request is:

```json
{"missionId":"4f11c51c-572d-4d79-8e65-07d3398c802f","actionId":"54475610-b91b-4240-aafa-fbbbf48f7400","epoch":7,"argumentsDigest":"56af42f13b65d0550913d25525d7bdc693b1c4cdb46a390b21c46e3e9d2d1811","nonce":"EL5jDIHoBTaKH9FMHLZry6-VS-vP_XQZhsLSq2rbyxA","scope":"once","approve":true}
```

The distinct local-alias approval request has no `missionId`, `ownerKind`, category, alias, leaf, or grant supplied by the client; the path supplies the action ID and the server reloads those authority fields before reconstructing the canonical digest:

```json
{"actionId":"54475610-b91b-4240-aafa-fbbbf48f7400","epoch":7,"argumentsDigest":"56af42f13b65d0550913d25525d7bdc693b1c4cdb46a390b21c46e3e9d2d1811","nonce":"EL5jDIHoBTaKH9FMHLZry6-VS-vP_XQZhsLSq2rbyxA","scope":"once","approve":true}
```

Every direct/admin HTTP mutation carries this nested object; `owner_kind` and `category` are selected by the server registry, never by the client:

```json
{"effect":{"requestId":"2f5e86dd-ec61-4c34-a376-cb03143d3bf8","epoch":7,"operation":"chat.send","payloadDigest":"69bf8919432c747e8ecfd3f12e24267272525a9321b077f74f34a66d846e14fe"}}
```

An exact retry returns the stored terminal `effectReceipt`; a reused `requestId` with a different operation/digest returns `409 EFFECT_REQUEST_CONFLICT`; `active` or `outcome_unclear` returns 409 and is never replayed.

### New file responsibilities

- `console/effect_gate.py`: types, canonical semantic digest, exact approval transitions, effect capabilities, STOP/reset, receipt persistence, and startup reconciliation dispatch.
- `console/effect_registry.py`: exact route/tool/transport/extension classification and permit rules.
- `executor/fd_ops.py`: portable descriptor-relative traversal, generic `create_directory_at`, and audited macOS `rename_exclusive_at`; direct-intent code consumes these primitives and never reimplements them.
- `executor/process_spawn.py`: runtime symbol resolution, blocked bootstrap spawn, durable ownership handoff, group termination, and reconciliation.
- `native/macos/process_release.swift`: installed, signed, manifest-owned bootstrap that blocks on the inherited release pipe, closes it, and `execvp`s the reviewed argv.
- `executor/local_alias_worker.py`: fixed manifest-owned child program; it opens/revalidates filesystem-root-to-alias descriptors and performs the only local-alias `mkdirat`.
- `executor/local_alias_worker_runner.py`: attested installed-script launch, blocked ownership/release, strict deadline, receipt parsing, group close/reap, and local-alias reconciliation. It has no dependency on `ToolExecutor` or `WorkspaceHandle`.
- `executor/tools.py`: public structured tool methods over `WorkspaceHandle`, with no path reopen.
- `orchestration/store.py`: versioned migration and transaction primitives; it does not make authorization policy decisions.
- `orchestration/loop.py`: mission action-to-approval/effect ordering.
- `orchestration/protocol.py`, `orchestration/runner.py`, `executor/policy.py`: single exact tool registry including `move_file`.
- `console/attachments.py`, `console/settings.py`, `console/onboarding.py`: private activated writers and deterministic reconciliation metadata.
- `console/chat.py`, `console/missions.py`: direct/mission effect orchestration and durable STOP API.
- `console/chrome_extension.py`: final backend-to-extension permit check and dispatch receipt boundary.
- `transport/browser_chrome_extension.py`, `transport/chatgpt_web/adapter.py`: typed permit propagation through the storage-clamped Chrome-extension driver without duplicating transport selection/validation.
- `chrome-extension/service-worker.js`, `chrome-extension/service-worker-core.js`: backend-only capture and zero toolbar-retained pixels.
- `console/server.py`: startup reconciliation and legacy mutator tombstones. `console/local_executor.py` remains unreachable historical/development code and is not modified by this plan.

### Stable error codes

```python
STOP_ACTIVE = "STOP_ACTIVE"
STOP_EPOCH_STALE = "STOP_EPOCH_STALE"
STOP_NOT_SETTLED = "STOP_NOT_SETTLED"
STOP_RESET_CONFLICT = "STOP_RESET_CONFLICT"
APPROVAL_MISMATCH = "APPROVAL_MISMATCH"
APPROVAL_REPLAYED = "APPROVAL_REPLAYED"
EFFECT_REQUEST_CONFLICT = "EFFECT_REQUEST_CONFLICT"
EFFECT_NOT_ACTIVE = "EFFECT_NOT_ACTIVE"
EFFECT_CAPABILITY_INVALID = "EFFECT_CAPABILITY_INVALID"
EFFECT_OUTCOME_UNCLEAR = "EFFECT_OUTCOME_UNCLEAR"
BROWSER_DELIVERY_UNCERTAIN = "BROWSER_DELIVERY_UNCERTAIN"
MOVE_OUTCOME_UNCLEAR = "MOVE_OUTCOME_UNCLEAR"
PROCESS_OWNERSHIP_UNCLEAR = "PROCESS_OWNERSHIP_UNCLEAR"
LOCAL_ALIAS_UNAVAILABLE = "LOCAL_ALIAS_UNAVAILABLE"
LOCAL_ALIAS_PERMISSION_REQUIRED = "LOCAL_ALIAS_PERMISSION_REQUIRED"
LOCAL_ALIAS_ACCESS_UNCLEAR = "LOCAL_ALIAS_ACCESS_UNCLEAR"
LOCAL_ALIAS_CHANGED = "LOCAL_ALIAS_CHANGED"
INVALID_LOCAL_LEAF = "INVALID_LOCAL_LEAF"
LOCAL_ACTION_APPROVAL_MISMATCH = "LOCAL_ACTION_APPROVAL_MISMATCH"
LOCAL_ACTION_CANCELLED_BY_STOP = "LOCAL_ACTION_CANCELLED_BY_STOP"
LOCAL_ACTION_OUTCOME_UNCLEAR = "LOCAL_ACTION_OUTCOME_UNCLEAR"
LOCAL_ACTION_UNSUPPORTED = "LOCAL_ACTION_UNSUPPORTED"
TARGET_ALREADY_EXISTS = "TARGET_ALREADY_EXISTS"
STORAGE_NOT_READY = "STORAGE_NOT_READY"
MIGRATION_REVIEW_REQUIRED = "MIGRATION_REVIEW_REQUIRED"
LEGACY_TASK_ENDPOINT_DISABLED = "LEGACY_TASK_ENDPOINT_DISABLED"
```

### Task 1: Version and migrate the durable control schema

**Files:**
- Modify: `orchestration/store.py`
- Modify: `tests/test_protocol_state_store.py`
- Modify: `tests/test_store_lifecycle.py`

**Interfaces:**
- Consumes: existing `Store(path)` and current eleven-table v1 databases.
- Produces: `Store.transaction_immediate()`, `Store.control_row()`, `Store.effect_rows(states: Iterable[str] = ())`, final schema version `3`, the four local-alias tables, and SQLite durability `synchronous=FULL`.

- [ ] **Step 1: Write the failing migration and durability tests**

```python
def test_v1_database_migrates_without_authorizing_legacy_approvals(self):
    legacy = create_v1_store(self.db_path)
    legacy.record_approval("old", self.mission_id, self.action_id, "write_file", "once", True)
    legacy.close()
    store = Store(self.db_path)
    self.assertEqual(store.schema_version, 3)
    self.assertEqual(store.count("approvals"), 0)
    self.assertEqual(store.count("approvals_legacy_v1"), 1)
    self.assertEqual(store.control_row()["state"], "inactive")
    self.assertEqual(store.control_row()["epoch"], 0)

def test_store_forces_full_synchronous_and_exact_v3_effect_literals(self):
    store = Store(self.db_path)
    self.assertEqual(store._conn.execute("PRAGMA synchronous").fetchone()[0], 2)
    self.assertEqual(store._conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
    self.assertEqual(effect_owner_check(store),
                     ("mission", "direct_ui", "admin_ui", "local_alias_action"))
    self.assertEqual(effect_category_check(store),
                     ("filesystem", "process", "browser", "sensitive_read"))

def test_v2_effect_rebuild_preserves_count_and_canonical_digest(self):
    legacy = create_v2_store_with_every_recognized_effect_state(self.db_path)
    effects_before = canonical_effect_rows_digest(legacy)
    approvals_before = canonical_mission_approval_rows_digest(legacy)
    legacy.close()
    migrated = Store(self.db_path)
    self.assertEqual(migrated.schema_version, 3)
    self.assertEqual(canonical_effect_rows_digest(migrated), effects_before)
    self.assertEqual(canonical_mission_approval_rows_digest(migrated), approvals_before)
    self.assertEqual(migrated._conn.execute("PRAGMA foreign_key_check").fetchall(), [])
    self.assertEqual(migrated._conn.execute("PRAGMA quick_check").fetchone()[0], "ok")

def test_v2_unknown_effect_literal_fails_closed_without_runtime_resume(self):
    seed_v2_effect_literal(self.db_path, owner_kind="future_owner")
    with self.assertRaisesRegex(MigrationReviewRequired, "MIGRATION_REVIEW_REQUIRED"):
        Store(self.db_path)
    self.assertFalse(runtime_resume_called())

def test_v3_rebuild_count_and_digest_failures_roll_back_each_table_exactly(self):
    for table in ("approvals", "effects"):
        for validation in ("count", "digest"):
            failpoint = f"{table}_{validation}_mismatch"
            with self.subTest(table=table, validation=validation):
                db_path = create_v2_store_copy(self.db_path, failpoint)
                before_names = table_names_without_migration(db_path)
                before_rows = canonical_v2_rows(db_path)
                before_digests = canonical_v2_table_digests(db_path)
                with self.assertRaisesRegex(MigrationReviewRequired,
                                            "MIGRATION_REVIEW_REQUIRED"):
                    Store(db_path, migration_failpoint=failpoint)
                self.assertEqual(table_names_without_migration(db_path), before_names)
                self.assertEqual(canonical_v2_rows(db_path), before_rows)
                self.assertEqual(canonical_v2_table_digests(db_path), before_digests)
                self.assertEqual(read_user_version_without_migration(db_path), 2)

def test_each_pre_swap_interruption_rolls_back_the_entire_v3_transaction(self):
    for table in ("approvals", "effects"):
        failpoint = f"interrupt_immediately_before_{table}_swap"
        with self.subTest(table=table):
            db_path = create_v2_store_copy(self.db_path, failpoint)
            before_names = table_names_without_migration(db_path)
            before_rows = canonical_v2_rows(db_path)
            before_digests = canonical_v2_table_digests(db_path)
            with self.assertRaisesRegex(MigrationReviewRequired,
                                        "MIGRATION_REVIEW_REQUIRED"):
                Store(db_path, migration_failpoint=failpoint)
            self.assertEqual(table_names_without_migration(db_path), before_names)
            self.assertEqual(canonical_v2_rows(db_path), before_rows)
            self.assertEqual(canonical_v2_table_digests(db_path), before_digests)
            self.assertEqual(read_user_version_without_migration(db_path), 2)

def test_foreign_keys_are_enabled_before_migration_and_every_store_use(self):
    observed = record_pragmas_during_open(create_v2_store_copy(self.db_path, "pragma"))
    self.assertEqual(observed[0], ("foreign_keys", 1))
    store = Store(self.db_path)
    with self.assertRaises(sqlite3.IntegrityError):
        insert_effect_with_missing_parent(store)

def test_v3_local_approval_and_effect_xor_constraints_are_exact(self):
    store = Store(self.db_path)
    for mutation in ("local_scope_broad", "local_action_id_mismatch",
                     "second_approval_same_local_action", "direct_with_mission_id",
                     "admin_with_action_id", "local_with_request_id"):
        with self.subTest(mutation=mutation):
            with self.assertRaises(sqlite3.IntegrityError):
                insert_invalid_v3_row(store, mutation)

def test_direct_request_id_is_globally_unique_across_direct_and_admin(self):
    store = Store(self.db_path)
    insert_direct_effect(store, owner_kind="direct_ui", request_id=REQUEST_ID)
    with self.assertRaises(sqlite3.IntegrityError):
        insert_direct_effect(store, owner_kind="admin_ui", request_id=REQUEST_ID)
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `"$PYTHON" tests/test_protocol_state_store.py StoreSchemaTestCase -v && "$PYTHON" tests/test_store_lifecycle.py -v`

Expected: FAIL because `schema_version`, `approvals_legacy_v1`, `control_state`, `effects`, and FULL synchronous configuration do not exist.

- [ ] **Step 3: Add explicit v1-to-v2 and v2-to-v3 migrations under immediate transactions**

Implement `SCHEMA_VERSION = 3`. The v1-to-v2 step validates the legacy v1 table/column set before renaming `approvals` to `approvals_legacy_v1`; it creates the control, exact mission approvals, and legacy-v2 effects tables. In one immediate transaction, v2-to-v3 creates all four local-alias tables, rebuilds `approvals` with a typed subject/XOR constraint and partial unique indexes, and rebuilds `effects`; it never attempts to alter either CHECK constraint in place. The SQL below is the final v3 shape after both steps; a fresh database applies both migration functions in order and records both migration rows.

```sql
CREATE TABLE schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at REAL NOT NULL
);
CREATE TABLE control_state (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  state TEXT NOT NULL CHECK (state IN ('inactive','stopping','stopped','resetting')),
  stop_requested_at REAL,
  stopped_at REAL,
  reset_at REAL,
  updated_at REAL NOT NULL
);
CREATE TABLE approvals (
  id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('mission','local_alias_action')),
  mission_id TEXT REFERENCES missions(id),
  local_action_id TEXT REFERENCES local_alias_actions(action_id),
  action_id TEXT NOT NULL,
  tool TEXT NOT NULL,
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  arguments_digest TEXT NOT NULL CHECK (length(arguments_digest) = 64),
  nonce TEXT NOT NULL UNIQUE,
  scope TEXT NOT NULL CHECK (scope IN ('once','tool-for-mission','all-writes-for-mission')),
  decision TEXT NOT NULL CHECK (decision IN ('pending','approved','denied','invalidated')),
  nonce_consumed_at REAL,
  effect_consumed_at REAL,
  created_at REAL NOT NULL,
  decided_at REAL,
  CHECK ((owner_kind='mission' AND mission_id IS NOT NULL AND local_action_id IS NULL) OR
         (owner_kind='local_alias_action' AND mission_id IS NULL AND
          local_action_id IS NOT NULL AND action_id=local_action_id AND scope='once'))
);
CREATE UNIQUE INDEX approvals_mission_exact
ON approvals(mission_id, action_id, epoch, arguments_digest)
WHERE owner_kind='mission';
CREATE UNIQUE INDEX approvals_local_alias_one_per_action
ON approvals(local_action_id)
WHERE owner_kind='local_alias_action';
CREATE TABLE effects (
  id TEXT PRIMARY KEY,
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('mission','direct_ui','admin_ui','local_alias_action')),
  mission_id TEXT REFERENCES missions(id),
  action_id TEXT,
  request_id TEXT,
  epoch INTEGER NOT NULL CHECK (epoch >= 0),
  operation TEXT NOT NULL,
  payload_digest TEXT NOT NULL CHECK (length(payload_digest) = 64),
  parent_effect_id TEXT REFERENCES effects(id),
  category TEXT NOT NULL CHECK (category IN ('filesystem','process','browser','sensitive_read')),
  state TEXT NOT NULL CHECK (state IN ('intent','active','succeeded','failed','outcome_unclear')),
  authorization_json TEXT NOT NULL,
  intent_json TEXT NOT NULL,
  ownership_json TEXT,
  receipt_json TEXT,
  error_code TEXT,
  created_at REAL NOT NULL,
  activated_at REAL,
  finished_at REAL,
  CHECK ((owner_kind='mission' AND mission_id IS NOT NULL AND request_id IS NULL) OR
         (owner_kind IN ('direct_ui','admin_ui') AND mission_id IS NULL AND
          action_id IS NULL AND request_id IS NOT NULL) OR
         (owner_kind='local_alias_action' AND mission_id IS NULL AND
          action_id IS NOT NULL AND request_id IS NULL))
);
CREATE UNIQUE INDEX effects_direct_request
ON effects(request_id)
WHERE owner_kind IN ('direct_ui','admin_ui');
CREATE UNIQUE INDEX effects_local_alias_action
ON effects(action_id)
WHERE owner_kind='local_alias_action';
```

Create the v3 local-alias tables with the exact DDL below; no equivalent legacy `WorkspaceGrant` is copied or promoted:

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

Execute `PRAGMA foreign_keys=ON` and verify it reads back `1` immediately after every SQLite connection opens, before inspecting `user_version`, starting a migration, or serving any read/write method. Set `PRAGMA synchronous=FULL` before the migration transaction. For an existing v2 database, first create the four local tables, then create `approvals_v3` and `effects_v3`. Copy only recognized mission approval rows into `approvals_v3` with `owner_kind='mission'`, `local_action_id=NULL`, and every original field unchanged; no local approval can pre-exist. Copy only recognized effect literals. For each rebuilt table independently, compare source/destination row count plus a canonical SHA-256 over every copied column ordered by primary key. Expose the six test-only failpoints `approvals_count_mismatch`, `approvals_digest_mismatch`, `effects_count_mismatch`, `effects_digest_mismatch`, `interrupt_immediately_before_approvals_swap`, and `interrupt_immediately_before_effects_swap`; they are accepted only by the test constructor seam and never by production configuration. Only after both validations pass may the migration swap `approvals`, then `effects`, and recreate indexes. Run `PRAGMA foreign_key_check` and `PRAGMA quick_check`; set `PRAGMA user_version=3` and commit only when both are clean. Every count/digest mismatch and each distinct interruption immediately before its named swap raises `MIGRATION_REVIEW_REQUIRED`, rolls back the one encompassing transaction, and leaves the complete v2 table-name set, ordered rows, canonical per-table digests, and `user_version=2` unchanged. Unknown subject/owner/category, a partial schema, a legacy standard-alias grant needing interpretation, or `user_version > 3` fails closed before recovery or runtime bind.

- [ ] **Step 4: Expose narrow transaction/read primitives**

```python
@contextmanager
def transaction_immediate(self) -> Iterator[sqlite3.Connection]:
    self._conn.execute("BEGIN IMMEDIATE")
    try:
        yield self._conn
    except BaseException:
        self._conn.rollback()
        raise
    else:
        self._conn.commit()
```

The two exact read signatures are `control_row(self) -> dict[str, Any]` and `effect_rows(self, *, states: Iterable[str] = ()) -> list[dict[str, Any]]`.

Do not expose the raw connection to routes. Preserve v1 approval rows only in `approvals_legacy_v1`; no migration maps them to a current epoch or usable nonce.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_protocol_state_store.py -v && "$PYTHON" tests/test_store_lifecycle.py -v`

Expected: PASS; reopening the migrated file is idempotent, reports schema version 3, preserves all recognized effects byte-for-byte, and refuses unknown owner/category literals without binding runtime.

```bash
git add orchestration/store.py tests/test_protocol_state_store.py tests/test_store_lifecycle.py
git commit -m "feat: add durable effect schema migration"
```

### Task 2: Implement exact digests, approvals, capabilities, and STOP/reset

**Files:**
- Create: `console/effect_gate.py`
- Create: `tests/test_effect_gate.py`
- Modify: `orchestration/store.py`

**Interfaces:**
- Consumes: `Store.transaction_immediate()` from Task 1.
- Produces: every frozen type and `EffectGate` signature in “New durable-effect interfaces”; `canonical_digest(operation, payload) -> str`; `StopStatus.to_public() -> dict[str, JSONValue]`.
- Test collection: create `tests/test_effect_gate.py` with `import sys`, `import unittest`, class-based cases, and the exact global direct-execution guard before the RED command in Step 3.

- [ ] **Step 1: Write deterministic digest and exact-approval tests**

```python
def test_canonical_digest_rejects_non_json_and_normalizes_key_order(self):
    left = canonical_digest("write_file", {"content": "x", "path": "a.txt"})
    right = canonical_digest("write_file", {"path": "a.txt", "content": "x"})
    self.assertEqual(left, right)
    with self.assertRaises(TypeError):
        canonical_digest("write_file", {"bad": Path("a")})

def test_delayed_approval_a_cannot_approve_action_b(self):
    a = gate.register_pending_approval(
        mission_id=mission_id, action_id=action_a, tool="write_file",
        arguments={"path":"a.txt","content":"A"}, scope="once",
    )
    gate.register_pending_approval(
        mission_id=mission_id, action_id=action_b, tool="write_file",
        arguments={"path":"b.txt","content":"B"}, scope="once",
    )
    with self.assertRaisesRegex(EffectGateConflict, "APPROVAL_MISMATCH"):
        gate.decide_approval(MissionApprovalResponse(
            mission_id=mission_id, action_id=action_b, epoch=a.epoch,
            arguments_digest=a.arguments_digest, nonce=a.nonce,
            scope="once", approve=True,
        ))
```

- [ ] **Step 2: Write STOP race and capability-forgery tests**

```python
def test_stop_wins_before_activation_and_reset_requires_quiescence(self):
    challenge = pending_write(gate)
    approve_exactly(gate, challenge)
    stopped = gate.request_stop()
    self.assertEqual(stopped.state, "stopping")
    with self.assertRaisesRegex(EffectGateConflict, "STOP_EPOCH_STALE"):
        activate_challenge(gate, challenge)
    self.assertEqual(gate.settle_stop().state, "stopped")
    with self.assertRaisesRegex(EffectGateConflict, "STOP_RESET_CONFLICT"):
        gate.reset_stop(expected_epoch=challenge.epoch)
    reset = gate.reset_stop(expected_epoch=stopped.epoch)
    self.assertEqual((reset.state, reset.epoch), ("inactive", stopped.epoch + 1))

def test_activation_wins_then_stop_waits_and_capability_remains_valid(self):
    challenge = pending_write(gate)
    approve_exactly(gate, challenge)
    activation = activate_challenge(gate, challenge)
    stopping = gate.request_stop()
    self.assertEqual(stopping.active_effect_count, 1)
    gate.assert_activation(
        activation, owner_kind="mission", category="filesystem",
        operation="write_file",
    )
    self.assertEqual(gate.settle_stop().state, "stopping")
    gate.succeed(activation, {"sha256": "a" * 64})
    self.assertEqual(gate.settle_stop().state, "stopped")

def test_caller_cannot_construct_or_reuse_activation(self):
    with self.assertRaises(TypeError):
        EffectActivation(effect_id="forged")
    activation = active_direct_effect(gate)
    gate.succeed(activation, {"sha256": "a" * 64})
    with self.assertRaisesRegex(EffectGateConflict, "EFFECT_NOT_ACTIVE"):
        gate.assert_activation(
            activation, owner_kind="direct_ui", category="filesystem",
            operation="attachment.stage",
        )

def test_direct_request_id_is_unique_across_operation_and_digest():
    request = DirectEffectRequest(request_id=request_id, epoch=0,
                                  operation="settings.save", payload_digest=digest_a)
    first = gate.begin_direct_intent(request, owner_kind="admin_ui", category="filesystem")
    exact = gate.begin_direct_intent(request, owner_kind="admin_ui", category="filesystem")
    self.assertEqual(exact.effect_id, first.effect_id)
    for operation, digest in (("onboarding.dismiss", digest_a),
                              ("settings.save", digest_b)):
        with self.subTest(operation=operation, digest=digest):
            with self.assertRaisesRegex(EffectGateConflict, "EFFECT_REQUEST_CONFLICT"):
                gate.begin_direct_intent(
                    replace(request, operation=operation, payload_digest=digest),
                    owner_kind="admin_ui", category="filesystem",
                )
    with self.assertRaisesRegex(EffectGateConflict, "EFFECT_REQUEST_CONFLICT"):
        gate.begin_direct_intent(request, owner_kind="direct_ui",
                                 category="filesystem")

def test_local_approval_has_typed_subject_and_cannot_replay_as_mission():
    challenge = gate.register_local_alias_approval(
        action_id=action_id, grant_id=grant_id, catalog_entry_id=catalog_id,
        catalog_revision=3, alias="desktop", operation="create_directory",
        allowed_leaf="cortex-live-test", payload_digest=payload_digest,
        authorization_epoch=11,
    )
    self.assertFalse(hasattr(challenge, "mission_id"))
    with self.assertRaisesRegex(EffectGateConflict, "APPROVAL_MISMATCH"):
        gate.decide_approval(MissionApprovalResponse(
            mission_id=mission_id, action_id=challenge.action_id,
            epoch=challenge.epoch, arguments_digest=challenge.arguments_digest,
            nonce=challenge.nonce, scope="once", approve=True,
        ))
    receipt = gate.decide_approval(LocalAliasApprovalResponse(
        action_id=challenge.action_id, epoch=challenge.epoch,
        arguments_digest=challenge.arguments_digest, nonce=challenge.nonce,
        scope="once", approve=True,
    ))
    self.assertEqual(receipt.grant_id, grant_id)
    self.assertEqual(store.count("missions"), 0)

def test_access_activation_without_permit_is_effect_capability_invalid(self):
    access = begin_owned_access_intent(gate)
    with self.assertRaisesRegex(EffectGateConflict, "^EFFECT_CAPABILITY_INVALID$"):
        gate.activate_direct_intent(access.effect_id)

def test_local_activation_without_permit_is_effect_capability_invalid(self):
    local, approval = begin_owned_local_alias_intent_and_approval(gate)
    with self.assertRaisesRegex(EffectGateConflict, "^EFFECT_CAPABILITY_INVALID$"):
        gate.activate_local_alias_intent(
            local.effect_id, approval=approval, blocked_worker_permit=None,
        )
```

- [ ] **Step 3: Run RED**

Run: `"$PYTHON" tests/test_effect_gate.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'console.effect_gate'`.

- [ ] **Step 4: Implement canonicalization and all serialized state transitions**

Canonical bytes are exactly:

```python
def canonical_digest(operation: str, payload: Mapping[str, JSONValue]) -> str:
    document = {"operation": operation, "payload": payload}
    encoded = json.dumps(
        document, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
```

Validate UUID v4 request IDs, UUID action/mission/grant IDs, 64 lowercase hexadecimal digests, and 43-character Base64URL nonces. `register_pending_approval` reads the current epoch and inserts a typed `mission` pending row. `register_local_alias_approval` reloads the action, grant, catalog revision, access observation, STOP epoch and authorization epoch from server-owned rows; requires state `awaiting_approval`, exact alias/operation/normalized leaf, scope `once`, `action_id == local_action_id`, and no mission row; then computes the canonical arguments digest over action ID, grant ID, catalog ID/revision, alias, operation, leaf, payload digest, STOP epoch and authorization epoch and inserts the sole approval row allowed for that action. A byte-identical call returns the same challenge; changed data, denial followed by a new challenge, or a second nonce for the action returns `LOCAL_ACTION_APPROVAL_MISMATCH` and requires a newly finalized action. It never trusts owner/category/alias/leaf/digest authority from HTTP.

`decide_approval` dispatches on the Python response variant, loads the same typed subject, and compares subject/action/epoch/digest/nonce/scope under one immediate transaction; a mission response can never consume a local nonce and vice versa. It consumes the nonce exactly once and stores approved/denied. `activate_mission_effect` rechecks current pending action, current inactive epoch, digest, decision, and unused effect-consumption field; then marks the approval consumed and inserts the effect directly as `active` in the same transaction. `activate_local_alias_intent` likewise reloads and recomputes the exact local tuple, requires the matching approved `LocalAliasApprovalReceipt`, current STOP and authorization epochs, and atomically consumes that central approval while moving only the pre-existing local intent to `active`; it cannot create a mission or accept a broad scope. For the two blocked-worker tuples, an absent, forged, wrong-tuple, wrong-effect, wrong-ownership, stale-storage, stale-protection, stale-epoch or replayed `BlockedWorkerActivationPermit` raises exactly internal `EFFECT_CAPABILITY_INVALID` before approval consumption or state change. This internal permit failure is never serialized as a local-action terminal code; the route adapter maps the governing STOP/storage condition through the already frozen public error contract.

Capabilities use a gate-private `object()` authority plus the effect's exact durable fields. `BlockedWorkerActivationPermit` is single-use and gate-private: the runner's package-private issuer can mint it only after the runner has observed a coherent `PASS/RUNTIME_READY` status, revalidated the current protection-facts digest and verified the exact durable blocked ownership. The permit binds effect ID, exact owner/category/operation, current STOP epoch, canonical ownership digest, canonical `StorageStatus` observation digest and canonical protection-facts digest. `assert_activation` rereads the effect and requires the same gate authority, durable state `active`, and matching owner/category/operation/digest/activation epoch. It deliberately does not require `activation.epoch == control_state.epoch`: that comparison occurs only inside activation, so an effect that won serialization before STOP can finish under its recorded epoch while STOP waits. Terminal methods accept only `active`, replace receipt/error atomically, and reject any second terminalization.

`record_blocked_ownership` is the sole pre-activation exception: it accepts only an intent matching exactly one of `(local_alias_action, filesystem, create_directory)` or `(direct_ui, sensitive_read, verify_local_alias_access)`, only once, and only the runner-produced keys `pid`, `pgid`, `startSec`, `startUsec`, `released=false`; it rejects every browser/process/general-filesystem tuple and any client-supplied extra field. `activate_local_alias_intent` and the access path's `activate_direct_intent` require the matching `BlockedWorkerActivationPermit` and, in the same immediate transaction, re-hash the exact still-unreleased ownership row and compare the permit epoch to current control state before consuming it. Ordinary `record_ownership` continues to require `EffectActivation`. Updating either worker record to `released=true` requires the matching activation and preserves PID/PGID/start unchanged.

`begin_direct_intent` first queries the globally unique `request_id` across `direct_ui` and `admin_ui`. Exact owner+operation+digest retry returns the existing intent or terminal receipt; a different owner, operation, or digest raises `EFFECT_REQUEST_CONFLICT`; `active` and `outcome_unclear` never activate again. Composite child effects use deterministic UUIDv5 request IDs derived from the frontend parent UUID, child ordinal, and operation so every direct/admin row preserves the same global uniqueness rule.

`request_stop` executes exactly `epoch = epoch + 1`, `state = 'stopping'`, invalidates `pending` or `approved` approvals whose effect is unconsumed, and returns counts. `settle_stop` reaches `stopped` only when `activeEffectCount == 0`; `outcome_unclear` does not pretend to be active but keeps `resetAllowed=false`. `reset_stop(expected_epoch=current_epoch)` requires exact current epoch, `stopped`, zero active, and zero unclear, then performs `resetting`, epoch increment, approval invalidation, and `inactive` before commit.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_effect_gate.py -v && "$PYTHON" tests/test_protocol_state_store.py -v`

Expected: PASS for both deterministic orders: STOP-before-activation rejects dispatch with `STOP_EPOCH_STALE`; activation-before-STOP remains executable, is counted by STOP, and must terminalize before `stopped`.

```bash
git add console/effect_gate.py orchestration/store.py tests/test_effect_gate.py tests/test_protocol_state_store.py
git commit -m "feat: serialize approvals effects and stop epochs"
```

### Task 3: Bind MissionLoop approval and execution to the exact durable action

**Files:**
- Modify: `orchestration/loop.py`
- Modify: `console/missions.py`
- Modify: `orchestration/runner.py`
- Modify: `tests/test_loop_mock.py`
- Modify: `tests/test_missions_api.py`
- Modify: `tests/test_approval_scope_regression.py`
- Modify: `tests/test_workspace_handle.py`

**Interfaces:**
- Consumes: `EffectGate.register_pending_approval`, `decide_approval`, `activate_mission_effect`; `StorageContract.open() -> StorageBinding` and `StorageContract.open_workspace(binding, requested) -> WorkspaceHandle` from the storage plan.
- Produces: `MissionLoop.__init__(*, store: Store, mission_id: str, orchestrator: Any, tools: ToolExecutor, effect_gate: EffectGate, policy: PolicyEngine | None = None, approval_callback: ApprovalCallback | None = None, action_validator: Callable[[dict, dict | None, ToolError | None], Any] | None = None, final_validator: Callable[[dict, ToolExecutor], Any] | None = None, budgets: Budgets | None = None, clock: Callable[[], float] = time.time, conversation: dict | None = None, contract: str | None = None)`; exact `ApprovalIn`, exact approval response JSON, mission payload field `pendingApproval: ApprovalChallenge | null`, and one explicit owner for each `StorageBinding`/`WorkspaceHandle` lifetime.

- [ ] **Step 1: Write RED tests for the displayed challenge and exact response**

```python
class ApprovalIn(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    mission_id: UUID
    action_id: UUID
    epoch: int = Field(ge=0)
    arguments_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")
    scope: Literal["once", "tool", "all-writes"]
    approve: bool

async def test_approval_response_must_echo_every_displayed_field(client):
    pending = await wait_pending_approval(client, mission_id)
    wrong = {**pending, "actionId": str(uuid.uuid4()), "approve": True}
    response = await client.post(f"/api/missions/{mission_id}/approve", json=wrong)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "APPROVAL_MISMATCH"
    assert not (workspace / "a.txt").exists()
```

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_loop_mock.py -v && "$PYTHON" tests/test_missions_api.py -v && "$PYTHON" tests/test_approval_scope_regression.py -v`

Expected: FAIL because approval is an in-memory event containing only scope/boolean and execution is not epoch/digest-bound.

- [ ] **Step 3: Replace the in-memory authorization decision with the durable challenge**

Add `effect_gate` to `MissionLoop.__init__`. On a policy-approved action compute `arguments_digest = canonical_digest(tool, arguments)`. For any write/process tool, register the pending approval before exposing `WAITING_FOR_APPROVAL`; for a policy mode that requires no click, create an epoch-bound authorization fact but still pass through `activate_mission_effect`. `move_file`, `run_process`, `run_tests`, and acceptance-test writes always force scope `once` regardless of wider policy state.

The callback becomes notification-only:

```python
ApprovalCallback = Callable[[ApprovalChallenge, PolicyDecision], Awaitable[None]]

async def _await_exact_approval(self, challenge: ApprovalChallenge) -> ApprovalReceipt:
    await self.approval_callback(challenge, self._policy_decision)
    return self.effect_gate.approval_receipt(
        mission_id=challenge.mission_id,
        action_id=challenge.action_id,
        epoch=challenge.epoch,
        arguments_digest=challenge.arguments_digest,
    )
```

Immediately before `getattr(self.tools, tool)`, activate the mission effect. Pass `activation=` only to tools classified as mutating/process. If STOP wins, build a `DENIED` report with blocker `STOP_EPOCH_STALE`; do not call the tool.

Mission admission owns descriptor lifetime explicitly: `create_mission` constructs `StorageContract`, retains `binding = contract.open()`, obtains `workspace_handle = contract.open_workspace(binding, body.workspace)` before mission persistence, then transfers both to `MissionRuntime`. `ToolExecutor` borrows the handle. `MissionRuntime` closes the handle first and binding second only after every child effect is terminal and the mission task/writer lease is quiescent. Resume repeats `contract.open()` plus `open_workspace()` from the stored relative workspace display path before any browser/effect action; failed reopen leaves the mission paused and creates no transport or executor. `ModeARunner` receives an already-open handle and never creates one from a string.

`TransportOrchestratorClient.next_decision` activates a mission-owned browser child before contract/report send. The initial contract uses `action_id=None`; reports use their exact action ID. A confirmed extension receipt terminalizes succeeded; entry into `send_json` followed by crash/cancellation/EOF terminalizes `BROWSER_DELIVERY_UNCERTAIN`, and resume never resends it automatically.

- [ ] **Step 4: Make the HTTP route decide only the exact durable challenge**

Remove `MissionRuntime.approval_scope` as authority. The route requires body `missionId == path mission_id`, converts UI scope names to stored scope names, calls `decide_approval`, wakes only the matching waiter, and returns:

```json
{"schemaVersion":1,"approved":true,"missionId":"4f11c51c-572d-4d79-8e65-07d3398c802f","actionId":"54475610-b91b-4240-aafa-fbbbf48f7400","epoch":7,"argumentsDigest":"56af42f13b65d0550913d25525d7bdc693b1c4cdb46a390b21c46e3e9d2d1811","scope":"once","nonceConsumed":true}
```

Late, repeated, stale-epoch, wrong-digest, and action-A-for-action-B responses are 409. Denial consumes the nonce and produces a DENIED report; it cannot be retried as approval.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_loop_mock.py -v && "$PYTHON" tests/test_missions_api.py -v && "$PYTHON" tests/test_approval_scope_regression.py -v && "$PYTHON" tests/test_workspace_handle.py -v`

Expected: PASS; test evidence shows the effect row is active before tool invocation and the approval's `effect_consumed_at` is set once.

```bash
git add orchestration/loop.py orchestration/runner.py console/missions.py tests/test_loop_mock.py tests/test_missions_api.py tests/test_approval_scope_regression.py tests/test_workspace_handle.py
git commit -m "feat: bind mission approvals to exact durable actions"
```

### Task 4: Build descriptor-relative executor primitives and migrate read tools

**Files:**
- Create: `executor/fd_ops.py`
- Modify: `executor/tools.py`
- Modify: `executor/policy.py`
- Modify: `tests/test_executor_tools.py`
- Modify: `tests/test_process_policy.py`
- Modify: `tests/test_workspace_path_fuzzing.py`
- Modify: `tests/test_unicode_path_fuzzing.py`

**Interfaces:**
- Consumes: read-only `WorkspaceHandle.revalidate()` and `duplicate_workspace_fd()` from the storage plan.
- Produces: `ToolExecutor(workspace: WorkspaceHandle, *, effect_gate: EffectGate, test_commands: list[list[str]] | None = None)`, `PolicyEngine(workspace: WorkspaceHandle, *, mode: str = WRITE_WITH_APPROVALS, test_commands: list[list[str]] | None = None, allow_processes: bool = False, primary_model: str = DEFAULT_PRIMARY_MODEL, fallback_model: str = DEFAULT_FALLBACK_MODEL)`, `CheckpointManager(workspace: WorkspaceHandle, effect_gate: EffectGate)`, `detect_test_command(workspace: WorkspaceHandle) -> list[str] | None`, and descriptor helpers below.

Exact helper signatures are `components(relative: str) -> tuple[str, ...]`, `open_parent(root_fd: int, relative: str) -> Iterator[tuple[int, str]]` as a context manager, `open_directory_at(root_fd: int, relative: str = ".") -> int`, `open_regular_at(root_fd: int, relative: str, *, writable: bool = False) -> int`, `create_directory_at(parent_fd: int, name: str, *, mode: int = 0o700) -> os.stat_result`, `stat_at(parent_fd: int, name: str) -> os.stat_result`, `rename_exclusive_at(src_dir_fd: int, src: str, dst_dir_fd: int, dst: str) -> None`, and `fsync_directory(fd: int) -> None`.

- [ ] **Step 1: Write tests that replace paths after admission**

```python
async def test_read_uses_retained_fd_after_absolute_name_is_replaced(handle, root):
    executor = ToolExecutor(handle, effect_gate=gate)
    (root / "safe.txt").write_text("safe", encoding="utf-8")
    root.rename(root.with_name("displaced"))
    root.mkdir()
    (root / "safe.txt").write_text("attacker", encoding="utf-8")
    assert (await executor.read_file("safe.txt"))["content"] == "safe"

async def test_every_component_is_no_follow(handle):
    for rel in generated_relative_paths():
        with self.subTest(rel=rel):
            assert_rejected_before_opening_external_inode(executor, rel)
```

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_executor_tools.py -v && "$PYTHON" tests/test_workspace_path_fuzzing.py -v && "$PYTHON" tests/test_unicode_path_fuzzing.py -v`

Expected: FAIL because current executor calls `Path.resolve`, `iterdir`, `rglob`, `open(path)`, and `os.walk` after admission.

- [ ] **Step 3: Implement descriptor traversal with an exact component grammar**

Reject empty strings except `.`, absolute paths, `~`, NUL, backslash, empty interior components, `.`, `..`, and components longer than `NAME_MAX`. Open each ancestor with `os.open(name, O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC, dir_fd=current_fd)`, verify directory type and `st_dev == workspace.identity.workspace_dev`, and close every duplicated/intermediate FD in `finally`.

`open_regular_at` requires `S_ISREG`, `st_nlink == 1`, same device, and stable `(dev, ino, mode, size)` across pre/post `fstat`. `list_directory` uses `os.listdir(fd)` plus `os.stat(name, dir_fd=fd, follow_symlinks=False)`. `search_text` uses an explicit FD recursion stack, never follows symlinks, applies `SKIP_DIRS`, and tracks `(dev, ino)` to reject cycles/duplicates.

- [ ] **Step 4: Refactor ToolExecutor reads and validation to borrowed-handle semantics**

```python
class ToolExecutor:
    def __init__(self, workspace: WorkspaceHandle, *, effect_gate: EffectGate,
                 test_commands: list[list[str]] | None = None):
        if not isinstance(workspace, WorkspaceHandle):
            raise TypeError("ToolExecutor requires WorkspaceHandle")
        self.workspace = workspace
        self.effect_gate = effect_gate

    def _revalidate(self) -> WorkspaceIdentity:
        return self.workspace.revalidate()
```

Update `list_directory`, `read_file`, `file_exists`, `search_text`, and deterministic validation helpers to use FD operations. Reports expose only relative `display_path`; no absolute path, FD integer, device, inode, or APFS UUID reaches ChatGPT.

Migrate every remaining executor path helper in the same task: `CheckpointManager._iter_files/create_checkpoint/restore_checkpoint`, `detect_test_command`, `check_command_allowed`, `sanitized_process_environment`, `validate_write_result`, git repository detection, and policy workspace admission. `PolicyEngine` stores the immutable `WorkspaceIdentity`, not a resolved `Path`; storage admission is authoritative, and command-specific file existence is checked with `open_regular_at`. Checkpoints use descriptor traversal and require their own filesystem activation for create/restore. The child environment uses `HOME=/var/empty`, omits parent secrets, and relies on fchdir rather than an absolute workspace string.

No production exception is allowed in the static guard. The only permitted `Path.resolve`, `os.walk`, `rglob`, or path-based open/cwd occurrences are fixture setup lines beneath `tests/`; the Task 16 command scopes its zero-match assertion to `executor/*.py` and fails before any direct intent is created.

Although `git_status` and `git_diff` are read-only in the orchestration protocol, they still launch an OS process. Their exact signatures become `git_status(self, *, activation: EffectActivation) -> dict` and `git_diff(self, path: str | None = None, *, activation: EffectActivation) -> dict`; MissionLoop activates a no-click mission process effect before either call, and STOP can therefore block their launch. `READ_ONLY_TOOLS` remains a semantic protocol partition; add `PROCESS_EFFECT_TOOLS = frozenset({"git_status", "git_diff", "run_process", "run_tests"})` for effect dispatch.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_executor_tools.py -v && "$PYTHON" tests/test_process_policy.py -v && "$PYTHON" tests/test_workspace_path_fuzzing.py -v && "$PYTHON" tests/test_unicode_path_fuzzing.py -v`

Expected: PASS, including mount/path substitution and symlink races with zero external read.

```bash
git add executor/fd_ops.py executor/tools.py executor/policy.py tests/test_executor_tools.py tests/test_process_policy.py tests/test_workspace_path_fuzzing.py tests/test_unicode_path_fuzzing.py
git commit -m "refactor: confine executor reads to workspace descriptors"
```

### Task 5: Migrate write tools and add exclusive `move_file`

**Files:**
- Modify: `executor/fd_ops.py`
- Modify: `executor/tools.py`
- Modify: `orchestration/protocol.py`
- Modify: `tests/test_executor_tools.py`
- Modify: `tests/test_command_policy_fuzz.py`

**Interfaces:**
- Consumes: `EffectActivation`, `EffectGate.assert_activation`, and descriptor primitives.
- Produces: descriptor-only `write_file`, `apply_patch`, `create_directory`, and `move_file(source, destination, *, activation) -> dict`.

- [ ] **Step 1: Write RED tests for pre-syscall revalidation and move boundaries**

```python
async def test_mutation_revalidates_handle_after_effect_activation(handle):
    activation = activate_write("write_file", {"path":"a.txt","content":"A"})
    replace_mount_after_activation()
    with self.assertRaisesRegex(ToolDenied, "WORKSPACE_IDENTITY_CHANGED"):
        await executor.write_file("a.txt", "A", activation=activation)
    self.assertFalse(attacker_root.joinpath("a.txt").exists())

async def test_move_file_is_exclusive_and_hash_preserving(handle):
    source = seed_regular("in/a.txt", b"A")
    activation = activate_write("move_file", {"source":"in/a.txt","destination":"out/a.txt"})
    result = await executor.move_file("in/a.txt", "out/a.txt", activation=activation)
    self.assertEqual(result["before"]["sha256"], result["after"]["sha256"])
    self.assertFalse(source.exists())
```

Fault-inject before rename, after rename before first directory fsync, after both fsyncs, and before terminal receipt. Expected classifications are safe failure only when source remains exact and destination absent; success only when destination is the intended inode/hash and source absent; every other combination is `MOVE_OUTCOME_UNCLEAR`.

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_executor_tools.py -v && "$PYTHON" tests/test_command_policy_fuzz.py -v`

Expected: FAIL because writes reopen paths and `move_file` is absent.

- [ ] **Step 3: Implement the audited macOS rename binding**

```python
RENAME_EXCL = 0x00000004

def rename_exclusive_at(src_dir_fd: int, src: str, dst_dir_fd: int, dst: str) -> None:
    rc = libc.renameatx_np(src_dir_fd, src.encode(), dst_dir_fd, dst.encode(), RENAME_EXCL)
    if rc != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), dst)
```

Resolve `renameatx_np` once; if absent return `RENAME_EXCL_UNAVAILABLE`. Do not call `os.rename`, `os.replace`, `shutil.move`, copy/delete, or an overwriting flag for `move_file`.

- [ ] **Step 4: Refactor each write around the activation boundary**

For every mutator: validate arguments without touching the target; call `assert_activation`; call `WorkspaceHandle.revalidate()` immediately next; open verified parent FDs; snapshot prior identity/hash where applicable; perform the descriptor syscall; fsync file and all changed parent directories; reread through FD; persist the terminal receipt.

Use exact public signatures:

Exact public signatures are `write_file(self, path: str, content: str, *, activation: EffectActivation) -> dict`, `apply_patch(self, path: str, replacements: list[dict], *, activation: EffectActivation) -> dict`, `create_directory(self, path: str, *, activation: EffectActivation) -> dict`, and `move_file(self, source: str, destination: str, *, activation: EffectActivation) -> dict`.

`move_file` requires source regular/non-symlink/nlink=1, absent destination, existing verified destination parent, same device, and a `once` approval recorded for the exact source/destination digest. Its intent receipt contains source `(dev, ino, size, sha256)` and requested destination; its success receipt contains destination `(dev, ino, size, sha256)` and both parent fsync receipts.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_executor_tools.py -v && "$PYTHON" tests/test_command_policy_fuzz.py -v`

Expected: PASS; no test observes overwrite, cross-device move, symlink traversal, or automatic replay.

```bash
git add executor/fd_ops.py executor/tools.py orchestration/protocol.py tests/test_executor_tools.py tests/test_command_policy_fuzz.py
git commit -m "feat: add durable descriptor relative file mutations"
```

### Task 6: Launch processes with `addfchdir`, release pipe, and durable ownership

**Files:**
- Create: `executor/process_spawn.py`
- Create: `native/macos/process_release.swift`
- Modify: `executor/tools.py`
- Modify: `console/process_ownership.py`
- Modify: `console/native_helpers.py`
- Modify: `console/installer.py`
- Modify: `tests/test_process_policy.py`
- Modify: `tests/test_process_ownership.py`
- Modify: `tests/test_installer.py`

**Interfaces:**
- Consumes: `WorkspaceHandle.duplicate_workspace_fd`, `EffectActivation`, `EffectGate.record_ownership`, and storage-plan `attest_helper(name: str, manifest: Mapping[str, object]) -> AttestedHelper` with retained `AttestedHelper.fd`.
- Produces: the narrow extension `AttestedHelper.revalidate_for_spawn() -> Path`, `spawn_blocked`, `release_owned_process`, `terminate_owned_process`, `reconcile_process_effect`; activated `run_process`/`run_tests`.

```python
@dataclass(frozen=True, slots=True)
class OwnedProcess:
    pid: int
    pgid: int
    start_time: str
    executable: str
    argv_hash: str
    release_fd: int
```

Exact function signatures are `spawn_blocked(*, argv: Sequence[str], cwd_fd: int, env: Mapping[str, str]) -> OwnedProcess`, `release_owned_process(process: OwnedProcess) -> None`, `terminate_owned_process(process: OwnedProcess, *, term_timeout: float = 2.0) -> None`, and `reconcile_process_effect(ownership: Mapping[str, JSONValue]) -> ReconcileResult`.

- [ ] **Step 1: Write symbol-selection and no-fallback tests**

```python
def test_macos_14_prefers_np_and_macos_26_prefers_standard_symbol():
    self.assertEqual(resolve_addfchdir(fake_libc(np=True, standard=False)), "posix_spawn_file_actions_addfchdir_np")
    self.assertEqual(resolve_addfchdir(fake_libc(np=True, standard=True), darwin_major=25), "posix_spawn_file_actions_addfchdir_np")
    self.assertEqual(resolve_addfchdir(fake_libc(np=True, standard=True), darwin_major=26), "posix_spawn_file_actions_addfchdir")

def test_missing_addfchdir_fails_before_spawn():
    with self.assertRaisesRegex(ToolDenied, "PROCESS_FCHDIR_UNAVAILABLE"):
        spawn_blocked(argv=["python3","site.py"], cwd_fd=cwd_fd, env={})
    posix_spawn.assert_not_called()

def test_process_release_helper_is_installed_signed_and_attested(installed_manifest):
    record = installed_manifest["native_helpers"]["process-release"]
    helper = attest_helper("process-release", installed_manifest)
    self.assertEqual(helper.sha256, record["sha256"])
    self.assertEqual(helper.revalidate_for_spawn(), helper.path)
    self.assertGreater(helper.fd, 2)
```

- [ ] **Step 2: Write release/cancel/STOP ownership tests**

Pause after spawn and assert the requested script marker is absent; record PID/PGID/start identity; release one pipe byte; assert execution begins. Inject timeout, STOP, and `asyncio.CancelledError`; require TERM, then KILL only after the fixed two-second TERM deadline, exact process-group disappearance, and terminal effect receipt. Restart with a live exact group returns `PROCESS_OWNERSHIP_UNCLEAR` and blocks reset; a gone exact group becomes failed-safe.

- [ ] **Step 3: Run RED**

Run: `"$PYTHON" tests/test_process_policy.py -v && "$PYTHON" tests/test_process_ownership.py -v && "$PYTHON" tests/test_installer.py -v`

Expected: FAIL because the current `asyncio.create_subprocess_exec` call supplies a path-based `cwd` and executes before durable ownership.

- [ ] **Step 4: Install, attest, and launch a trusted blocked bootstrap over `posix_spawn`**

Add `process-release` as the fourth ordered entry in the storage plan's `NATIVE_HELPERS` tuple in this task only; no other plan writes that record afterward. `console/installer.py` compiles `native/macos/process_release.swift` with the same equipped `xcrun swiftc`, ad-hoc signs it, records source/binary SHA-256, CDHash, device, inode, owner, and mode, and subjects it to existing staged publication, rollback, Doctor, rebuild refusal, and uninstall-preservation rules. `tests/test_installer.py` requires exact order `macos-ax-send`, `disk-image-keychain`, `storage-mount-probe`, `process-release`, proves a fresh install contains and attests the helper, and proves source/binary/signature tamper prevents spawn.

Extend `AttestedHelper` in `console/native_helpers.py` with `revalidate_for_spawn() -> Path`: while its attestation FD remains open, compare live `fstat(fd)` against the manifest record, reopen the private native parent with no-follow, compare `lstat(path)` device/inode/owner/mode to that same FD, recompute SHA-256 and CDHash, and return `path` only on exact equality. This is the one assigned extension to the storage helper contract; it does not duplicate `attest_helper` or `run_attested_helper`. The documented same-UID malicious replacement threat remains out of scope between immediate revalidation and `posix_spawn`; no FD-exec claim is made.

Resolve libc symbols at runtime with `ctypes`. Immediately before spawn call `helper = attest_helper("process-release", owned_manifest)`, retain `helper.fd`, and pass only `helper.revalidate_for_spawn()` to `posix_spawn`; close the attestation only after spawn returns. Initialize file actions; add `dup2` for stdout/stderr and release-read FD; add fchdir for the duplicated verified cwd FD; set `POSIX_SPAWN_SETPGROUP` with pgroup 0; `posix_spawn` the attested helper as `process-release --release-fd 7 -- python3 site.py` in the focused fixture. The Swift helper reads exactly one byte, closes the pipe, and calls `execvp`; EOF exits 125 without executing requested argv. It accepts no secret, path cwd, shell string, or environment-supplied release authority.

Ordering in `ToolExecutor.run_process` is exact:

```python
activation = self._require_process_activation(activation, operation="run_process")
self.workspace.revalidate()
cwd_fd = open_directory_at(self.workspace.workspace_fd, cwd)
owned = spawn_blocked(argv=argv, cwd_fd=cwd_fd, env=sanitized_process_environment())
self.effect_gate.record_ownership(activation, owned.to_json())
release_owned_process(owned)
return await collect_owned_process(owned, timeout=timeout)
```

Any failure between spawn and release closes the write FD, terminates/verifies the group, and records failed or unclear based on ownership proof. `run_tests` delegates to the same activated path without creating a second effect.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_process_policy.py -v && "$PYTHON" tests/test_process_ownership.py -v && "$PYTHON" tests/test_installer.py -v`

Expected: PASS on the equipped macOS SDK; the marker remains absent until durable ownership and no descendant remains after cancellation.

```bash
git add executor/process_spawn.py native/macos/process_release.swift executor/tools.py console/process_ownership.py console/native_helpers.py console/installer.py tests/test_process_policy.py tests/test_process_ownership.py tests/test_installer.py
git commit -m "feat: block process launch until ownership is durable"
```

### Task 7: Make the tool registry exact and ChatGPT-visible list derived

**Files:**
- Modify: `orchestration/protocol.py`
- Modify: `orchestration/runner.py`
- Modify: `executor/policy.py`
- Modify: `executor/tools.py`
- Modify: `tests/test_protocol_report_fuzz.py`
- Modify: `tests/test_runner_mode_a.py`
- Modify: `tests/test_command_policy_fuzz.py`

**Interfaces:**
- Consumes: public `ToolExecutor` methods from Tasks 4-6.
- Produces: one ordered `ALLOWED_TOOLS` tuple and derived `READ_ONLY_TOOLS`, `WRITE_TOOLS`, policy registries, schema summaries, and public method oracle.

- [ ] **Step 1: Write the exact equality oracle**

```python
EXPECTED = (
    "list_directory", "read_file", "file_exists", "search_text",
    "write_file", "apply_patch", "create_directory", "move_file",
    "run_process", "run_tests", "git_status", "git_diff",
)

def test_every_tool_registry_and_public_method_matches_exactly():
    self.assertEqual(ALLOWED_TOOLS, EXPECTED)
    self.assertEqual(tuple(TOOL_ARGUMENTS), EXPECTED)
    self.assertEqual(READ_ONLY_TOOLS | WRITE_TOOLS, frozenset(EXPECTED))
    self.assertEqual(policy.ALL_TOOLS, frozenset(EXPECTED))
    self.assertEqual(public_tool_methods(ToolExecutor), frozenset(EXPECTED))
    contract = render_contract("Inspect safely", mission_id, "qa-workspace")
    self.assertEqual(parse_contract_tool_order(contract), EXPECTED)
```

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_protocol_report_fuzz.py -v && "$PYTHON" tests/test_runner_mode_a.py -v && "$PYTHON" tests/test_command_policy_fuzz.py -v`

Expected: FAIL because `move_file` is missing from static registries and `ALLOWED_TOOLS_CSV` duplicates the protocol.

- [ ] **Step 3: Add the exact schema and approval rule**

```python
TOOL_ARGUMENTS["move_file"] = {
    "required": ["source", "destination"],
    "types": {"source": str, "destination": str},
}
WRITE_TOOLS = frozenset(ALLOWED_TOOLS) - READ_ONLY_TOOLS
ONE_SHOT_ONLY_TOOLS = frozenset({"move_file", "run_process", "run_tests"})
```

Extend path validation keys with `source` and `destination`. Reject identical normalized paths. Policy never treats tool-wide or all-writes scope as satisfying a one-shot-only tool.

- [ ] **Step 4: Remove the second ChatGPT allowlist**

Delete `ALLOWED_TOOLS_CSV`. Render tool names with `", ".join(ALLOWED_TOOLS)` and argument schemas from the same ordered map. The oracle ignores private methods and exactly compares callable public methods excluding constructor/properties.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_protocol_report_fuzz.py -v && "$PYTHON" tests/test_runner_mode_a.py -v && "$PYTHON" tests/test_command_policy_fuzz.py -v`

Expected: PASS with exact ordered equality and no duplicate allowlist string.

```bash
git add orchestration/protocol.py orchestration/runner.py executor/policy.py executor/tools.py tests/test_protocol_report_fuzz.py tests/test_runner_mode_a.py tests/test_command_policy_fuzz.py
git commit -m "feat: derive the exact structured tool registry"
```

### Task 8: Gate attachment staging before the first byte and reconcile crashes

**Files:**
- Modify: `console/attachments.py`
- Modify: `console/chat.py`
- Create: `tests/test_direct_effect_recovery.py`
- Modify: `tests/test_attachment_boundaries.py`

**Interfaces:**
- Consumes: `DirectEffectRequest`, `EffectGate.begin_direct_intent`, `activate_direct_intent`, and `EffectActivation`.
- Produces: activated private attachment writers and `StagingExpectation` metadata.
- Test collection: create `tests/test_direct_effect_recovery.py` with `import sys`, `import unittest`, class-based cases, and the exact global direct-execution guard before its first direct RED command.

```python
@dataclass(frozen=True, slots=True)
class StagingExpectation:
    directory_dev: int
    directory_ino: int
    temporary_basename: str
    final_basename: str
    prior_target: FileIdentity | None
```

Exact private writer signatures are `_store_upload_activated(name: str, decoded: BinaryIO, *, activation: EffectActivation) -> dict[str, JSONValue]` and `_stage_path_activated(source_fd: int, name: str, *, activation: EffectActivation) -> dict[str, JSONValue]`.

- [ ] **Step 1: Add crash-boundary RED tests**

Parameterize `before_temp_open`, `after_temp_open`, `during_stream`, `after_file_fsync`, `before_publish`, `after_publish`, and `before_receipt`. At every boundary reopen `Store`, call startup reconciliation, and assert exactly one of:

- exact final identity/hash -> `succeeded`;
- untouched prior target and no publication -> `failed`;
- deterministic temp quarantined and no target -> `failed`;
- any contradictory target/temp/hash combination -> `outcome_unclear` and reset refused.

Also race STOP at before-intent, between intent/activation, after open, and after write-before-publication; no byte may exist when STOP wins before activation.

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_direct_effect_recovery.py -v && "$PYTHON" tests/test_attachment_boundaries.py -v`

Expected: FAIL because `store_upload` decodes to memory and calls `write_bytes` without durable intent; `stage_path` opens its destination before an activation.

- [ ] **Step 3: Make public staging entry points require a durable request**

The route first validates metadata and Base64 syntax without opening an output. For request `2f5e86dd-ec61-4c34-a376-cb03143d3bf8` and server nonce `7ec9a1b6`, the deterministic fixture basename is `.2f5e86dd-ec61-4c34-a376-cb03143d3bf8.7ec9a1b6.tmp`; production uses the same `.{requestId}.{serverNonce}.tmp` formula. It opens the private staging directory by retained FD, records `StagingExpectation` in an `intent`, fsyncs SQLite/WAL, then performs the second activation transaction. Directory creation and final publication call only Task 4/5 `create_directory_at` and `rename_exclusive_at`; intent code orchestrates them and contains no second mkdir/rename binding. Only `_store_upload_activated` may call `openat(O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW)` for streamed content.

Stream-decode Base64 in bounded chunks while hashing; enforce limits during the stream; fsync file and directory; call `record_ownership` with temp dev/inode/size/content digest, final basename, expected final digest, and prior target facts; publish exclusively; reread/fstat; then `succeed`.

- [ ] **Step 4: Implement idempotent startup reconciliation**

`reconcile_attachment_effect(row)` opens only the journaled private directory identity. It never adopts an unjournaled file. It quarantines the exact active temp only when name/dev/inode/hash match; it never sends a recovered attachment. Exact terminal retry returns the descriptor receipt; active/unclear returns 409 without restaging.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_direct_effect_recovery.py -v && "$PYTHON" tests/test_attachment_boundaries.py -v`

Expected: PASS with intent committed before every observed temp open and no recovered auto-send.

```bash
git add console/attachments.py console/chat.py tests/test_direct_effect_recovery.py tests/test_attachment_boundaries.py
git commit -m "feat: persist attachment intents before staging bytes"
```

### Task 9: Put Settings, Onboarding, and opt-in writes behind admin capabilities

**Files:**
- Modify: `console/settings.py`
- Modify: `console/onboarding.py`
- Modify: `console/missions.py`
- Modify: `tests/test_chat_settings_api.py`
- Modify: `tests/test_direct_effect_recovery.py`
- Modify: `tests/test_onboarding_runtime_truth.py`

**Interfaces:**
- Consumes: HTTP `effect` metadata, `EffectGate` admin intent/activation, the storage plan's already-validated canonical settings payload, `browser_transport=chrome_extension` clamp, and exclusive storage-state lock behavior.
- Produces: `_save_settings_activated`, `_set_completed_activated`, `_set_optin_activated`; stable retry receipts.

- [ ] **Step 1: Write RED tests proving low-level writers reject direct calls**

```python
def test_settings_low_level_writer_requires_admin_activation():
    with self.assertRaisesRegex(EffectGateConflict, "EFFECT_CAPABILITY_INVALID"):
        settings._save_settings_activated(payload, activation=object())
    self.assertFalse(settings.SETTINGS_FILE.exists())

async def test_stop_between_settings_intent_and_activation_preserves_old_bytes(client):
    pause_gate_at("after_intent")
    request = asyncio.create_task(client.put("/api/settings", json=body_with_effect))
    gate.request_stop()
    release_gate()
    assert (await request).status_code == 409
    assert settings.SETTINGS_FILE.read_bytes() == old_bytes
```

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_chat_settings_api.py -v && "$PYTHON" tests/test_direct_effect_recovery.py -v && "$PYTHON" tests/test_onboarding_runtime_truth.py -v`

Expected: FAIL because all three writers are callable without a durable capability.

- [ ] **Step 3: Canonicalize complete semantic bodies before intent**

For Settings digest the fully canonical payload returned by the storage plan's existing validator after defaults, storage projection, and transport clamp; this plan adds no alternate path validator, clamp, settings schema, or lock implementation. For Onboarding digest `{"completed": true}`; for opt-in digest `{"accepted": bool}`. Require exact operation names `settings.save`, `onboarding.dismiss`, and `transport.opt_in`. Routes reject a client digest that differs from `canonical_digest(operation, canonical_payload)` before intent.

The effect choke receives the already-held storage-plan lock token for a settings write and refuses a missing/invalid token; it does not reacquire or redefine lock order. It uses Task 4/5 generic FD temporary/open/fsync/`rename_exclusive_at` primitives, so Settings/Onboarding intent code only orders validation -> intent -> activation -> generic publication -> receipt.

- [ ] **Step 4: Reconcile every injected publication boundary**

Test old file present and absent at before temp open, after open, after fsync, before/after atomic publication, and before receipt. Exact expected final bytes become succeeded; exact old bytes/no new target become failed-safe; mismatch becomes unclear. Never infer success from parseable but different JSON.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_chat_settings_api.py -v && "$PYTHON" tests/test_direct_effect_recovery.py -v && "$PYTHON" tests/test_onboarding_runtime_truth.py -v`

Expected: PASS; STOP prevents each admin activation and exact retries are idempotent.

```bash
git add console/settings.py console/onboarding.py console/missions.py tests/test_chat_settings_api.py tests/test_direct_effect_recovery.py tests/test_onboarding_runtime_truth.py
git commit -m "feat: gate administrative writes with durable intents"
```

### Task 10: Enforce browser permits at the final extension choke point

**Files:**
- Create: `console/effect_registry.py`
- Modify: `console/chrome_extension.py`
- Modify: `transport/browser_chrome_extension.py`
- Modify: `transport/chatgpt_web/adapter.py`
- Modify: `chrome-extension/service-worker-core.js`
- Modify: `chrome-extension/tests/extension.test.mjs`
- Modify: `tests/test_chrome_extension_bridge.py`
- Modify: `tests/test_chrome_extension_driver.py`
- Modify: `tests/test_transport_session_isolation.py`

**Interfaces:**
- Consumes: `EffectActivation`, `ExistingSessionReadPermit`, `StopCleanupPermit`, and the storage plan's fail-closed `chrome_extension` clamp/factory. This task does not alter `load_browser_settings`, transport selection, or storage validation.
- Produces:

`BrowserPermit` is exactly `EffectActivation | ExistingSessionReadPermit | StopCleanupPermit`. The choke-point signature is `ChromeExtensionManager.command(self, session: str, action: str, payload: dict[str, JSONValue], timeout: float = DEFAULT_COMMAND_TIMEOUT_SECONDS, *, permit: BrowserPermit) -> Any`.

- [ ] **Step 1: Write RED choke-point tests**

```python
async def test_effect_command_without_matching_activation_emits_no_envelope():
    for action in BROWSER_EFFECT_ACTIONS:
        with self.subTest(action=action):
            with self.assertRaisesRegex(BridgeProtocolError, "EFFECT_CAPABILITY_INVALID"):
                await manager.command("s", action, {}, permit=read_permit)
            self.assertEqual(connection.sent, [])

async def test_stop_cleanup_permit_is_narrow():
    permit = gate.stop_cleanup_permit(operation="press_stop")
    await manager.command("s", "press_stop", {}, permit=permit)
    with self.assertRaisesRegex(BridgeProtocolError, "EFFECT_CAPABILITY_INVALID"):
        await manager.command("s", "send_text", {"text":"x"}, permit=permit)

async def test_cancel_from_entry_into_send_json_is_delivery_uncertain():
    connection.enter_send_json.set()
    task = asyncio.create_task(manager.command(
        "s", "send_text", {"text": "x"}, permit=send_activation,
    ))
    await connection.entered_send_json.wait()
    task.cancel()
    with self.assertRaises(asyncio.CancelledError):
        await task
    self.assertEqual(effect_row(send_activation.effect_id)["state"], "outcome_unclear")
    self.assertEqual(effect_row(send_activation.effect_id)["error_code"], "BROWSER_DELIVERY_UNCERTAIN")

async def test_attachment_phase_failure_stops_sequence_without_replay():
    connection.fail_on_action = "attachment_chunk"
    with self.assertRaisesRegex(BridgeProtocolError, "BROWSER_DELIVERY_UNCERTAIN"):
        await driver.upload_files_named([fixture], permit=upload_activation)
    self.assertEqual(connection.actions, ["attachment_begin", "attachment_chunk"])
    self.assertNotIn("attachment_commit", connection.actions)
    self.assertEqual(effect_row(upload_activation.effect_id)["state"], "outcome_unclear")
```

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_chrome_extension_bridge.py -v && "$PYTHON" tests/test_chrome_extension_driver.py -v && "$PYTHON" tests/test_transport_session_isolation.py -v && node --test chrome-extension/tests/extension.test.mjs`

Expected: FAIL because `command` emits any allowlisted action without a durable token.

- [ ] **Step 3: Define the exact browser action classes**

```python
BROWSER_EFFECT_ACTIONS = frozenset({
    "open_chatgpt", "focus_tab", "navigate", "close_tab", "spa_navigate",
    "send_text", "attachment_begin", "attachment_chunk", "attachment_commit",
    "send_bare", "capture_screenshot", "select_model",
})
BROWSER_CONDITIONAL_READS = frozenset({"probe", "list_conversations", "list_models"})
BROWSER_PURE_READS = frozenset({"get_state", "get_light_state", "list_tabs", "await_attachment"})
BROWSER_STOP_CLEANUP = frozenset({"press_stop", "release_session"})
```

Conditional reads require an existing-session permit and a manager-proven bound session; otherwise return `BROWSER_EFFECT_REQUIRED` before envelope creation. Clear bound-session proof on disconnect/worker reconnect. Heartbeats remain outside `command` and cannot mutate browser state.

- [ ] **Step 4: Persist dispatch before `send_json` and classify post-dispatch failure**

For `EffectActivation`, assign the envelope request ID and call `record_ownership` with session/action/request ID and `dispatchStartedAt` before dispatch. A connection change detected before invoking `send_json` is failed-safe. The instant control enters `connection.send_json(envelope)` is the uncertainty boundary: any exception, `CancelledError`, timeout, disconnect, EOF, or malformed/missing response from that call onward becomes `BROWSER_DELIVERY_UNCERTAIN`, even when no bytes can be proven written. No driver retry loop may reissue that effect. Confirmed result terminalizes succeeded/failed with the exact extension receipt.

Attachment upload is one browser effect `browser.attachment_upload` and one activation spanning the fixed phases `attachment_begin -> attachment_chunk[sequence=0..n-1] -> attachment_commit`. `attachment_begin` carries stable `uploadId`, filename, byte count, content SHA-256, MIME, and total chunks; each chunk carries the same upload ID, zero-based sequence and chunk SHA-256; commit carries the same total byte count/content digest. Before every phase envelope, persist the phase/sequence in ownership. If any phase crosses the `send_json` boundary without a confirmed matching receipt, mark the whole upload uncertain, emit no later chunk/commit, and never replay begin/chunk/commit automatically. The extension rejects a phase whose upload ID, sequence, totals, or digest differs from the established begin record.

Propagate keyword-only `permit` through browser driver/transport methods for create, focus, navigate, SPA navigate, close, model selection, send, upload, capture. `press_stop` and `release_session` accept only cleanup permit during STOP; ordinary user cancellation activates its own browser effect.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_chrome_extension_bridge.py -v && "$PYTHON" tests/test_chrome_extension_driver.py -v && "$PYTHON" tests/test_transport_session_isolation.py -v && node --test chrome-extension/tests/extension.test.mjs`

Expected: PASS; connection spy sees zero envelope for absent/wrong/stale permits and exactly one envelope for a valid activation.

```bash
git add console/effect_registry.py console/chrome_extension.py transport/browser_chrome_extension.py transport/chatgpt_web/adapter.py chrome-extension/service-worker-core.js chrome-extension/tests/extension.test.mjs tests/test_chrome_extension_bridge.py tests/test_chrome_extension_driver.py tests/test_transport_session_isolation.py
git commit -m "feat: require durable permits at browser dispatch"
```

### Task 11: Compose chat, attachment, capture, and cancellation child effects

**Files:**
- Modify: `console/chat.py`
- Modify: `console/attachments.py`
- Modify: `console/missions.py`
- Modify: `transport/chatgpt_web/adapter.py`
- Modify: `tests/test_direct_effect_recovery.py`
- Modify: `tests/test_chat_mission_pool_sharing.py`
- Modify: `tests/test_mission_attachment_contract.py`

**Interfaces:**
- Consumes: direct intent, browser permit, attachment activated writer, STOP cleanup permit.
- Produces: one parent direct request with ordered child effects and retained staged-artifact receipts.

- [ ] **Step 1: Write composite STOP/crash RED tests**

For `chat.send`, `chat.send_with_attachment`, and `chat.send_screenshot`, pause between every child. Assert STOP after local stage leaves the exact staged synthetic artifact and prevents capture/send; STOP after capture prevents local publication/send; STOP after browser dispatch records delivery uncertainty and never retries. A third-writer refusal occurs before any child intent or browser envelope and preserves draft/staged file.

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_direct_effect_recovery.py -v && "$PYTHON" tests/test_chat_mission_pool_sharing.py -v && "$PYTHON" tests/test_mission_attachment_contract.py -v`

Expected: FAIL because current route stages and schedules an unjournaled background task, and capture selects/navigates before durable intent.

- [ ] **Step 3: Give every flow an exact parent and ordered children**

Use operation names and categories:

```python
CHAT_EFFECT_FLOW = {
    "chat.send": (("browser.send_text", "browser"),),
    "chat.send_with_attachment": (
        ("attachment.stage", "filesystem"),
        ("browser.attachment_upload", "browser"),
        ("browser.send", "browser"),
    ),
    "chat.send_screenshot": (
        ("browser.capture_screenshot", "sensitive_read"),
        ("attachment.stage_capture", "filesystem"),
        ("browser.attachment_upload", "browser"),
        ("browser.send", "browser"),
    ),
}
```

The frontend request ID identifies the parent. Each child gets a deterministic UUIDv5 request ID derived from `(parent request UUID, child ordinal, operation)` and is persisted with `parent_effect_id`, preserving globally unique direct/admin `request_id` rows and exact-retry reconstruction. Before each child, compare parent request ID/digest and current epoch, then begin/activate that child. Persist child ordering in the parent receipt. The upload composite uses one child activation across its fixed begin/chunk/commit sequence and records each phase receipt; the later send has a different child activation.

`console/chat.py` no longer lets `_persist_runs` create/replace `chat-runs.json` as an unclassified side effect. Initial chat-run publication is the first filesystem child `chat.run_state.create` under the parent request; later status/event updates are durable bookkeeping tied to that same parent/effect tree and may continue only to record terminal reconciliation during STOP. The writer uses Task 4/5 generic FD publication primitives. Startup removes the blanket `cleanup_abandoned` deletion sweep: only a reconciler with exact journaled temp/final identity may quarantine a partial; terminal attachment release is its own classified cleanup child and STOP retains, rather than deletes, an unpublished staged artifact.

- [ ] **Step 4: Make cancellation ownership explicit**

Normal `/chat/runs/{id}/cancel` carries a new direct effect request and activates `browser.press_stop`; STOP quiescence uses only `StopCleanupPermit("press_stop")`. Mission cancellation follows the same distinction. Task cancellation awaits browser/process ownership reconciliation before releasing writer leases. `CancelledError` after browser dispatch sets uncertainty rather than `CANCELLED` success.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_direct_effect_recovery.py -v && "$PYTHON" tests/test_chat_mission_pool_sharing.py -v && "$PYTHON" tests/test_mission_attachment_contract.py -v`

Expected: PASS; every effect tree has ordered terminal children, no post-STOP activation, and no auto-send of a retained partial.

```bash
git add console/chat.py console/attachments.py console/missions.py transport/chatgpt_web/adapter.py tests/test_direct_effect_recovery.py tests/test_chat_mission_pool_sharing.py tests/test_mission_attachment_contract.py
git commit -m "feat: compose durable direct chat effects"
```

### Task 12: Remove toolbar capture and require backend sensitive-read activation

**Files:**
- Modify: `chrome-extension/service-worker.js`
- Modify: `chrome-extension/service-worker-core.js`
- Modify: `chrome-extension/tests/extension.test.mjs`
- Modify: `tests/test_chrome_extension_driver.py`

**Interfaces:**
- Consumes: `capture_screenshot` envelope already authorized by Task 10.
- Produces: immediate backend-command capture only; no retained pixel state.

- [ ] **Step 1: Write the toolbar zero-capture test**

```javascript
test("toolbar click cannot capture or retain page pixels", async () => {
  await registeredActionClick({id: 17, windowId: 2, url: CHAT_URL});
  assert.equal(chrome.debugger.attach.mock.calls.length, 0);
  assert.equal(chrome.tabs.captureVisibleTab.mock.calls.length, 0);
  assert.equal(chrome.scripting.executeScript.mock.calls.length, 0);
  assert.equal("pendingCapture" in context, false);
});
```

- [ ] **Step 2: Run RED**

Run: `node --test chrome-extension/tests/extension.test.mjs && "$PYTHON" tests/test_chrome_extension_driver.py -v`

Expected: FAIL because `chrome.action.onClicked` calls debugger capture and `routeCommand` reads `pendingCapture`.

- [ ] **Step 3: Delete toolbar and pending-capture behavior**

Remove `captureTabViaDebuggerExactly` import from `service-worker.js`, remove `pendingCapture` from context, and make `chrome.action.onClicked` only call `connect()` with no tab inspection or capture API. Remove TTL, tab-removal cleanup, and reuse branches for `pendingCapture`.

`routeCommand("capture_screenshot")` validates the bound tab and expected URL, calls `captureTabViaDebuggerExactly` once inside the command, rechecks tab ID/URL after capture, restores the privacy mask, and returns pixels only in the command result. It stores no data URL in module, session, local, sync, or in-memory context after return.

- [ ] **Step 4: Add failure assertions**

Test mask setup/restoration failure, debugger detach failure, target change, and command cancellation. All fail without a pixel cache; a later command performs a fresh capture and never returns prior bytes.

- [ ] **Step 5: Run GREEN and commit**

Run: `node --test chrome-extension/tests/extension.test.mjs && "$PYTHON" tests/test_chrome_extension_driver.py -v`

Expected: PASS; toolbar click causes zero capture/debugger/DOM-mask call and backend command causes exactly one protected capture.

```bash
git add chrome-extension/service-worker.js chrome-extension/service-worker-core.js chrome-extension/tests/extension.test.mjs tests/test_chrome_extension_driver.py
git commit -m "fix: remove toolbar screenshot retention"
```

### Task 13: Install and confine the fixed local-alias worker

**Files:**
- Create: `executor/local_alias_worker.py`
- Create: `executor/local_alias_worker_runner.py`
- Modify: `console/installer.py`
- Modify: `console/effect_gate.py`
- Modify: `orchestration/store.py`
- Create: `tests/test_local_alias_worker.py`
- Create: `tests/test_local_alias_worker_runner.py`
- Modify: `tests/test_installer.py`
- Modify: `tests/test_effect_gate.py`
- Modify: `tests/test_store_lifecycle.py`

**Interfaces:**
- Consumes: Task 2 `EffectActivation`, `BlockedWorkerActivationPermit`, `EffectGate.activate_direct_intent`, `EffectGate.activate_local_alias_intent`, `EffectGate.assert_activation`, `record_blocked_ownership`, terminal methods; exact v3 local-alias rows from Task 1; only opaque `StorageContract.assert_runtime_ready() -> StorageStatus` from storage authority; the manifest-owned `installed_home`, storage-owned committed settings projection, and equipped installed interpreter at `CORTEX_HOME/venv/bin/python`. `StorageContract.open/open_workspace/revalidate`, `StorageBinding`, `WorkspaceHandle`, mount descriptors, vault identities and APFS UUIDs are forbidden dependencies in both local-alias modules.
- Produces: the frozen `LocalRootIdentity`, `LocalDescriptorEdge`, `LocalAliasProtectedRoot`, `LocalAliasProtectionFacts`, `LocalAliasProtectionResolver`, `server_local_runtime_projection_resolver(installed_home: Path) -> Callable[[StorageStatus], tuple[LocalAliasProtectedRoot, ...]]`, `LocalAliasCatalogEntry`, `LocalAliasAccessObservation`, `LocalAliasGrant`, `LocalAliasHandle`, unchanged public `LocalAliasWorkerRequest`, `LocalAliasWorkerReceipt`, `BlockedLocalAliasWorker`, and exact `LocalAliasWorkerRunner` contracts listed above; installed manifest record `fixed_workers.local-alias-worker`.
- Boundary: `executor/local_alias_worker.py` and its runner must have zero import, annotation, constructor parameter, or call edge to `ToolExecutor`, `WorkspaceHandle`, `MissionLoop`, process tools, browser transport, attachments, or the generic tool registry. The intent plan constructs the catalog/grant/action rows and calls this runner; it does not redefine the worker, durable effect, installation, ownership, or reconciliation logic.
- Test collection: create both `tests/test_local_alias_worker.py` and `tests/test_local_alias_worker_runner.py` with `import sys`, `import unittest`, class-based cases, and the exact global direct-execution guard before the Step 2 RED commands.

- [ ] **Step 1: Write the exact inventory, installation, and separation tests**

```python
def test_local_alias_effect_inventory_is_exact():
    self.assertEqual(SENSITIVE_READ_OPERATIONS,
                     frozenset({"verify_local_alias_access", "capture_screenshot"}))
    self.assertEqual(
        LOCAL_ALIAS_EFFECT_RULES,
        {
            "verify_local_alias_access": ("direct_ui", "sensitive_read"),
            "create_directory": ("local_alias_action", "filesystem"),
        },
    )

def test_blocked_ownership_accepts_only_the_two_worker_tuples(self):
    allowed = (
        ("direct_ui", "sensitive_read", "verify_local_alias_access"),
        ("local_alias_action", "filesystem", "create_directory"),
    )
    for owner, category, operation in allowed:
        with self.subTest(owner=owner, category=category, operation=operation):
            intent = seeded_intent(owner, category, operation)
            gate.record_blocked_ownership(intent.effect_id, exact_blocked_identity())
            self.assertEqual(effect_row(intent.effect_id)["ownership"]["released"], False)
    for owner, category, operation in all_other_worker_tuple_permutations():
        with self.subTest(owner=owner, category=category, operation=operation):
            with self.assertRaisesRegex(EffectGateConflict,
                                        "EFFECT_CAPABILITY_INVALID"):
                intent = seeded_intent(owner, category, operation)
                gate.record_blocked_ownership(intent.effect_id,
                                              exact_blocked_identity())

def test_local_alias_modules_cannot_cross_workspace_executor_boundary():
    forbidden = {"ToolExecutor", "WorkspaceHandle", "MissionLoop"}
    self.assertFalse(forbidden & imported_or_referenced_names(LOCAL_ALIAS_MODULES))
    self.assertNotIn("verify_access", ALLOWED_TOOLS)
    self.assertEqual(ALLOWED_LOCAL_ALIAS_WORKER_OPERATIONS,
                     ("verify_access", "create_directory"))

def test_install_owns_and_attests_fixed_worker(installed_home):
    record = installed_manifest(installed_home)["fixed_workers"]["local-alias-worker"]
    self.assertEqual(record["relative_path"], "app/executor/local_alias_worker.py")
    self.assertEqual(record["interpreter_relative_path"], "venv/bin/python")
    self.assertEqual(set(record), {
        "relative_path", "sha256", "device", "inode", "uid", "mode",
        "interpreter_relative_path", "interpreter_sha256", "interpreter_device",
        "interpreter_inode", "interpreter_uid", "interpreter_mode",
    })
    self.assertEqual(attest_local_alias_worker(installed_home).sha256, record["sha256"])
```

The second assertion about `create_directory` above refers to the generic public tool registry: assert it remains a `ToolExecutor` tool while the local-alias worker protocol is separately and exactly `verify_access | create_directory`; also assert neither registry is used to dispatch the other. Tamper each installed script/interpreter hash, device, inode, uid, and mode independently and require refusal before child spawn. Test fresh install, reinstall, Doctor, staged-publication rollback, and uninstall preservation/removal consistently with the existing app manifest rules.

- [ ] **Step 2: Run installation and boundary tests RED**

Run: `"$PYTHON" tests/test_installer.py -v && "$PYTHON" tests/test_local_alias_worker_runner.py && "$PYTHON" tests/test_effect_gate.py`

Expected: FAIL because there is no fixed worker asset, manifest record, attestor, runner, or local-alias effect inventory.

- [ ] **Step 3: Install one immutable Python worker and attest both script and interpreter**

During installer staging, descriptor-copy the reviewed repository file to `CORTEX_HOME/app/executor/local_alias_worker.py`, reject symlinks/special files/device changes, chmod `0700`, fsync the file and both parent directories, and atomically publish it with the existing app payload. Record exactly relative script/interpreter paths, SHA-256, device, inode, uid, and mode under `owned.json["fixed_workers"]["local-alias-worker"]`. The interpreter must be the installer-owned `CORTEX_HOME/venv/bin/python`, not `sys.executable`, `/usr/bin/env`, `PATH`, or a request field.

`attest_local_alias_worker(installed_home: Path) -> AttestedFixedWorker` opens the owned manifest, app parent, script, venv parent, and interpreter without following links; compares live FD identity/owner/mode and script SHA-256 to the record immediately before spawn; and retains script/interpreter proof FDs until `posix_spawn` returns. `AttestedFixedWorker` exposes only the already-verified absolute `script_path`, `interpreter_path`, proof FDs, identities, and `close()`. Spawn argv is exactly `[interpreter_path, "-I", "-S", script_path]`; request data is never in argv and no shell or second program is permitted. Doctor must report a required `local_alias_worker_attested` check, and any mismatch is `LOCAL_ACTION_UNSUPPORTED` before an effect is activated.

`LocalAliasProtectionResolver` is runner-private and derives its inputs from exactly five server sources: effective `getuid()/getpwuid_r()` identity and home; `installed_home` plus the descriptor-attested owned manifest; the opaque current `StorageContract.assert_runtime_ready()` result; the committed server local-runtime projection returned by `server_local_runtime_projection_resolver(installed_home)`; and fixed macOS locations compiled in the module. `StorageStatus` contributes only its canonical opaque readiness digest. The resolver never calls `StorageContract.open`, `open_workspace` or `revalidate`, never receives `StorageBinding`/`WorkspaceHandle`, and neither sees nor stores a mount FD, vault root identity/path, storage-image identity or APFS UUID.

Under required storage, the already frozen storage layout makes canonical mount, external storage root and browser-cache/profile strict descendants of the manifest-owned `installed_home`; therefore the descriptor-proven `cortex_home` relation check protects that entire subtree transitively without naming or opening any vault object. The server projection contributes no additional required-storage path. With no required marker, `server_local_runtime_projection_resolver` may return only the already committed local browser/cache projection as `local_runtime_projection`; it is non-authoritative and can only add a rejection relation, never authorize an alias, effect or write. It descriptor-opens that local projection component-by-component with no-follow, returns identities or parent-descriptor-proven absence, and has no environment/client/model fallback or storage binding edge.

The fixed macOS locations are exactly home-relative `.ssh`, `.gnupg`, `.aws`, `.config/gcloud`, `Library/Keychains`, plus absolute `/Library/Keychains`, `/System/Library/Keychains`, and `/dev`, represented by `FIXED_HOME_CREDENTIAL_COMPONENTS` and `FIXED_ABSOLUTE_PROTECTED_COMPONENTS`. The resolver accepts no client, model, request, `$HOME`, `CORTEX_HOME` environment, browser payload or arbitrary-path field. It descriptor-opens every existing local root with `O_NOFOLLOW`, records filesystem-root identity, the complete root-to-home identity chain, and each forbidden root-to-leaf named identity chain, and records a stable `(kind, components)` absence only for an `ENOENT` proven from its already verified parent descriptor. Any other missing-parent ambiguity, permission failure, symlink, wrong type or identity race fails closed. It closes temporary FDs after producing immutable facts and hashes the opaque readiness, ordered present local identities, proven absences and provenance. The fixed provenance order is `SERVER_ONLY_PROTECTION_SOURCES`. `/` and the complete home are structural anchors, not members of `PROTECTED_ROOT_KINDS`: the alias must be exactly the strict one-component `Desktop|Documents|Downloads` child of that home, and equality with or ancestry over either anchor is rejected while this single expected descendant relation is required.

- [ ] **Step 4: Write descriptor-chain and exact-leaf worker tests RED**

Use only a fixture-injected temporary home and fixed fixture alias; never open the user's real Desktop, Documents, or Downloads. The child test seam supplies an already-open fixture filesystem-root FD plus fake `getuid()`/`getpwuid_r()` data while exercising the same production walker.

```python
def test_create_directory_performs_one_exact_mkdirat(worker_harness):
    receipt = worker_harness.run_create(alias="desktop", allowed_leaf="Cortex QA")
    self.assertEqual(worker_harness.mkdirat_calls,
                     [(worker_harness.alias_fd, b"Cortex QA", 0o700)])
    self.assertEqual(receipt.code, "CREATED")
    self.assertEqual(receipt.created_inode, os.stat("Cortex QA", dir_fd=worker_harness.alias_fd).st_ino)
    self.assertEqual(worker_harness.unrelated_changes(), [])

def test_each_named_descriptor_edge_is_checked_before_and_after_mkdir(worker_harness):
    worker_harness.replace_edge_at_barrier("home", "after_mkdir")
    receipt = worker_harness.finish()
    self.assertEqual(receipt.code, "LOCAL_ALIAS_CHANGED")
    self.assertTrue(worker_harness.entered_mkdirat)

def test_root_uid_and_protected_aliases_fail_before_descriptor_walk(self):
    for case in ("effective_uid_zero", "alias_is_filesystem_root",
                 "alias_is_complete_home", "alias_is_cortex_home",
                 "alias_is_cortex_home_descendant_mount",
                 "alias_is_cortex_home_descendant_storage",
                 "alias_is_cortex_home_descendant_browser_cache",
                 "alias_is_no_marker_local_projection",
                 "alias_is_credential_store", "alias_is_keychain_path",
                 "alias_is_device_path"):
        with self.subTest(case=case):
            receipt = run_worker_identity_case(case)
            self.assertEqual(receipt.code, "LOCAL_ACTION_UNSUPPORTED")
            self.assertEqual(mkdirat_calls(), [])

def test_alias_relation_to_every_protected_root_is_rejected_server_side(self):
    for relation in ("equal", "alias_inside_protected_subtree",
                     "alias_is_authority_bearing_ancestor"):
        for kind in PROTECTED_ROOT_KINDS:
            with self.subTest(relation=relation, kind=kind):
                harness = protection_harness(kind=kind, relation=relation)
                with self.assertRaisesRegex(LocalAliasWorkerError,
                                            "LOCAL_ACTION_UNSUPPORTED"):
                    harness.runner.spawn_blocked(
                        request=harness.request, intent=harness.intent,
                    )
                self.assertEqual(harness.spawn_count, 0)
                self.assertEqual(harness.alias_open_count, 0)

def test_protection_provenance_cannot_be_forged_or_raced(self):
    for source in ("client", "model", "environment"):
        with self.subTest(source=source):
            harness = protection_harness(forged_source=source)
            self.assertEqual(harness.resolver.resolve_request_fields, ())
            self.assertEqual(harness.resolver.resolve_environment_reads, ())
            self.assertEqual(harness.resolver.facts.provenance_sources,
                             SERVER_ONLY_PROTECTION_SOURCES)
    for barrier in ("before_spawn", "before_activation", "before_release"):
        with self.subTest(barrier=barrier):
            result = protection_harness(
                replace_protected_identity_at=barrier,
            ).execute()
            self.assertEqual(result.code, "LOCAL_ALIAS_CHANGED")
            self.assertEqual(result.worker_release_count, 0)

def test_local_runner_never_opens_storage_binding_or_workspace(self):
    storage = opaque_ready_storage_contract()
    storage.open.side_effect = AssertionError("STORAGE_OPEN_FORBIDDEN")
    storage.open_workspace.side_effect = AssertionError("WORKSPACE_OPEN_FORBIDDEN")
    storage.revalidate.side_effect = AssertionError("STORAGE_REVALIDATE_FORBIDDEN")
    harness = protection_harness(storage_contract=storage)
    result = harness.execute_through_all_three_readiness_barriers()
    self.assertEqual(result.code, "CREATED")
    self.assertEqual(storage.assert_runtime_ready.call_count, 3)
    self.assertEqual(storage.open.call_count, 0)
    self.assertEqual(storage.open_workspace.call_count, 0)
    self.assertEqual(storage.revalidate.call_count, 0)
    self.assertTrue({
        "mount_fd", "vault_path", "vault_root_identity",
        "storage_transaction_id", "storage_apfs_volume_uuid",
    }.isdisjoint(LocalAliasProtectionFacts.__dataclass_fields__))

def test_cortex_home_relation_transitively_blocks_required_storage_descendants(self):
    for relation in ("equal", "descendant", "authority_ancestor"):
        for protected_descendant in (
            "canonical_mount", "canonical_storage_root", "browser_cache",
        ):
            with self.subTest(relation=relation, protected=protected_descendant):
                harness = required_storage_relation_harness(
                    relation=relation, protected_descendant=protected_descendant,
                )
                with self.assertRaisesRegex(LocalAliasWorkerError,
                                            "^LOCAL_ACTION_UNSUPPORTED$"):
                    harness.runner.spawn_blocked(
                        request=harness.request, intent=harness.intent,
                    )
                self.assertEqual(harness.storage.open.call_count, 0)
                self.assertEqual(harness.storage.open_workspace.call_count, 0)
                self.assertEqual(harness.spawn_count, 0)
```

Parameterize replacement/symlink/device/inode/UID/file-type/mode races at filesystem-root→each absolute home component→fixed alias, before the leaf probe, immediately before `mkdirat`, and after it. Assert every retained edge's `fstat(fd)` and named `fstatat(parent_fd, child_name, AT_SYMLINK_NOFOLLOW)` identity policy is checked both before and after: real directory, no symlink, exact device/inode/type; home chain derived from the effective user's `getpwuid_r` entry; final alias UID equals the effective UID and exact catalog/observation/grant `(device,inode,uid,mode)` matches. For every protected-root kind, test all three path-component relations exactly: alias equals protected root, protected-root components are a strict prefix of alias components (alias inside its subtree), and alias components are a strict prefix of protected-root components (alias is an authority-bearing ancestor). All three fail before spawn/descriptor walk; unrelated component tuples continue. Pre-`mkdirat` cases perform zero mutation; a post-`mkdirat` chain mismatch returns `LOCAL_ALIAS_CHANGED` and maps to `outcome_unclear`.

Test leaf values `""`, `.`, `..`, `.hidden`, slash, NUL, backslash, non-NFC, leading/trailing whitespace, every ASCII/Unicode control, each bidi control, encoded separators, exactly 120 UTF-8 bytes, and 121 UTF-8 bytes. Exactly 120 valid bytes pass; every invalid/hidden/over-limit case returns `INVALID_LOCAL_LEAF` before opening the alias or calling `mkdirat`. Test existing regular file, directory, symlink, dangling symlink, FIFO, and socket: all return `TARGET_ALREADY_EXISTS`, call zero `mkdirat`, and never overwrite.

- [ ] **Step 5: Implement the worker's full retained chain and single syscall boundary**

The child accepts exactly one UTF-8 JSON object of at most 16 KiB from private stdin and rejects missing/extra/type-invalid fields. It obtains `uid = getuid()`, rejects `uid == 0`, and obtains the absolute home from `getpwuid_r(uid)`; it never reads `$HOME`, `expanduser`, client/model paths, catalog labels, or arbitrary aliases. Before spawn, the runner resolves `LocalAliasProtectionFacts` and compares the server-derived alias component tuple to every forbidden `PROTECTED_ROOT_KINDS` tuple under exactly three relations: equality, protected root as a strict prefix of alias (alias is inside a protected subtree), and alias as a strict prefix of protected root (alias would carry authority over it). Any match rejects before attestation/spawn. The forbidden set is exactly descriptor-attested `installed_home` (transitively including its required-storage mount/storage/browser-cache descendants), optional no-marker `local_runtime_projection` roots, fixed credential stores, user/system Keychain roots and `/dev`; unknown/unopenable/symlinked local roots fail closed. No required-storage vault or browser-profile path/FD/identity is separately opened or represented. Separately, the filesystem root and complete effective-user home identity chains are mandatory structural anchors: alias equality/ancestry is rejected and only the exact fixed one-child descendant is accepted. The child independently enforces that the alias is exactly one fixed `Desktop|Documents|Downloads` child of the verified `getpwuid_r` home and, after opening, rejects identity equality with its retained filesystem-root/home descriptors; injected tests substitute only constructor-owned server resolvers and never alter `LocalAliasWorkerRequest` or touch live locations. Begin with `os.open("/", O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)`. For every absolute home component and the fixed platform alias leaf selected by the enum, call `openat(parent_fd, child_name, O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC)`, require a real no-follow directory and stable exact device/inode/type against the named edge, retain an independent `F_DUPFD_CLOEXEC`, and store `LocalDescriptorEdge(parent_fd, child_fd, child_name.encode(), identity)`. The final alias additionally requires effective UID ownership and exact catalog/observation/grant `(device,inode,uid,mode)`; no ancestor is granted alias authority. `LocalAliasHandle.root_fd` is exactly the final retained alias-directory FD, never the filesystem-root or home FD.

Before access success and both immediately before and after mutation, `LocalAliasHandle.revalidate_chain()` calls `fstat` on every retained child and `fstatat(parent_fd, child_name, AT_SYMLINK_NOFOLLOW)` on every root→home→alias named edge, reapplying the exact per-edge policies above. `verify_access` stops there and emits a bounded receipt without any path. `create_directory` also requires exact catalog revision and `expected_identity`, validates one NFC, non-hidden, single-component leaf of at most 120 UTF-8 bytes with no separator, NUL, ASCII/Unicode control, bidi control, dot segment, or surrounding whitespace, probes it with `fstatat(..., AT_SYMLINK_NOFOLLOW)`, and on absence calls exactly `mkdirat(handle.root_fd, allowed_leaf, 0o700)`. It then revalidates the full chain, opens the created leaf with `O_DIRECTORY|O_NOFOLLOW`, verifies uid/device/inode/mode `0700`, fsyncs created directory and alias root, and emits one JSON receipt of at most 4 KiB containing only the frozen receipt fields. Close every retained/duplicate FD on every return/exception.

There is no list/read/move/delete/copy/process/network/attachment/capture operation, recursive mkdir, generic path resolver, `ToolExecutor` helper call, or automatic cleanup. On non-macOS the worker/runner returns `LOCAL_ACTION_UNSUPPORTED` before spawn.

- [ ] **Step 6: Write blocked-release, STOP/deadline, and uncertainty tests RED**

```python
async def test_runner_releases_only_after_active_effect_and_owned_pid_are_durable(runner):
    run = runner.start_paused(request=create_request(), activation=activation)
    self.assertFalse(run.worker.entered_descriptor_walk)
    self.assertEqual(durable_ownership(run.effect_id), {
        "pid": run.pid, "pgid": run.pgid,
        "startSec": run.start_sec, "startUsec": run.start_usec,
        "released": False,
    })
    run.allow_record_ownership_to_commit()
    await run.finished
    self.assertTrue(ownership_release_precedes_worker_entry(run.effect_id))

async def test_stop_wins_before_local_activation_and_child_never_walks(runner):
    intent = begin_local_alias_intent()
    blocked = runner.spawn_blocked(request=create_request(), intent=intent)
    permit = runner.assert_pre_activation_ready(intent=intent)
    gate.request_stop()
    with self.assertRaisesRegex(EffectGateConflict, "STOP_EPOCH_STALE"):
        gate.activate_local_alias_intent(
            intent.effect_id, approval=local_approval_receipt(),
            blocked_worker_permit=permit,
        )
    await runner.abort_blocked(intent=intent,
                               code="LOCAL_ACTION_CANCELLED_BY_STOP")
    self.assertEqual(local_action_state(intent.effect_id), "cancelled_by_stop")
    self.assertEqual(local_action_public_code(intent.effect_id),
                     "LOCAL_ACTION_CANCELLED_BY_STOP")
    self.assertFalse(worker_entered_descriptor_walk(blocked))

async def test_local_activation_wins_then_stop_keeps_capability_valid(runner):
    intent = begin_local_alias_intent()
    request = create_request()
    runner.spawn_blocked(request=request, intent=intent)
    permit = runner.assert_pre_activation_ready(intent=intent)
    activation = gate.activate_local_alias_intent(
        intent.effect_id, approval=local_approval_receipt(),
        blocked_worker_permit=permit,
    )
    stopping = gate.request_stop()
    gate.assert_activation(activation, owner_kind="local_alias_action",
                           category="filesystem", operation="create_directory")
    self.assertEqual(stopping.active_effect_count, 1)
    await runner.run(request=request, activation=activation)
    self.assertEqual(gate.settle_stop().state, "stopped")

async def test_storage_readiness_is_rechecked_at_all_worker_boundaries(self):
    blocked_states = ("required_storage_host_absent", "vault_detached",
                      "transition_active", "rollback_active",
                      "managed_start_lease_absent", "ownership_ignored",
                      "storage_image_identity_changed", "apfs_uuid_changed",
                      "contradictory_status")
    boundaries = ("before_spawn", "before_activation", "before_release")
    operations = ("verify_local_alias_access", "create_directory")
    for operation in operations:
        for state in blocked_states:
            for boundary in boundaries:
                with self.subTest(operation=operation, state=state,
                                  boundary=boundary):
                    harness = storage_boundary_harness(operation, state, boundary)
                    result = await harness.execute()
                    self.assertEqual(result.code, "STORAGE_NOT_READY")
                    self.assertEqual(harness.worker_release_count, 0)
                    self.assertEqual(harness.alias_walk_count, 0)
                    self.assertEqual(harness.mkdirat_calls, [])
                    self.assertTrue(harness.blocked_child_absent_or_reaped)
                    if boundary == "before_release" and operation == "verify_local_alias_access":
                        self.assertEqual(harness.effect_state, "failed")
                        self.assertEqual(harness.effect_error_code, "STORAGE_NOT_READY")
                        self.assertEqual(harness.access_observation_count, 0)
                    if boundary == "before_release" and operation == "create_directory":
                        self.assertEqual(harness.effect_state, "failed")
                        self.assertEqual(harness.local_action_state, "failed_safe")
                        self.assertEqual(harness.local_action_code, "STORAGE_NOT_READY")
    for operation in operations:
        with self.subTest(operation=operation, state="managed_no_required_marker"):
            harness = storage_boundary_harness(
                operation, "managed_no_required_marker", "all_ready")
            result = await harness.execute()
            self.assertNotEqual(result.code, "STORAGE_NOT_READY")
            self.assertEqual(harness.worker_release_count, 1)

async def test_pre_activation_permit_is_exact_single_use_and_cannot_ignore_ownership(self):
    for mutation in ("forged", "other_effect", "other_tuple", "other_ownership",
                     "stale_storage", "stale_protection", "stale_epoch",
                     "ownership_ignored", "replay"):
        with self.subTest(mutation=mutation):
            harness = blocked_activation_harness(mutation)
            with self.assertRaisesRegex(EffectGateConflict,
                                        "^EFFECT_CAPABILITY_INVALID$"):
                harness.activate()
            self.assertEqual(harness.active_effect_count, 0)
            self.assertEqual(harness.worker_release_count, 0)
```

Use barriers, not sleeps, at spawn, ownership commit, release, descriptor open, last absence check, entry into `mkdirat`, post-check, receipt write, terminal database write, pipe close, and reap. Parameterize STOP, `CancelledError`, exact 60-second timeout, stdin/control EOF, output EOF, malformed/oversize receipt, child exit, and simulated crash at every barrier. Assert exact PID/PGID/start ownership; TERM then KILL only after the fixed two-second TERM budget; all pipes/proof/root FDs closed; exact child reaped or the matching group proven absent; and no signal sent to a reused PID/start identity.

Expected mapping is exhaustive and exact: absent/invalid standard alias → `LOCAL_ALIAS_UNAVAILABLE`; changed device/inode/UID/type/symlink/catalog identity → `LOCAL_ALIAS_CHANGED`; `EPERM|EACCES` → terminal failed sensitive-read `LOCAL_ALIAS_PERMISSION_REQUIRED`; invalid leaf → `INVALID_LOCAL_LEAF`; unsupported platform/alias/operation/shape → `LOCAL_ACTION_UNSUPPORTED`; approval subject/digest/nonce/scope/epoch mismatch → `LOCAL_ACTION_APPROVAL_MISMATCH`; storage gate failure → `STORAGE_NOT_READY`; existing target of any type → `TARGET_ALREADY_EXISTS` with zero `mkdirat`. Access STOP/timeout/EOF/malformed/crash/cancel/unknown → terminal failed sensitive-read `LOCAL_ALIAS_ACCESS_UNCLEAR`, no observation, STOP may settle/reset. Write STOP before activation → `cancelled_by_stop/LOCAL_ACTION_CANCELLED_BY_STOP`, no descriptor walk or `mkdirat`; `STOP_EPOCH_STALE` remains internal and is never serialized by the local API. STOP after activation with no sufficient terminal receipt → `outcome_unclear/LOCAL_ACTION_OUTCOME_UNCLEAR` even when termination occurred before `mkdirat`; ordinary caller cancellation before entry into `mkdirat` may become `failed_safe` only after the same worker proves target absence. Any exception/cancel/timeout/EOF/malformed/crash after entry into `mkdirat` and before a durable terminal receipt → `outcome_unclear/LOCAL_ACTION_OUTCOME_UNCLEAR`, never replayed, reset blocked. A post-mkdir chain mismatch is always `outcome_unclear/LOCAL_ALIAS_CHANGED`, even though the retained old alias may contain the new leaf.

- [ ] **Step 7: Implement strict owned runner and startup reconciliation**

`spawn_blocked` accepts only a durable `EffectIntent` whose operation/digest matches the request. Immediately before any attestation or process creation it calls only `storage_contract.assert_runtime_ready()` and treats every non-`PASS/RUNTIME_READY` opaque result—including fixtures representing required-host absence, detached storage, transition, rollback, missing managed-start lease, ownership-ignored mount, storage-image identity change, APFS UUID change, or contradictory status—as `STORAGE_NOT_READY`. It never asks which vault fact caused the failure. It then resolves `LocalAliasProtectionFacts`, checks all three local protected-root relations, and revalidates every local server-source descriptor/digest before attestation. A managed local runtime with no required-storage marker remains admissible exactly as defined by the opaque status; only its non-authoritative committed local projection can add rejection roots. Only a ready and unchanged protection result permits attestation of the fixed installed worker/interpreter, bounded stdin/stdout and blocked control pipes, sanitized fixed-locale environment, and `posix_spawn` with `POSIX_SPAWN_SETPGROUP`, `closefrom`/explicit close actions, and only the required pipe FDs. The child cannot enter its request loop until one control byte arrives. Immediately after spawn, obtain macOS process start seconds/microseconds from `proc_pidinfo`, require `pgid == pid`, call `record_blocked_ownership` with exactly `pid`, `pgid`, `startSec`, `startUsec`, `released=false`, fsync that intent row, and return the opaque lease.

After ownership is durable, the caller must call `assert_pre_activation_ready(intent=intent) -> BlockedWorkerActivationPermit`. It accepts exactly `(direct_ui,sensitive_read,verify_local_alias_access)` or `(local_alias_action,filesystem,create_directory)`, performs a fresh opaque `StorageContract.assert_runtime_ready()`, re-resolves and revalidates the complete local `LocalAliasProtectionFacts` plus every named identity chain, verifies the blocked group against the exact durable ownership row, and only then asks the gate-private issuer for a single-use permit bound to the readiness/protection/ownership digests and current epoch. The access caller passes it to `activate_direct_intent(effect_id, blocked_worker_permit=permit)`; the create caller passes it to `activate_local_alias_intent(effect_id, approval=approval, blocked_worker_permit=permit)`. Either activation rejects an omitted, stale, forged, replayed or wrong ownership/effect/tuple permit with exactly internal `EFFECT_CAPABILITY_INVALID`. STOP and activation therefore serialize after owned PID persistence and the second readiness barrier.

`run` requires `deadline_seconds is 60`, finds the private blocked lease by `activation.effect_id`, calls `assert_activation` with exactly the same corresponding tuple, calls only opaque `StorageContract.assert_runtime_ready()` a third time immediately before release, and re-resolves/revalidates the same local protection-facts digest, ownership semantics and exact process identity. Only then may it update ownership to `released=true`, fsync it, and write one release byte. Any invalid permit/tuple is internal `EFFECT_CAPABILITY_INVALID`; readiness failure is `STORAGE_NOT_READY`; a changed local protected-root fact is `LOCAL_ALIAS_CHANGED`. Each pre-release failure produces zero alias walk/`mkdirat`. If the third readiness/protection barrier fails after activation but before release, shielded cleanup closes the release pipe and reaps the still-blocked child, then terminalizes the active effect as `failed` with `STORAGE_NOT_READY` for an opaque readiness contradiction or `LOCAL_ALIAS_CHANGED` for a local protected-root identity/digest change. The access path creates zero observation; the create path maps the receipt to `failed_safe` with the same public code, zero alias walk and zero `mkdirat`. If STOP wins before activation, `abort_blocked` closes the release writer, terminates/reaps the still-blocked group, and the externally visible local code is exactly `LOCAL_ACTION_CANCELLED_BY_STOP`; internal `STOP_EPOCH_STALE` and `EFFECT_CAPABILITY_INVALID` are never exposed on the local API. EOF before release likewise guarantees zero walk. The runner measures the single strict 60-second monotonic deadline from `spawn_blocked` through receipt validation, closes stdin after the one request, accepts exactly one bounded receipt, closes all pipes/proof FDs, waits/reaps the child, and terminalizes only after exit status and receipt agree.

STOP/cancel/error cleanup is shielded from cancellation: close the control writer, signal only an exact matching `(pid, pgid, startSec, startUsec)`, wait two seconds for TERM, KILL the same still-matching group if needed, close every FD, and reap. `reconcile_local_alias_effect(ownership, intent) -> ReconcileResult` reopens the exact catalog alias through the same worker. For an active write, an exact matching durable worker receipt and inode restores `created`; proven target absence restores `failed_safe`; an existing target without sufficient creator/inode proof or any unverifiable chain becomes `outcome_unclear`. It never retries `mkdirat` and never deletes. Active access checks reconcile only to failed `LOCAL_ALIAS_ACCESS_UNCLEAR` and create no observation.

- [ ] **Step 8: Run GREEN, prove lifecycle semantics, and commit**

Run: `"$PYTHON" tests/test_local_alias_worker.py -v && "$PYTHON" tests/test_local_alias_worker_runner.py -v && "$PYTHON" tests/test_installer.py -v && "$PYTHON" tests/test_effect_gate.py -v && "$PYTHON" tests/test_store_lifecycle.py -v`

Expected: PASS on macOS with exactly one fixture-root `mkdirat`, complete pre/post chain attestation, no real user-folder access, activation-before-STOP completing or becoming explicitly unclear, STOP-before-activation performing zero spawn/mutation, strict 60-second ownership cleanup, and restart never replaying or deleting an uncertain action.

```bash
git add executor/local_alias_worker.py executor/local_alias_worker_runner.py console/installer.py console/effect_gate.py orchestration/store.py tests/test_local_alias_worker.py tests/test_local_alias_worker_runner.py tests/test_installer.py tests/test_effect_gate.py tests/test_store_lifecycle.py
git commit -m "feat: add attested local alias action worker"
```

### Task 14: Enforce complete route/tool/transport/extension classification

**Files:**
- Modify: `console/effect_registry.py`
- Create: `tests/test_effect_gate_routes.py`
- Modify: `console/server.py`
- Modify: `tests/test_local_alias_worker_runner.py`

**Interfaces:**
- Consumes: FastAPI `app.routes`, `ToolExecutor`, `LocalAliasWorkerRunner`, storage-clamped `ChromeExtensionBrowserDriver`, backend `ALLOWED_ACTIONS`, and extension `ALLOWED_COMMANDS` source.
- Produces: `SURFACE_CLASSIFICATION` with one entry per checked surface and a failing oracle for any missing/duplicate entry.
- Test collection: create `tests/test_effect_gate_routes.py` with `import sys`, `import unittest`, class-based cases, and the exact global direct-execution guard before its first direct RED command.

- [ ] **Step 1: Write the four-way source inventory test**

```python
def test_every_surface_has_exactly_one_classification():
    discovered = [
        *(("http", name) for name in discover_mutating_or_sensitive_http_routes(app)),
        *(("tool_executor", name) for name in discover_public_tool_methods(ToolExecutor)),
        *(("browser_driver", name) for name in discover_browser_driver_methods(ChromeExtensionBrowserDriver)),
        *(("local_alias_worker", name) for name in discover_local_alias_worker_operations(LocalAliasWorkerRunner)),
        *(("extension_backend", name) for name in discover_backend_extension_actions(ALLOWED_ACTIONS)),
        *(("extension_javascript", name) for name in discover_js_extension_actions(SERVICE_WORKER_CORE)),
    ]
    registered = [(rule.origin, rule.name) for rule in SURFACE_CLASSIFICATION]
    discovered_counts = Counter(discovered)
    registered_counts = Counter(registered)
    self.assertEqual([item for item, count in discovered_counts.items() if count != 1], [])
    self.assertEqual([item for item, count in registered_counts.items() if count != 1], [])
    self.assertEqual(registered_counts, discovered_counts)
```

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_effect_gate_routes.py -v`

Expected: FAIL and print the exact currently unclassified routes/methods/actions.

- [ ] **Step 3: Fill the registry with explicit durable rules**

Each record is `SurfaceRule(origin, name, owner_kind, category, permit, operation, stop_rule)` and `(origin,name)` is its exact registry key. Classify mission mutators, direct attachment/capture staging, Settings/Onboarding/opt-in, browser control, sensitive capture, pure reads, STOP cleanup, durable bookkeeping, and disabled legacy endpoints. Add exactly `verify_local_alias_access -> direct_ui/sensitive_read` and `create_directory -> local_alias_action/filesystem`; require `SENSITIVE_READ_OPERATIONS == {verify_local_alias_access, capture_screenshot}` and reject any third sensitive-read operation. The local-alias worker is its own source inventory and must not be inferred from or added to the generic tool registry. Storage installer/cutover/import/rollback are explicitly `outside_mission_gate` and the test requires their exclusive storage-state contract; they never receive a mission effect token.

For HTTP, include POST/PUT mutation routes plus GET routes that can reach conditional browser control. A route classified `pure_read` is tested with spies proving zero file write, browser envelope, process creation, effect insert, and tab focus/create. New routes fail CI until classified.

- [ ] **Step 4: Check backend/extension equality**

Parse the JS `ALLOWED_COMMANDS` literal without executing the service worker. Compare ordered lists and `Counter((origin, action))` values for backend and JavaScript origins; reject duplicates in either source before comparing names. Then require those actions partition exactly into effect, conditional-read, pure-read, and STOP-cleanup lists with a `Counter` whose every value is one. No `set(...)` conversion may erase duplicate discoveries or registrations.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_effect_gate_routes.py -v`

Expected: PASS with zero missing, duplicate, or extra classification.

```bash
git add console/effect_registry.py tests/test_effect_gate_routes.py tests/test_local_alias_worker_runner.py console/server.py
git commit -m "test: require complete durable effect classification"
```

### Task 15: Disable legacy mutating task endpoints before body parsing

**Files:**
- Modify: `console/server.py`
- Modify: `tests/test_executor_runtime_truth.py`
- Modify: `tests/test_effect_gate_routes.py`

**Interfaces:**
- Consumes: `LEGACY_TASK_ENDPOINT_DISABLED` error code.
- Produces: raw-request tombstones for `POST /api/tasks` and `POST /api/tasks/{task_id}/orchestrator-reply`; read-only task history remains available.

- [ ] **Step 1: Write the body-shape and zero-side-effect matrix**

```python
class LegacyTaskTombstoneTest(unittest.TestCase):
    def test_legacy_posts_always_410_without_parsing_or_side_effect(self):
        cases = (
            ("/api/tasks", None, None),
            ("/api/tasks", b"{", "application/json"),
            ("/api/tasks", json.dumps({"unknown": True}).encode(), "application/json"),
            ("/api/tasks", json.dumps({"goal": "x"}).encode(), "application/json"),
            ("/api/tasks/missing/orchestrator-reply", None, None),
            ("/api/tasks/missing/orchestrator-reply", b"{", "application/json"),
            ("/api/tasks/known/orchestrator-reply", json.dumps({"text": "x"}).encode(), "application/json"),
        )
        before = task_store_snapshot()
        with mock.patch("server.run_task", create=True) as run_task, \
             mock.patch("executor.process_spawn.spawn_blocked") as process_spawn:
            for path, body, content_type in cases:
                with self.subTest(path=path, body=body):
                    headers = {"Content-Type": content_type} if content_type else {}
                    response = self.client.request("POST", path, content=body, headers=headers)
                    self.assertEqual(response.status_code, 410)
                    self.assertEqual(
                        response.json()["detail"]["code"],
                        "LEGACY_TASK_ENDPOINT_DISABLED",
                    )
        run_task.assert_not_called()
        process_spawn.assert_not_called()
        self.assertEqual(task_store_snapshot(), before)
```

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_executor_runtime_truth.py -v && "$PYTHON" tests/test_effect_gate_routes.py -v`

Expected: FAIL with 422/404/201 responses and current `run_task` reachability.

- [ ] **Step 3: Replace both handlers with raw `Request` tombstones**

```python
@app.post("/api/tasks", status_code=410)
async def create_task_disabled(request: Request) -> JSONResponse:
    del request
    return JSONResponse(status_code=410, content={
        "detail": {"code": LEGACY_TASK_ENDPOINT_DISABLED}
    })

@app.post("/api/tasks/{task_id}/orchestrator-reply", status_code=410)
async def orchestrator_reply_disabled(task_id: str, request: Request) -> JSONResponse:
    del task_id, request
    return JSONResponse(status_code=410, content={
        "detail": {"code": LEGACY_TASK_ENDPOINT_DISABLED}
    })
```

Do not declare `TaskIn`, `ReplyIn`, or any Pydantic body on these handlers. Remove `_run`, `TaskIn`, `ReplyIn`, and the product import of `run_task` from `console/server.py`. Leave `console/local_executor.py` unchanged as historical/development code; the source-graph test requires no product router or server callable to import or invoke it.

- [ ] **Step 4: Prove malformed bodies never reach validation**

Inspect OpenAPI: both POST routes have no `requestBody`. Verify background task count, process spy, filesystem inventory, SQLite rows, and `_iterations` bytes are unchanged for every matrix entry.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_executor_runtime_truth.py -v && "$PYTHON" tests/test_effect_gate_routes.py -v`

Expected: PASS with 410 for every body/ID variant and zero local mutation.

```bash
git add console/server.py tests/test_executor_runtime_truth.py tests/test_effect_gate_routes.py
git commit -m "fix: tombstone legacy task mutation endpoints"
```

### Task 16: Reconcile active effects before startup/resume and make STOP status durable

**Files:**
- Modify: `console/server.py`
- Modify: `console/missions.py`
- Modify: `console/chat.py`
- Modify: `executor/local_alias_worker_runner.py`
- Modify: `orchestration/store.py`
- Modify: `tests/test_missions_api.py`
- Modify: `tests/test_direct_effect_recovery.py`
- Modify: `tests/test_store_lifecycle.py`
- Modify: `tests/test_local_alias_worker_runner.py`

**Interfaces:**
- Consumes: all category/operation reconcilers, `EffectGate.reconcile_startup`, process/browser uncertainty rules, and `reconcile_local_alias_effect`.
- Produces: stable `/api/transport/status`, durable `/stop-everything`, exact `/stop-reset`, and startup barrier.

- [ ] **Step 1: Write startup and STOP/reset sequence RED tests**

```python
async def test_startup_reconciles_before_mission_resume_or_route_readiness(client_factory):
    seed_active_local_alias_effect()
    client = await client_factory(paused_before_lifespan=True)
    assert not client.bound
    release_reconciler()
    assert (await client.get("/api/transport/status")).status_code == 200
    assert reconciliation_finished_before_bind()

async def test_stop_active_concurrent_reset_refusal_then_fresh_epoch():
    active = activate_owned_process()
    stopping = await post_stop()
    refused = await post_reset({"expectedEpoch": stopping["epoch"]})
    assert refused.status_code == 409
    terminate_and_reconcile(active)
    assert gate.settle_stop().state == "stopped"
    reset = await post_reset({"expectedEpoch": stopping["epoch"]})
    assert reset.json()["epoch"] == stopping["epoch"] + 1
```

- [ ] **Step 2: Run RED**

Run: `"$PYTHON" tests/test_missions_api.py -v && "$PYTHON" tests/test_direct_effect_recovery.py -v && "$PYTHON" tests/test_store_lifecycle.py -v`

Expected: FAIL because `_global_stop` is process memory, reset is unconditional, and lifespan does not reconcile effects.

- [ ] **Step 3: Put reconciliation before runtime initialization and bind**

In FastAPI lifespan, after storage/managed-start gates but before `_initialize_runtime` or `yield`, open Store, build `EffectGate`, and reconcile every `active` effect with an exact category/operation reconciler. Unknown operation/category is `outcome_unclear`. Mission resume and recovered chat-run restoration remain blocked until reconciliation finishes. Intent-only effects cancel safely without touching disk; browser active after dispatch becomes uncertain; move/process/filesystem use recorded identities. An active `local_alias_action/filesystem/create_directory` invokes only `reconcile_local_alias_effect`: matching terminal receipt plus inode may restore `created`, worker-proven absence becomes `failed_safe`, and existing/unverifiable target becomes `outcome_unclear`; it never invokes `mkdirat` or deletion. An active `direct_ui/sensitive_read/verify_local_alias_access` becomes failed `LOCAL_ALIAS_ACCESS_UNCLEAR` with no observation and does not block reset.

- [ ] **Step 4: Replace process memory STOP with stable API contracts**

`GET /api/transport/status` merges warning/opt-in with `StopStatus.to_public()`. `POST /api/transport/stop-everything` calls `request_stop`, cancels pending waits, uses cleanup permits for `press_stop`/`release_session`, terminates owned process groups, reconciles them, calls `settle_stop`, and returns the stable status plus `missionsStopped`. It may return `stopping`; it never reports stopped while owned effects remain.

`POST /api/transport/stop-reset` uses:

```python
class StopResetIn(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")
    expected_epoch: int = Field(ge=0)
```

It calls only `gate.reset_stop(expected_epoch=body.expected_epoch)`. Concurrent/stale/reset-with-active/reset-with-unclear returns 409 with the stable error code and current status.

- [ ] **Step 5: Run GREEN and commit**

Run: `"$PYTHON" tests/test_missions_api.py -v && "$PYTHON" tests/test_direct_effect_recovery.py -v && "$PYTHON" tests/test_store_lifecycle.py -v`

Expected: PASS for `inactive -> stopping -> stopped -> resetting -> inactive`, with epoch increments at STOP and reset and no stale approval surviving restart.

```bash
git add console/server.py console/missions.py console/chat.py executor/local_alias_worker_runner.py orchestration/store.py tests/test_missions_api.py tests/test_direct_effect_recovery.py tests/test_store_lifecycle.py tests/test_local_alias_worker_runner.py
git commit -m "feat: reconcile durable effects before runtime startup"
```

### Task 17: Run deterministic acceptance races and the full focused suite

**Files:**
- Modify: `tests/test_effect_gate.py`
- Modify: `tests/test_effect_gate_routes.py`
- Modify: `tests/test_direct_effect_recovery.py`
- Modify: `tests/test_loop_mock.py`
- Modify: `tests/test_executor_tools.py`
- Modify: `tests/test_process_ownership.py`
- Modify: `tests/test_local_alias_worker.py`
- Modify: `tests/test_local_alias_worker_runner.py`
- Modify: `tests/test_chrome_extension_bridge.py`
- Modify: `tests/test_chrome_extension_driver.py`
- Create: `tests/test_durable_effects_gate.py`
- Modify: `scripts/test-all.sh`

**Interfaces:**
- Consumes: all preceding contracts.
- Produces: deterministic evidence for approval A/B, approval→STOP→dispatch, browser uncertainty, move boundaries, process/local-alias cancellation, stale approvals, local-alias chain races, STOP/reset quiescence, and a stdlib-unittest aggregate collection oracle.
- Test collection: create `tests/test_durable_effects_gate.py` with `import sys`, `import unittest`, class-based cases, and the exact global direct-execution guard before Step 2; the oracle below rejects missing guards in every new directly executed durable test file.

- [ ] **Step 1: Add the complete race matrix**

Create the following real direct-script gate; every referenced file must be loadable by `unittest`, collect at least one case, and be named by the aggregate runner:

```python
def iter_unittest_cases(suite: unittest.TestSuite) -> Iterator[unittest.TestCase]:
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from iter_unittest_cases(item)
        else:
            yield item

class DurableEffectsGateTest(unittest.TestCase):
    REQUIRED_TEST_FILES = (
        "test_effect_gate.py", "test_effect_gate_routes.py",
        "test_direct_effect_recovery.py", "test_executor_tools.py",
        "test_process_ownership.py", "test_local_alias_worker.py",
        "test_local_alias_worker_runner.py", "test_chrome_extension_bridge.py",
        "test_chrome_extension_driver.py", "test_durable_effects_gate.py",
    )
    NEW_DIRECT_TEST_FILES = (
        "test_effect_gate.py", "test_direct_effect_recovery.py",
        "test_local_alias_worker.py", "test_local_alias_worker_runner.py",
        "test_effect_gate_routes.py", "test_durable_effects_gate.py",
    )
    DIRECT_GUARD = """if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    count = suite.countTestCases()
    if count <= 0:
        raise SystemExit(2)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)"""

    def test_aggregate_runner_collects_every_durable_suite(self):
        script = Path("scripts/test-all.sh").read_text(encoding="utf-8")
        for filename in self.REQUIRED_TEST_FILES:
            with self.subTest(filename=filename):
                suite = unittest.defaultTestLoader.discover("tests", pattern=filename)
                cases = tuple(iter_unittest_cases(suite))
                self.assertGreater(len(cases), 0)
                self.assertNotIn("_FailedTest",
                                 {type(case).__name__ for case in cases})
                self.assertIn(f"tests/{filename}", script)

    def test_every_new_direct_test_has_exact_nonzero_guard(self):
        for filename in self.NEW_DIRECT_TEST_FILES:
            with self.subTest(filename=filename):
                source = (Path("tests") / filename).read_text(encoding="utf-8")
                self.assertTrue(source.rstrip().endswith(self.DIRECT_GUARD))

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    count = suite.countTestCases()
    if count <= 0:
        raise SystemExit(2)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
```

Use barriers rather than sleeps for:

```text
approval A delayed into action B -> APPROVAL_MISMATCH, no B activation
approval accepted -> STOP commits -> dispatch attempt -> STOP_EPOCH_STALE
browser intent -> envelope sent -> crash -> BROWSER_DELIVERY_UNCERTAIN, one envelope
move intent -> each rename/fsync/receipt boundary -> exact three-way reconcile
process blocked child -> CancelledError -> group verified gone
restart -> stale pending/approved approval invalidated
STOP active -> concurrent reset refused -> quiescence -> reset -> fresh action only
direct intent -> STOP before activation -> zero temporary opens
local alias intent -> blocked PID durable -> STOP before activation -> cancelled_by_stop, zero descriptor walk/mkdirat
local alias active -> STOP -> capability remains valid until terminal/unclear; STOP settles, reset waits on unclear
blocked worker activation -> permit omitted/forged/replayed/wrong ownership/storage/protection/epoch -> no activation or release
storage/protection loss after activation before release -> active effect failed, access observation zero, create failed_safe, zero walk/mkdirat
local alias vs each forbidden root -> equal/descendant/authority-ancestor plus identity race at spawn/preactivation/release -> rejected and reaped
local alias chain edge changes before mkdirat -> failed_safe, zero mkdirat
local alias chain edge changes after mkdirat -> LOCAL_ALIAS_CHANGED/outcome_unclear, no replay/delete
local alias child -> timeout/EOF/crash/cancel at each boundary -> exact close/reap and required terminal mapping
```

- [ ] **Step 2: Run the aggregate selector and verify deterministic RED**

Run: `"$PYTHON" tests/test_durable_effects_gate.py`

Expected: FAIL with an `assertIn` naming the first focused suite absent from `scripts/test-all.sh`; collection error, zero collected cases, skip, timeout, or an unrelated failure does not satisfy RED.

- [ ] **Step 3: Wire the exact focused suites into the aggregate runner**

Add each literal path represented by `REQUIRED_TEST_FILES` to `scripts/test-all.sh` as the corresponding independent `"$PYTHON" tests/test_effect_gate.py`, `"$PYTHON" tests/test_effect_gate_routes.py`, `"$PYTHON" tests/test_direct_effect_recovery.py`, `"$PYTHON" tests/test_executor_tools.py`, `"$PYTHON" tests/test_process_ownership.py`, `"$PYTHON" tests/test_local_alias_worker.py`, `"$PYTHON" tests/test_local_alias_worker_runner.py`, `"$PYTHON" tests/test_chrome_extension_bridge.py`, `"$PYTHON" tests/test_chrome_extension_driver.py`, and `"$PYTHON" tests/test_durable_effects_gate.py` command after the equipped-interpreter preflight and before the full backend gate. Preserve `set -e`, reject any zero-count/skip signal through `test_durable_effects_gate.py`, and add no pytest dependency or invocation.

- [ ] **Step 4: After Tasks 1-16, run each focused command independently and verify GREEN**

```bash
"$PYTHON" tests/test_executor_tools.py
"$PYTHON" tests/test_command_policy_fuzz.py
"$PYTHON" tests/test_protocol_report_fuzz.py
"$PYTHON" tests/test_protocol_state_store.py
"$PYTHON" tests/test_store_lifecycle.py
"$PYTHON" tests/test_loop_mock.py
"$PYTHON" tests/test_runner_mode_a.py
"$PYTHON" tests/test_process_policy.py
"$PYTHON" tests/test_process_ownership.py
"$PYTHON" tests/test_local_alias_worker.py
"$PYTHON" tests/test_local_alias_worker_runner.py
"$PYTHON" tests/test_missions_api.py
"$PYTHON" tests/test_effect_gate.py
"$PYTHON" tests/test_effect_gate_routes.py
"$PYTHON" tests/test_direct_effect_recovery.py
"$PYTHON" tests/test_chat_settings_api.py
"$PYTHON" tests/test_attachment_boundaries.py
"$PYTHON" tests/test_workspace_handle.py
"$PYTHON" tests/test_workspace_path_fuzzing.py
node --test chrome-extension/tests/extension.test.mjs
"$PYTHON" tests/test_chrome_extension_bridge.py
"$PYTHON" tests/test_chrome_extension_driver.py
"$PYTHON" tests/test_transport_session_isolation.py
"$PYTHON" tests/test_durable_effects_gate.py
```

Expected: every command selects tests and passes with zero required skip; no SecurityAgent, Chrome control, runtime bind, or external workspace mutation occurs.

- [ ] **Step 5: Run static source guards**

Run:

```bash
! rg -n 'Path\.resolve\(|os\.walk\(|\.rglob\(|cwd=str\(' executor
! rg -n 'pendingCapture|chrome\.action\.onClicked.*capture|ALLOWED_TOOLS_CSV' chrome-extension orchestration executor console
! rg -n 'asyncio\.create_subprocess_exec' executor/tools.py
! rg -n 'ToolExecutor|WorkspaceHandle|MissionLoop' executor/local_alias_worker.py executor/local_alias_worker_runner.py
! rg -n 'StorageBinding|storage_contract\.open\(|open_workspace\(|storage_contract\.revalidate\(|mount_fd|apfs_volume_uuid|vault_root' executor/local_alias_worker.py executor/local_alias_worker_runner.py
rg -n 'Desktop|Documents|Downloads' tests/test_local_alias_worker.py tests/test_local_alias_worker_runner.py
```

Expected: zero matches in executor production code for path reopen/process fallback; zero `pendingCapture` or duplicate tool allowlist; toolbar handler contains no capture call; zero executor/workspace/mission crossing from the local worker modules; zero storage binding/open/revalidate, mount FD, APFS UUID, or vault-root authority in either local worker module. The user-folder-name grep may match only enum/assertion text and must be paired with the fixture audit proving every opened root is below the temporary test directory; no test may resolve or open the live user's aliases. Test fixtures may mention other forbidden strings only in explicit negative assertions.

- [ ] **Step 6: Run the full repository gate**

Run: `PYTHON="$PYTHON" scripts/test-all.sh`

Expected: backend, extension, frontend unit/coverage/typecheck/lint/build/E2E/accessibility/runtime/privacy/release suites pass with no frontend-skip message and no test added by this plan skipped.

- [ ] **Step 7: Review and commit only test closure**

Run: `git diff --check && git status --short`

Expected: clean whitespace check; only intended implementation/test files are changed; no QA evidence, runtime database, attachment, compiled binary, or Chrome state is tracked.

```bash
git add tests/test_effect_gate.py tests/test_effect_gate_routes.py tests/test_direct_effect_recovery.py tests/test_loop_mock.py tests/test_executor_tools.py tests/test_process_ownership.py tests/test_local_alias_worker.py tests/test_local_alias_worker_runner.py tests/test_chrome_extension_bridge.py tests/test_chrome_extension_driver.py tests/test_durable_effects_gate.py scripts/test-all.sh
git commit -m "test: close durable effect race coverage"
```

## Execution handoff

The implementation order is fixed: Tasks 1-3 establish durable authorization; Tasks 4-7 replace executor path/process behavior; Tasks 8-12 gate direct/admin/browser surfaces; Task 13 installs and confines the separate local-alias execution class; Tasks 14-16 close inventories, legacy entry points, startup, and STOP/reset; Task 17 is the deterministic/full verification gate. The UI/intent plan consumes the frozen HTTP contracts and runner interfaces in this document and must not redefine effect states, digest rules, approval fields, STOP transitions, worker ownership, reconciliation, or retry semantics. The live-QA plan may execute T12-T18 only after Task 17 passes and after the owner separately approves the exact synthetic payloads and browser/filesystem effects.
