# S3 Owned-Process Supervision Implementation Plan

> **For implementation workers:** Execute tasks in order. For every production
> behavior, write and run the named RED test before changing production code,
> then run the same selection GREEN. A skip, empty selection, or non-PASS
> unittest outcome is a failed gate.

**Goal:** Create, integrate, package, and prove a persistent Swift storage
broker so Python never owns or signals an `hdiutil`/`diskutil` child and durable
recovery never invents cleanup or closure.

**Architecture:** One isolated broker owns each serialized storage workflow.
Python admits the request under the storage lock, attests the installed broker
through an open FD, writes the five-state ledger, and communicates through a
private authenticated socket. The broker alone performs native spawn, identity,
signal, wait, reap, secret delivery, and detach attestation. It retains terminal
proof until Python acknowledges a closed ledger record after fsync.

**Tech stack:** Swift 6, Darwin, Foundation, Security.framework; Python 3.11 and
3.14 standard library; Bash; `unittest`; setuptools.

**Spec:** `docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md`

## Execution contract

- The broker and client do not exist in the installed product at plan start.
  They must be created and wired into product façades; test compilation of the
  current disk helper is not an installed route.
- This plan supersedes the one-shot disk-helper portions of
  `2026-09-02-v054-storage-runtime-foundation.md`. Execute S3 before that plan's
  lifecycle, operator-CLI, and runtime start/stop consumers. Preserve its public
  request/response and storage-lock interfaces.
- Python may supervise the broker PID. It never receives or infers a native
  child PID/PGID and never calls signal/wait for one.
- Default tests are no-effect. macOS synthetic tests may spawn synthetic
  children and local sockets, but may not invoke real Keychain, `hdiutil`, or
  `diskutil` effects.
- Live tests stay outside default discovery, require the exact action-time gate,
  use disposable synthetic data, and never substitute for hermetic or macOS
  synthetic proof.
- No source-token grep, static scenario inventory, or hand-maintained total is an
  acceptance proof. Runtime mutations exercise real decoders and transitions.
- Install lock precedes storage lock. Preserve unrelated changes and stop on the
  first failed gate.

Before each task, establish distinct interpreters:

```bash
PYTHON311="$(command -v python3.11)"
PYTHON314="$(command -v python3.14)"
test -x "$PYTHON311"
test -x "$PYTHON314"
test "$PYTHON311" != "$PYTHON314"
REPO_ROOT="$(git rev-parse --show-toplevel)"
SOURCE_ROOT="$REPO_ROOT/console:$REPO_ROOT"
```

Every source-tree Python command below is executed with
`PYTHONPATH="$SOURCE_ROOT"`; omission is a command error. Installed-wheel and
installed-app tests explicitly clear `PYTHONPATH`, make the checkout
inaccessible, and seed a homonymous module sentinel that must not be imported.

## File map

| Path | Action | Responsibility |
| --- | --- | --- |
| `native/macos/disk_image_keychain.swift` | Modify | Production broker, protocol, native ownership, secret handling, detach attestation; test routes compile only in the test profile |
| `console/storage_broker.py` | Create | Canonical codec, public client, private probe, ledger, recovery |
| `console/storage_reconciliation.py` | Create | Sole reconciliation record/probe/postcondition schema and CAS implementation |
| `console/native_helpers.py` | Foundation Task 4 creates | S3 Task 7 completes the same atomic installed broker/probe registry and FD-held attestation unit |
| `console/installed_storage_runtime.py` | Create | Deferred Task 7 lock-bound installed-generation aggregate factory |
| `console/storage_lifecycle.py` | Foundation Task 5 creates | Seven lock-carrying descriptor-first methods; S3 Task 6 only gates them |
| `console/storage_transition.py`, `console/storage_contract.py` | Foundation Tasks 6/7 create | Product journal and APFS/encryption proofs with injected backends; S3 Task 6 only gates them |
| `console/cortex_paths.py` | Foundation Task 5 modifies | Installed topology paths |
| `console/startup_lease.py` | Foundation Task 13 creates | Startup capability and lease |
| `console/server.py` | Foundation Task 13 modifies | Lifespan integration |
| `console/storage_guard.py` | Foundation Task 7 modifies | Private locked mounted-image probe only |
| `console/installer.py` | Modify | Build, publish, manifest, update/reinstall refusal, Doctor, uninstall |
| `native/build-profiles/macos-ax-send-v1.json` | Foundation Task 4 creates | Canonical AX helper production build profile in the Task 7 atomic unit |
| `native/build-profiles/storage-mount-probe-v1.json` | Foundation Task 4 creates | Canonical descriptor-probe production build profile in the Task 7 atomic unit |
| `native/build-profiles/storage-broker-v1.json` | Foundation Task 4 creates | Canonical broker production build profile without test routes in the Task 7 atomic unit |
| `scripts/cortex-storage.py` | Foundation Task 11 creates | Operator façade over `StorageLifecycle`; redacted unresolved status |
| `scripts/check-cortex-storage.py` | Foundation Task 7 modifies | Guard wrapper over injected contract until Task 7 installs the aggregate |
| `scripts/cortex.sh` | Foundation Tasks 12/13 then install unit modify | Recovery admission plus lifecycle mount/start and stop/detach |
| `scripts/start-local.sh` | Foundation Task 12 modifies | Delegate to `cortex.sh start` |
| `scripts/configure-external-storage.py` | Foundation Task 11 modifies | Compatibility wrapper over lifecycle/transition only |
| `scripts/run-storage-supervision-matrix.py` | Create | Criteria-aware executed-test runner and renderers |
| `scripts/test-all.sh` | Modify | Hermetic dual-Python gate |
| `scripts/verify-release-evidence.py` | Modify | S3 artifact and criteria validation |
| `pyproject.toml` | Modify | Package client, lifecycle, attestation module, Swift source, and schemas |
| `tests/fixtures/storage_protocol_v1_vectors.json` | Create | Shared canonical codec/hash vectors |
| `tests/storage_supervision_criteria.json` | Create | Versioned criteria registry independent of test count |
| `tests/storage_supervision_modules.json` | Create | Versioned, hashed production module inventory |
| `tests/test_disk_image_keychain_helper.py` | Modify | Swift broker protocol/native/secret/detach and gated live tests |
| `tests/test_storage_broker.py` | Create | Python codec/client/ledger/recovery tests |
| `tests/test_storage_reconciliation.py` | Create | Closed reconciliation union, terminal-broker probe, CAS, ACK, and crash tests |
| `tests/test_storage_lifecycle.py` | Foundation Task 5 creates | Seven locked façade routes |
| `tests/test_storage_cli.py` | Foundation Task 11 creates | Operator CLI delegation and manual-block behavior |
| `tests/test_storage_guard.py` | Foundation Task 7 modifies | Private locked probe integration |
| `tests/test_storage_guard_integration.py` | Foundation Tasks 7/12/13 modify | Startup guard product route |
| `tests/test_process_ownership.py` | Foundation Task 13 modifies | Shell admission and no native signal/wait boundary |
| `tests/test_start_local.py` | Foundation Tasks 12/13 modify | Start/stop lifecycle delegation |
| `tests/test_storage_transition.py`, `tests/test_storage_contract.py`, `tests/test_cortex_paths.py`, `tests/test_startup_lease.py` | Foundation creates | Product-journal, identity, installed-path, lease, and crash-window reconciliation |
| `tests/test_storage_import.py`, `tests/test_storage_runtime_ready.py`, `tests/test_workspace_handle.py` | Foundation creates | Import, readiness, and vault-handle focused coverage |
| `tests/test_store_lifecycle.py` | Foundation Task 13 modifies | Server/store lifecycle integration |
| `tests/test_installer.py` | Modify | Build/publish/update/Doctor/uninstall ownership |
| `tests/test_installed_storage_wheel.py` | Create | Installed binary/client/provenance and no-test-route proof |
| `tests/test_installed_storage_runtime.py` | Create | Same-generation broker/probe/lifecycle/contract aggregate and lock binding |
| `tests/test_storage_supervision_matrix.py` | Create | Criteria selection, status handling, determinism |
| `tests/test_public_privacy.py` | Modify | JSON/Markdown redaction and comparison tables |
| `tests/test_release_manifest.py` | Modify | Hash-bound release contract |
| `tests/test_ci_contract.py`, `.github/workflows/ci.yml` | Modify | Atomic dual-Python CI migration |
| `tests/storage_dual_python_active_paths.json` | Create | Hash-bound active scan paths and exact frozen-document exclusions |
| `README.md` | Modify | Canonical dual-Python command |
| `console/README.md`, `CONTRIBUTING.md`, `docs/agent-installation.md` | Modify | Remove mono-Python gate instructions or emit the migration error |
| `docs/testing.md` | Modify | Evidence tiers, gates, and interpretation |
| `docs/verification/v0.5.4-storage-supervision-receipt.json` | Create | Canonical per-test event receipt |
| `docs/verification/v0.5.4-storage-supervision.json` | Create | Canonical public evidence |
| `docs/verification/v0.5.4-storage-supervision.md` | Create | Deterministic public comparison/test tables |

