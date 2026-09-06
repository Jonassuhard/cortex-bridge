# Cortex Bridge v0.5.4 Storage Runtime Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and test the fail-closed storage runtime foundation for Cortex Bridge without creating the production vault or mutating a real production Keychain, disk image, or Chrome profile.

**Architecture:** A single descriptor-first `StorageContract` owns storage truth, backed by the persistent S3 Swift broker, the descriptor mount probe, a private ordered lock set, and a durable transition journal. A redacted operator CLI composes preflight, disposable Keychain proof, vault lifecycle, controlled import, cutover, rollback, and status, while `cortex.sh` alone owns runtime mount/detach and a one-shot managed-start lease. `WorkspaceHandle` remains a strictly vault-only persistent-FD boundary; a separate read-only runtime-readiness assertion lets later local-alias actions observe storage and managed-start health without receiving vault or local-filesystem authority.

**Tech Stack:** Python 3.11 and 3.14, Swift with Security.framework and Darwin, macOS 14/15/26, APFS DiskImages on an ExFAT host, FastAPI lifespan, Bash, `unittest`, `xcrun swiftc`, `codesign`, `diskutil`, `hdiutil`, Git and Gitleaks.

**Spec:** `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md` frozen at SHA-256 `30b74475822692388d07a3d3891d12ab625feb0d5cc209b699933c54f8589b4c`, normative addendum `docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md` frozen at SHA-256 `38dff2d114ddf3a8f2262f3ac2b37dcbec9fd33951934c5d5c03a9a0c4acc08b`, and the S3 owned-process design/plan frozen by the completion program.

## Global Constraints

- Preserve the legacy sparsebundle: never attach it, open it for write, repair it, compact it, convert it, rename it, delete it, guess its password, or claim a full band-content identity proof.
- Before the first legacy metadata open and before every image operation, retain an opened host-volume FD and prove the same UUID, filesystem, canonical no-follow location, and `MNT_NOATIME`; a failed or absent proof performs zero legacy reads.
- The production target is exactly `HOST_VOLUME/CORTEX_BRIDGE_2026_09.sparsebundle`, a 256 GiB AES-256 sparsebundle with one APFS volume named `CORTEX_BRIDGE_2026_09`, mounted at `CORTEX_HOME/mounts/CORTEX_BRIDGE_2026_09` with storage root `NEW_MOUNT/CORTEX_BRIDGE`.
- Require at least 320 GiB free before production image creation and retain a 128 GiB operational free-space floor before bulk import.
- Do not create the production vault or invoke a real production Keychain/disk mutation while implementing this plan. Production lifecycle commands are implemented and tested with fakes only; their later live execution is a separately reviewed action.
- A real disposable Keychain/image integration test is forbidden unless the invocation contains both `--allow-effects` and `CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION=YES_DISPOSABLE_64_MIB_ONLY`; absence of either gate exits before `SecItemAdd`, `hdiutil create`, attach, detach, or cleanup.
- Disposable cleanup is a separate action-time authorization: only `keychain-spike --cleanup-approved` may delete the exact disposable item and 64 MiB image after proving exactly one UUID/service match. No production deletion command exists.
- Generate 32 random bytes with `SecRandomCopyBytes`, encode 43 Base64URL ASCII characters without padding, append one terminal NUL only for `hdiutil -stdinpass`, keep secrets out of arguments/environment/files/stdout/stderr, and overwrite mutable secret buffers before helper exit.
- Keychain items use generic-password class, encryption UUID account, service `com.cortexbridge.encrypted-storage`, sparsebundle-basename label, description `disk image password`, transaction UUID generic tag, `kSecUseDataProtectionKeychain=true`, `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`, synchronizable disabled, and `kSecUseAuthenticationUIFail` on every add/read/delete query.
- `errSecInteractionNotAllowed`, authentication-required/cancelled status, any SecurityAgent observation, UUID collision, zero/multiple reconciliation matches, or an unavailable helper is terminal and never falls back to UI, `-agentpass`, a plaintext recovery file, `security -g`, or a command-line secret.
- Every attach is issued by the attested persistent broker with `-stdinpass`, `-owners on`, `-nobrowse`, and the exact controlled mount. Every detach is fresh-attested and normal, never forced.
- Keep `CORTEX_HOME`, settings, SQLite, logs, pids, locks, venv, helpers, attachments, runs, and private quarantine on the local internal disk. External storage receives only the canonical directories and allowlisted imported data.
- External directories are exactly `00_INDEX`, `10_SOURCE`, `20_WORKSPACES`, `30_EVIDENCE`, `50_CACHE_REBUILDABLE/browser-profiles`, `90_ARCHIVES`, and `99_QUARANTINE`, all real owner-only `0700` directories on the verified APFS device; `40_ARCHIVES` is invalid.
- Required or release runtime accepts only `browser_transport=chrome_extension`. `playwright` and `webbridge` remain development-fixture-only when required storage is absent, and rejection happens before driver construction.
- `CORTEX_STORAGE_BOOTSTRAP` and `CORTEX_STORAGE_REQUIRED_MARKER` are either unset or resolve to the exact private files under the verified `CORTEX_HOME`; alternate overrides fail closed.
- Lock order is `.install.lock` → `storage-state.lock` → `storage-admission.lock`, acquired once by the outer caller. Mutations use install-shared/storage-exclusive/admission-exclusive; guard/Doctor/selftest probes use install-shared/storage-shared/admission-exclusive; installer/update/uninstall use all three exclusive. The broker client never reacquires a lock. All waits are bounded.
- `storage-transition.json` blocks start, server, API readiness, Doctor, and selftest in every state except a verified `committed`; rollback runs only while Cortex is verified stopped.
- `WorkspaceHandle`, `StorageBinding`, `StorageContract.open_workspace_locked()`, mission admission, and the generic executor remain strictly vault-only: accepted workspace relative paths have the exact first component `20_WORKSPACES`; Desktop, Documents, Downloads, `LocalAliasRef`, and `LocalAliasHandle` never enter these interfaces.
- `StorageContract.assert_runtime_ready_locked(lock_set) -> StorageStatus` is read-only. It opens no standard alias, creates no binding/handle/grant/approval/effect, and fails closed before a later `local_alias_action` can proceed when required storage is absent, detached, contradictory or transitioning, or when the current process lacks a valid consumed managed-start lease.
- With no required-storage marker, only a managed product runtime may receive `RUNTIME_READY`; the explicit development fixture may run without the vault but cannot use that absence to authorize a local-alias action.
- This plan does not implement `LocalAliasHandle`, `LocalAliasActionService`, `executor/local_alias_worker.py`, alias catalog/grants, `mkdirat`, local access checks, TCC prompting, or any Desktop/Documents/Downloads mutation. Those remain sequential downstream-plan ownership.
- The common storage CLI envelope is exactly `{schema_version:1, operation, verdict:"PASS|FAIL|UNCLEAR", transaction_id, code, checks:[{id,status,evidence}], private_paths_redacted:true}`. Both verdict fields use only `PASS`, `FAIL`, or `UNCLEAR`; evidence contains stable non-sensitive tokens, never a secret or private path.
- `status` adds exactly `storage_state`, `mounted`, `runtime_allowed`, and `recovery:"UNCLEAR"`. It does not infer readiness from path existence.
- `scripts/cortex.sh extension-path --json` returns only an installed local extension path whose existence and manifest hash are verified; it never points to the external repository checkout that stop will detach.
- No unrestricted process execution, arbitrary source/destination import, `sudo`, ownership-setting change, external network expansion, browser-profile copy, production publication, merge, tag, push, or unrelated refactor belongs to this plan.
- A single-`PYTHON` test-all invocation is a migration error with code `S3_DUAL_PYTHON_REQUIRED`. Source commands use the absolute repository root as `PYTHONPATH=<root>/console:<root>` and run under distinct Python 3.11 and 3.14; installed-app tests clear that root and make the checkout inaccessible. Legacy `$PYTHON` blocks below are command templates only: execution substitutes each equipped interpreter with that absolute import root, and literal mono-Python execution is forbidden.
- The sole Phase S DAG is Foundation Tasks `1, 2` → S3 Tasks `1-5` (broker/client core with injected attestation; these replace Foundation Task 3) → Foundation Tasks `6, 5, 7, 8, 9, 10, 11`, atomic `12+13`, then `14` (all consumers use injected backends) → S3 Task `6` (PASS-only integration gate over those existing behaviors) → the atomic Foundation Task `4` + S3 Task `7` installation unit → S3 Tasks `8-12`. A later task never asks for RED on a behavior an earlier task already created, and no file or production behavior is created twice. The completion ledger names the reviewed legacy boundary `S3_FAIL_frozen`, this corrective contract `S3_corrective`, and the resulting implementation checkpoint `S4`.
- Before the first S4 production or test edit, the completion ledger must already contain the independent `S3_corrective` PASS review ID and exact reviewed design/plan hashes; S4 binds that ID and the reviewed planning base. A pending, failed, unclear, stale, or missing review stops this plan.
- Tasks 12 and 13 are one reviewable unit. Write both tasks' tests before production code, run the union as RED, implement the blocked lease primitives before wiring runtime mount/start, retain the `StorageBinding` until the exact ACK, run the complete union as GREEN, and create only the combined commit specified at the end of Task 13. The individual Task 12 commit boundary is deliberately suppressed; no test or acceptance criterion is removed.

---

## File map and ownership

| File | Responsibility in this plan |
| --- | --- |
| `console/storage_result.py` | Strict redacted result/check schema plus the canonical `StorageStatus` shared by transition, contract and operator code. |
| `console/storage_lock.py` | Sole descriptor-verified `StorageLockSet` for install → storage → admission, with existing-marker attestation, bounded shared/exclusive locking, and no nested acquisition. |
| `native/macos/storage_mount_probe.swift` | `fstatfs(2)` facts for one inherited directory FD without reopening a path. |
| `native/macos/disk_image_keychain.swift` | Persistent S3 broker: secret generation, owned native children, Keychain add/read/delete, mount, attested normal detach, terminal retention. |
| `console/native_helpers.py` | Ordered helper definitions, manifest attestation, pre-spawn verification, and stable helper invocation. |
| `console/installer.py` | Transactional installation/Doctor/uninstall policy for three helpers and the installed local extension copy. |
| `console/storage_transition.py` | Snapshot manifest, journal phases, exact resume, publication, reconciliation, and idempotent rollback. |
| `console/storage_reconciliation.py` | Canonical S3 reconciliation records, probe union, postconditions, CAS, and terminal-broker ACK handshake. |
| `console/storage_broker.py` | S3 native backend, private probe, durable broker ledger and recovery; never a public lifecycle façade. |
| `console/storage_lifecycle.py` | FD-first seven-method authority that constructs broker requests internally and reconciles native results into the transition journal. |
| `console/storage_contract.py` | Sole fail-closed vault authority, retained `StorageBinding`, and read-only managed-runtime readiness assertion. |
| `executor/workspace_handle.py` | Complete vault-only persistent-FD workspace interface for later general-mission executor/effect integration. |
| `tests/test_storage_runtime_ready.py` | Local-alias consumer boundary matrix proving failed storage/transition/lease state cannot reach a downstream admission callback. |
| `console/storage_guard.py` | Thin CLI adapter over `StorageContract`, preserving stable storage exit codes. |
| `console/settings.py`, `transport/browser.py` | Immutable storage projection and pre-factory `chrome_extension` clamp. |
| `console/storage_import.py`, `scripts/import-cortex-storage.py` | Receipt-bound descriptor copy and exact-ref Git import, exposed only through the import script. |
| `scripts/cortex-storage.py` | Redacted operator façade with the eight approved subcommands. |
| `scripts/configure-external-storage.py` | Compatibility wrapper that delegates publication/rollback to the journaled implementation. |
| `console/startup_lease.py`, `console/process_ownership.py`, `console/server.py` | Blocked child handshake, one-shot lease validation/consumption, and lifespan enforcement. |
| `scripts/cortex.sh`, `scripts/start-local.sh` | One-click mount/start and stop/detach ownership; installed extension path query. |

### Task 1: Redacted result schema and ordered storage lock

**Files:**
- Modify: `console/storage_result.py`
- Modify: `console/storage_lock.py`
- Modify: `tests/test_storage_lock.py`
- Modify: `tests/test_installer.py`

**Interfaces:**
- Consumes: `console.lifecycle_lock.open_lifecycle_lock(path: Path) -> int` for canonical private marker creation.
- Produces: `CheckResult`, `OperationResult`, canonical `StorageStatus`, and the
  sole public lock entrypoint
  `ordered_storage_locks(home, *, install_mode, storage_mode,
  bootstrap_install=None, timeout_seconds=5.0) ->
  ContextManager[StorageLockSet]`. Lower-level marker
  opens are private and reject acquisition while the caller already owns any
  member of a lock set.

- [ ] **Step 1: Write failing schema and lock tests**

Create tests that reject lowercase/unknown verdicts, path-shaped evidence, extra output fields, unsafe/symlink/hardlinked lock markers, and reversed lock ordering. Prove a shared holder coexists with another shared holder, excludes an exclusive holder until release, and times out with `STORAGE_LOCK_TIMEOUT` without running its callback. Prove the sole public ordered context never creates a missing marker outside installation, returns `STORAGE_LOCK_MISSING`, and leaves the private runtime directory identity and entries unchanged. Forge a wrong-home, closed, wrong-mode, missing-admission, replaced-marker, and nested lock set; `assert_active` must reject each before any callback or attestation.
With an injected `BootstrapInstallLease`, prove the context adopts the already
shared-locked exact install FD without reopening/relocking it, then acquires
storage and admission. Reject wrong-home, closed, replaced, exclusive-request,
or identity-mismatched leases before reading a generation byte.

Define and test the exact bundle:

```python
LockMode = Literal["shared", "exclusive"]

class BootstrapInstallLease(Protocol):
    home: Path
    install_lock_fd: int
    install_lock_dev_u32: int
    install_lock_ino: int
    install_lock_uid: int
    install_lock_mode: Literal[384]
    active: bool

@dataclass(slots=True)
class StorageLockSet:
    home: Path
    home_dev_u32: int
    home_ino: int
    home_uid: int
    home_mode: Literal[448]
    install_fd: int
    install_dev_u32: int
    install_ino: int
    install_uid: int
    storage_fd: int
    storage_dev_u32: int
    storage_ino: int
    storage_uid: int
    admission_fd: int
    admission_dev_u32: int
    admission_ino: int
    admission_uid: int
    install_mode: LockMode
    storage_mode: LockMode
    admission_mode: Literal["exclusive"]
    marker_mode: Literal[384]
    deadline_ns: int
    active: bool
    def assert_active(self, *, home: Path,
                      required_install_mode: LockMode,
                      required_storage_mode: LockMode) -> None: ...
    def close(self) -> None: ...

def ordered_storage_locks(
    home: Path, *, install_mode: LockMode, storage_mode: LockMode,
    bootstrap_install: BootstrapInstallLease | None = None,
    create_markers: Literal["never", "installer"] = "never",
    timeout_seconds: float = 5.0,
) -> ContextManager[StorageLockSet]: ...
```

The one common monotonic deadline covers no-follow creation/attestation and
acquisition of `.install.lock`, `storage-state.lock`, then
`storage-admission.lock`. Each is regular, single-link, current-UID mode `0600`
under a current-UID mode `0700` directory. Release reverses order in `finally`.
Lifecycle, contract/readiness, guard, Doctor, selftest, runtime, installer, and
reconciliation receive the acquired bundle and call only `*_locked` internals;
nested acquisition is `STORAGE_LOCK_NESTED`. `assert_active` revalidates the
home and all three marker FD identities, current UID, modes, active flag, and
mode sufficiency; exclusive satisfies a shared requirement, never the reverse.

```python
result = OperationResult(
    operation="status",
    verdict="PASS",
    transaction_id="8ce4e7ce-8e9a-45ef-a112-64a14dfc1c83",
    code="STORAGE_READY",
    checks=(CheckResult("journal", "PASS", "committed_transaction_verified"),),
)
assert result.to_dict() == {
    "schema_version": 1,
    "operation": "status",
    "verdict": "PASS",
    "transaction_id": "8ce4e7ce-8e9a-45ef-a112-64a14dfc1c83",
    "code": "STORAGE_READY",
    "checks": [{"id": "journal", "status": "PASS", "evidence": "committed_transaction_verified"}],
    "private_paths_redacted": True,
}
with self.assertRaisesRegex(StorageLockError, "STORAGE_LOCK_TIMEOUT"):
    with ordered_storage_locks(
        home, install_mode="shared", storage_mode="exclusive",
        timeout_seconds=0.05,
    ):
        self.fail("contended callback reached")
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" -m unittest tests.test_storage_lock -v
```

Expected: FAIL because the current lock implementation has no exact three-lock
`StorageLockSet`, admission marker, shared deadline, or nested-acquire refusal.

- [ ] **Step 3: Implement the strict data and lock contracts**

Use these exact public types and reject `/`, `~`, URI schemes, control characters, UUID-like secrets longer than the explicitly allowed transaction ID field, or environment-derived text in `checks[].evidence`:

```python
Verdict = Literal["PASS", "FAIL", "UNCLEAR"]
LockMode = Literal["shared", "exclusive"]

@dataclass(frozen=True)
class CheckResult:
    id: str
    status: Verdict
    evidence: str

@dataclass(frozen=True)
class StorageStatus:
    verdict: Verdict
    code: str
    transaction_id: str | None
    storage_state: str
    mounted: bool
    runtime_allowed: bool
    recovery: Literal["UNCLEAR"] = "UNCLEAR"

@dataclass(frozen=True)
class OperationResult:
    operation: str
    verdict: Verdict
    transaction_id: str | None
    code: str
    checks: tuple[CheckResult, ...]
    storage_state: str | None = None
    mounted: bool | None = None
    runtime_allowed: bool | None = None
    recovery: Literal["UNCLEAR"] | None = None
    def to_dict(self) -> dict[str, object]: ...

class StorageLockError(RuntimeError):
    code: str

class BootstrapInstallLease(Protocol):
    home: Path
    install_lock_fd: int
    install_lock_dev_u32: int
    install_lock_ino: int
    install_lock_uid: int
    install_lock_mode: Literal[384]
    active: bool

@dataclass(slots=True)
class StorageLockSet:
    home: Path
    home_dev_u32: int
    home_ino: int
    home_uid: int
    home_mode: Literal[448]
    install_fd: int
    install_dev_u32: int
    install_ino: int
    install_uid: int
    storage_fd: int
    storage_dev_u32: int
    storage_ino: int
    storage_uid: int
    admission_fd: int
    admission_dev_u32: int
    admission_ino: int
    admission_uid: int
    install_mode: LockMode
    storage_mode: LockMode
    admission_mode: Literal["exclusive"]
    marker_mode: Literal[384]
    deadline_ns: int
    active: bool
    def assert_active(self, *, home: Path,
                      required_install_mode: LockMode,
                      required_storage_mode: LockMode) -> None: ...
    def close(self) -> None: ...

def ordered_storage_locks(
    home: Path, *, install_mode: LockMode, storage_mode: LockMode,
    bootstrap_install: BootstrapInstallLease | None = None,
    create_markers: Literal["never", "installer"] = "never",
    timeout_seconds: float = 5.0,
) -> ContextManager[StorageLockSet]: ...
```

`create_markers="installer"` is accepted only with install/storage exclusive and
creates all three markers through private no-follow helpers. Every other caller
uses the default `"never"`; missing markers fail closed. Then use
`fcntl.flock(..., LOCK_SH|LOCK_NB)` or `LOCK_EX|LOCK_NB` with one monotonic
deadline and 20 ms capped polling. The context acquires install, storage, and
admission in that order and releases them in reverse order in `finally`. No
lower-level lock opener is public.
When `bootstrap_install` is present, `install_mode` must be `shared`; the
context validates and adopts its already-held exact install open-file
description, never reacquires it, and still acquires storage then admission
against the same deadline. This is the only product-runtime path from the stable
bootstrap into a complete `StorageLockSet`.
`OperationResult.to_dict()` always emits the seven common keys in the global constraint and rejects non-status use of the four status-only fields. For `operation="status"`, it emits those seven plus all four non-optional status additions; it never serializes a `None` status field for another operation.

- [ ] **Step 4: Run GREEN tests**

Run:

```bash
"$PYTHON" -m unittest tests.test_storage_lock tests.test_process_ownership -v
```

Expected: PASS; existing lifecycle lock behavior remains unchanged and the new lock tests prove bounded contention and ordering.

- [ ] **Step 5: Commit the atomic foundation**

```bash
git add console/storage_result.py console/storage_lock.py tests/test_storage_lock.py tests/test_installer.py
git commit -m "feat(storage): add redacted results and ordered lock"
```

### Task 2: Descriptor-only mount probe helper

**Files:**
- Modify: `native/macos/storage_mount_probe.swift`
- Modify: `tests/test_storage_mount_probe.py`

**Interfaces:**
- Consumes: one inherited directory FD supplied as decimal `--fd FD_NUMBER`; no path argument is accepted.
- Produces: one JSON line `{schema_version:1,st_dev_u32:uint32,fsid_u32:[uint32,uint32],flags:uint64,filesystem_type:str,mount_from:str,mount_on:str}` and exit codes `0` success, `64` invalid input, `70` `fstat`/`fstatfs` failure. Every Darwin `dev_t`/`fsid_t` component is encoded as `UInt32(bitPattern:)`; Python preserves the `0...UInt32.max` bit pattern and converts back to signed only for native comparison.

- [ ] **Step 1: Write the failing native contract tests**

Compile the source with the equipped SDK and test the exact same inherited FD, a closed FD, a regular-file FD, unexpected arguments, and deterministic FD replacement. Assert the JSON key set exactly and compute ownership/noatime from flags in Python rather than parsing localized `diskutil` text.

```python
directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
completed = subprocess.run(
    [str(binary), "--fd", str(directory_fd)],
    pass_fds=(directory_fd,), capture_output=True, text=True, check=False,
)
payload = json.loads(completed.stdout)
self.assertEqual(set(payload), {
    "schema_version", "st_dev_u32", "fsid_u32", "flags",
    "filesystem_type", "mount_from", "mount_on",
})
self.assertEqual(payload["schema_version"], 1)
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_storage_mount_probe.py
```

Expected: FAIL because the current probe does not yet satisfy every exact
descriptor, closed-key, replacement, and production-build-profile assertion. A
zero-test selection or skip is a failure.

- [ ] **Step 3: Implement the minimal Swift helper**

Use `Darwin.fstat` to require a directory, then `Darwin.fstatfs` on the inherited FD. Copy fixed-size C character arrays only up to their first NUL, serialize with `JSONSerialization`, and never call `open`, `realpath`, `URL(fileURLWithPath:)`, `diskutil`, or `hdiutil`.

```swift
struct MountFacts: Codable {
    let schema_version: Int
    let st_dev_u32: UInt32
    let fsid_u32: [UInt32]
    let flags: UInt64
    let filesystem_type: String
    let mount_from: String
    let mount_on: String
}

func probe(fd: Int32) throws -> MountFacts
```

Require `fcntl(fd, F_GETFD) != -1`, `S_IFDIR`, two-element `fsid_u32`, valid UTF-8 filesystem/mount strings without control characters, and exactly one newline-terminated JSON result. Golden cases cover native signed values `Int32.min`, `-1`, `0`, and `Int32.max` and their exact unsigned JSON projections.

- [ ] **Step 4: Run GREEN tests and compile the production form**

Run:

```bash
"$PYTHON" tests/test_storage_mount_probe.py
xcrun swiftc native/macos/storage_mount_probe.swift -o /tmp/cortex-storage-mount-probe-plan-test
codesign --force --sign - /tmp/cortex-storage-mount-probe-plan-test
codesign --verify --strict /tmp/cortex-storage-mount-probe-plan-test
rm /tmp/cortex-storage-mount-probe-plan-test
```

Expected: PASS with no skipped native test; `codesign --verify --strict` exits `0`.

- [ ] **Step 5: Commit the helper**

```bash
git add native/macos/storage_mount_probe.swift tests/test_storage_mount_probe.py
git commit -m "feat(storage): add descriptor mount probe"
```

### Task 3: Freeze the unsafe one-shot boundary as `S3_FAIL_frozen`

**Normative disposition:** This is a frozen finding, not an implementation
task. Inspect the existing test-compiled
`native/macos/disk_image_keychain.swift` and
`tests/test_disk_image_keychain_helper.py`, and retain the reviewed proof that
terminating the one-shot helper can leave its native group reparented. Record
that rejected boundary as `S3_FAIL_frozen`. Do not modify, compile, invoke,
install, stage, or commit a one-shot `disk-image-keychain` route from this
task. S3 Tasks 1-5 own the next source/test changes and require their own RED
selection before creating the persistent broker/client core.

The one-shot JSON-stdin interface, per-call helper lifecycle, direct detach
device input, and any claim that helper exit proves child cleanup are
superseded. They are neither an accepted interface nor a compatibility path.

### Task 4: Install the three-helper registry and persistent S3 broker

**Files:**
- Create: `console/native_helpers.py`
- Create: `native/build-profiles/macos-ax-send-v1.json`
- Create: `native/build-profiles/storage-mount-probe-v1.json`
- Create: `native/build-profiles/storage-broker-v1.json`
- Modify: `console/installer.py`
- Modify: `transport/browser_chrome_extension.py`
- Modify: `scripts/cortex.sh`
- Modify: `tests/test_installer.py`
- Modify: `tests/test_chrome_extension_driver.py`
- Modify: `tests/test_cortex_shell_guards.py`

**Interfaces:**
- Consumes: the AX source `transport/macos_ax_send.swift`, the Task 2 mount-probe
  source, the persistent broker source completed by S3 Tasks 1-5, existing
  installer transaction primitives, and the Task 1 `StorageLockSet`.
- Produces: ordered `NATIVE_HELPERS`, S3 `AttestedBrokerExecutable`, manifest
  `owned.json["native_helpers"]`, and `cortex.sh extension-path --json`. Disk
  operations use `StorageBrokerClient`; `run_attested_helper` remains only for
  `macos-ax-send` and `storage-mount-probe` and cannot run a disk helper.

- [ ] **Step 1: Write failing installer/lifecycle tests**

Extend installer tests to require this exact order and record shape:

```python
self.assertEqual(list(manifest["native_helpers"]), [
    "macos-ax-send", "storage-mount-probe", "storage-broker",
])
for record in manifest["native_helpers"].values():
    self.assertEqual(set(record), {
        "target", "source", "source_sha256", "build_profile_sha256",
        "sha256", "cdhash",
        "dev_u32", "ino", "uid", "mode",
    })
    self.assertEqual(record["mode"], 0o700)
```

Cover `xcrun swiftc`, ad-hoc signing, strict signature verification, staged fsync/publication rollback, source/profile/binary/CDHash/device/inode/owner/mode tampering, helper execution refusal before spawn, compatible stopped update, incompatible update refusal, and whole-operation uninstall refusal while a vault is configured. Also require an exact local extension copy, ordered relative file manifest, reinstall hash stability, tamper failure, and all-or-nothing preservation during vault-aware uninstall.

```python
payload = json.loads(self.run_script("cortex.sh", "extension-path", "--json").stdout)
self.assertEqual(payload["status"], "verified")
self.assertEqual(Path(payload["path"]), self.cortex_home / "app" / "chrome-extension")
self.assertNotIn(str(ROOT / "chrome-extension"), payload["path"])
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" -m unittest \
  tests.test_installer.InstallerTest.test_fresh_install_compiles_helper_in_staging_and_records_exact_ownership \
  tests.test_installer.InstallerTest.test_storage_helpers_are_attested_and_vault_aware \
  tests.test_installer.InstallerTest.test_installed_extension_path_is_local_and_hash_verified \
  tests.test_chrome_extension_driver \
  tests.test_cortex_shell_guards -v
```

Expected: FAIL because the manifest has one `native_helper`, the storage helpers are unknown, and `extension-path` is absent.