## Exact interfaces

`console/storage_broker.py` exports only the public types and methods below.
The leading-underscore probe types remain module-private.
`StorageLockSet` is the sole three-lock bundle from
`console.storage_lock.ordered_storage_locks`; the client accepts an already
owned bundle and never constructs or nests one.

```python
class LedgerState(StrEnum):
    OPEN_PREPARED = "OPEN_PREPARED"
    OPEN_RUNNING = "OPEN_RUNNING"
    OPEN_UNRESOLVED = "OPEN_UNRESOLVED"
    CLOSED_SUCCESS = "CLOSED_SUCCESS"
    CLOSED_FAILURE = "CLOSED_FAILURE"

PublicStorageOperation = Literal[
    "create", "mount", "detach", "inspect-item",
    "delete-disposable-item",
]

class UnresolvedReason(StrEnum):
    CHANNEL_LOST = "CHANNEL_LOST"
    BROKER_LOST = "BROKER_LOST"
    BOOT_MISMATCH = "BOOT_MISMATCH"
    ECHILD = "ECHILD"
    IDENTITY_UNCERTAIN = "IDENTITY_UNCERTAIN"
    WAITABILITY_LOST = "WAITABILITY_LOST"
    TERMINAL_AMBIGUOUS = "TERMINAL_AMBIGUOUS"
    GROUP_PRESENT = "GROUP_PRESENT"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"

@dataclass(frozen=True, slots=True)
class BootIdentity:
    seconds: int
    microseconds: int

DarwinU32 = NewType("DarwinU32", int)

@dataclass(slots=True)
class AttestedBrokerExecutable:
    path: Path
    fd: int
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: int
    sha256: str
    build_profile_sha256: str
    def close(self) -> None: ...

@dataclass(slots=True)
class AttestedMountProbe:
    path: Path
    fd: int
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: Literal[448]
    sha256: str
    build_profile_sha256: str
    def close(self) -> None: ...

@dataclass(frozen=True, slots=True)
class BrokerSocketIdentity:
    path: Path
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: int

class NativeHelperManifestRecord(TypedDict):
    target: str
    source: str
    source_sha256: str
    build_profile_sha256: str
    sha256: str
    cdhash: str
    dev_u32: DarwinU32
    ino: int
    uid: int
    mode: Literal[448]

class InstalledStorageRuntimeGeneration(TypedDict):
    schema_version: Literal[1]
    generation_id: UUID
    python_tree_sha256: str
    scripts_tree_sha256: str
    native_sources_tree_sha256: str
    build_profiles_tree_sha256: str
    extension_tree_sha256: str
    interpreter_sha256: str
    interpreter_dev_u32: DarwinU32
    interpreter_ino: int
    interpreter_uid: int
    interpreter_mode: int
    native_helpers: Mapping[str, NativeHelperManifestRecord]
    owned_manifest_sha256: str
    generation_record_sha256: str

@dataclass(frozen=True, slots=True)
class _StorageBrokerRequest:
    schema_version: Literal[1]
    operation: PublicStorageOperation
    image_path: Path
    mount_path: Path | None
    volume_name: str | None
    size: str | None
    transaction_id: UUID
    expected_encryption_uuid: str | None
    disposable: bool
    cleanup_approved: bool

@dataclass(frozen=True, slots=True)
class _BrokerProbeRequest:
    schema_version: Literal[1]
    operation: Literal["probe-mounted-image"]
    transaction_id: UUID
    image_path: Path
    mount_path: Path
    expected_volume_name: str
    expected_volume_uuid: UUID
    expected_encryption_uuid: UUID
    image_identity: tuple[DarwinU32, int]
    mount_identity: tuple[DarwinU32, int, DarwinU32, DarwinU32]
    expected_mapping_count: Literal[1]

StorageLocalCode = Literal[
    "OK", "INVALID_REQUEST", "CLEANUP_NOT_AUTHORIZED",
    "RANDOM_GENERATION_FAILED", "HDIUTIL_FAILED",
    "IMAGE_ENCRYPTION_INVALID", "KEYCHAIN_ITEM_COLLISION",
    "KEYCHAIN_ITEM_NOT_FOUND", "KEYCHAIN_ITEM_AMBIGUOUS",
    "KEYCHAIN_INTERACTION_FORBIDDEN", "KEYCHAIN_SECRET_INVALID",
    "KEYCHAIN_FAILED", "MOUNT_MAPPING_INVALID", "MOUNT_CLEANUP_UNCLEAR",
    "SUPERVISION_UNRESOLVED", "CANCELLED", "INTERNAL_ERROR",
]

@dataclass(frozen=True, slots=True)
class StorageLocalResponse:
    schema_version: Literal[1]
    operation: PublicStorageOperation
    code: StorageLocalCode
    encryption_uuid: str | None
    device: str | None
    item_count: int | None

@dataclass(frozen=True, slots=True)
class StorageEvidenceResponse:
    schema_version: Literal[1]
    operation: PublicStorageOperation
    code: StorageLocalCode
    item_count: int | None

def to_storage_evidence_response(
    response: StorageLocalResponse,
) -> StorageEvidenceResponse: ...

@dataclass(frozen=True, slots=True)
class StorageBrokerResult:
    workflow_id: UUID
    generation: int
    state: LedgerState
    response: "BrokerTerminalResponse | None"
    result_sha256: str
    closed_ready_sha256: str | None
    child_reaped: bool
    group_absent: bool
    native_cleanup_proven: bool

@dataclass(frozen=True, slots=True)
class MountedImageProof:
    mount_path: Path
    image_dev_u32: DarwinU32
    image_ino: int
    mount_dev_u32: DarwinU32
    mount_ino: int
    mount_fsid0_u32: DarwinU32
    mount_fsid1_u32: DarwinU32
    volume_name: str
    volume_uuid: UUID
    encryption_uuid: UUID
    mapping_count: Literal[1]
    filesystem_type: Literal["apfs"]
    writable: Literal[True]
    encrypted: Literal[True]
    request_sha256: str

class LocalBrokerTerminalResponse(TypedDict):
    response_kind: Literal["local"]
    response: StorageLocalResponse

class MountedProofBrokerTerminalResponse(TypedDict):
    response_kind: Literal["mounted_image_proof"]
    response: MountedImageProof

BrokerTerminalResponse = (
    LocalBrokerTerminalResponse | MountedProofBrokerTerminalResponse
)

@dataclass(frozen=True, slots=True)
class StorageWorkflowRecord:
    schema_version: Literal[1]
    state: LedgerState
    workflow_id: UUID
    generation: int
    operation: PublicStorageOperation | Literal["probe-mounted-image"]
    transaction_id: UUID
    canonical_request: Mapping[str, object]
    request_sha256: str
    broker_sha256: str
    broker_dev_u32: DarwinU32
    broker_ino: int
    broker_uid: int
    broker_mode: int
    broker_pid: int | None
    broker_sid: int | None
    broker_pgid: int | None
    socket: BrokerSocketIdentity
    boot: BootIdentity
    effect_budget_ns: int
    cleanup_budget_ns: int
    started_monotonic_ns: int | None
    command_sha256: str | None
    unresolved_reason: UnresolvedReason | None
    result_sha256: str | None
    closed_ready_sha256: str | None
    child_reaped: bool
    group_absent: bool
    native_cleanup_proven: bool
    terminal_outcome: Literal["success", "failure", "unresolved"] | None
    terminal_code: StorageLocalCode | None
    terminal_response: BrokerTerminalResponse | None
    reconciliation_required: bool
    record_sha256: str

class StorageWorkflowLedger:
    def prepare(self, request: _StorageBrokerRequest | _BrokerProbeRequest,
                executable: AttestedBrokerExecutable,
                socket: BrokerSocketIdentity, boot: BootIdentity,
                *, effect_budget_ns: int,
                cleanup_budget_ns: int) -> StorageWorkflowRecord: ...
    def mark_running_before_start(self, workflow_id: UUID, generation: int,
                                  *, broker_pid: int, broker_sid: int,
                                  broker_pgid: int) -> StorageWorkflowRecord: ...
    def close_preexec_failure(self, workflow_id: UUID,
                              generation: int) -> StorageWorkflowRecord: ...
    def mark_unresolved(self, workflow_id: UUID, generation: int,
                        reason: UnresolvedReason) -> StorageWorkflowRecord: ...
    def close_from_ready(self, result: StorageBrokerResult) -> StorageWorkflowRecord: ...
    def load_all(self) -> tuple[StorageWorkflowRecord, ...]: ...

# console/storage_reconciliation.py is the sole owner of all reconciliation
# schemas. storage_broker and storage_transition import them; neither redeclares
# or serializes a parallel shape.
class ReconciliationState(StrEnum):
    PENDING = "pending"
    RECONCILED = "reconciled"
    UNCLEAR = "unclear"

class CreatePostcondition(TypedDict):
    kind: Literal["create"]
    disposition: Literal["absent", "present_consistent"]
    image_present: bool
    image_identity_sha256: str | None
    keychain_item_count: Literal[0, 1]
    encryption_uuid: str | None

class MountPostcondition(TypedDict):
    kind: Literal["mount"]
    disposition: Literal["absent", "exact_mapping"]
    mapping_count: Literal[0, 1]
    mount_empty: bool
    mounted_image_proof_sha256: str | None

class DetachPostcondition(TypedDict):
    kind: Literal["detach"]
    mapping_count: Literal[0]
    mount_empty: Literal[True]

class InspectItemPostcondition(TypedDict):
    kind: Literal["inspect_item"]
    item_count: Literal[0, 1]

class DeleteItemPostcondition(TypedDict):
    kind: Literal["delete_disposable_item"]
    item_count: Literal[0]
    transaction_match: Literal[True]

class MountedImageProbePostcondition(TypedDict):
    kind: Literal["mounted_image_probe"]
    proof_sha256: str
    mapping_count: Literal[1]

ReconciliationPostcondition = (
    CreatePostcondition | MountPostcondition | DetachPostcondition |
    InspectItemPostcondition | DeleteItemPostcondition |
    MountedImageProbePostcondition
)

class CreateReconciliationProbe(TypedDict):
    probe_kind: Literal["create_absent_or_consistent"]
    image_path: str
    expected_image_identity_sha256: str | None
    keychain_query_sha256: str
    expected_encryption_uuid: str | None

class MountReconciliationProbe(TypedDict):
    probe_kind: Literal["mount_mapping_zero_or_one"]
    image_path: str
    mount_path: str
    expected_volume_name: str
    expected_volume_uuid: str
    expected_encryption_uuid: str

class DetachReconciliationProbe(TypedDict):
    probe_kind: Literal["detach_mapping_zero"]
    image_path: str
    mount_path: str

class ItemReconciliationProbe(TypedDict):
    probe_kind: Literal["item_count_zero_or_one"]
    keychain_query_sha256: str

class DeleteReconciliationProbe(TypedDict):
    probe_kind: Literal["deleted_item_count_zero"]
    keychain_query_sha256: str
    transaction_match: Literal[True]

class MountedImageReconciliationProbe(TypedDict):
    probe_kind: Literal["mounted_image_exact_one"]
    image_path: str
    mount_path: str
    expected_volume_name: str
    expected_volume_uuid: str
    expected_encryption_uuid: str

ReconciliationProbePayload = (
    CreateReconciliationProbe | MountReconciliationProbe |
    DetachReconciliationProbe | ItemReconciliationProbe |
    DeleteReconciliationProbe | MountedImageReconciliationProbe
)

@dataclass(frozen=True, slots=True)
class ReconciliationProbeRequest:
    schema_version: Literal[1]
    workflow_id: UUID
    generation: int
    transaction_id: UUID
    operation: PublicStorageOperation | Literal["probe-mounted-image"]
    request_sha256: str
    result_sha256: str
    payload: ReconciliationProbePayload

@dataclass(frozen=True, slots=True)
class ReconciliationRecord:
    schema_version: Literal[1]
    workflow_id: UUID
    generation: int
    transaction_id: UUID
    operation: PublicStorageOperation | Literal["probe-mounted-image"]
    request_sha256: str
    result_sha256: str
    state: ReconciliationState
    postcondition: ReconciliationPostcondition | None
    reconciliation_probe_sha256: str | None
    postcondition_sha256: str | None
    previous_record_sha256: str | None
    record_sha256: str

@dataclass(slots=True)
class _ReconciliationCapability:
    fd: int
    workflow_id: UUID
    generation: int
    transaction_id: UUID
    request_sha256: str
    result_sha256: str
    record_sha256: str
    consumed: bool
    def close(self) -> None: ...

class StorageBrokerClient:
    def __init__(self, *, home: Path,
                 executable: AttestedBrokerExecutable,
                 ledger: StorageWorkflowLedger) -> None: ...
    def _run_locked(self, lock_set: StorageLockSet,
                    request: _StorageBrokerRequest, *, effect_budget_ns: int,
                    cleanup_budget_ns: int) -> StorageBrokerResult: ...
    def _probe_mounted_image_locked(
        self, lock_set: StorageLockSet, *, image_path: Path, mount_path: Path,
        expected_volume_name: str, expected_volume_uuid: UUID,
        expected_encryption_uuid: UUID,
        image_identity: tuple[DarwinU32, int],
        mount_identity: tuple[DarwinU32, int, DarwinU32, DarwinU32],
        expected_mapping_count: Literal[1], effect_budget_ns: int,
    ) -> MountedImageProof: ...
    def _recover_open_workflows_locked(
        self, lock_set: StorageLockSet, *, recovery_budget_ns: int,
    ) -> tuple[StorageWorkflowRecord, ...]: ...
    def _late_close_locked(
        self, lock_set: StorageLockSet, workflow_id: UUID, generation: int,
        *, recovery_budget_ns: int,
    ) -> StorageWorkflowRecord: ...
    def _reconcile_locked(
        self, lock_set: StorageLockSet, request: ReconciliationProbeRequest,
        *, capability: _ReconciliationCapability,
    ) -> ReconciliationPostcondition: ...
```

Every method first calls `lock_set.assert_active` for the client's exact home.
Effect, recovery, late-close, and reconciliation require install-shared or
stronger, storage-exclusive, and admission-exclusive. Read-only mounted proof
requires install-shared or stronger, storage-shared or stronger, and
admission-exclusive. Missing, closed, wrong-home, wrong-mode, replaced, or
forged lock sets fail before connection, capability use, or attestation.

`StorageLifecycle` alone constructs `_StorageBrokerRequest` and calls
`_run_locked()`; neither name is exported or accepted from a CLI caller. The
private `_probe_mounted_image_locked()` entrypoint alone constructs
`_BrokerProbeRequest` with operation `probe-mounted-image`.

`console/storage_lifecycle.py` remains the descriptor-first product authority.
Callers pass lifecycle inputs, never `_StorageBrokerRequest`; the lifecycle
constructs that private backend request only after host/FD/journal validation:

```python
class StorageLifecycle:
    def __init__(self, paths: StoragePaths, *, broker: StorageBrokerClient,
                 fd_probe: FdProbe, mount_verifier: MountVerifier) -> None: ...
    def preflight_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def keychain_spike_locked(self, lock_set: StorageLockSet, *,
                              cleanup_approved: bool) -> OperationResult: ...
    def create_vault_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def initialize_layout_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def mount_or_adopt_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def detach_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def status_locked(self, lock_set: StorageLockSet) -> OperationResult: ...

@dataclass(slots=True)
class InstalledStorageRuntime:
    home: Path
    generation: InstalledStorageRuntimeGeneration
    broker_executable: AttestedBrokerExecutable
    mount_probe_executable: AttestedMountProbe
    ledger: StorageWorkflowLedger
    broker: StorageBrokerClient
    fd_probe: FdProbe
    paths: StoragePaths
    lifecycle: StorageLifecycle
    contract: StorageContract
    @classmethod
    def from_installed_home_locked(
        cls, home: Path, lock_set: StorageLockSet,
    ) -> Self: ...
    def close(self) -> None: ...
```