- [ ] **Step 3: Implement ordered helper and extension installation**

Define:

```python
@dataclass(frozen=True)
class NativeHelperSpec:
    name: str
    source: Path
    target_name: str
    build_profile: Path
    frameworks: tuple[str, ...] = ()

NATIVE_HELPERS: tuple[NativeHelperSpec, ...] = (
    NativeHelperSpec("macos-ax-send", ROOT / "transport/macos_ax_send.swift", "cortex-macos-ax-send", ROOT / "native/build-profiles/macos-ax-send-v1.json"),
    NativeHelperSpec("storage-mount-probe", ROOT / "native/macos/storage_mount_probe.swift", "storage-mount-probe", ROOT / "native/build-profiles/storage-mount-probe-v1.json"),
    NativeHelperSpec("storage-broker", ROOT / "native/macos/disk_image_keychain.swift", "cortex-storage-broker", ROOT / "native/build-profiles/storage-broker-v1.json", ("Security",)),
)

@dataclass(frozen=True)
class AttestedHelper:
    name: str
    path: Path
    fd: int
    sha256: str
    cdhash: str
    def close(self) -> None: ...
```

Compile into private staging with `xcrun swiftc`, append `-framework Security` only for the Keychain helper, chmod `0700`, run `codesign --force --sign -`, verify `codesign --verify --strict`, extract CDHash from `codesign -dvv`, and publish all helper records in one ordered manifest replacement under install/storage/admission exclusive locks. Before spawn, open the generation's `app/bin` by FD, compare path and opened FD, every recorded field including `dev_u32`, SHA-256 and live CDHash. `run_attested_helper` may launch only AX or `storage-mount-probe --fd`; broker launch uses the lock-bound client path.

The S3 installer unit replaces `CORTEX_HOME/native` disk-helper publication with
one `installed_storage_runtime_generation`: `app/bin` contains the broker,
mount probe, and AX helper; `app/python` contains the installed application;
`app/scripts`, `app/native-src`, and `app/build-profiles` contain the exact
scripts, three native sources, and three canonical build profiles;
`app/chrome-extension` contains the installed extension; `owned.json` contains
the interpreter identity and complete ordered manifest. Its
recoverable transaction binds and publishes all of these resources as one
generation, publishes exactly three `owned.json["native_helpers"]` entries in
the order above with the same closed field set, and refuses a mixed generation.
Installed commands import only `app/python`; wheel tests clear the checkout
import root and use a homonymous-module sentinel.

Copy `chrome-extension` descriptor-relatively to `CORTEX_HOME/app/chrome-extension`, reject symlinks/special files/device changes, fsync every file/directory, and add its ordered relative SHA-256 manifest to `owned.json`. `extension-path --json` verifies the copy against that record before returning exactly four keys: `schema_version=1`, `status="verified"`, `path=str(CORTEX_HOME / "app" / "chrome-extension")`, and `manifest_sha256` as 64 lowercase hex characters. This command is the deliberate exception that returns its required local path; storage operator results remain redacted. Replace `transport/browser_chrome_extension.py` runtime compilation with `attest_helper("macos-ax-send", manifest)` and pre-spawn FD/hash/signature revalidation; migrate the old single-helper manifest/path transactionally rather than silently adopting it.

Treat legacy `owned.json["chrome_extension_path"]` as untrusted historical metadata: never open, traverse, copy from, attest, or return that path. The only migration source is the reviewed `chrome-extension` tree in the current implementation checkout, copied descriptor-relatively into private installer staging. Keep the old installed manifest byte-identical until every staged extension file and directory is fsynced, its ordered relative manifest is verified, and the staging parent is fsynced; then atomically publish the local copy and the new owned-manifest record. A crash must leave either the exact old state or one complete verified new state, never a mixed record/tree. A successful migration removes `chrome_extension_path`, is idempotent on reinstall, and `extension-path --json` must fail closed if any legacy field survives. Add tests for hostile/symlinked legacy values, crash at every publication boundary, rollback, idempotent retry, and absence of the legacy field after success.

- [ ] **Step 4: Implement Doctor/rebuild/uninstall fail-closed behavior and run GREEN**

Doctor returns one required check per helper, the complete generation, and the local extension. Update/reinstall may publish a compatible generation only while runtime is proven stopped, every broker workflow is durably closed, every transition effect is reconciled, and no unresolved record exists; the presence of a compatible vault Keychain item alone is not a veto. Any incompatible schema/build profile, unreadable reconciliation state, or failed attestation refuses before publication. Publication and rollback cover the complete generation atomically. If a vault bootstrap/journal configures a vault, uninstall refuses the whole operation with `STORAGE_VAULT_CONFIGURED` and preserves the generation byte-for-byte; it does not partially remove application, Python, scripts, helpers, profiles, manifest, interpreter, or extension. Without a configured vault, uninstall removes only resources whose full manifest identity still matches and never calls a helper delete operation or signals a foreign process.

Run:

```bash
"$PYTHON" -m unittest tests.test_installer tests.test_chrome_extension_driver \
  tests.test_cortex_shell_guards -v
```

Expected: PASS; helper tamper is detected before execution, local extension resolution never depends on the repo after install, and uninstall cannot strand the vault.

- [ ] **Step 5: Preserve the atomic installer unit and continue to S3 Task 7**

```bash
git diff --check
git status --short
```

Expected: only the Foundation Task 4 and S3 Task 7 installation-unit files are
modified. Do not stage or commit; S3 Task 7 adds the installed aggregate,
checkout-inaccessible tests, and the single atomic commit for this union.

### Task 5: FD-first preflight and storage lifecycle primitives

**Files:**
- Create: `console/storage_lifecycle.py`
- Create: `tests/test_storage_lifecycle.py`
- Modify: `console/cortex_paths.py`

**Interfaces:**
- Consumes: attested `storage-mount-probe`, S3 `StorageBrokerClient`, the active
  Task 1 `StorageLockSet`, Task 6 `TransitionJournal`,
  `load_transition_locked`, `advance_transition_locked`, and exact locked
  journal publication. Every
  `hdiutil`/`diskutil` operation and private mapping probe goes through the
  broker; no direct runner or raw caller request exists.
- Produces: `StoragePaths`, `HostBinding`, `LegacySnapshot`, and the seven lock-carrying methods `StorageLifecycle.preflight_locked()`, `.keychain_spike_locked()`, `.create_vault_locked()`, `.initialize_layout_locked()`, `.mount_or_adopt_locked()`, `.detach_locked()`, and `.status_locked()`.

- [ ] **Step 1: Write failing no-effect lifecycle tests**

Use temporary directories, a fake S3 broker, and fake descriptor probes. Prove all of the following ordering and failure behavior:

- host FD opens with `O_DIRECTORY | O_NOFOLLOW` and remains live through each operation/post-check;
- host `volume_uuid`, `filesystem_type`, `fsid`, mount point, and `MNT_NOATIME` match before any legacy snapshot function is called;
- a no-`MNT_NOATIME` result yields `HOST_NOATIME_REQUIRED` and the legacy open/hash spy has zero calls;
- `NEW_IMAGE` and `NEW_MOUNT` must be absent, the legacy/new basenames differ, and 320 GiB free is required before create;
- host replacement/disconnect between pre/post probe yields `HOST_IDENTITY_CHANGED`;
- legacy evidence is limited to canonical no-symlink path, file count, allocated bytes, and hashes for `Info.plist`, `Info.bckup`, and `token`;
- create sends one non-secret request to the helper, never logs its request paths, and never deletes on failure;
- production create requires `diskutil verifyVolume` success without repair after each verified attach, performs two normal detach/remount proofs, and uses a third attach for the live cutover mount;
- mount-or-adopt adopts only after the injected mounted-storage verifier returns `PASS`; verifier `FAIL`/`UNCLEAR` leaves the image attached for diagnosis but returns failure, while detach is normal and verifies no mapping plus an empty mount point;
- initialize-layout creates only the exact directory tree with mode `0700`, current UID, same APFS device, and no symlink component.

```python
lifecycle = StorageLifecycle(
    paths,
    broker=fake_broker,
    fd_probe=fake_fd_probe,
    mount_verifier=fake_mount_verifier,
)
status = lifecycle.preflight_locked(lock_set)
self.assertEqual(status.code, "HOST_NOATIME_REQUIRED")
self.assertEqual(legacy_snapshot_spy.call_count, 0)

self.assertEqual(lifecycle.layout_names, (
    "00_INDEX", "10_SOURCE", "20_WORKSPACES", "30_EVIDENCE",
    "50_CACHE_REBUILDABLE", "90_ARCHIVES", "99_QUARANTINE",
))
self.assertFalse((storage_root / "40_ARCHIVES").exists())
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" -m unittest tests.test_storage_lifecycle -v
```

Expected: FAIL because `console.storage_lifecycle` does not exist.

- [ ] **Step 3: Implement exact path and lifecycle types**

Add local runtime fields to `CortexPaths` without moving existing state: `native`, `mounts`, `private_quarantine`, `storage_transition`, and `storage_lock`. Define:

```python
@dataclass(frozen=True)
class StoragePaths:
    home: Path
    host_volume: Path
    legacy_image: Path
    new_image: Path
    mount: Path
    root: Path
    bootstrap: Path
    marker: Path
    transition: Path
    quarantine: Path

@dataclass
class HostBinding:
    fd: int
    volume_uuid: str
    filesystem_type: str
    fsid_u32: tuple[DarwinU32, DarwinU32]
    mount_from: str
    flags: int
    def close(self) -> None: ...

@dataclass(frozen=True)
class LegacySnapshot:
    file_count: int
    allocated_bytes: int
    metadata_sha256: Mapping[str, str]

MountVerifier = Callable[[StorageLockSet], OperationResult]

class StorageLifecycle:
    def __init__(self, paths: StoragePaths, *, broker: StorageBrokerClient,
                 fd_probe: FdProbe,
                 mount_verifier: MountVerifier) -> None: ...
    def preflight_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def keychain_spike_locked(self, lock_set: StorageLockSet, *,
                              cleanup_approved: bool) -> OperationResult: ...
    def create_vault_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def initialize_layout_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def mount_or_adopt_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def detach_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
    def status_locked(self, lock_set: StorageLockSet) -> OperationResult: ...
```

Every method validates the active same-home install/storage/admission set before
using the injected broker or FD probe. Mutations require storage-exclusive;
preflight/status may use storage-shared. The constructor performs no installed
attestation and Tasks 5-14 exercise only injected backends.
`mount_or_adopt_locked(lock_set)` passes that exact object to `mount_verifier`;
a verifier may not capture or substitute another set. Tests cover absent,
different, closed, replaced, and captured-A/passed-B sets before any read or
broker call.

Open and traverse relative names from `host_fd`; reject symlinks and special files with `os.stat(..., dir_fd=..., follow_symlinks=False)`. Reprobe the same FD before and after each subprocess/helper call. Treat ExFAT inode as observational only; bind host identity to UUID, fsid, filesystem type, mount-from, and retained FD. Snapshot the three legacy metadata names read-only only after host/noatime/absence/free-space/attachment gates, and never read `bands/*`. Create `CORTEX_HOME/mounts` and the exact empty mount leaf through a pinned local owner-only no-follow chain, both mode `0700`; never use `/Volumes`.

- [ ] **Step 4: Implement spike/create/layout/mount/detach state machines and run GREEN**

`keychain_spike_locked` begins or resumes the one exact Task 6 transition,
generates a unique disposable transaction and basename, constructs each
validated S3 request internally, invokes the locked broker create, normal
detach, two fresh-process mounts with full UUID/APFS/mount checks and detach
after each, then atomically publishes `phase="spike_passed"` with the canonical
non-secret receipt SHA-256. The gated live harness records the baseline
SecurityAgent process/window set and fails if any new prompt/process/window is
observed. Without cleanup authorization it quarantines by exact host-FD-relative
rename and leaves the item intact; with authorization it requests exact
disposable cleanup. A missing, replaced, mismatched or non-`spike_passed`
receipt blocks production creation.

`create_vault_locked` requires a journaled passed spike, records
`image_create_started` before broker invocation, and reconciles a missing
lifecycle receipt from the S3 closed private record plus transaction tag and
UUID/service. Reconciliation adopts exactly one item only after the broker
mounts that exact image twice; zero matches quarantines the unrecoverable image
before a new transaction, and multiple/mismatched matches stop for manual
review. After create, require encryption metadata, attach with `-owners on`,
exact same-FD guard, broker-owned `diskutil verifyVolume` success without
repair, normal detach/no mapping/empty mount, repeat that cycle once, then a
third attach establishes the live cutover mount. `native_cleanup_proven` never
sets `effect_reconciled`; the transition journal does so only after the S3
reconciliation handshake and operation-specific postcondition fsync.
`mount_or_adopt_locked` calls the injected verifier and adopts only `PASS`.
`detach_locked` accepts only the broker's fresh attested exact mapping and
leaves the mount directory empty.

Run:

```bash
"$PYTHON" -m unittest tests.test_storage_lifecycle tests.test_cortex_home -v
```

Expected: PASS with no real DiskImages/Keychain call; all injected race and order assertions pass.

- [ ] **Step 5: Commit lifecycle primitives**

```bash
git add console/storage_lifecycle.py console/cortex_paths.py tests/test_storage_lifecycle.py
git commit -m "feat(storage): add FD-first lifecycle primitives"
```

### Task 6: Durable transition snapshots, journal and idempotent rollback

**Files:**
- Create: `console/storage_transition.py`
- Create: `tests/test_storage_transition.py`

**Interfaces:**
- Consumes: Task 1 canonical `StorageStatus`, the active exclusive
  `StorageLockSet`, private `CORTEX_HOME` descriptor, and verified
  stopped-process callback.
- Produces: `StorageProjection`, `TransitionJournal`, `SnapshotManifest`, and
  only these lock-carrying entrypoints:

```python
def begin_transition_locked(
    lock_set: StorageLockSet, home: Path, target: StorageProjection, *,
    target_image_basename: Literal["CORTEX_BRIDGE_2026_09.sparsebundle"],
) -> TransitionJournal: ...
def advance_transition_locked(
    lock_set: StorageLockSet, journal: TransitionJournal, *,
    phase: TransitionPhase, updates: Mapping[str, object],
) -> TransitionJournal: ...
def commit_transition_locked(
    lock_set: StorageLockSet, journal: TransitionJournal,
) -> TransitionJournal: ...
def load_transition_locked(
    lock_set: StorageLockSet, home: Path,
) -> TransitionJournal | None: ...
def runtime_transition_status_locked(
    lock_set: StorageLockSet, home: Path,
) -> StorageStatus: ...
def rollback_transition_locked(
    lock_set: StorageLockSet, home: Path, *, process_status: ProcessStatus,
) -> OperationResult: ...
```

- [ ] **Step 1: Write failing snapshot/journal crash tests**

For each of `settings.json`, `storage-bootstrap.json`, and `storage-required`, parameterize originally present and absent states. Inject a crash after snapshot file fsync, manifest fsync, journal publication, each target publication, each target-parent fsync, offline verification, `rolling_back`, each restoration, and `rolled_back`. Assert that every interrupted forward/rollback phase blocks runtime and that rerunning rollback restores exact bytes, mode, and presence without choosing another quarantine.

```python
for boundary in PUBLICATION_BOUNDARIES:
    with self.subTest(boundary=boundary, originally_present=present):
        harness.crash_after(boundary)
        self.assertEqual(
            runtime_transition_status_locked(lock_set, home).runtime_allowed,
            False,
        )
        receipt = rollback_transition_locked(
            lock_set, home, process_status=STOPPED,
        )
        self.assertEqual(receipt.code, "STORAGE_ROLLBACK_COMPLETE")
        self.assertEqual(harness.current_states(), harness.original_states())
```

Also test journal schema/type validation, phase-number monotonicity, journal/path substitution, mismatched manifest hash, multiple historical quarantines, target hash mismatch, settings changes outside the storage projection, spike-receipt substitution, target-image-basename substitution, illegal phase/field combinations, and rejection of rollback when process state is not exactly `stopped`. Inject crashes immediately before and after `spike_create_started`, helper create/Keychain return, `spike_keychain_bound`, each of the two mount-verification and normal-detach cycles, disposable deletion or quarantine publication, `spike_disposition_recorded`, `spike_passed`, production `image_create_started`, and production `keychain_bound`; every resume must use the exact durable spike/production transaction, basename and optional encryption UUID and must neither create a second item nor guess a quarantine. Call every API with the same active set and test absent, different-home, closed, replaced-marker, weak-mode, and captured-A/passed-B substitutions. Every failure occurs before journal read, CAS, rename, or fsync; no public unlocked alias exists.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_storage_transition.py
```

Expected: FAIL because `console/storage_transition.py` is absent.

- [ ] **Step 3: Implement exact journal and snapshot schemas**

Use these immutable records and canonical SHA-256 over compact sorted UTF-8 JSON:

```python
@dataclass(frozen=True)
class StorageProjection:
    default_workspace: str
    browser_profile_root: str
    browser_transport: Literal["chrome_extension"]

TransitionPhase = Literal[
    "in_progress", "spike_create_started", "spike_keychain_bound",
    "spike_mount_one_verified", "spike_mount_two_verified",
    "spike_disposition_recorded", "spike_passed",
    "image_create_started", "keychain_bound",
    "bootstrap_published", "marker_published", "settings_published",
    "committed", "rolling_back", "rolled_back",
]

@dataclass(frozen=True)
class SnapshotEntry:
    name: Literal["settings.json", "storage-bootstrap.json", "storage-required"]
    present: bool
    mode: int | None
    size: int | None
    sha256: str | None
    dev_u32: DarwinU32 | None
    ino: int | None

@dataclass(frozen=True)
class SnapshotManifest:
    schema_version: Literal[1]
    entries: tuple[SnapshotEntry, SnapshotEntry, SnapshotEntry]

@dataclass(frozen=True)
class TransitionJournal:
    schema_version: Literal[1]
    transaction_id: str
    phase_number: int
    phase: TransitionPhase
    snapshot_relative: PurePosixPath
    snapshot_manifest_sha256: str
    originals: tuple[SnapshotEntry, SnapshotEntry, SnapshotEntry]
    target_bootstrap_sha256: str
    target_marker_sha256: str
    target_storage_projection_sha256: str
    target_image_basename: str
    spike_transaction_id: str | None
    spike_image_basename: str | None
    spike_encryption_uuid: str | None
    spike_disposition: Literal["deleted", "quarantined"] | None
    spike_receipt_sha256: str | None
    target_encryption_uuid: str | None
    reconciliation: Literal["not_started", "image_create_started", "keychain_bound"]
    s3_workflow_id: str | None
    s3_generation: int | None
    s3_operation: Literal[
        "create", "mount", "detach", "delete-disposable-item",
    ] | None
    s3_request_sha256: str | None
    s3_result_sha256: str | None
    effect_reconciled: bool
    reconciliation_record_sha256: str | None
```

`console/storage_transition.py` imports the sole S3 `ReconciliationRecord`,
`ReconciliationProbeRequest`, and closed `ReconciliationPostcondition` union
from `console/storage_reconciliation.py`; it declares no parallel schema. The
reconciliation module stores one current-UID mode `0600` no-follow record per
mutating workflow under the private reconciliation directory. Every transition is
`pending → reconciled|unclear`, binds workflow/generation/transaction/operation/
request/result digests, compares the previous digest, atomically replaces, and
fsyncs file and directory. `TransitionJournal.reconciliation_record_sha256`
must equal the current record; all five duplicated correlation fields must
equal that record before `effect_reconciled=true`, admission, or publication.
Read-only `inspect-item` and `probe-mounted-image` never set these transition
fields, never write a `ReconciliationRecord`, and close after exact cleanup
under storage-shared; failure is replayed later only as a new read workflow.

Every entrypoint first asserts the exact active same-home set and required mode.
Snapshot through verified descriptors into one unique `private-quarantine/` child named `f"storage-cutover-{transaction_id}"`. Fsync every file, manifest, snapshot directory, quarantine directory, then exclusively publish and fsync `storage-transition.json` in `in_progress` before any control-file change. `begin_transition_locked` receives `target_image_basename` explicitly and accepts only the literal `CORTEX_BRIDGE_2026_09.sparsebundle`; Task 6 never imports or anticipates Task 5 `StoragePaths`.

Before the disposable helper's first effect, `advance_transition_locked` durably publishes `spike_create_started` with a fresh `spike_transaction_id` and one generated `spike_image_basename`; neither may change on resume. The helper's create/Keychain receipt must be durably captured as `spike_keychain_bound` with its exact `spike_encryption_uuid` before the first mount. Each verified fresh-process mount plus normal detach advances exactly once through `spike_mount_one_verified` and `spike_mount_two_verified`. Exact approved deletion or descriptor-bound quarantine advances to `spike_disposition_recorded` with `spike_disposition`; only then may `spike_passed` add the canonical non-secret receipt SHA-256. `spike_passed` preserves all spike identifiers and has no production encryption UUID. Production `image_create_started` retains the spike proof and pins the already journaled target basename before the production helper call. Production `keychain_bound` additionally requires the helper-returned production encryption UUID. Every other phase/field combination is invalid. Resume only the exact relative snapshot whose digest matches the journal and only when every applicable spike/production identifier matches the durable prior phase. Do not archive/remove a blocking journal before `rolled_back` is durably written.

- [ ] **Step 4: Implement deterministic forward publication and rollback; run GREEN**

Use exclusive temporary files and `renameatx_np(..., RENAME_EXCL)`/verified swap primitives. Forward publication order is bootstrap, marker, settings while journal remains blocking; after reopening and hashing all three and running the offline contract, write `committed`. Rollback first writes `rolling_back`, restores exact present bytes/mode or exact absence, reopens and compares all states, then writes `rolled_back`. Every replacement and parent directory is fsynced.

Run:

```bash
"$PYTHON" tests/test_storage_transition.py
```

Expected: PASS for every crash boundary and both presence matrices; no snapshot guessing or partial runtime allowance occurs.

- [ ] **Step 5: Commit durable transition support**

```bash
git add console/storage_transition.py tests/test_storage_transition.py
git commit -m "feat(storage): journal cutover and rollback"
```

### Task 7: FD-first guard, core workspace binding and sole StorageContract authority

**Files:**
- Create: `executor/workspace_handle.py`
- Create: `console/storage_contract.py`
- Modify: `console/storage_guard.py`
- Modify: `scripts/check-cortex-storage.py`
- Modify: `tests/test_storage_guard.py`
- Modify: `tests/test_storage_guard_integration.py`

**Interfaces:**
- Consumes: exact committed transition/bootstrap, S3 private broker probe,
  mount probe, and descriptor host/image facts. All `diskutil`/`hdiutil`
  observations preserve APFS/encryption/mapping identities through the broker.
- Produces: canonical `executor.workspace_handle.MountFacts`, a core vault-only `WorkspaceHandle` returned by general-mission admission, `StorageStatus`, `StorageBinding`, `StorageContract`, stable `check_required_storage(home: Path) -> int`, and redacted `storage-check --json`.

- [ ] **Step 1: Write failing same-FD/identity/ownership tests**

Extend unit/integration tests to cover missing/failed probe, `MNT_IGNORE_OWNERSHIP` set, missing host `MNT_NOATIME`, probe-before/after device/fsid/mount-from/mount-on/flags change, mount path replacement, cloned APFS UUID, wrong volume name, wrong encryption UUID, wrong canonical image, multiple image mappings, image device mismatch, storage-root symlink/cross-device, hostile env overrides, and active transition. Prove `open_workspace_locked()` accepts exactly the vault `20_WORKSPACES` root or a descriptor-opened descendant and rejects `Desktop`, `Documents`, `Downloads`, `20_WORKSPACES-escape`, absolute local paths, and an object shaped like `LocalAliasRef` before duplicating a workspace FD. Task 13, after creating the lease implementation, owns the mounted-but-unleased direct-Uvicorn regression.

```python
before = MountFacts(41, (9, 10), 0, "apfs", "/dev/disk9s1", str(mount))
after = dataclasses.replace(before, fsid_u32=(9, 11))
with self.assertRaisesRegex(StorageContractError, "STORAGE_DESCRIPTOR_CHANGED"):
    contract.open_locked(lock_set)

ignored = dataclasses.replace(before, flags=MNT_IGNORE_OWNERSHIP)
self.assertEqual(contract.probe_locked(lock_set).code, "STORAGE_OWNERSHIP_IGNORED")
self.assertFalse(contract.probe_locked(lock_set).runtime_allowed)
```

Require `diskutil info -plist` to be called on `mount_from` (`/dev/disk…`), never on a path, and assert no test/parser expects a localized `Owners` field.
Force private-probe success, ordinary failure, client crash, and ambiguous
cleanup under storage-shared. Success/failure must durably close with
`reconciliation_required=false` and no lock upgrade or transition write;
ambiguous cleanup remains `OPEN_UNRESOLVED`. A later exact probe uses a new
read-only workflow rather than replaying START or reusing the old result.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_storage_guard.py
"$PYTHON" tests/test_storage_guard_integration.py
```

Expected: FAIL because the current guard reopens paths, does not prove ownership/noatime/internal encryption UUID, and has no `StorageContract`.

- [ ] **Step 3: Implement the exact public contract**

```python
# executor/workspace_handle.py; console.storage_contract re-exports MountFacts
# and imports/re-exports the canonical StorageStatus from console.storage_result.
from console.storage_result import StorageStatus, Verdict

@dataclass(frozen=True)
class MountFacts:
    st_dev_u32: DarwinU32
    fsid_u32: tuple[DarwinU32, DarwinU32]
    flags: int
    filesystem_type: str
    mount_from: str
    mount_on: str

@dataclass
class StorageBinding:
    transaction_id: str
    host_fd: int
    mount_fd: int
    root_fd: int
    host_volume_uuid: str
    host_fsid_u32: tuple[DarwinU32, DarwinU32]
    mount_device_u32: DarwinU32
    mount_fsid_u32: tuple[DarwinU32, DarwinU32]
    apfs_volume_uuid: str
    encryption_uuid: str
    volume_name: str
    image_basename: str
    root_relative: PurePosixPath
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...

class StorageContractError(RuntimeError):
    code: str

class StorageContract:
    def __init__(self, home: Path, *, environment: Mapping[str, str] | None = None,
                 broker: StorageBrokerClient,
                 fd_probe: FdProbe = probe_mount_fd) -> None: ...
    def probe_locked(self, lock_set: StorageLockSet) -> StorageStatus: ...
    def open_locked(self, lock_set: StorageLockSet) -> StorageBinding: ...
    def revalidate_locked(self, lock_set: StorageLockSet,
                          binding: StorageBinding) -> MountFacts: ...
    def open_workspace_locked(self, lock_set: StorageLockSet,
                              binding: StorageBinding,
                              requested: str | Path) -> WorkspaceHandle: ...
```

Each method first validates an active same-home `StorageLockSet` with
install-shared or stronger and admission-exclusive; `open_locked`,
`revalidate_locked`, and `open_workspace_locked` also require
storage-exclusive, while `probe_locked` permits storage-shared. The injected
backend is supplied by tests and callers in Tasks 5-14; no installed artifact
is attested in this task. `probe_locked()` opens transient FDs and always
closes them. With neither required marker nor transition journal it returns
exactly `StorageStatus("PASS", "STORAGE_NOT_REQUIRED", None, "unconfigured",
False, True)` without probing an external host or mount. `open_locked()`
remains vault-only and therefore rejects that optional-storage status; it
retains host/mount/root FDs and returns them only after exact private control
files and committed projection, host and mount descriptor proofs, and one S3
private locked probe that returns exact APFS name/UUID/writable/encryption/
image/mount/mapping facts. It repeats descriptor probes around the broker
observation and opens the root descriptor-relatively with current UID/mode
`0700` on the same APFS device.

Create the core `WorkspaceHandle.from_verified_fds(...)`, borrowed `mount_fd`/`workspace_fd`, `identity`, `revalidate()`, and `close()` contract in `executor/workspace_handle.py` now so `open_workspace_locked()` is a functioning interface in this task. The first normalized relative component must equal `20_WORKSPACES`; use component equality, never string-prefix matching. `StorageContract` gains no local-root constructor, alias parameter, or local action method. Task 8 adds the remaining duplication/context-manager API and adversarial lifetime/fuzz coverage before any downstream plan consumes it.

- [ ] **Step 4: Reduce the old guard to an adapter and run GREEN**

Map `StorageContractError.code` to existing nonzero exit classes without printing private paths. `configured_bootstrap` rejects alternate env values before existence checks. `check_required_storage` takes the storage lock shared, rejects any non-committed transition, and treats a required marker with missing bootstrap/journal as failure.

Run:

```bash
"$PYTHON" tests/test_storage_guard.py
"$PYTHON" tests/test_storage_guard_integration.py
```

Expected: PASS; every race/ownership/host/image case fails closed, and vault workspace admission rejects every local-alias-shaped input before duplicating an FD.

- [ ] **Step 5: Commit the storage authority**

```bash
git add executor/workspace_handle.py console/storage_contract.py console/storage_guard.py \
  scripts/check-cortex-storage.py tests/test_storage_guard.py \
  tests/test_storage_guard_integration.py
git commit -m "feat(storage): enforce descriptor storage contract"
```

### Task 8: Complete and adversarially verify the vault-only WorkspaceHandle interface

**Files:**
- Modify: `executor/workspace_handle.py`
- Create: `tests/test_workspace_handle.py`
- Modify: `tests/test_workspace_path_fuzzing.py`

**Interfaces:**
- Consumes: the core `executor/workspace_handle.py` created by Task 7, already verified mount/workspace directory FDs, and a `MountFacts`-compatible probe callable. It does not import `console.storage_contract` and does not accept an absolute trusted path.
- Produces: `WorkspaceIdentity`, vault-only `WorkspaceHandle`, and the exact final API consumed by the later general-mission/effect plan; no `ToolExecutor`, local-alias, or worker integration occurs here.

- [ ] **Step 1: Write failing lifetime, confinement and race tests**

Cover constructor FD duplication, caller closing originals, borrowed-FD validity, relative display path, exact `20_WORKSPACES` root/descendant acceptance, `Desktop`/`Documents`/`Downloads`/`20_WORKSPACES-escape` plus `..`/absolute/NUL/empty/symlink rejection, cross-device rejection, mount/workspace inode replacement after open, detach exposing the underlying mount directory, changed fstatfs device/fsid/mount-from/mount-on/flags, duplicate FD ownership, idempotent close, context-manager close, and every method/property after close. Pass a test-only object with `kind="local_alias"` to every public constructor/admission boundary and require `TypeError` or `WORKSPACE_NOT_VAULT` before any FD duplication.

```python
handle = WorkspaceHandle.from_verified_fds(
    mount_fd=mount_fd,
    workspace_fd=workspace_fd,
    storage_transaction_id="8ce4e7ce-8e9a-45ef-a112-64a14dfc1c83",
    apfs_volume_uuid="12345678-1234-1234-1234-123456789ABC",
    relative_path=PurePosixPath("20_WORKSPACES/qa-run"),
    fd_probe=fake_probe,
)
os.close(mount_fd)
os.close(workspace_fd)
self.assertEqual(handle.display_path, "20_WORKSPACES/qa-run")
self.assertEqual(handle.revalidate(), handle.identity)
owned_dup = handle.duplicate_workspace_fd()
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_workspace_handle.py
"$PYTHON" tests/test_workspace_path_fuzzing.py
```

Expected: FAIL because Task 7's existing core handle deliberately lacks `duplicate_workspace_fd()`, context-manager closure, and closed-handle rejection for every FD property/method; the pre-existing fuzz tests also exercise only path resolution.

- [ ] **Step 3: Implement the exact final interface**

```python
@dataclass(frozen=True)
class WorkspaceIdentity:
    storage_transaction_id: str
    mount_dev_u32: DarwinU32
    mount_fsid_u32: tuple[DarwinU32, DarwinU32]
    workspace_dev_u32: DarwinU32
    workspace_ino: int
    apfs_volume_uuid: str
    relative_path: PurePosixPath

class WorkspaceHandleClosed(RuntimeError): ...
class WorkspaceIdentityChanged(RuntimeError): ...

class WorkspaceHandle:
    @classmethod
    def from_verified_fds(cls, *, mount_fd: int, workspace_fd: int,
                          storage_transaction_id: str,
                          apfs_volume_uuid: str,
                          relative_path: PurePosixPath,
                          fd_probe: Callable[[int], MountFacts]) -> Self: ...
    @property
    def identity(self) -> WorkspaceIdentity: ...
    @property
    def mount_fd(self) -> int: ...
    @property
    def workspace_fd(self) -> int: ...
    @property
    def display_path(self) -> str: ...
    def revalidate(self) -> WorkspaceIdentity: ...
    def duplicate_workspace_fd(self) -> int: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
```

Validate the type and normalized relative components before duplicating either input FD. Immediately duplicate both valid input FDs with `fcntl.F_DUPFD_CLOEXEC`; originals remain caller-owned. Require both opened objects are directories, same `st_dev`, the first relative component equals `20_WORKSPACES`, and probe mount `st_dev` equals `fstat(mount_fd).st_dev`. Freeze initial `fstat` and `fstatfs` identity. `mount_fd`/`workspace_fd` are borrowed until close; callers must not close them. `duplicate_workspace_fd` returns a caller-owned CLOEXEC duplicate. There is no constructor overload for `LocalAliasHandle`, standard aliases, or arbitrary local roots.

- [ ] **Step 4: Implement revalidation/close and run GREEN**

`revalidate()` repeats `fstat` on both retained FDs plus the injected `fstatfs` probe, requires exact device/inode/fsid/mount-from/mount-on/flags and APFS, then returns the unchanged identity. After close, every FD property, duplicate, or revalidation raises `WorkspaceHandleClosed`; close itself is idempotent.

Run:

```bash
"$PYTHON" tests/test_workspace_handle.py
"$PYTHON" tests/test_workspace_path_fuzzing.py
```

Expected: PASS across deterministic detach/replacement and Unicode/traversal fuzz cases.

- [ ] **Step 5: Commit the final handle interface**

```bash
git add executor/workspace_handle.py tests/test_workspace_handle.py \
  tests/test_workspace_path_fuzzing.py
git commit -m "feat(executor): add persistent workspace handle"
```

### Task 9: Immutable storage projection and browser transport clamp

**Files:**
- Modify: `console/settings.py`
- Modify: `transport/browser.py`
- Modify: `tests/test_chat_settings_api.py`
- Modify: `tests/test_playwright_driver.py`
- Modify: `tests/test_chrome_extension_driver.py`

**Interfaces:**
- Consumes: `StorageProjection` from Task 6, `StorageContract.probe_locked(lock_set) -> StorageStatus`, committed journal projection, and existing `CORTEX_ALLOW_DEVELOPMENT_FIXTURES` fixture gate.
- Produces: `canonical_storage_projection(settings: Mapping[str, object]) -> StorageProjection`, `storage_projection_sha256(projection: StorageProjection) -> str`, and `validate_browser_transport(settings: Mapping[str, object], *, storage_status: StorageStatus, development_fixture: bool) -> Literal["chrome_extension", "playwright", "webbridge"]`.

- [ ] **Step 1: Write failing projection/clamp tests**

Make the in-process Chat Settings server fixture hermetic before starting Uvicorn: save `console.server.RUNTIME_PATHS`, replace it with a `CortexPaths` instance rooted in that test class's existing private temporary directory, and restore it even when class setup fails. Seed the process-default runtime fixture with a required-storage marker whose target is absent and prove the test server still consults only its explicit temporary runtime. This is test isolation, not a production storage bypass; subprocess tests of the real default/required path remain unchanged.

Load required-storage settings containing `playwright`, `webbridge`, an alternate default workspace, an alternate profile root, a symlinked profile root, and a post-cutover mutation. Patch all three driver constructors and require zero constructor calls on every rejected case. Prove language/theme may change when the three-field projection remains byte-identical.

```python
for legacy in ("playwright", "webbridge"):
    with self.subTest(legacy=legacy), patch.multiple(
        browser,
        PlaywrightBrowserDriver=playwright_ctor,
        WebBridgeDriver=webbridge_ctor,
        ChromeExtensionBrowserDriver=extension_ctor,
    ):
        with self.assertRaisesRegex(ValueError, "BROWSER_TRANSPORT_REQUIRED"):
            browser.create_browser_driver("s", {**required_settings, "browser_transport": legacy})
        self.assertEqual(playwright_ctor.call_count, 0)
        self.assertEqual(webbridge_ctor.call_count, 0)
        self.assertEqual(extension_ctor.call_count, 0)
```

Also prove the explicit development fixture permits legacy transports only when the required marker/bootstrap/transition are all absent, and `browser_profile_root` remains an empty, confined, inactive directory under active Chrome extension transport.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_chat_settings_api.py
"$PYTHON" -m unittest tests.test_playwright_driver tests.test_chrome_extension_driver -v
```

Expected: FAIL because current Settings permits mutation and the browser factory accepts both legacy transports under required storage.

- [ ] **Step 3: Implement the canonical three-field projection**

```python
def canonical_storage_projection(settings: Mapping[str, object]) -> StorageProjection: ...
def storage_projection_sha256(projection: StorageProjection) -> str: ...
def validate_browser_transport(
    settings: Mapping[str, object], *, storage_status: StorageStatus,
    development_fixture: bool,
) -> Literal["chrome_extension", "playwright", "webbridge"]: ...
```

Canonical serialization contains exactly sorted keys `browser_profile_root`, `browser_transport`, `default_workspace`, compact separators, and UTF-8. When storage is required, values must be the exact canonical descriptor-proven `storage_root/20_WORKSPACES`, `storage_root/50_CACHE_REBUILDABLE/browser-profiles`, and `chrome_extension`. Settings reads and writes take the shared/exclusive storage lock respectively, check the transition first, and compare the committed digest before returning or publishing.

- [ ] **Step 4: Clamp before factory creation and run GREEN**

`load_browser_settings` obtains storage status before importing/constructing a legacy driver. `create_browser_driver(..., transport_name=...)` cannot override the clamp. Required or release runtime rejects any selected value other than `chrome_extension` with `BROWSER_TRANSPORT_REQUIRED`; fixture legacy transports require `CORTEX_ALLOW_DEVELOPMENT_FIXTURES=1` and no required-storage artifact.

Run:

```bash
"$PYTHON" tests/test_chat_settings_api.py
"$PYTHON" -m unittest tests.test_playwright_driver tests.test_chrome_extension_driver -v
```

Expected: PASS; both legacy settings produce zero browser construction under required storage and allowed theme/language changes retain the exact projection digest.

- [ ] **Step 5: Commit the immutable projection**

```bash
git add console/settings.py transport/browser.py tests/test_chat_settings_api.py \
  tests/test_playwright_driver.py tests/test_chrome_extension_driver.py
git commit -m "feat(storage): clamp runtime storage projection"
```

### Task 10: Receipt-bound descriptor importer

**Files:**
- Create: `console/storage_import.py`
- Create: `scripts/import-cortex-storage.py`
- Create: `tests/test_storage_import.py`

**Interfaces:**
- Consumes: exclusive storage lock, open/revalidated `StorageBinding`, source path plus one exact typed receipt, `/usr/bin/git`, and `gitleaks` through strict injected runners.
- Produces: `ImportMode`, `SyntheticReceipt`, `EvidenceReceipt`, `GitReceipt`, `freeze_source_manifest(...)`, `import_regular_tree(...)`, `import_git(...)`, and the only executable import entrypoint `scripts/import-cortex-storage.py`.

- [ ] **Step 1: Write failing allowlist/manifest/race tests**

Cover the exact three modes and reject an arbitrary source/destination pair, missing/mismatched QA transaction, invalid privacy hash/review IDs, unnamed Git ref, ref/commit mismatch, target collision, symlink, FIFO/socket/device, hardlink (`st_nlink != 1`), duplicate `(st_dev, st_ino)`, source cross-device, destination not on bound APFS, source replacement/mutation during read, destination mutation, hash mismatch, nonzero zero-difference dry run, and any browser profile/cookie/local-storage/authentication/credential/current-personal-workspace content. While recovery is `UNCLEAR`, reject a receipt/data classification other than synthetic, reproducibly rebuildable, reviewed evidence, or the exact reviewed Git commit.

```python
manifest = freeze_source_manifest(source_fd)
self.assertEqual(
    [(entry.relative_path.as_posix(), entry.size, entry.sha256) for entry in manifest.entries],
    sorted(expected_entries),
)
with self.assertRaisesRegex(StorageImportError, "IMPORT_SOURCE_CHANGED"):
    import_regular_tree(binding, source, SyntheticReceipt(qa_transaction_id="wrong"))