`InstalledStorageRuntime.from_installed_home_locked` is the sole product
factory. It first validates an active same-home install-shared-or-stronger,
storage-shared-or-stronger, admission-exclusive set, then attests one manifest
generation and composes exactly its broker, descriptor-only
`storage-mount-probe --fd`, ledger, paths, lifecycle, and contract. The returned
objects cannot outlive the lock set; `close()` drops both executable FDs before
the outer context releases locks. Tests and Foundation Tasks 5-14 use injected
`AttestedBrokerExecutable`, `FdProbe`, ledger, and client constructors; they do
not call the installed factory before the installation unit exists.

The Swift broker command line is exactly:

```text
cortex-storage-broker --broker-fd FD --start-capability-fd FD --reconciliation-capability-fd FD --workflow-id UUID --generation UINT64
```

The START capability carries the exact fsynced record/request/operation/budget/
boot grant and is inherited only by the broker. Its exec environment is exactly
`PATH=/usr/bin:/bin:/usr/sbin:/sbin`, `LANG=C`, and `LC_ALL=C`; no parent
environment entry is inherited. The broker accepts no operation, executable,
argv, secret, path, or device on its command line or environment. Production
message names and private native types are:

```swift
private enum BrokerMessageType: String {
    case hello = "HELLO", start = "START", started = "STARTED"
    case cancel = "CANCEL", status = "STATUS", result = "RESULT"
    case close = "CLOSE", closedReady = "CLOSED_READY"
    case commitAck = "COMMIT_ACK", committed = "COMMITTED"
    case reconcileProbe = "RECONCILE_PROBE"
    case reconciliationResult = "RECONCILIATION_RESULT"
    case reconciliationAck = "RECONCILIATION_ACK"
    case finalized = "FINALIZED", lateClose = "LATE_CLOSE"
    case protocolError = "PROTOCOL_ERROR"
}
private enum NativeChildState {
    case absent, suspendedRegistered, running, exitedUnreaped, reaped, unresolved
}
private struct NativeChildIdentity {
    let pid: pid_t
    let parentPID: pid_t
    let processGroup: pid_t
    let uid: uid_t
    let startSeconds: UInt64
    let startMicroseconds: UInt64
    let executableDeviceU32: UInt32
    let executableInode: ino_t
}
```

`BudgetPolicyV1` constants are exactly those in the design. Both languages use
the design's canonical codec and digest projections. The shared vectors are data
inputs, not implementation output copied from one language to the other.

The criteria registry has this exact top-level shape:

```json
{"schema_version":1,"criteria":{"S3-PROTOCOL-CODEC":{"required_tags":["protocol-codec"],"tiers":["hermetic"],"python_versions":["3.11","3.14"],"mutation_required":true}}}
```

The complete registry has stable IDs for protocol/codec, launch binding,
process ownership, parent loss, broker loss truth, ledger recovery, terminal
ACK, secret handling, detach attestation, product façades, install lifecycle,
privacy, and live-gate separation. IDs are normative; their number is not a test
total. Every selected test declares one or more runtime criterion tags and one
evidence tier.

| Criterion ID | Required runtime tag | Required tier | Required Python | Mutation proof |
| --- | --- | --- | --- | --- |
| `S3-PROTOCOL-CODEC` | `protocol-codec` | `hermetic` | 3.11 and 3.14 | yes |
| `S3-LAUNCH-BINDING` | `launch-binding` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-PROCESS-OWNERSHIP` | `process-ownership` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-PARENT-LOSS` | `parent-loss` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-BROKER-LOSS-TRUTH` | `broker-loss-truth` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-LEDGER-RECOVERY` | `ledger-recovery` | `hermetic` | 3.11 and 3.14 | yes |
| `S3-TERMINAL-ACK` | `terminal-ack` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-LOCK-CARRYING` | `lock-carrying` | `hermetic` | 3.11 and 3.14 | yes |
| `S3-RECONCILIATION-PROBE` | `reconciliation-probe` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-SECRET-HANDLING` | `secret-handling` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-DETACH-ATTESTATION` | `detach-attestation` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-PRODUCT-FACADES` | `product-facades` | `hermetic` | 3.11 and 3.14 | yes |
| `S3-INSTALL-LIFECYCLE` | `install-lifecycle` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-INSTALLED-RUNTIME` | `installed-runtime` | `macos_synthetic` | 3.11 and 3.14 | yes |
| `S3-DARWIN-U32` | `darwin-u32` | `hermetic` | 3.11 and 3.14 | yes |
| `S3-PRIVACY-RELEASE` | `privacy-release` | `hermetic` | 3.11 and 3.14 | yes |
| `S3-LIVE-GATE-SEPARATION` | `live-gate-separation` | `hermetic` | 3.11 and 3.14 | yes |

`tests/storage_supervision_modules.json` is canonical JSON with exactly
`schema_version`, `source_modules`, and `sha256`. `source_modules` is the sorted
closed list below; `sha256` uses the ledger canonical codec over the object
without `sha256`:

```text
tests.test_chat_settings_api
tests.test_chrome_extension_driver
tests.test_ci_contract
tests.test_cortex_home
tests.test_cortex_paths
tests.test_cortex_shell_guards
tests.test_disk_image_keychain_helper
tests.test_executor_runtime_truth
tests.test_installed_storage_runtime
tests.test_installed_storage_wheel
tests.test_installer
tests.test_missions_api
tests.test_playwright_driver
tests.test_process_ownership
tests.test_public_privacy
tests.test_release_manifest
tests.test_selftest
tests.test_start_local
tests.test_startup_lease
tests.test_storage_broker
tests.test_storage_cli
tests.test_storage_configuration
tests.test_storage_contract
tests.test_storage_guard
tests.test_storage_guard_integration
tests.test_storage_import
tests.test_storage_lifecycle
tests.test_storage_lock
tests.test_storage_mount_probe
tests.test_storage_reconciliation
tests.test_storage_runtime_ready
tests.test_storage_supervision_matrix
tests.test_storage_transition
tests.test_store_lifecycle
tests.test_workspace_handle
tests.test_workspace_path_fuzzing
```

The runner emits one closed event per discovered selected test:

```python
CauseCode = Literal[
    "NONE", "ASSERTION_FAILED", "ERROR_RAISED", "SKIPPED",
    "EXPECTED_FAILURE", "UNEXPECTED_SUCCESS", "SUBTEST_FAILED",
    "SUBTEST_ERROR", "DEADLINE_EXPIRED", "PROCESS_INTERRUPTED",
    "EVENT_MISSING",
]

class MutationProof(TypedDict):
    criterion_id: str
    mutation_id: str
    input_sha256: str
    expected_sha256: str
    observed_sha256: str
    outcome: Literal["REJECTED_AS_EXPECTED"]

class S3TestEvent(TypedDict):
    test_id: str
    tags: list[str]
    tier: Literal["hermetic", "macos_synthetic", "owner_live", "provider_live"]
    interpreter_path_sha256: str
    python_version: Literal["3.11", "3.14"]
    status: Literal[
        "PASS", "FAIL", "ERROR", "SKIP", "XFAIL", "XPASS",
        "SUBTEST_FAIL", "SUBTEST_ERROR", "TIMEOUT", "INTERRUPTED", "MISSING",
    ]
    cause_code: CauseCode
    mutation_proofs: list[MutationProof]
```

For every `mutation_required` criterion, the registry lists the exact allowed
mutation IDs. Each must have one canonical proof whose criterion/mutation IDs
match and whose input/expected/observed digests recompute from runner-owned
typed values. Missing, duplicate, cross-criterion, mismatched, or non-canonical
proof is non-PASS. Receipt construction never serializes exception text,
stdout, stderr, environment, or free-form diagnostic data.

Each module runs in a subprocess with a 180-second monotonic deadline; one
interpreter run has a 1,800-second deadline. The supervisor maps exit without a
complete event set to `MISSING`, deadline expiry to `TIMEOUT`, and caught
SIGINT/SIGTERM/KeyboardInterrupt to `INTERRUPTED`, writes a non-PASS receipt,
and returns nonzero.

The release-manifest object is exact:

```python
class StorageSupervisionEvidence(TypedDict):
    schemaVersion: Literal[1]
    verdict: Literal["PASS", "FAIL", "UNCLEAR"]
    criteriaRegistry: Literal["tests/storage_supervision_criteria.json"]
    criteriaRegistrySha256: str
    moduleInventory: Literal["tests/storage_supervision_modules.json"]
    moduleInventorySha256: str
    receiptArtifact: Literal["docs/verification/v0.5.4-storage-supervision-receipt.json"]
    receiptSha256: str
    jsonArtifact: Literal["docs/verification/v0.5.4-storage-supervision.json"]
    jsonSha256: str
    markdownArtifact: Literal["docs/verification/v0.5.4-storage-supervision.md"]
    markdownSha256: str
    installedBrokerSha256: str
    installedBrokerBuildProfileSha256: str
    pythonVersions: list[Literal["3.11", "3.14"]]
    ownerLive: Literal["not_run", "PASS", "FAIL", "UNCLEAR"]
    providerLive: Literal["not_run", "PASS", "FAIL", "UNCLEAR"]
```

## Task 1: Canonical codec and protocol core

**Files:** modify `native/macos/disk_image_keychain.swift`; create
`console/storage_broker.py`, `tests/fixtures/storage_protocol_v1_vectors.json`,
and `tests/test_storage_broker.py`; modify
`tests/test_disk_image_keychain_helper.py`.

**RED**

Write tests that independently encode/decode all frame and ledger variants in
Swift and Python; verify exact bytes/digests for Unicode, slash, controls, zero,
`UInt64.max`, and signed Darwin observations `Int32.min`, `-1`, `0`, and
`Int32.max` encoded through the exact `_u32` bit-pattern fields; mutate key
order, escapes, duplicate keys, hash domain,
projection, length, nonce, cursor, generation, and unknown fields. Add strict
broker CLI and peer/socket authentication tests. Mutate every semantic request
constraint from the design: root/path/suffix, control/NUL/dot component,
UUID, size, volume, disposable/cleanup matrix, and operation mismatch; require
zero capability grant and zero native effect.
Cover `_BrokerProbeRequest` and both `BrokerTerminalResponse` discriminants in
Swift/Python golden vectors. Reject local/probe cross-kind payloads, both union
arms set, neither arm set, extra proof fields, wrong operation, and private proof
serialization through any public result or receipt. Verify that
`to_storage_evidence_response` omits `device` and `encryption_uuid`, preserves
only schema/operation/code/item count, and rejects `/dev/disk*` in every public
API, receipt, and renderer. The same independently
verified vector file covers ledger, reconciliation-record, and installed-
generation hash domains; a domain or omitted-field substitution must fail.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v \
  tests.test_storage_broker.CanonicalCodecTests \
  tests.test_storage_broker.ProtocolCoreTests \
  tests.test_disk_image_keychain_helper.BrokerProtocolTests
```

Expected RED: the client, production broker mode, and vectors do not exist.

**GREEN**

Implement the restricted codec twice, exact hash domains, 16-KiB framing,
single-use nonce/cursors, closed message set, strict CLI, peer/socket checks,
`SO_NOSIGPIPE`, and a broker state machine that cannot effect before `START`.
Keep test scenarios behind a Swift compile condition absent from production.

Run the same command under `$PYTHON311`, then replace it with `$PYTHON314` and
run again. Both must explicitly PASS.

## Task 2: Broker launch isolation and native ownership

**Files:** modify `native/macos/disk_image_keychain.swift`,
`console/storage_broker.py`, `tests/test_disk_image_keychain_helper.py`, and
`tests/test_storage_broker.py`.

**RED**

Add macOS synthetic tests for separate SID/PGID, controller-group `SIGINT`,
`SIGHUP`, and `SIGTERM`, parent crash/EOF, `POSIX_SPAWN_START_SUSPENDED`,
pre-resume identity and non-consuming waitability registration, an ultra-short
child, identity replacement immediately before resume, TERM then KILL with
fresh proofs, `ECHILD`, exact reap, group absence, post-reap no-signal, and FD
inheritance. Name the broker-loss test exactly
`test_broker_loss_after_spawn_marks_unresolved_and_makes_no_orphan_absence_claim`;
it must assert `native_cleanup_proven=false` and must not assert group absence.
Race a same-UID listener client before the owner and send a different START;
without the inherited exact `START_GRANT` it must create zero effect. Pollute
the parent with `DYLD_*`, `PYTHON*`, `HOME`, virtualenv, and unexpected
`CORTEX_*`; prove the broker receives only the three allowlisted variables.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v \
  tests.test_disk_image_keychain_helper.BrokerOwnershipTests \
  tests.test_storage_broker.BrokerLaunchIsolationTests
```

Expected RED: current spawn has no persistent isolated broker or suspended
registration handshake.

**GREEN**

Launch the broker with `start_new_session=True`, an attested listener FD, and an
exec-status pipe. Pass the private capability FD, but write its exact grant only
after `OPEN_RUNNING` fsync. Seal envp before exec and verify it before any
effect. Install broker signal dispositions before accepting `START`.
Spawn every native child suspended with an atomic new group, register identity
and waitability, then resume. Apply `POSIX_SPAWN_CLOEXEC_DEFAULT` and map only
stdin/stdout/stderr. Implement identity-before-signal, observe-before-reap, and
post-reap group-absence ordering. Do not add any Python cleanup fallback.

Run the RED command unchanged. Also run it after swapping `$PYTHON311` for
`$PYTHON314`.

## Task 3: Secret channel and SIGPIPE discipline

**Files:** modify `native/macos/disk_image_keychain.swift` and
`tests/test_disk_image_keychain_helper.py`.

**RED**

Add injected Security/hdiutil tests for exact random length and Base64URL form,
dedicated bounded stdin delivery with terminating NUL, partial write/EINTR/EPIPE,
child SIGPIPE reset, broker `sigaction`/socket behavior, `memset_s` on every
owned mutable buffer and error path, and absence from argv/env/protocol/ledger/
logs/receipts. Inspect the synthetic child's open FDs and prove no listener,
client, ledger, executable, install-lock, or exec-status FD is inherited.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v \
  tests.test_disk_image_keychain_helper.BrokerSecretTests \
  tests.test_disk_image_keychain_helper.BrokerFdInheritanceTests
```

Expected RED: the current helper does not meet the broker lifetime contract.

**GREEN**

Move Keychain and secret lifetime into the broker, use only the dedicated pipe,
cap all data, zero every application-owned mutable copy, and retain cleanup
after EPIPE. State the immutable Security.framework/kernel limitation in test
evidence. Run the unchanged selection under both interpreters.

## Task 4: Fresh detach attestation

**Files:** modify `native/macos/disk_image_keychain.swift` and
`tests/test_disk_image_keychain_helper.py`.

**RED**

Build injected plist/device/mount adapters and mutate mount path, mount FD,
image identity, mapping cardinality, device node, `st_rdev`, volume UUID,
generation, command digest, and the value immediately before detach. Require
zero detach on every mutation, single-use attestation, the exact attested
operand, normal detach only, and post-effect verification that cannot authorize
the prior effect.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v \
  tests.test_disk_image_keychain_helper.BrokerDetachAttestationTests