```

For Git, assert the exact first clone argv and reject `.gitmodules`, mode `160000`, `submodule.*`, alternates, `refs/replace/*`, dirty status, secret-scan failure, objects outside the advertised ref graph, destination HEAD mismatch, changed source ref, retained remote/URL, and second-scan failure.

```python
self.assertEqual(clone_argv, [
    "/usr/bin/git", "clone", "--no-local", "--no-hardlinks", "--single-branch",
    "--no-tags", "--branch", frozen_ref, "--no-recurse-submodules",
    source_path, temporary_destination,
])
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_storage_import.py
```

Expected: FAIL because the importer and its executable entrypoint are absent.

- [ ] **Step 3: Implement exact receipt and manifest types**

```python
class ImportMode(StrEnum):
    SYNTHETIC = "synthetic"
    EVIDENCE = "evidence"
    GIT = "git"

@dataclass(frozen=True)
class SyntheticReceipt:
    qa_transaction_id: str

@dataclass(frozen=True)
class EvidenceReceipt:
    privacy_manifest_sha256: str
    review_ids: tuple[str, ...]

@dataclass(frozen=True)
class GitReceipt:
    local_ref: str
    commit: str

@dataclass(frozen=True)
class ManifestEntry:
    relative_path: PurePosixPath
    size: int
    sha256: str
    mode: int
    dev_u32: DarwinU32
    ino: int

@dataclass(frozen=True)
class SourceManifest:
    entries: tuple[ManifestEntry, ...]
    digest: str
    total_bytes: int
```

Walk source/destination only from opened directory descriptors, sort raw relative names deterministically, reject every non-regular/non-directory entry, require one device and unique single-link inode per regular file, and revalidate identity before/during/after streaming. Copy to exclusive temporary destination names, fsync file and directory, rebuild the destination manifest, require exact relative path/size/hash/mode equality and a zero-difference verification, then publish exclusively. Any failure moves only the incomplete destination into `99_QUARANTINE` after revalidating the binding; the source remains intact.

- [ ] **Step 4: Implement exact Git pack import and executable boundary; run GREEN**

Before clone, require clean status, named local ref equals the 40/64-hex frozen commit, and passing history plus no-Git working-tree Gitleaks scans. After the exact clone command: verify destination HEAD independently; reread source ref; verify tracked-content manifest; run `git fsck --full` and reject dangling/unreachable output; remove `origin`; require no remotes, URLs, alternates, replace/submodule config/ref, dirty files, or second secret-scan finding.

`scripts/import-cortex-storage.py` accepts only:

```text
--mode synthetic --source PATH --qa-transaction-id UUID
--mode evidence --source PATH --privacy-manifest-sha256 SHA256 --review-id ID --review-id ID
--mode git --source PATH --ref NAMED_LOCAL_REF --commit EXACT_COMMIT
```

Each form also requires exactly one of `--dry-run` or `--approve-plan HASH`. It derives fixed destinations from mode, never accepts `--destination`, takes the exclusive storage lock, recalculates the canonical plan hash before the first source/destination open, opens/revalidates the contract before and after import, and emits only the redacted common result schema.

Run:

```bash
"$PYTHON" tests/test_storage_import.py
```

Expected: PASS, including exact clone argv, mutation injection, no-follow traversal, manifest equality, quarantine, and source-preservation cases.

- [ ] **Step 5: Commit the controlled importer**

```bash
git add console/storage_import.py scripts/import-cortex-storage.py tests/test_storage_import.py
git commit -m "feat(storage): add controlled descriptor importer"
```

### Task 11: Operator CLI, vault plan hashes, cutover publication and rollback

**Files:**
- Create: `scripts/cortex-storage.py`
- Create: `tests/test_storage_cli.py`
- Modify: `scripts/configure-external-storage.py`
- Modify: `tests/test_storage_configuration.py`

**Interfaces:**
- Consumes: Tasks 1, 5-7, 9-10 and `process_ownership.classify`; no storage logic is reconstructed in the CLI.
- Produces: exact subcommands `preflight`, `keychain-spike`, `create-vault`, `initialize-layout`, `import`, `publish-cutover`, `rollback`, and `status`; mutating commands use reviewed plan hashes.

- [ ] **Step 1: Write failing parser/output/approval tests**

Require the exact public subcommand set, reject unknown options, reject `--approve-plan` on read-only commands, require exactly one of `--dry-run` or `--approve-plan HASH` for every mutating command, recalculate plan hashes under locks before effects, and reject stale/mismatched approval with zero lifecycle/import/publication calls. Capture stdout/stderr and seed private paths/passphrase-like text in raised exceptions; output must be one valid redacted JSON line and contain none of those values.

```python
self.assertEqual(set(parser._subparsers._group_actions[0].choices), {
    "preflight", "keychain-spike", "create-vault", "initialize-layout",
    "import", "publish-cutover", "rollback", "status",
})
self.assertEqual(dry["code"], "PLAN_READY")
plan_check = next(check for check in dry["checks"] if check["id"] == "plan_hash")
self.assertRegex(plan_check["evidence"], r"^sha256_[0-9a-f]{64}$")
```

Test `status` exact additions and constant recovery limitation:

```python
self.assertEqual(status["recovery"], "UNCLEAR")
self.assertIs(type(status["mounted"]), bool)
self.assertIs(type(status["runtime_allowed"]), bool)
self.assertIn(status["storage_state"], {
    "unconfigured", "in_progress", "committed", "rolling_back", "rolled_back",
})
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_storage_cli.py
"$PYTHON" tests/test_storage_configuration.py
```

Expected: FAIL because the façade is absent and the configuration script publishes two files without the new journal/settings transaction.

- [ ] **Step 3: Implement exact read-only and dry-run syntax**

`preflight` and `status` execute read-only and require `--json`:

```text
$PYTHON scripts/cortex-storage.py preflight --host-volume HOST --legacy-image LEGACY --json
$PYTHON scripts/cortex-storage.py status --json
```

Mutating operations are plan-hash gated:

```text
$PYTHON scripts/cortex-storage.py keychain-spike --host-volume HOST [--cleanup-approved] --dry-run --json
$PYTHON scripts/cortex-storage.py keychain-spike --host-volume HOST [--cleanup-approved] --approve-plan HASH --json
$PYTHON scripts/cortex-storage.py create-vault --host-volume HOST --dry-run --json
$PYTHON scripts/cortex-storage.py create-vault --host-volume HOST --approve-plan HASH --json
$PYTHON scripts/cortex-storage.py initialize-layout --dry-run --json
$PYTHON scripts/cortex-storage.py initialize-layout --approve-plan HASH --json
$PYTHON scripts/cortex-storage.py publish-cutover --dry-run --json
$PYTHON scripts/cortex-storage.py publish-cutover --approve-plan HASH --json
$PYTHON scripts/cortex-storage.py rollback --dry-run --json
$PYTHON scripts/cortex-storage.py rollback --approve-plan HASH --json
```

The `import` subcommand accepts the exact Task 10 receipt arguments plus either `--dry-run` or `--approve-plan HASH` and delegates with `os.execve` to `scripts/import-cortex-storage.py`; it does not import/copy directly. Canonical plan JSON contains operation, transaction ID, non-secret host UUID/image basename/volume name, expected prior journal state, target hashes, and receipt digest, but no absolute path or secret. Dry run emits `code=PLAN_READY`; its `plan_hash` check evidence must match `^sha256_[0-9a-f]{64}$` rather than adding a top-level field.

- [ ] **Step 4: Implement cutover/rollback orchestration and run GREEN**

`publish-cutover` under install-then-storage locks requires verified stopped runtime, passed spike, created/remounted production image, initialized layout, open `StorageContract`, and 128 GiB free floor. It publishes only:

```python
StorageProjection(
    default_workspace=str(binding_root / "20_WORKSPACES"),
    browser_profile_root=str(binding_root / "50_CACHE_REBUILDABLE" / "browser-profiles"),
    browser_transport="chrome_extension",
)
```

It delegates journal/snapshot/publication/offline verification to `storage_transition`; the CLI never writes control files itself. `rollback` requires verified stopped state and invokes the idempotent transition rollback. Convert `scripts/configure-external-storage.py` into a compatibility parser that builds the same approved plan and delegates to these exact functions, with no independent publication path.

Run:

```bash
"$PYTHON" tests/test_storage_cli.py
"$PYTHON" tests/test_storage_configuration.py
"$PYTHON" tests/test_storage_transition.py
```

Expected: PASS; stale plans perform zero effect, common JSON never contains a private path, and configuration/rollback use one journal implementation.

- [ ] **Step 5: Commit the operator façade**

```bash
git add scripts/cortex-storage.py scripts/configure-external-storage.py \
  tests/test_storage_cli.py tests/test_storage_configuration.py
git commit -m "feat(storage): add journaled operator CLI"
```

### Task 12: One-click mount/start and stop/detach lifecycle

**Atomic-block rule:** This task and Task 13 are executed by one implementation owner without an intermediate commit. Write Task 12 Step 1 and Task 13 Step 1 first, then run the union of both RED command sets. Implement Task 13's blocked child/lease primitives, then this task's mount/start/stop integration, then Task 13's lifespan and cleanup gates. Do not run the Task 12 GREEN gate or create a Task 12 commit until the complete combined behavior is implemented.

**Files:**
- Modify: `scripts/cortex.sh`
- Modify: `scripts/start-local.sh`
- Modify: `console/storage_lifecycle.py`
- Modify: `console/installer.py`
- Modify: `tests/test_storage_guard_integration.py`
- Modify: `tests/test_selftest.py`
- Modify: `tests/test_start_local.py`
- Modify: `tests/test_installer.py`

**Interfaces:**
- Consumes: `StorageLifecycle.mount_or_adopt_locked(lock_set)`,
  `StorageLifecycle.detach_locked(lock_set)`, the active `StorageLockSet`,
  owned-process status, and the existing `/api/transport/stop-everything`
  quiescence endpoint.
- Produces: `RuntimeMount`, `runtime_mount_locked(...) -> RuntimeMount`, `runtime_detach_locked(...) -> OperationResult`, `cortex.sh start` as the sole mount owner, `cortex.sh stop` as the sole detach owner, `STORAGE_ATTACHED_BLOCKED`, and a `start-local.sh` delegate that cannot execute `server.py` directly.

- [ ] **Step 1: Write failing lifecycle owner tests**

Build a fake attested broker/guard/server harness and prove:

- start acquires shared install lock then exclusive storage lock before adopt/mount;
- an already mounted image is adopted only after the full contract, otherwise start performs no server spawn;
- an absent mount causes exactly one broker mount then a full guard before spawn;
- missing host, locked Keychain, prompt-required result, missing item, transition-active state, or contradictory image mapping prints only an actionable stable code and spawns no server;
- start never mentions/opens the legacy image and never passes a credential;
- stop calls durable STOP/quiescence, closes the owned server/workspace lifetime, then takes exclusive storage lock and performs one normal detach;
- a blocked detach leaves the server stopped, keeps mapping evidence, returns nonzero and reports `STORAGE_ATTACHED_BLOCKED`;
- two complete start/mount/stop/detach cycles pass with empty mount point and no image mapping after each stop;
- `start-local.sh` calls `bash scripts/cortex.sh start` exactly once and contains no `server.py` execution.

```python
self.assertEqual(events, [
    "install_lock_shared", "storage_lock_exclusive", "admission_lock_exclusive",
    "broker_mount", "contract_open", "server_spawn", "lease_fsync",
    "ownership_fsync", "child_consume", "ack", "binding_close",
    "lock_set_release",
])
self.assertNotIn("-force", helper_detach_argv)
self.assertNotIn("server.py", start_local_calls)
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_storage_guard_integration.py
"$PYTHON" tests/test_start_local.py
"$PYTHON" tests/test_selftest.py
```

Expected: FAIL because current start only checks an already mounted path, stop does not detach, and `start-local.sh` directly executes `server.py`.

- [ ] **Step 3: Implement the single runtime mount/detach owner**

Add internal, non-operator entrypoints in `console/storage_lifecycle.py`:

```python
@dataclass
class RuntimeMount:
    result: OperationResult
    binding: StorageBinding | None
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...

def operation_from_storage_status(operation: str,
                                  status: StorageStatus) -> OperationResult:
    """Preserve verdict/code/transaction and emit one redacted contract check."""
    return OperationResult(
        operation=operation,
        verdict=status.verdict,
        transaction_id=status.transaction_id,
        code=status.code,
        checks=(CheckResult(
            id="storage_contract",
            status=status.verdict,
            evidence={
                "PASS": "contract_passed",
                "FAIL": "contract_rejected",
                "UNCLEAR": "contract_unclear",
            }[status.verdict],
        ),),
    )

def runtime_mount_locked(*, lock_set: StorageLockSet,
                         lifecycle: StorageLifecycle,
                         contract: StorageContract) -> RuntimeMount:
    """Adopt or mount under the caller's active set and retain the binding."""

def runtime_detach_locked(*, lock_set: StorageLockSet,
                          lifecycle: StorageLifecycle,
                          process_status: ProcessStatus) -> OperationResult:
    """Require verified stopped state, normal detach, no mapping and empty mount."""
```

`runtime_mount_locked` validates the same-home install-shared-or-stronger,
storage-exclusive, admission-exclusive set. Tasks 12-14 inject the already
constructed lifecycle, contract, broker, ledger, and FD probe; they neither
attest nor import an installed runtime. Its mount verifier calls
`contract.probe_locked(lock_set)` and the adapter copies only verdict, code,
and transaction ID plus one stable redacted check, never a path or status-only
field. It calls `lifecycle.mount_or_adopt_locked(lock_set)` and, only after that
returns `PASS`, calls `contract.open_locked(lock_set)`. A non-PASS result returns
`RuntimeMount(result=<failure>, binding=None)`; a PASS result is valid only with
the retained `StorageBinding`. `RuntimeMount.close()` closes that binding
idempotently, and every exception/failure path closes it. Task 5 stays
independently GREEN with an injected verifier, and S3 Task 7 later replaces the
injected construction only at the product entrypoint with
`InstalledStorageRuntime.from_installed_home_locked(home, lock_set,
bootstrap_handle)`.

`cortex.sh start` invokes the one Task 13 Python coordinator, never a separate
mount subprocess whose exit would discard the FDs. In Foundation tests the
coordinator receives the injected runtime components and active set, calls
`runtime_mount_locked` only when storage is required, retains the returned
object through child spawn, durable lease/ownership publication and exact ACK,
then closes it. S3 Task 7 wires the installed factory without changing this
behavior. Tests pause inside the ACK callback and require every retained
host/mount/root FD is valid there, then closed after success or failure.

- [ ] **Step 4: Implement ordered shutdown, Doctor/selftest integration and run GREEN**

When the owned server is running, `stop` first POSTs the existing loopback STOP endpoint, waits for quiescence, terminates only the verified owned process group, verifies no listener, then calls `runtime_detach_locked` under the same active exclusive set. When already stopped but storage is mapped, it still attempts verified normal detach. Doctor and selftest receive one shared set and consume `StorageContract.probe_locked`; neither can report healthy/pass when transition, ownership, image, projection, helper, or env override checks fail.

Run:

```bash
"$PYTHON" tests/test_storage_guard_integration.py
"$PYTHON" tests/test_start_local.py
"$PYTHON" tests/test_selftest.py
"$PYTHON" -m unittest tests.test_installer.InstallerTest.test_doctor_json_is_stable_without_optional_services -v
```

Expected: PASS, including two mount/detach cycles, the blocked-detach status, and delegated launcher.

- [ ] **Step 5: Preserve the uncommitted atomic block and continue to Task 13**

```bash
git diff --check
git status --short
```

Expected: only files owned by Tasks 12 and 13 are modified. Do not stage or commit yet; proceed directly to Task 13 and keep the same implementation owner.

### Task 13: Blocked server, one-shot startup lease and lifespan enforcement

**Files:**
- Create: `console/startup_lease.py`
- Create: `tests/test_startup_lease.py`
- Modify: `console/process_ownership.py`
- Modify: `console/server.py`
- Modify: `scripts/cortex.sh`
- Modify: `tests/test_process_ownership.py`
- Modify: `tests/test_storage_guard_integration.py`
- Modify: `tests/test_start_local.py`
- Modify: `tests/test_missions_api.py`
- Modify: `tests/test_store_lifecycle.py`
- Modify: `tests/test_executor_runtime_truth.py`

**Interfaces:**
- Consumes: Task 12 `RuntimeMount`, optional committed storage transaction ID,
  attested private pids-directory FD, `socket.socketpair`, stable server
  PID/PGID/start identity, handshake-only launcher identity, the caller's
  active `StorageLockSet`, and injected lifecycle/contract backends when
  storage is required.
- Produces: `ManagedProcessIdentity`, `StartupLease`, `ManagedStartContext`,
  `ManagedStartReceipt`, `RuntimeLifespanRecord`, the sole signature
  `launch_managed_runtime(home: Path, *, lock_set: StorageLockSet, lifecycle:
  StorageLifecycle, contract: StorageContract, timeout_seconds: float = 5.0)
  -> ManagedStartReceipt`, `publish_startup_lease(...)`,
  `child_consume_startup_lease(...)`, `parent_release_and_wait_ack(...)`,
  `_require_managed_start_context(...)`, and read-only
  `managed_runtime_is_ready_locked(...)` consumed by Task 14. No wrapper or
  overload named `launch_managed_runtime` has another signature.

- [ ] **Step 1: Write failing handshake/lease tests**

Use real local socketpairs and disposable pids directories without binding a network port. Pause deterministically at child-spawn, identity-capture, lease-fsync, ownership-record-fsync, parent-send, child-consume, receipt-fsync, ACK, and pre-bind boundaries. Cover success plus timeout, EOF, malformed frame, wrong lease ID, wrong nonce, expired lease, wrong server PID/PGID/start, wrong launcher identity before ACK, wrong pids FD identity, wrong transaction, replay, replacement, missing ACK, child exit, launcher exit after ACK, repeated readiness, and ACK followed by changed storage binding.
Pause additionally before/after `STARTING`, lifespan initialization,
`READY`, and pre-teardown `CLOSED` fsync. A pre-READY crash and a still-live
process after `CLOSED` must both fail readiness; stale boot/generation/previous
digest records are rejected.

```python
lease = publish_startup_lease(
    pids_fd=pids_fd,
    identity=ManagedProcessIdentity(
        pid=child_pid, pgid=child_pgid, start_time=child_start,
    ),
    storage_transaction_id=transaction_id,
    ttl_seconds=5.0,
)
context = child_consume_startup_lease(
    control_fd=child_control.fileno(), pids_fd=pids_fd,
    expected_transaction_id=transaction_id,
)
self.assertEqual(context.lease_id, lease.lease_id)
with self.assertRaisesRegex(StartupLeaseError, "STARTUP_LEASE_REPLAYED"):
    child_consume_startup_lease(
        control_fd=replay_control.fileno(), pids_fd=pids_fd,
        expected_transaction_id=transaction_id,
    )
```

Integration tests must assert the port is never listening before ACK, `cortex.sh start` creates the blocked handshake for both required-storage and no-marker product runtime, direct `python server.py` is permitted only with `CORTEX_ALLOW_DEVELOPMENT_FIXTURES=1` and no required marker, and direct `python -m uvicorn server:app` with healthy mounted required storage but no consumed lease exits without serving a request. The explicit development fixture has no managed context and therefore cannot later satisfy local-alias readiness.

Every in-process Uvicorn/lifespan fixture in `tests/test_missions_api.py`, `tests/test_store_lifecycle.py`, and `tests/test_executor_runtime_truth.py` must save the imported server's `RUNTIME_PATHS`, bind it to that test's owner-only temporary runtime before entering lifespan, select the explicit development-fixture or injected managed-start context required by the case, and restore both paths and environment on setup failure and teardown. Add a regression that seeds a broken process-default required-storage projection and proves these unit fixtures never consult it. Keep the real subprocess tests for default/required `CORTEX_HOME`, direct entrypoints and missing lease unchanged; no product code may ignore a genuine required marker. Task 9 applies the same rule to `tests/test_chat_settings_api.py` before this atomic block.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_startup_lease.py
"$PYTHON" tests/test_process_ownership.py
"$PYTHON" tests/test_storage_guard_integration.py
"$PYTHON" tests/test_start_local.py
"$PYTHON" tests/test_missions_api.py
"$PYTHON" tests/test_store_lifecycle.py
"$PYTHON" tests/test_executor_runtime_truth.py
```

Expected: FAIL because startup currently spawns an immediately runnable server and no one-shot lease exists.

- [ ] **Step 3: Implement exact identity and lease records**

```python
@dataclass(frozen=True)
class ManagedProcessIdentity:
    pid: int
    pgid: int
    start_time: str

@dataclass(frozen=True)
class StartupLease:
    schema_version: Literal[1]
    lease_id: str
    nonce: str
    identity: ManagedProcessIdentity
    launcher_pid: int
    launcher_start_time: str
    pids_dev_u32: DarwinU32
    pids_ino: int
    pids_uid: int
    pids_mode: Literal[448]
    storage_transaction_id: str | None
    boot: BootIdentity
    generation_record_sha256: str
    expires_at_monotonic_ns: int

@dataclass(frozen=True)
class ManagedStartContext:
    lease_id: str
    identity: ManagedProcessIdentity
    storage_transaction_id: str | None
    boot: BootIdentity
    generation_record_sha256: str
    receipt_sha256: str

@dataclass(frozen=True)
class ManagedStartReceipt:
    lease_id: str
    child_pid: int
    storage_transaction_id: str | None
    acknowledged: Literal[True]

RuntimeLifespanState = Literal["STARTING", "READY", "CLOSED"]

@dataclass(frozen=True)
class RuntimeLifespanRecord:
    schema_version: Literal[1]
    state: RuntimeLifespanState
    lease_id: str
    lease_receipt_sha256: str
    identity: ManagedProcessIdentity
    storage_transaction_id: str | None
    boot: BootIdentity
    generation_record_sha256: str
    previous_record_sha256: str | None
    record_sha256: str

def launch_managed_runtime(
    home: Path, *, lock_set: StorageLockSet,
    lifecycle: StorageLifecycle, contract: StorageContract,
    timeout_seconds: float = 5.0,
) -> ManagedStartReceipt: ...

def publish_startup_lease(*, pids_fd: int, identity: ManagedProcessIdentity,
                          storage_transaction_id: str | None,
                          boot: BootIdentity,
                          generation_record_sha256: str,
                          ttl_seconds: float = 5.0) -> StartupLease: ...

def parent_release_and_wait_ack(control_fd: int, lease: StartupLease,
                                *, timeout_seconds: float = 5.0) -> None: ...

def child_consume_startup_lease(*, control_fd: int, pids_fd: int,
                                expected_transaction_id: str | None) -> ManagedStartContext: ...

def _require_managed_start_context(home: Path,
                                   storage_status: StorageStatus) -> ManagedStartContext: ...

def managed_runtime_is_ready_locked(
    lock_set: StorageLockSet, *, home: Path,
    expected_storage_transaction_id: str | None,
) -> bool: ...
```

Create one private `SOCK_STREAM` socketpair for every non-fixture product start. `launch_managed_runtime` is the sole Python owner of the optional Task 12 `RuntimeMount`, the socketpair, child process and parent handshake. It uses only the installed/equipped fixed server entrypoint and exposes no arbitrary argv or executable parameter. Spawn with `close_fds=True` and exactly two explicit inherited descriptors: `control_fd` and a `F_DUPFD_CLOEXEC` duplicate of the already attested `pids_fd`. The lease binds that directory's device/inode/UID/mode `0700`, boot identity, and selected installed generation; the child `fstat`s the duplicate before descriptor-relative consume and closes both inherited FDs after ACK. Parent captures stable server PID/PGID/start plus launcher identity, atomically publishes/fsyncs lease and owned process record, then sends only lease ID plus nonce. Parent identity is validated only during consume/ACK. The child exclusively renames the lease to a consumed receipt, fsyncs receipt and directory, stores the in-process context, writes/fsyncs `STARTING`, and ACKs the receipt hash. `launch_managed_runtime` returns after ACK and may exit normally. Required storage binds a non-null committed transaction; a no-marker managed runtime binds `None`.

- [ ] **Step 4: Enforce parent cleanup and independent lifespan gate; run GREEN**

Parent accepts only the exact ACK before continuing readiness checks. Timeout, EOF, invalid/missing ACK, child exit, changed identity, or wrong pids descriptor terminates the exact owned process group after revalidation. In `_application_lifespan`, every non-fixture runtime calls `_require_managed_start_context` before initialization and matches the binding transaction. It CAS-writes/fsyncs `READY` only after initialization succeeds and CAS-writes/fsyncs `CLOSED` before teardown. `managed_runtime_is_ready_locked` first validates the exact active set, then the live server PID/PGID/start, consumed receipt, transaction, boot, generation, and current `READY` record without requiring the launcher PID to exist. Add GREEN assertions that readiness remains true across repeated checks after the launcher exits; it is false for `STARTING`, pre-READY crash, a development fixture, unconsumed/expired lease, wrong transaction/boot/generation, replay, replaced receipt, server identity mismatch, or a live process with `CLOSED` lifespan.

Run:

```bash
"$PYTHON" tests/test_startup_lease.py
"$PYTHON" tests/test_process_ownership.py
"$PYTHON" tests/test_storage_guard_integration.py
"$PYTHON" tests/test_start_local.py
```

Expected: PASS; every failure leaves no listener/owned child, replay is rejected, and both direct server entrypoints fail closed under required storage.

- [ ] **Step 5: Run the complete atomic GREEN gate and commit managed mount/startup**

Run every command below independently after both tasks are implemented:

```bash
"$PYTHON" tests/test_startup_lease.py
"$PYTHON" tests/test_process_ownership.py
"$PYTHON" tests/test_storage_guard_integration.py
"$PYTHON" tests/test_start_local.py
"$PYTHON" tests/test_selftest.py
"$PYTHON" tests/test_missions_api.py
"$PYTHON" tests/test_store_lifecycle.py
"$PYTHON" tests/test_executor_runtime_truth.py
"$PYTHON" -m unittest \
  tests.test_installer.InstallerTest.test_doctor_json_is_stable_without_optional_services -v
```

Expected: every command passes, the server never listens before the exact lease ACK, the storage binding remains live until that ACK, every failure leaves no owned child/listener, stop detaches normally only after quiescence, and two full mount/start/stop/detach cycles pass.

```bash
git add console/startup_lease.py console/process_ownership.py console/server.py \
  console/storage_lifecycle.py console/installer.py scripts/cortex.sh scripts/start-local.sh \
  tests/test_startup_lease.py tests/test_process_ownership.py \
  tests/test_storage_guard_integration.py tests/test_start_local.py \
  tests/test_selftest.py tests/test_installer.py tests/test_missions_api.py \
  tests/test_store_lifecycle.py tests/test_executor_runtime_truth.py
git commit -m "feat(storage): own managed mount and startup lifecycle"
```

### Task 14: Read-only managed-runtime readiness boundary for local-alias consumers

**Files:**
- Modify: `console/storage_contract.py`
- Create: `tests/test_storage_runtime_ready.py`

**Interfaces:**
- Consumes: one read-only `ordered_storage_locks(home, install_mode="shared", storage_mode="shared") -> ContextManager[StorageLockSet]` from Task 1, `StorageContract.probe_locked(lock_set) -> StorageStatus` from Task 7, and `managed_runtime_is_ready_locked(lock_set, *, home: Path, expected_storage_transaction_id: str | None) -> bool` from Task 13.
- Produces: exact read-only `StorageContract.assert_runtime_ready_locked(lock_set: StorageLockSet) -> StorageStatus`; it produces no `WorkspaceHandle`, `StorageBinding`, alias handle, grant, approval, effect, worker process, mount, or filesystem mutation.

- [ ] **Step 1: Write the failing local-alias readiness matrix**

Create a table-driven unit test using temporary private runtime files, fake storage/helper probes, and a fake managed-runtime probe. Cover these exact cases:

| Case | Storage observation | Managed context | Expected result |
| --- | --- | --- | --- |
| required host absent | `FAIL`, unmounted | valid-looking | `FAIL/STORAGE_NOT_READY`, admission callback 0 |
| required vault detached | `FAIL`, unmounted | valid-looking | `FAIL/STORAGE_NOT_READY`, admission callback 0 |
| transition `in_progress` | `FAIL`, unmounted | valid-looking | `FAIL/STORAGE_NOT_READY`, admission callback 0 |
| transition `rolling_back` | `FAIL`, unmounted | valid-looking | `FAIL/STORAGE_NOT_READY`, admission callback 0 |
| required storage healthy but lease absent/mismatched | `PASS`, committed, mounted, transaction present | false | `FAIL/STORAGE_NOT_READY`, admission callback 0 |
| no required marker but unmanaged development fixture | `PASS`, unconfigured, unmounted, no transaction | false | `FAIL/STORAGE_NOT_READY`, admission callback 0 |
| no required marker and managed product runtime | `PASS`, unconfigured, unmounted, no transaction | true | `PASS/RUNTIME_READY`, admission callback 1 |
| required storage and matching managed product runtime | `PASS`, committed, mounted, transaction present | true | `PASS/RUNTIME_READY`, admission callback 1 |

Use this test-only consumer to prove the future `local_alias_action` boundary without implementing its service or worker:

```python
def consume_local_alias_readiness(contract: StorageContract,
                                  lock_set: StorageLockSet,
                                  admission: Callable[[], None]) -> StorageStatus:
    status = contract.assert_runtime_ready_locked(lock_set)
    if status.verdict == "PASS" and status.runtime_allowed:
        admission()
    return status

for case in RUNTIME_READINESS_CASES:
    admission = Mock()
    contract = make_contract(
        storage_status=case.storage_status,
        managed_runtime_ready=case.managed_runtime_ready,
    )
    status = consume_local_alias_readiness(contract, lock_set, admission)
    self.assertEqual((status.verdict, status.code), case.expected)
    self.assertEqual(admission.call_count, case.expected_admissions)
```

Add this second test-only two-boundary harness:

```python
def consume_local_alias_twice(contract: StorageContract,
                              lock_set: StorageLockSet,
                              finalize: Callable[[], None],
                              mutate_observation: Callable[[], None],
                              activate: Callable[[], None]) -> tuple[StorageStatus, StorageStatus | None]:
    before_finalize = contract.assert_runtime_ready_locked(lock_set)
    if before_finalize.verdict != "PASS" or not before_finalize.runtime_allowed:
        return before_finalize, None
    finalize()
    mutate_observation()
    before_activation = contract.assert_runtime_ready_locked(lock_set)
    if before_activation.verdict == "PASS" and before_activation.runtime_allowed:
        activate()
    return before_finalize, before_activation
```

Start healthy, let finalization pass once, then separately inject required-vault detach, host loss, `in_progress`, `rolling_back`, and loss/mismatch of the consumed managed-start context before the second call. Each case must record `finalize.call_count == 1` and `activate.call_count == 0`; an unchanged healthy case records `1/1`. This proves both mandated checks and prevents a grant created while healthy from becoming a storage-recovery escape after readiness changes.

The fixture must make `StorageContract.open_locked(lock_set)`,
`open_workspace_locked(lock_set, binding, requested)`, every mutating
`StorageLifecycle.*_locked` method,
alias opens, and any actual grant/approval/effect/worker callback raise
immediately. Snapshot the temporary runtime tree before and after each
assertion and require identical relative entries, bytes, modes, and inode
identities. Assert one bounded install-shared/storage-shared/admission-exclusive
`StorageLockSet` encloses both the locked storage probe and managed-context
check, then releases on success, failure, exception, and timeout; a queued
transition cannot interleave and no nested acquire occurs. Also inject a
managed-runtime probe exception and require `UNCLEAR/STORAGE_NOT_READY`, not
admission. Pass set B to a probe fixture that captured set A and require failure
before either runtime record is read.

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```bash
"$PYTHON" tests/test_storage_runtime_ready.py
```

Expected: FAIL with `AttributeError: 'StorageContract' object has no attribute
'assert_runtime_ready_locked'`; every mutation and admission sentinel remains
at zero.

- [ ] **Step 3: Implement the exact read-only interface**

Add the optional probe keyword to the complete Task 7 constructor and define the method exactly:

```python
class ManagedRuntimeProbe(Protocol):
    def __call__(self, lock_set: StorageLockSet, *, home: Path,
                 expected_storage_transaction_id: str | None) -> bool: ...

def _default_managed_runtime_probe(
    lock_set: StorageLockSet, *, home: Path,
    expected_storage_transaction_id: str | None,
) -> bool:
    from startup_lease import managed_runtime_is_ready_locked
    return managed_runtime_is_ready_locked(
        lock_set, home=home,
        expected_storage_transaction_id=expected_storage_transaction_id,
    )

class StorageContract:
    def __init__(self, home: Path, *, environment: Mapping[str, str] | None = None,
                 broker: StorageBrokerClient,
                 fd_probe: FdProbe = probe_mount_fd,
                 managed_runtime_probe: ManagedRuntimeProbe =
                     _default_managed_runtime_probe) -> None: ...

    def assert_runtime_ready_locked(
        self, lock_set: StorageLockSet,
    ) -> StorageStatus:
        try:
            lock_set.assert_active(
                home=self._home, required_install_mode="shared",
                required_storage_mode="shared",
            )
            status = self.probe_locked(lock_set)
            optional = (
                status.storage_state == "unconfigured"
                and not status.mounted
                and status.transaction_id is None
            )
            required = (
                status.storage_state == "committed"
                and status.mounted
                and status.transaction_id is not None
            )
            if (
                status.verdict != "PASS"
                or not status.runtime_allowed
                or not (optional or required)
            ):
                return dataclasses.replace(
                    status,
                    verdict="UNCLEAR" if status.verdict == "UNCLEAR" else "FAIL",
                    code="STORAGE_NOT_READY",
                    runtime_allowed=False,
                )
            try:
                managed = self._managed_runtime_probe(
                    lock_set, home=self._home,
                    expected_storage_transaction_id=status.transaction_id,
                )
            except Exception:
                return dataclasses.replace(
                    status, verdict="UNCLEAR", code="STORAGE_NOT_READY",
                    runtime_allowed=False,
                )
            if not managed:
                return dataclasses.replace(
                    status, verdict="FAIL", code="STORAGE_NOT_READY",
                    runtime_allowed=False,
                )
            return dataclasses.replace(status, code="RUNTIME_READY")
        except (StorageLockError, OSError):
            return StorageStatus(
                verdict="UNCLEAR",
                code="STORAGE_NOT_READY",
                transaction_id=None,
                storage_state="unknown",
                mounted=False,
                runtime_allowed=False,
            )
```

Store the injected probe as `self._managed_runtime_probe`.
`assert_runtime_ready_locked()` accepts only the caller-owned active same-home
install-shared/storage-shared/admission-exclusive set, retains it through both
observations, calls `probe_locked()` once, and accepts only one of two coherent
storage projections: `(storage_state="unconfigured", mounted=False,
transaction_id=None)` or `(storage_state="committed", mounted=True,
transaction_id=<non-empty UUID>)`, always with `verdict="PASS"` and
`runtime_allowed=True`. A missing, closed, wrong-home, wrong-mode, replaced, or
forged set returns the exact `UNCLEAR/STORAGE_NOT_READY` unknown-state value.
A storage failure, `UNCLEAR`, active/rollback journal, detached committed vault,
missing transaction, or contradictory tuple returns `STORAGE_NOT_READY` with
`runtime_allowed=False`. Do not call the managed-runtime probe after a storage
failure. The outer caller, not this method, releases the set.

For a coherent projection, call the injected probe once with the same
`lock_set`, `home`, and exact transaction ID or `None`. False returns
`FAIL/STORAGE_NOT_READY`; an exception returns `UNCLEAR/STORAGE_NOT_READY`;
true returns `PASS/RUNTIME_READY` only when the lifecycle record is exactly
`READY`, while preserving storage state, mounted flag, transaction ID, and
`recovery="UNCLEAR"`. This method takes only shared/read-only observations: it
does not call `open_locked(lock_set)`,
`open_workspace_locked(lock_set, binding, requested)`, a lifecycle mutation,
or any local-alias module, and it never creates, consumes, refreshes, or deletes
a lease.

- [ ] **Step 4: Run GREEN contract and lease integration tests**

Run independently:

```bash
"$PYTHON" tests/test_storage_runtime_ready.py
"$PYTHON" tests/test_startup_lease.py
"$PYTHON" tests/test_storage_guard.py
"$PYTHON" tests/test_workspace_handle.py
```

Expected: PASS; failed finalization cases perform zero admission, every readiness loss between finalization and activation performs zero activation, all cases perform zero actual local worker/filesystem mutation, both coherent unchanged managed-runtime cases pass, and every workspace-handle case remains confined to exact `20_WORKSPACES`.

- [ ] **Step 5: Commit the read-only readiness boundary**

```bash
git add console/storage_contract.py tests/test_storage_runtime_ready.py
git commit -m "feat(storage): expose managed runtime readiness"
```

## Deferred final verification gate (after Foundation 4 + S3 Task 7)

Do not execute this section immediately after Task 14. First run the PASS-only
S3 Task 6 gate, then complete and commit the atomic Foundation Task 4 + S3 Task
7 installation unit. Execute this section immediately before S3 Task 8; it
creates no behavior and no commit.

**Files:**
- Inspect: `git diff --name-only`
- Inspect: `git status --short`

**Interfaces:**
- Consumes: all interfaces produced by Tasks 1-14 plus the installed aggregate
  and complete-generation publication from S3 Task 7.
- Produces: a tested code foundation ready for the separate live-vault plan and later mission/effect integration; it creates no production vault and performs no real production Keychain/disk mutation.

- [ ] **Step 1: Run all storage-focused suites independently**

Run each command from the repository root:

```bash
"$PYTHON" tests/test_disk_image_keychain_helper.py
"$PYTHON" tests/test_storage_broker.py
"$PYTHON" tests/test_storage_reconciliation.py
"$PYTHON" tests/test_storage_mount_probe.py
"$PYTHON" tests/test_storage_lock.py
"$PYTHON" tests/test_storage_lifecycle.py
"$PYTHON" tests/test_storage_guard.py
"$PYTHON" tests/test_storage_guard_integration.py
"$PYTHON" tests/test_storage_configuration.py
"$PYTHON" tests/test_storage_transition.py
"$PYTHON" tests/test_storage_import.py
"$PYTHON" tests/test_storage_cli.py
"$PYTHON" tests/test_installer.py
"$PYTHON" tests/test_installed_storage_runtime.py
"$PYTHON" tests/test_installed_storage_wheel.py
"$PYTHON" tests/test_selftest.py
"$PYTHON" tests/test_start_local.py
"$PYTHON" tests/test_startup_lease.py
"$PYTHON" tests/test_storage_runtime_ready.py
"$PYTHON" tests/test_process_ownership.py
"$PYTHON" tests/test_chat_settings_api.py
"$PYTHON" tests/test_workspace_handle.py
"$PYTHON" tests/test_workspace_path_fuzzing.py
"$PYTHON" tests/test_missions_api.py
"$PYTHON" tests/test_store_lifecycle.py
"$PYTHON" tests/test_executor_runtime_truth.py
```

Expected: every command exits `0`, selects at least one test, and performs no
real Keychain or disk-image operation. The separate owner-live command in S3
Task 11 remains unexecuted unless separately authorized at action time.

- [ ] **Step 2: Run syntax, type-adjacent and shell gates**

Run:

```bash
"$PYTHON" -m compileall -q console executor scripts tests
bash -n scripts/cortex.sh scripts/start-local.sh scripts/install.sh scripts/uninstall.sh
shellcheck scripts/cortex.sh scripts/start-local.sh scripts/install.sh scripts/uninstall.sh
scripts/verify-links.sh
git diff --check
```

Expected: all commands exit `0`; no malformed Python, Bash, shell warning, broken link, or whitespace error remains.

- [ ] **Step 3: Audit forbidden behavior and interface consistency**

Run:

```bash
rg -n -- '-agentpass|security -g|dump-keychain|-force|enableOwnership|sudo' \
  native/macos console/storage_*.py scripts/cortex-storage.py scripts/import-cortex-storage.py
rg -n 'ToolExecutor\(' console executor tests
rg -n 'WorkspaceHandle|StorageContract|StorageStatus|StorageBinding' console executor tests
rg -n '40_ARCHIVES|browser_transport.*(playwright|webbridge)' console scripts tests
rg -n 'LocalAliasHandle|local_alias_worker|LocalAliasActionService|mkdirat' \
  console/storage_contract.py executor/workspace_handle.py
```

Expected: the first command finds no executable fallback/privilege path (test assertions and explicit rejection constants may name forbidden strings); production `ToolExecutor` still has no partial path/handle hybrid added by this plan; every consumer uses the exact signatures in Tasks 7-8 and 14; `40_ARCHIVES` is rejected rather than created; legacy browser transports appear only in fixture branches and negative tests; the final command returns no match because storage authority and the vault handle implement no local-alias worker, handle, service, or `mkdirat` path.

- [ ] **Step 4: Run the existing complete automated gate**

Run:

```bash
test -d frontend/node_modules
PYTHON311="$(command -v python3.11)" \
PYTHON314="$(command -v python3.14)" \
scripts/test-all.sh
```

Expected: the complete backend, extension, frontend unit/coverage, typecheck, lint, fresh build, E2E, accessibility, runtime, privacy and release-evidence gate exits `0` without a frontend-skip message.

- [ ] **Step 5: Review diff, secrets and atomic history**

Run:

```bash
gitleaks detect --source . --no-banner --redact --no-git
git diff --check
git status --short
git log --oneline --decorate -14
```

Expected: no working-tree secret finding; only files named in this plan are changed; each implementation unit has one reviewable atomic commit, with Tasks 12+13 represented by their one required combined commit; no merge, tag, push, production vault, production Keychain item, or real storage publication occurred.

Do not create an additional completion commit when the tree is already clean. If Step 2-4 required a narrowly scoped correction, amend only the task commit that owns those files after rerunning its RED/GREEN command and this final gate.

## Execution boundary

- This plan ends with implementation and isolated verification of the storage foundation.
- The separately authorized live plan may call the eight `scripts/cortex-storage.py` subcommands in order without rebuilding their logic.
- The live plan must still show each dry-run hash before applying a mutating command, separately authorize disposable cleanup, and never infer production authorization from approval of this implementation plan.
- `WorkspaceHandle` remains vault-only. Downstream local-alias finalization/activation may consume only `StorageContract.assert_runtime_ready_locked(lock_set) -> StorageStatus`; it cannot receive a `StorageBinding` or `WorkspaceHandle` and must repeat the assertion at both boundaries under an active set.
- Mission admission, `ToolExecutor(workspace: WorkspaceHandle)`, FD-relative file tools/process `addfchdir`, local-alias catalog/grant/action/worker implementation, runtime truth UI, STOP effect epochs, black-box T12-T18, and live R1-R5 remain owned by their separate implementation/live plans.