```

Expected RED: current detach is snapshot-based and cannot bind the mutation.

**GREEN**

Implement the design's one-turn `DetachAttestation`, consume it once with no
intervening effect, and fail unresolved on mismatch or replay. Run the same
selection under Python 3.11 and 3.14.

## Task 5: Lock-bound client, ledger, and retained-broker reconciliation

**Files:** create `console/storage_reconciliation.py` and
`tests/test_storage_reconciliation.py`; modify `console/storage_broker.py`,
`native/macos/disk_image_keychain.swift`, `tests/test_storage_broker.py`, and
`tests/test_disk_image_keychain_helper.py`. Production helper discovery and
installed attestation are deliberately absent until Task 7; tests inject an
`AttestedBrokerExecutable` and executable-attestor callable.

**RED**

Add mutation and crash tests for:

- install-shared lock and attested executable FD retained through `HELLO`;
- missing lock argument, wrong-home/closed/wrong-mode/missing-admission or
  replaced-marker sets rejected before attestation, connection, or START;
- path replacement between attestation/spawn and between spawn/`HELLO`, with
  zero `START` and zero effect;
- exact `kern.boottime`, boot mismatch, budget zero/max/max-plus-one/overflow,
  broker-enforced effect/cleanup/total/recovery bounds, and injected clock
  advance or sleep/resume semantics;
- fsynced `OPEN_PREPARED` before spawn, crash before spawn, exec failure, crash
  after exec-status EOF, before `HELLO`, after `HELLO`, after fsynced
  `OPEN_RUNNING`, after START write, and after `STARTED`;
- channel loss, stale generation, CAS failure, `ECHILD`, and ambiguous terminal
  data producing `OPEN_UNRESOLVED` only;
- `CLOSED_READY` retained across client death, death after ready before ledger
  fsync, death after fsync before `COMMIT_ACK`, repeated exact ACK, wrong ACK,
  lost `COMMITTED`, closed-record recovery ACK, and `FINALIZED` replay;
- `OPEN_PREPARED` with no broker closing failure by the no-START invariant;
- broker absent after possible effect remaining a redacted manual block;
- external construction/call of `_StorageBrokerRequest`/`_run_locked()` rejected
  before connection while lifecycle and the private guard method succeed;
- no Python call to native-child signal/wait primitives.
- closed records persist transaction ID and canonical non-secret terminal
  result; crash after `COMMIT_ACK` but before product-journal fsync resumes
  reconciliation without replaying the effect.
- every `ReconciliationProbeRequest` arm and every zero/one postcondition,
  `ReconciliationRecord` pending/reconciled/unclear CAS and fsync, crash
  before/after pending fsync, probe, result, final-record fsync, and ACK, stale
  digests, exact replay returning the cached result without probing twice, and a private
  single-use read-only capability that permits only the blocking workflow's
  probe under the existing lock owner and cannot create general admission;
- after `COMMIT_ACK` with `reconciliation_required=true`, broker retention,
  `RECONCILE_PROBE`, `RECONCILIATION_RESULT`, fsynced record,
  `RECONCILIATION_ACK`, and `FINALIZED`, including recovery replay without a
  second `START` or a new broker.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v \
  tests.test_storage_broker tests.test_storage_reconciliation
```

Expected RED: lock-carrying broker methods, the retained reconciliation
protocol, and the canonical reconciliation module do not exist.

**GREEN**

Implement no-follow ledger CAS and file/directory fsync, the exact launch
ordering, FD/path/self-identity `HELLO` binding, five states, broker-enforced
duration budgets, two-phase terminal commit, idempotent recovery/ACK, and
failure-only `late_close`. `OPEN_RUNNING` must be durable before `START`.
Closed records are immutable. An unavailable broker after possible effect
leaves `OPEN_UNRESOLVED`; no operator API edits it. All broker entrypoints are
the exact `*_locked` methods and validate the active same-home set before
attestation or protocol I/O. Persist the exact `ReconciliationRecord` through
the sole reconciliation module. When reconciliation is required, Python first
fsyncs the exact `pending` record. The original broker retains terminal state
after `COMMIT_ACK`, consumes one matching private probe capability, executes
that unique probe once, caches and returns the typed postcondition without
mutation, and returns the same bytes on exact replay. Python CAS-writes and
fsyncs `reconciled|unclear` from the pending digest. The broker then waits for
the final-record-bound `RECONCILIATION_ACK`, replies `FINALIZED`, and only then
exits. Recovery replays this sequence against that retained broker and never
sends `START` or executes a second probe. Native cleanup never changes
reconciliation state.

Run the complete module under each interpreter:

```bash
for PY in "$PYTHON311" "$PYTHON314"; do
  PYTHONPATH="$SOURCE_ROOT" "$PY" -m unittest -v \
    tests.test_storage_broker tests.test_storage_reconciliation
done
```

## Task 6: Cross-plan integration gate over existing consumers

**Files:** inspect only the production and test files completed by Foundation
Tasks 5-14. This task creates or modifies no file and has no commit.

**Gate precondition**

Use the injected attested broker and descriptor-probe fakes already built by the
Foundation tasks and exercise the complete existing façade:
`preflight_locked`, `keychain_spike_locked`, `create_vault_locked`,
`initialize_layout_locked`, `mount_or_adopt_locked`, `detach_locked`, and
`status_locked`, plus configuration compatibility, transition/contract,
runtime lease/server, and guard entrypoints. Prove:

- lifecycle alone constructs each request after descriptor/host/journal proof;
  callers cannot pass a raw request and facade-operation mismatch is rejected;
- every native effect reaches the broker backend with preserved APFS name/UUID,
  encryption UUID, image/mount identity, and mapping cardinality;
- guard reaches only `_probe_mounted_image_locked()` with the same active set;
- `start-local.sh` delegates once to `cortex.sh start` and cannot exec
  `server.py` directly;
- stop quiesces the verified server before normal broker detach;
- admission runs bounded recovery and refuses any open/unresolved record;
- patched native-command subprocess routes, `os.kill`, `os.killpg`,
  `os.waitpid`, direct `hdiutil`, direct `diskutil`, and the test-only helper
  route are never reached by a product storage operation; the broker is the
  sole parent of `hdiutil`/`diskutil`, while the injected equivalent of
  `storage-mount-probe --fd` is the sole descriptor-only helper and has no
  DiskImages/Keychain capability;
- unresolved terminal/no broker produces nonzero
  `S3_MANUAL_RECOVERY_REQUIRED`, redacted output, and no ledger mutation.
- after `STARTED`, `CLOSED_FAILURE` remains admission-blocking until the
  transition journal fsyncs operation-specific `effect_reconciled=true` for
  create, mount, detach, inspect, disposable Keychain deletion, or probe;
- guard+Doctor, probe+start, and probe+update races follow install → storage →
  admission ordering with one exclusive admission owner and no nested acquire.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v \
  tests.test_storage_lifecycle \
  tests.test_storage_cli \
  tests.test_storage_transition \
  tests.test_storage_contract \
  tests.test_cortex_paths \
  tests.test_storage_guard \
  tests.test_storage_guard_integration \
  tests.test_process_ownership \
  tests.test_storage_reconciliation \
  tests.test_startup_lease \
  tests.test_store_lifecycle \
  tests.test_start_local
```

Expected: PASS under Python 3.11 and 3.14. This is not a RED step: all behavior
was created and passed RED/GREEN in its owning Foundation task.

**Failure routing and commit boundary**

If any assertion fails, stop and return to the earlier Foundation or S3 core
task that owns the behavior, add the regression to that task's original RED
selection, repair it there, and rerun this entire gate. Task 6 itself performs
no implementation, staging, or commit and cannot paper over a failure with a
second façade or compatibility fallback.

## Task 7: Package, attest, update, diagnose, and uninstall

**Files:** continue the uncommitted Foundation Task 4 changes in
`console/installer.py`, `console/native_helpers.py`,
`native/build-profiles/macos-ax-send-v1.json`,
`native/build-profiles/storage-mount-probe-v1.json`,
`native/build-profiles/storage-broker-v1.json`,
`transport/browser_chrome_extension.py`, `scripts/cortex.sh`,
`tests/test_installer.py`, `tests/test_chrome_extension_driver.py`, and
`tests/test_cortex_shell_guards.py`; modify `pyproject.toml`; create
`console/installed_storage_runtime.py`, `tests/test_installed_storage_wheel.py`,
and `tests/test_installed_storage_runtime.py`.

**RED**

Build an installed wheel/runtime in a temporary home and require the broker,
client, lifecycle, Swift source, manifest schema, source digest, production
build-profile digest, binary digest, vnode, owner, and mode. Execute the
installed broker—not the checkout or test compilation—with every test-only
argument and environment switch; require CLI rejection before socket,
Keychain, or DiskImages access.

Require one exact `installed_storage_runtime_generation`: `app/bin` contains
`cortex-storage-broker`, `storage-mount-probe`, and `cortex-macos-ax-send`;
`app/python` contains the packaged application; `app/scripts` contains every
installed entrypoint; `app/native-src` and `app/build-profiles` contain the
three exact native sources and canonical build profiles;
`app/chrome-extension` contains the installed extension; and `owned.json`
binds those trees plus the exact interpreter. Require the same canonical
`extension_tree_sha256` in the relative extension manifest, generation record,
Doctor evidence, and installed proof. Require
`owned.json["native_helpers"]` to contain exactly `macos-ax-send`,
`storage-mount-probe`, and `storage-broker`, in that order. Every entry has
exactly `target`, `source`, `source_sha256`, `build_profile_sha256`, `sha256`,
`cdhash`, `dev_u32`, `ino`, `uid`, and `mode`.
Install through `scripts/install.sh`, then run installed `cortex.sh` with the
checkout unreadable and a homonymous site-package sentinel present.

Construct `InstalledStorageRuntime.from_installed_home_locked(home, lock_set)`
under one active same-home set and require that broker, mount-probe `FdProbe`,
ledger, paths, lifecycle, and contract all bind the same generation. Reject
factory calls with absent, wrong-home, closed, weak-mode, missing-admission,
replaced, or nested lock sets. Prove no attestation begins before
install-shared acquisition and both executable FDs close before set release.
Run start, stop, guard, Doctor, and operator CLI from the installed app with the
checkout inaccessible. Allow exactly the broker as parent of
`hdiutil`/`diskutil` and `storage-mount-probe --fd` as the descriptor-only
helper; reject any other storage subprocess or any path argument to the probe.

Mutate every application, Python, script, source, profile, manifest,
interpreter, and helper identity. Test update and reinstall under one
install-exclusive/storage-exclusive/admission-exclusive `StorageLockSet`:
runtime stopped, compatible schema/build profiles, bounded recovery, zero open
or unresolved records, and every transition reconciliation `reconciled` are
mandatory before any publication. An existing compatible vault Keychain item
alone is not a veto. Crash between
binary swap and manifest publication; the resulting mismatch must be detected
and execution refused. Test Doctor read-only re-attestation. Test uninstall
refusal for open/unresolved/unauthenticated broker. With a configured vault,
require whole-operation `STORAGE_VAULT_CONFIGURED` refusal and byte-identical
preservation of the complete generation; without one, removal is limited to
exact manifest-owned resources, with no signal or deletion of replacements.
Inject crashes between application-module tree, installed scripts, extension
tree, source, profile, each helper binary, and manifest publication; mutate the
extension relative manifest and `extension_tree_sha256`. Each recovery yields
one complete generation or refusal, never a mixed executable topology.

```bash
env -u PYTHONPATH "$PYTHON311" -m unittest -v \
  tests.test_installer \
  tests.test_installed_storage_wheel \
  tests.test_installed_storage_runtime
```

Expected RED: installer currently builds only the AX helper and the disk broker
has no installed route.

**GREEN**

Add a production Swift build without the testing compile condition, strict
sign/verify/hash staging, atomic publication and directory fsync, packaged
Python modules/data, `InstalledStorageRuntime.from_installed_home_locked`,
FD-held broker/probe attestation, and manifest ownership. Refuse
update/reinstall until runtime stop, compatibility, recovery, closure, and
reconciliation are all proven. Refuse uninstall as a whole while a vault is
configured. Publish or roll back the complete generation atomically; do not
adopt a crash-swapped binary. Run the same selection under both interpreters.
Migrate the legacy single-helper manifest atomically to the exact three-entry
registry and common record schema.

Run the same three-module RED selection unchanged under Python 3.11 and 3.14,
then run the Foundation Task 4 selection. Commit the entire installation unit
once:

```bash
git add console/installer.py console/native_helpers.py \
  console/installed_storage_runtime.py \
  native/build-profiles/macos-ax-send-v1.json \
  native/build-profiles/storage-mount-probe-v1.json \
  native/build-profiles/storage-broker-v1.json \
  transport/browser_chrome_extension.py scripts/cortex.sh pyproject.toml \
  tests/test_installer.py tests/test_chrome_extension_driver.py \
  tests/test_cortex_shell_guards.py tests/test_installed_storage_wheel.py \
  tests/test_installed_storage_runtime.py
git commit -m "feat(storage): install one attested storage runtime generation"
```

## Task 8: Versioned criteria registry and deterministic executed matrix

**Files:** create `tests/storage_supervision_criteria.json`,
`tests/storage_supervision_modules.json`,
`docs/verification/v0.5.4-storage-supervision-receipt.json`,
`scripts/run-storage-supervision-matrix.py`, and
`tests/test_storage_supervision_matrix.py`.

**RED**

Build synthetic unittest fixtures for explicit PASS, failure, error, skip,
expected failure, unexpected success, subtest failure/error, timeout,
abort/interruption, missing result, and empty selection. Mutate selection by
removing a module/test, satisfying a criterion only from fixture tier,
duplicating a criterion tag, changing tier, omitting one required Python
version, changing a registry ID, and changing receipt order.
Remove or rename `tests.test_disk_image_keychain_helper`, change module-inventory
hash/path/order, replace it with a fixture module, kill a real subprocess with
SIGINT/SIGTERM, hang it beyond 180 seconds using an injected clock/deadline, and
exit without the discovered event set.
Compare the exact module arguments from every focused S3/foundation command
against `source_modules`; any module missing from either side or any extra
module blocks before execution. Mutate required mutation proof by omission,
duplicate, wrong criterion/mutation ID, wrong digest, non-canonical value, and
fake PASS without executing the mutation.

Require every status other than explicit PASS to block and prevent a PASS
artifact. Require each registry criterion exactly once per required
tier/version combination from an actually passed selected test. Counts, when
rendered, must be derived from those results only.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v tests.test_storage_supervision_matrix
```

Expected RED: criteria registry and runner do not exist.

**GREEN**

Implement the exact `S3TestEvent` stream and bounded subprocess supervisor,
closed registry/module-inventory validation, deterministic sorting, and the
canonical receipt at its fixed path. The runner, `test-all`, final command, and
release validator consume the same inventory hash and assert command/inventory
set equality. Validate each typed mutation proof against the registry and
recomputed digests. Privacy-validate the raw receipt before atomic write and
again after reopen. A fixture can test the
runner but cannot satisfy a production criterion.

```bash
for PY in "$PYTHON311" "$PYTHON314"; do
  PYTHONPATH="$SOURCE_ROOT" "$PY" -m unittest -v tests.test_storage_supervision_matrix
done
```

## Task 9: Hermetic dual-Python gate and documented command

**Files:** modify `scripts/test-all.sh`, `.github/workflows/ci.yml`,
`tests/test_ci_contract.py`, `README.md`, `console/README.md`,
`CONTRIBUTING.md`, `docs/agent-installation.md`, `docs/testing.md`, and
`tests/test_storage_supervision_matrix.py`; create
`tests/storage_dual_python_active_paths.json`.

**RED**

Add a test that extracts and executes the exact documented command:

```bash
PYTHON311="$(command -v python3.11)" \
PYTHON314="$(command -v python3.14)" \
./scripts/test-all.sh
```

Require distinct executable identities and exact reported major/minor versions.
Reject missing, same, symlink-equivalent, wrong-version, or relative interpreter
paths. Prove live flags are cleared and no real Keychain/DiskImages command is
reachable. Prove a failing first run prevents evidence publication and a
failing second run invalidates the combined receipt.
Scan only the closed active-path inventory below: any remaining mono-Python
`PYTHON=... scripts/test-all.sh` invocation must fail the contract. A direct
legacy invocation of `test-all.sh` with only `PYTHON` exits nonzero with the
stable code `S3_DUAL_PYTHON_REQUIRED` and the exact dual command, before tests.

`tests/storage_dual_python_active_paths.json` has exactly `schema_version`,
`active_paths`, `frozen_exclusions`, and `sha256`; its digest uses the S3
canonical codec over the object without `sha256`. `active_paths` is exactly,
in bytewise order: `.github/workflows/ci.yml`, `CONTRIBUTING.md`, `README.md`,
`console/README.md`, `docs/agent-installation.md`, `docs/testing.md`, and
`scripts/test-all.sh`. `frozen_exclusions` is an ordered array of exact
`{path,sha256}` records for every frozen spec/plan known to contain a historical
single-Python full-gate command. It contains no glob, directory, regex, or
prefix rule. The exact exclusion records are:

| Path | SHA-256 |
| --- | --- |
| `docs/superpowers/plans/2026-07-30-chrome-tab-bridge.md` | `12b97cc8e53e3e76e18606169e299f0538709c9e4337dc7c0392ac1a38429a60` |
| `docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md` | `b98b88a54bc27543555c465839ff1bea912fc343514fa3ffdf15caecfe61ffe1` |
| `docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md` | `bcd7a77dbf344c05f60238be326b6a96d853ec8063777e10931b0041502ef6a6` |
| `docs/superpowers/plans/2026-09-02-v054-live-cutover-and-release-qa.md` | `b8dda2316401eaee1b6408aa6cc68136b783524d6b99e5b30f64db7c30e83277` |
| `docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md` | `25d04484e4dcf337728ce96f0af642d3894be71dea0ef9a616f2552cd9121245` |
| `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md` | `a41bd652ece6803afa5a759f6bf806639ff17c1db067bc344aac5f452a04c827` |

At Task 9 execution, each exclusion SHA must exactly match the frozen
completion-ledger/master value or the independently recorded historical-plan
hash; any byte change, missing path, extra path, symlink, or unlisted file with
the legacy command fails. Frozen exclusions are never scanned as active
instructions and never become a compatibility success path.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v \
  tests.test_storage_supervision_matrix.DocumentedDualPythonCommandTests
```

Expected RED: current documentation and gate select one interpreter.

**GREEN**

Document the command above verbatim and make `test-all.sh` validate and execute
both interpreters in a clean hermetic environment. It runs the criteria-aware
matrix only after both complete suites explicitly PASS. Do not run live tests.
Update CI atomically to install distinct 3.11 and 3.14 interpreters and invoke
that command. Build and hash the exact active/exclusion manifest, and make both
the CI contract and matrix validate it. Update every file listed by this task in
the same change; there is no compatibility success path for the old
single-`PYTHON` gate.

```bash
PYTHON311="$PYTHON311" PYTHON314="$PYTHON314" ./scripts/test-all.sh
```

## Task 10: Privacy scrub and hash-bound public comparison tables

**Files:** modify `scripts/run-storage-supervision-matrix.py`,
`tests/test_public_privacy.py`, and `scripts/test-all.sh`; create
`docs/verification/v0.5.4-storage-supervision.json` and
`docs/verification/v0.5.4-storage-supervision.md`.

**RED**

Seed private paths, mount/device names, native IDs, account/Keychain labels,
secret-like values, stdout/stderr, environment data, and private test payloads
in every input/error field. Inject `/dev/disk99` through a
`StorageLocalResponse.device`, API adapter, raw receipt, JSON renderer, and
Markdown renderer; `to_storage_evidence_response` must omit it and every public
ingress must reject it before rendering. Require rejection before rendering. Mutate JSON and
Markdown independently, line endings, final newline, artifact path, receipt
digest, criteria digest, tier labels, and table row order. Require JSON and
Markdown to bind the same receipt and criteria registry.
Inject a third-party brand, tool, source, metric, extra column, free-text cell,
wrong vocabulary, wrong type, and non-canonical row order; each must reject.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v \
  tests.test_public_privacy \
  tests.test_storage_supervision_matrix.PublicRendererTests
```

Expected RED: public S3 artifacts and paired renderer do not exist.

**GREEN**

Generate canonical JSON and UTF-8/LF Markdown from one accepted receipt. The
Markdown includes public Cortex-only comparison and executed-test tables with
explicit `hermetic`, `macos_synthetic`, `owner_live`, and `provider_live`
tiers. `not_run` remains visible and cannot become PASS. Add the renderer's
`--check` mode to `test-all.sh` after generation is deterministic.

The comparison table columns are exactly `criterion`, `cortex_status`,
`evidence_tier`, `python_versions`, and `receipt_sha256`. The executed-test
table columns are exactly `test_id`, `criterion_tags`, `tier`,
`python_version`, and `status`. Rows sort by criterion or test ID, then Python
version. Cells use only registry IDs/tags, the four tiers, `3.11|3.14`, the
closed event statuses, lowercase SHA-256, and `not_run`; no prose cell exists.

Run the unchanged tests under both interpreters, then:

```bash
PYTHON311="$PYTHON311" PYTHON314="$PYTHON314" ./scripts/test-all.sh
```

## Task 11: Explicitly gated live macOS integration

**Files:** modify `tests/test_disk_image_keychain_helper.py`,
`tests/test_installed_storage_wheel.py`, `docs/testing.md`, and
`scripts/run-storage-supervision-matrix.py`.

**RED**

Keep live cases outside default unittest discovery. Prove either missing gate
exits before `SecItemAdd`, `hdiutil`, `diskutil`, or cleanup. Prove the live
route uses the installed, manifest-attested production broker and packaged
client, never a test compilation. Require unique disposable 64-MiB synthetic
data, normal detach, and separate cleanup authorization. Require fixture and
macOS synthetic receipts to state that they do not prove a live environment.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v \
  tests.test_disk_image_keychain_helper.LiveGateContractTests \
  tests.test_installed_storage_wheel.LiveRouteSelectionTests
```

Expected RED: installed live broker routing is absent. This RED command causes
no real effect.

**GREEN**

Implement only the gate and installed-route selection. Owner-live execution is
allowed solely by this separate command after fresh action-time approval:

```bash
CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION=YES_DISPOSABLE_64_MIB_ONLY \
  env -u PYTHONPATH "$PYTHON311" tests/test_disk_image_keychain_helper.py \
  --integration --allow-effects
```

Do not run that command during plan implementation, default CI, or release
verification without the approval. Provider-live evidence is accepted only as
an independently issued, validator-checked provider receipt; absent such a
receipt it remains `not_run`. Owner approval never becomes provider evidence.

## Task 12: Release evidence contract

**Files:** modify `scripts/verify-release-evidence.py`,
`tests/test_release_manifest.py`, `scripts/test-all.sh`, `README.md`, and
`docs/testing.md`.

**RED**

Add the exact `StorageSupervisionEvidence` object and reject:

- any verdict other than PASS or any non-PASS underlying unittest status;
- missing/changed/extra criteria, tag, required tier, mutation proof, or Python
  version;
- missing/changed/wrong-path/non-canonical receipt or module inventory and any
  mismatch among their hashes in JSON, Markdown, `test-all`, and manifest;
- same interpreter identity for 3.11 and 3.14;
- missing, non-canonical, wrong-path, wrong-hash, or different-receipt JSON and
  Markdown artifacts;
- missing/mismatched installed broker or production build-profile digest;
- a test-compiled broker, checkout-only client, or live test route in the
  installed binary;
- owner-live presented as provider-live, or fixture/synthetic evidence claiming
  live macOS proof.

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" -m unittest -v tests.test_release_manifest
```

Expected RED: release validation does not bind both public artifacts, criteria,
and installed production provenance.

**GREEN**

Validate raw bytes and canonical paths for both artifacts, their shared receipt
and criteria digest, exact installed provenance, dual-Python executions, and
tier truth. Bind the accepted object into the existing release manifest. Make
`test-all.sh` run the validator last and fail on `FAIL`, `UNCLEAR`, interruption,
timeout, or any missing explicit PASS.

```bash
for PY in "$PYTHON311" "$PYTHON314"; do
  PYTHONPATH="$SOURCE_ROOT" "$PY" -m unittest -v tests.test_release_manifest
done
PYTHON311="$PYTHON311" PYTHON314="$PYTHON314" ./scripts/test-all.sh
```

## Final verification

Run only after every task's unchanged RED selection has passed GREEN:

```bash
PYTHONPATH="$SOURCE_ROOT" "$PYTHON311" \
  scripts/run-storage-supervision-matrix.py \
  --module-inventory tests/storage_supervision_modules.json \
  --python311 "$PYTHON311" --python314 "$PYTHON314" \
  --receipt docs/verification/v0.5.4-storage-supervision-receipt.json \
  --json docs/verification/v0.5.4-storage-supervision.json \
  --markdown docs/verification/v0.5.4-storage-supervision.md
PYTHON311="$PYTHON311" PYTHON314="$PYTHON314" ./scripts/test-all.sh
bash -n scripts/cortex.sh scripts/start-local.sh scripts/test-all.sh
git diff --check
git status --short
```

Expected: each selected test reports explicit PASS, both distinct Python
versions are present in the receipt, live effects were not selected, both public
artifacts match their recorded hashes, and only intended files are modified.

Release remains blocked when an `OPEN_UNRESOLVED` workflow has no reachable
broker after possible native effect. That is the honest operational limit: the
product has no waitpid authority capable of proving closure, so manual
out-of-product investigation is required and S3 must not mint a release waiver.
