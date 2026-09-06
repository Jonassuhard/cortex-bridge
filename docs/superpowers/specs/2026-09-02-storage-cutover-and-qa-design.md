# Cortex Bridge Storage Cutover and QA Completion Design

**Status:** Architecture A approved by the owner; written specification pending review
**Date:** 2026-09-02
**Target:** v0.5.4 candidate

## Normative precedence for S3

`docs/superpowers/specs/2026-09-03-s3-owned-process-supervision-design.md`
takes precedence over this document for every disk-image helper, native-process
ownership, local protocol, recovery ledger, storage lock bundle, installed
native topology, update/reinstall/uninstall rule, and storage evidence gate.
In particular, every one-shot `disk-image-keychain` helper,
`CORTEX_HOME/native` storage-helper topology, fresh-helper-process mount clause,
direct Python `hdiutil`/`diskutil` spawn, and helper-preservation uninstall
clause below is historical and superseded. The persistent S3 broker and its
integrated storage-runtime generation are the only implementation path.

The R17 S3 contract also supersedes any unbounded or non-lock-carrying storage
factory, any reconciliation route that starts a replacement broker, and any
public response that exposes a device node. Product construction uses the
single lock-carrying installed-runtime aggregate. A workflow that requires
effect reconciliation retains its original broker until the closed probe
exchange is durably acknowledged; the local device-bearing response is mapped
to separate redacted storage evidence before rendering or export.

R17 further requires a pre-START durable recovery authority that cannot grant
START, exact owner-connection/audit-token binding, lock-carrying transition and
ledger APIs, and non-reconciliation-bearing read-only workflow failures. Only
the original retained broker may run the closed read-only reconciliation
observation allowlist. Product launch begins at the stable bootstrap outside
the mutable generation, retains install-shared through generation/interpreter
attestation and factory adoption, and treats runtime lifespan as the attested
`STARTING → READY → CLOSED` chain. These clauses supersede any contrary
startup, helper, recovery, or unlocked-journal wording below.

All descriptor-first host, APFS, volume-name/UUID, encryption UUID, Keychain,
mount, transition-journal, vault-only workspace, and live-authorization
requirements in this document remain normative unless S3 strengthens them.

## Decision

Cortex Bridge will stop depending on the inaccessible legacy disk image. No
operation in this design mounts, opens for write, repairs or modifies that
legacy sparsebundle; preservation is limited to this explicit non-mutation
contract, not an uncomputed byte-for-byte claim. A new dedicated 256 GiB
AES-256 sparsebundle with an APFS volume becomes verified external storage for
Cortex only after its identity, ownership, Keychain unlock, detach/remount,
rollback and runtime gates all pass.

Once storage is healthy, the remaining black-box tests run in a synthetic,
disposable workspace. Reproduced product defects are fixed with regression
tests in priority order. No release, merge, tag or push is implied by this
design.

## Verified starting point

- The legacy image is encrypted and detached.
- Its DiskImages metadata exposes exactly one passphrase slot, zero private-key
  recovery slots and one internal encryption UUID.
- The owner-provided passphrase is rejected even when six bytes reach
  `hdiutil` exactly through hidden standard input.
- No matching legacy Keychain item or recovery-key file was found.
- Native DiskImages lookup reached SecurityAgent but did not unlock the image
  automatically. A modern Data Protection/iCloud item therefore remains
  `UNCLEAR`, not proven usable.
- No repair, overwrite or mutation of the legacy image has been attempted.
- The external host filesystem is mounted and writable, but it is ExFAT. APFS
  protects the filesystem inside the image; the sparsebundle bands remain on a
  non-journaled ExFAT host and therefore require clean detach and separate
  backup rules.
- The active storage guard fails closed because its configured APFS volume is
  absent.
- The local runtime home, database, settings, virtual environment, native
  helper, process state and private locks remain available on the internal
  disk.

## Goals

- Restore a verified external Cortex workspace without touching the legacy
  image. Disaster recovery remains `UNCLEAR` until a detached copy and
  independent recovery secret are proven on a second support.
- Keep all secrets out of command arguments, shell history, files, reports,
  screenshots and Git.
- Prove automatic Keychain-backed remount twice before importing data or
  publishing configuration.
- Keep `CORTEX_HOME` local and move only approved large, rebuildable or
  workspace data to the verified external root.
- Preserve a complete rollback for every configuration file changed by the
  cutover.
- Make runtime and workspace status truthful in every visible panel.
- Finish black-box tests T12-T18 with synthetic data, explicit per-action
  approvals, no deletion and no executor network capability beyond the existing
  authenticated ChatGPT browser transport.
- Fix every reproduced P0/P1/P2 defect in scope with a failing regression test
  first.
- Produce anonymized evidence sufficient for a strict `PASS`, `FAIL` or
  `UNCLEAR` verdict.

## Non-goals

- No repair, compact, conversion, mount retry, password guessing, deletion or
  modification of the legacy sparsebundle.
- No copying from the inaccessible legacy volume.
- No reformatting of the external host disk.
- No automatic `sudo`, ownership override or security-setting change.
- No migration of the SQLite database, credentials, current logs, locks,
  attachments, runs, virtual environment or native helper off the internal
  disk.
- No OpenAI API, CAPTCHA bypass, hidden ChatGPT system prompt or replacement
  browser profile.
- No permanent deletion, new arbitrary outbound network capability, deployment,
  publication, merge, tag or Git push. The existing authenticated ChatGPT
  browser transport remains the only external product path.
- No claim that a ChatGPT response proves a local filesystem action.

## Runtime-resolved paths

Private host paths are discovered at execution time and recorded only in local,
ignored evidence. The committed design uses these stable names:

| Name | Contract |
| --- | --- |
| `HOST_VOLUME` | Mounted external host volume already used for Cortex disk images |
| `NEW_IMAGE` | `HOST_VOLUME/CORTEX_BRIDGE_2026_09.sparsebundle` |
| `NEW_VOLUME_NAME` | `CORTEX_BRIDGE_2026_09` |
| `NEW_MOUNT` | `CORTEX_HOME/mounts/CORTEX_BRIDGE_2026_09` |
| `NEW_ROOT` | `NEW_MOUNT/CORTEX_BRIDGE` |
| `CORTEX_HOME` | Existing dedicated local runtime home returned by `cortex.sh runtime-home` |

The executor must prove that `NEW_IMAGE` does not exist, that the legacy image
is outside the new target, that the host volume identity matches the preflight
snapshot, and that at least 320 GiB remains free before creation. Device names
such as `disk15s2` are observations, never durable identity.

The private mount point lives under `CORTEX_HOME`, not `/Volumes`, because an
unprivileged user cannot pre-create a controlled directory in the root-owned
`/Volumes`. Its complete parent chain is local, owner-only and no-follow.

## New vault lifecycle

### 1. Preflight and stop

Before the first write or legacy-bundle read:

- open and retain the host-volume directory FD, prove its UUID/filesystem and
  `noatime` mount flag, and bind the legacy/new-image relative paths to that FD.
  If `noatime` or host identity is absent, do not read legacy metadata and stop;
- only after that gate, snapshot the legacy image canonical no-symlink path,
  file count, allocated size and hashes of `Info.plist`, `Info.bckup` and `token`
  as read-only evidence; this detects obvious drift but is not a full
  band-content identity proof;
- prove no process has the legacy image attached;
- prove `NEW_IMAGE` and `NEW_MOUNT` are absent, then create `NEW_MOUNT` as an
  empty current-user directory with mode `0700` and no symlink component;
- stop Cortex through its verified process-ownership path;
- create an owner-only cutover transaction directory under
  `CORTEX_HOME/private-quarantine`; for each of `settings.json`,
  `storage-bootstrap.json` and `storage-required`, record presence or absence
  and, when present, copy the exact bytes through verified descriptors together
  with device/inode/mode/size/SHA-256. Fsync every snapshot file, its manifest
  and the transaction directory before publication;
- publish a private, durable `CORTEX_HOME/storage-transition.json` journal in
  state `in_progress` before changing any control file. Start, server, Doctor
  and selftest fail closed while that state is present;
- acquire the verified owner-only `CORTEX_HOME/storage-state.lock` exclusively
  by FD and retain it through image creation, publication and final
  `committed` journal fsync. Cutover/rollback/import and installer take it
  exclusively; guard/start/Doctor/selftest take it shared; Settings writes take
  it exclusively. When `.install.lock` is also needed, it is always acquired
  first, then `storage-state.lock`. Contention fails or waits within a bounded
  deadline; no operation relies on a point-in-time process scan.

Any failed precondition stops the cutover before image creation.

### 2. Throwaway Keychain spike

The helper-process wording in this section is superseded by the persistent S3
broker; the spike invariants and Keychain schema remain normative.

No production image is created until a disposable 64 MiB image proves the
entire secret and Keychain path. The implementation adds a small signed or
locally compiled macOS helper that owns the whole image-secret lifecycle. Given
only non-secret image parameters, it generates the passphrase with
`SecRandomCopyBytes`, retains it in mutable `Data`, spawns trusted `hdiutil
create -stdinpass` with a private stdin pipe and sanitized environment, reads
the resulting encryption UUID, and publishes the generic-password item through
Security.framework in the same process. It returns only structured status,
overwrites mutable secret buffers before exit, and never accepts, returns or
logs a passphrase.

The Keychain item is Cortex-owned. It is never placed in or expected to be read
from Apple's private `com.apple.DiskImagesKeychainGroup`, which a locally signed
helper cannot join. Only the same installed Cortex helper creates and reads the
item; every mount goes through that helper, which retrieves the secret and
feeds `hdiutil attach -stdinpass` through a private pipe.

The candidate item contract is:

- class: generic password;
- account: the DiskImages internal encryption UUID;
- service: `com.cortexbridge.encrypted-storage`;
- label: the sparsebundle basename;
- description: `disk image password`;
- generic application tag: the non-secret cutover transaction UUID;
- Data Protection Keychain enabled;
- accessibility: `kSecAttrAccessibleWhenUnlockedThisDeviceOnly`;
- every add/read/delete query sets
  `kSecUseAuthenticationUI = kSecUseAuthenticationUIFail`;
- synchronizable disabled. Enabling iCloud synchronization is a separate
  external effect and is not authorized by this design.

These attributes are a candidate contract, not assumed truth. The spike passes
only when all of the following are observed on the throwaway image using fresh
helper processes:

1. generate 32 random bytes and Base64URL-encode them without padding into 43
   printable ASCII characters, so the passphrase cannot contain an interior
   NUL;
2. feed those 43 characters plus one terminal NUL to `hdiutil -stdinpass`
   through the helper-owned private pipe; the child inherits no unrelated FD;
3. publish the item in the same helper process without a secret argument,
   inherited environment value, file, terminal echo or output;
4. detach normally;
5. perform two helper `mount` calls in separate processes; each retrieves its
   own Keychain item and invokes `hdiutil attach -stdinpass` without user input,
   command-line secret, environment secret, file or SecurityAgent prompt;
6. prove the expected encryption UUID, mount and filesystem after both calls;
7. delete only the disposable image and disposable Keychain item after a
   separate cleanup authorization, or quarantine both if cleanup is not
   authorized.

`errSecInteractionNotAllowed`, authentication-required/cancelled status or any
SecurityAgent process/window observation is a terminal failure, never a prompt
fallback. The negative harness injects an interaction-required Security result
and proves the helper emits only the stable error code without opening UI or
calling `hdiutil`.

If any step is `FAIL` or `UNCLEAR`, production image creation stops. Interactive
`-agentpass`, plaintext recovery files, `security -g`, `dump-keychain -d` and
`security ... -w <secret>` are not fallback paths.

Publication is add-only: any pre-existing item matching the throwaway or
production UUID/service is a collision and stops the run; the helper never
updates an unknown item. Cleanup selects the exact disposable UUID and service
and must observe exactly one match before deletion.

Before helper creation begins, the transition journal records
`image_create_started`, target image and transaction UUID. If the helper exits
without a receipt, recovery queries only that transaction tag plus the image
encryption UUID/service. Exactly one item that the helper can use to mount the
exact image twice is adopted and journaled `keychain_bound`; zero items means
the now-unrecoverable image is quarantined without deletion before a new
transaction; multiple/mismatched items stop for manual review. This reconciles
a crash after `SecItemAdd` without overwriting or deleting an unknown item.

### 3. Production secret, image and Keychain item

After the spike passes, the same installed helper creates a new 43-character
Base64URL passphrase from 32 random bytes in memory. The passphrase:

- is never printed;
- is never included in a process argument or environment variable;
- is never written to a temporary or recovery file;
- reaches `hdiutil create -stdinpass` only through a private pipe with one
  terminal NUL;
- reaches Security.framework only inside the same native process that generated
  it, without another IPC hop;
- is handled in mutable buffers that are overwritten before process exit; this
  reduces exposure but does not claim perfect erasure across kernel or
  framework copies.

`NEW_IMAGE` is a 256 GiB sparsebundle with AES-256 DiskImages encryption and a
single APFS volume named `NEW_VOLUME_NAME`. The ExFAT host does not persist
meaningful POSIX UID/GID/mode for the sparsebundle, so this design makes no
`0700` claim for the host bundle. Encryption, exact host-volume identity,
canonical path and a bundle manifest protect/detect content handling; physical
host access can still rename, delete or corrupt bands. Mode `0700` and
current-user ownership apply only to the controlled mount point and directories
inside the APFS volume. Sparse allocation does not reserve the full virtual
size, but a 128 GiB free-space floor remains an operational stop condition for
bulk imports.

`hdiutil isencrypted -plist` must then report `encrypted=true`, one passphrase,
zero private keys and a non-empty internal encryption UUID. The helper publishes
the production Keychain item using the spike-proven schema.

Automatic helper-backed mount is a convenience within an unlocked user session;
it does not prevent another process running as that user from invoking the
Cortex helper. It is not independent disaster recovery. Recovery remains
`UNCLEAR` in this release because the helper intentionally never reveals or
exports the passphrase. A future recovery-export design requires separate
approval and a different protected destination. No irreplaceable or
personal-only data enters the vault while that gate is `UNCLEAR`; synthetic QA
and rebuildable cache may proceed with the limitation recorded.

### 4. Mount, ownership and remount gates

The attested-helper wording in this section means the installed persistent S3
broker. Each workflow retains its one broker; no per-call or replacement helper
exists.

Every attach is launched by the attested Cortex helper with `-stdinpass`,
`-owners on`, `-nobrowse` and the exact controlled `NEW_MOUNT`. The helper
supplies only its own Keychain secret through a private pipe; no caller supplies
a credential and no SecurityAgent may open after Keychain publication.

Immediately before every create/attach/detach/backup/import operation, the
runner reopens the host volume, verifies its UUID, filesystem, `noatime` flag
and canonical no-follow image path, and retains the host FD until the operation
and post-check complete. A disconnect, path reuse or changed support fails
closed.

`storage_mount_probe.swift` is generic to any inherited directory FD. On the
host ExFAT FD it must report `MNT_NOATIME` set before the first legacy-bundle
open and before every image operation; on the mounted APFS FD it must report
`MNT_IGNORE_OWNERSHIP` clear. The preflight test injects a host result without
`MNT_NOATIME` and spies on all legacy snapshot open/hash functions: `PASS`
requires zero calls and no legacy access evidence.

The new volume must pass all of these gates before any Cortex data enters it:

1. attach through the helper-backed Keychain path with the required options;
2. `diskutil` reports the expected volume name and UUID, APFS, writable state
   and exact mount point, while a native descriptor-based `fstatfs(2)` probe
   proves that `MNT_IGNORE_OWNERSHIP` is not set;
3. `diskutil verifyVolume` returns success without repair;
4. normal detach succeeds without `-force`;
5. the image disappears from `hdiutil info` and `NEW_MOUNT` is empty;
6. the same attach and verification succeed a second time;
7. a second normal detach succeeds and leaves `NEW_MOUNT` empty;
8. a third attach establishes the live cutover mount.

The implementation adds `native/macos/storage_mount_probe.swift`. The guard
opens the controlled mount directory with `O_DIRECTORY | O_NOFOLLOW`, compares
its `fstat(2)` identity, and passes that already-open descriptor to the helper
as an inherited FD. The helper never reopens a path. It calls `fstatfs(2)` and
returns only non-secret `st_dev`, `fsid`, flags, filesystem type,
`f_mntfromname` and `f_mntonname`.

The guard calls `diskutil info -plist` on that exact `f_mntfromname`, not on a
path, and verifies the bootstrap APFS UUID and name. It also reads `hdiutil info
-plist` and requires one entity whose canonical `image-path` is exactly
`NEW_IMAGE` and whose `system-entities[].dev-entry` equals that same
`f_mntfromname`; `hdiutil isencrypted -plist` must still expose the expected
internal encryption UUID. It then probes the same FD again and requires
identical device, fsid, mount-from, mount-on and flags before opening `NEW_ROOT`
relative to the mount FD. A detach/remount, cloned-volume substitution, image
path replacement or host change at any point fails closed. The structured
result exposes
`owners_enabled = !(f_flags & MNT_IGNORE_OWNERSHIP)`. Human-facing `diskutil`
text may corroborate but is not parsed because its plist omits `Owners`. Native
tests cover enabled, ignored, helper failure and deterministic mount-path
replacement. No `sudo`, `diskutil enableOwnership` or implicit administrator
change is attempted.

### 4a. Installed native-helper contract

This subsection's disk-helper names, paths, rebuild veto, and partial uninstall
preservation are superseded by the complete S3 installed-runtime generation.
The AX helper and descriptor mount-probe identity requirements remain.

The installer extends its existing owned-helper manifest to an ordered
`native_helpers` map containing the current AX helper plus
`disk-image-keychain` and `storage-mount-probe`. It compiles each reviewed
source with the equipped `xcrun swiftc`, applies an ad-hoc signature, verifies
`codesign --verify --strict`, and records source SHA-256, binary SHA-256, CDHash,
device, inode, owner and mode. Staging, exclusive publication, fsync, rollback,
Doctor and uninstall use the existing verified installer transaction pattern.

The new binaries live below the owner-only local `CORTEX_HOME/native` directory
with mode `0700`. Before every execution, the caller opens that private parent
by descriptor, rejects symlinks/replacement, and verifies the binary identity,
hash, signature and manifest record immediately before spawn. The same-UID
malicious-mutation threat remains outside the documented threat model; no
unsupported FD-exec claim is made. A helper rebuild is forbidden while a vault
Keychain item exists: a future helper migration must first prove that the new
code identity can read or safely rekey the item. Uninstall preserves attested
storage helpers and their manifest while a vault exists; it never strands or
deletes the Keychain item implicitly.

### 4b. One-click runtime mount ownership

`scripts/cortex.sh start` owns the new-vault mount lifecycle. Under the ordered
install/storage locks it first adopts an already mounted volume only if the
full same-FD/image/host contract passes. If the mount is absent, it revalidates
the host and attested helper, invokes helper `mount`, then runs the guard before
launching the server. Missing host support, locked user session, unavailable
item, prompt, or contradictory mapping fails start with an actionable status;
it never tries the legacy image or falls back to a plaintext credential.

`scripts/cortex.sh stop` first drives durable STOP/quiescence, closes all
workspace handles and owned processes, then invokes helper `detach` under the
exclusive storage lock. Detach must be normal, never forced, and must leave no
`hdiutil` mapping plus an empty private mount point. If another owner prevents
detach, the server stays stopped but status reports `STORAGE_ATTACHED_BLOCKED`
rather than claiming a clean shutdown. Two complete start/mount/stop/detach
cycles are mandatory acceptance tests.

No alternate launcher may bypass that owner. Under required storage,
`cortex.sh start` first creates a private socketpair and spawns the server child
in a blocked bootstrap state with one inherited control FD; the child cannot
enter `uvicorn.run` or bind. The parent now knows PID/PGID/start identity,
publishes and fsyncs a one-shot lease containing nonce, PID, PPID/start identity,
committed storage transaction and short expiry, and records process ownership.
Only then does it send lease ID+nonce over the control FD.

`console/server.py` opens the private lease through the verified pids-directory
FD, validates it against `getpid`, parent/start identity and current committed
storage transaction, atomically consumes it, fsyncs the receipt, and returns an
ACK over the socket before binding. The parent releases startup only after that
ACK. Timeout, EOF, missing ACK, forged/expired/mismatched/replayed lease or child
exit causes the parent to terminate and verify the owned process group; no port
bind is accepted. `scripts/start-local.sh` delegates to `cortex.sh start`
instead of executing `server.py` directly. Direct `python server.py` is allowed
only in an explicit development fixture with no required-storage marker. Tests
pause at each handshake boundary and cover every failure, the delegated
launcher and subsequent owned stop/detach.

The FastAPI lifespan independently requires the consumed managed-start context
whenever storage is required. Thus `python -m uvicorn server:app` or another
module loader without the lease fails startup and serves no request even if the
mount itself is healthy. The existing direct-uvicorn storage integration test is
extended to the mounted-but-unleased case.

### 5. External directory contract

The following real directories are created with mode `0700`, current-user
ownership and no symlink component:

```text
NEW_ROOT/
  00_INDEX/
  10_SOURCE/
  20_WORKSPACES/
  30_EVIDENCE/
  50_CACHE_REBUILDABLE/
    browser-profiles/
  90_ARCHIVES/
  99_QUARANTINE/
```

`40_ARCHIVES` is not valid. The canonical archive category is `90_ARCHIVES`.

### 6. Copy-only import

Only `scripts/import-cortex-storage.py` may import data. It accepts three
explicit modes and no arbitrary source/destination pair. Each invocation is
bound to a frozen source manifest and receipt: synthetic workspaces must carry
the current QA transaction ID; evidence must carry the exact passing privacy
manifest hash and independent review IDs; Git must carry a named local ref and
exact reviewed commit. Selecting a mode is never itself proof:

- synthetic or reproducibly rebuildable local workspaces to `20_WORKSPACES`;
- privacy-reviewed, ignored QA reports to `30_EVIDENCE`;
- the exact clean, reviewed Cortex Git commit from a verified local Git path to
  `10_SOURCE/cortex-bridge`.

Regular-file imports walk from opened source and destination directory
descriptors, reject symlinks and special files, freeze an ordered source
manifest, revalidate every source identity while copying to exclusive temporary
destinations, fsync files/directories, then require an identical destination
manifest. Every source regular file must have `st_nlink == 1`, and each
`(st_dev, st_ino)` may occur only once in the manifest. The source tree must
remain on its initially observed device and the destination must remain on the
APFS device proven by the storage guard. A replacement, hardlink, duplicate
inode or mutation yields `IMPORT_SOURCE_CHANGED` and no publication.

Before the Git import, the source must have a clean status, a named local ref
equal to the exact frozen commit, and passing history plus working-tree secret
scans. `.gitmodules`, gitlink mode `160000`, `submodule.*`, alternates and
`refs/replace/*` are rejected. The importer uses `git clone --no-local
--no-hardlinks --single-branch --no-tags --branch <frozen-ref>
--no-recurse-submodules`; pack transport rather than a local object-directory
copy ensures unreachable/dangling source objects are not imported. It verifies
destination `HEAD == <exact-frozen-commit>` independent of the current source
value, then re-reads the source ref and requires it still equals that same
commit. It verifies the tracked-content manifest against the frozen commit, requires
`git fsck --full` with no dangling/unreachable object, removes the automatically
created local `origin`, and requires: `git remote` empty, no URL or alternate
in `.git/config`, no replace/submodule ref or configuration, a clean worktree
and second history plus working-tree Gitleaks scans. Any failure quarantines the
incomplete destination without deleting the source.

Every copy uses checksum verification and a zero-difference dry run. Sources
remain intact. No browser profile, cookie database, local storage,
authentication state, credential or current personal workspace is copied. The
`browser-profiles` directory is created empty for future rebuildable
Playwright-only state.

With the active `chrome_extension` transport, `browser_profile_root` is an
inactive Playwright-development setting. Only its empty-directory identity and
confinement are validated; it is never used as evidence for Chrome pairing,
extension reconnection or the live transport.

Because the sparsebundle bands live on ExFAT, clean detach is mandatory before
any backup. Before irreplaceable data is permitted, the complete detached
sparsebundle must be copied to a second physical support, both copies must have
matching ordered SHA-256 manifests for every bundle file including `bands/*`,
and the copy must attach with the recovery passphrase. In the absence of that
second support, recovery remains `UNCLEAR` and only synthetic or rebuildable
Cortex data may be stored.

The following remain local under `CORTEX_HOME`: database, settings, chat-run
state, iterations, attachments, runs, logs, process records, locks, virtual
environment, native helper and private quarantine.

## Atomic cutover and rollback

`configure-external-storage.py` publishes the new mount path, volume UUID,
encrypted backing image and storage root only after the guard passes. It
publishes settings, bootstrap and required marker as separate atomic file
replacements while the durable transition journal remains `in_progress`.
Every normal start/API/Doctor/selftest path checks that journal first and fails
closed, so a crash between files cannot expose a partially published state.

The journal schema contains a unique transaction ID, schema version, monotonic
phase number, phase name, relative snapshot-directory name, exact snapshot
manifest SHA-256, original presence/absence records, target bootstrap/marker
hashes, target storage-projection digest and Keychain/image reconciliation
state. Every phase replacement and parent directory is fsynced. A resume accepts
only the one snapshot directory whose relative name and manifest hash match the
journal; multiple historical quarantines are never guessed.

After all three files and parent directories are fsynced, the cutover runner
reopens them, verifies bootstrap/marker hashes plus the canonical storage
projection from settings and runs the offline storage contract. It then
atomically marks the journal `committed`. The committed journal pins the
bootstrap, marker and storage-only projection — not the full `settings.json`
hash. That projection contains exactly `default_workspace`,
`browser_profile_root` and `browser_transport`. A legitimate theme/language
change is allowed only if Settings validation keeps that projection identical;
required storage paths and product transport are immutable until a new
journaled cutover. This is a journaled sequence, not a false claim of one
multi-file transaction.

After publication, settings change only these values:

- `default_workspace = NEW_ROOT/20_WORKSPACES`;
- `browser_profile_root = NEW_ROOT/50_CACHE_REBUILDABLE/browser-profiles`;
- `browser_transport = chrome_extension`.

`console/storage_contract.py` is the single fail-closed authority. When
`storage-required` or a transition journal is active, `default_workspace` must
resolve to the exact canonical `storage_root/20_WORKSPACES`, and
`browser_profile_root` to the exact canonical
`storage_root/50_CACHE_REBUILDABLE/browser-profiles`. Both must exist as real
directories on the verified APFS device with no symlink component. A mission
workspace may be that workspace root or a real descendant opened beneath it;
it may never escape, cross device or traverse a symlink.

When required storage or release runtime is active, `browser_transport` is
clamped to `chrome_extension`. Inherited `playwright` or `webbridge` values are
rejected before browser factory creation and the UI exposes no control that can
select them. Those transports remain test/development-only behind the explicit
development-fixture environment with no required-storage marker. Regression
tests load both legacy values under required storage and prove zero browser
construction or command.

Successful mission admission returns a `WorkspaceHandle`, not a trusted path
string. It retains the verified mount and workspace directory FDs for the
mission lifetime plus device/fsid/APFS UUID and relative display path. On resume
or process restart, the handle is reopened from the verified mount FD and the
full contract reruns before any browser or local effect. `ToolExecutor` accepts
only this handle. File tools use descriptor-relative `openat`, `mkdirat` and
`renameatx_np` operations with `O_NOFOLLOW`; they never resolve and reopen the
workspace by absolute name. Immediately inside the durable effect gate they
rerun `fstat`/`fstatfs` on the retained FDs before the syscall. A detach cannot
redirect an operation into the underlying mount-point directory.

Approved process launch resolves the SDK symbol at runtime: it uses
`posix_spawn_file_actions_addfchdir_np` on supported macOS 14/15 systems and the
non-`_np` `posix_spawn_file_actions_addfchdir` on macOS 26+, always with the
verified workspace/cwd FD and a parent-child release pipe. If neither symbol is
available, process launch fails closed; there is no path-based `cwd` fallback.
The child cannot execute until durable process ownership has been recorded.
This fixes directory identity; it is not presented as a general OS sandbox, so
unrestricted processes remain disabled in T12-T16/T18 and T17 uses only its
exact displayed loopback command.

Settings reads/writes, storage guard, mission create/resume, onboarding,
runtime-status production, start, server, Doctor and selftest all call that
authority. `CORTEX_STORAGE_BOOTSTRAP` and
`CORTEX_STORAGE_REQUIRED_MARKER` must be unset or name the exact private files
under the verified `CORTEX_HOME`; any alternate override fails closed. Escape
paths, symlinks, missing directories, alternate devices, hostile environment
overrides and post-cutover mutation are rejected before readiness or mission
admission.

The storage manifest is rebuilt with relative paths. Cortex then runs, in
order: storage guard, start, Doctor, selftest, API readiness, extension pairing,
SQLite quick-check and two full restart/reconnect cycles.

Rollback is allowed only while Cortex is stopped. Before the first restoration
it atomically changes the journal to `rolling_back`, which blocks every normal
runtime path and retains the exclusive storage-state lock. It restores the exact
saved bytes, mode and presence/absence of
`settings.json`, `storage-bootstrap.json` and `storage-required` through private
temporary files, exclusive publication, fsync and directory fsync. After all
three states match the private snapshot manifest, it marks the journal
`rolled_back`; only then may the journal be archived or removed. A crash at any
earlier phase leaves a blocking journal that the same idempotent rollback runner
can resume. Tests inject a crash after every publication boundary for both
originally-present and originally-absent files.

Neither new nor legacy image is deleted automatically. A failed new image may
be quarantined by renaming only after revalidating the host-volume UUID,
canonical no-symlink path, expected basename, `Info.plist` hash and ordered
bundle manifest. ExFAT inode values are not treated as durable identity.
Deletion remains a separate owner decision.

## Product repair domains

### Runtime and workspace truth — P0

The UI must distinguish an installed/available candidate model from the
executor actually observed for the current task. `executor_available=true`
cannot override `executor_kind=unavailable`, a failed pipeline component,
`release_eligible=false`, or a missing workspace.

`console/runtime_observations.py` contains pure producers for storage guard,
workspace, executor and pipeline observations; it imports no route module.
`console/runtime_truth.py` is the sole composer and emits one versioned
structure. `/api/status`, `/api/pipeline/status`, `/api/settings` and
`/api/onboarding` all project from that same structure through explicit
response types. `console/onboarding.py` and frontend code never infer
`workspaceExists` or `workspaceUsable` from a path string.

Legacy `iterations.json` and `_latest_local_task_runtime_truth` become strictly
historical and may not participate in current executor/readiness truth. Tests
seed a contradictory legacy task marked running/eligible and prove all four
current endpoints still report only observed mission/runtime state.

`CortexApp.tsx`, `SettingsPanel.tsx`, `OnboardingPanel.tsx` and
`runtimeTruth.ts` consume that same response. Static demo values may exist only
in demo fixtures. A missing or unverified workspace cannot be labelled valid in
the status rail, settings or onboarding guide, and the settings runtime panel
cannot hardcode `healthy`, `ready` or fake paths.

### External-storage ownership guard — P0

`storage_guard.py` treats ownership as runtime truth, not a one-time manual
check. `native/macos/storage_mount_probe.swift` receives the already-open mount
descriptor and returns its `fstatfs(2)` facts. The guard derives
`owners_enabled = !(f_flags & MNT_IGNORE_OWNERSHIP)` and rejects the flag being
set, a missing/failed probe, a changed descriptor/device/fsid or any
contradiction before `STORAGE_READY`. It does not parse human-readable
`diskutil` output or expect an `Owners` key in `diskutil info -plist`, because
that key is not available on the target macOS version.

`configure-external-storage.py`, `storage-check`, start, Doctor and selftest all
consume the same guard result. Doctor cannot report healthy and selftest cannot
pass when required storage is absent, ownership is ignored, either canonical
settings path escapes the verified root, or the ownership probe is
unavailable.

### Mission admission and legacy executor closure — P0

Every mission create, resume and recovered-run path validates its requested
workspace through `storage_contract.py` immediately before persistence and
again when building or using the retained `WorkspaceHandle`. With required
storage active, the workspace must be the verified `20_WORKSPACES` root or a
descriptor-opened descendant on the same APFS device. Missing roots, absolute
escapes, symlinks, device changes and path replacement fail before any ChatGPT
or executor mutation.

The historical mutating `POST /api/tasks` and
`POST /api/tasks/{id}/orchestrator-reply` routes are removed from the product
execution surface and return `410 LEGACY_TASK_ENDPOINT_DISABLED` without
creating a background task. Read-only historical task retrieval may remain.
The two tombstone POST handlers accept the raw Request and declare no Pydantic
body model, so absent, malformed, unknown-ID and valid bodies all reach the same
410 response rather than FastAPI returning 422 first.
`console/local_executor.py` therefore has no product-exposed mutation entry;
all mission-requested local effects flow through `MissionLoop` and its shared
effect gate. A regression test proves that the disabled route cannot call
`run_task`, create a process, write a file or alter the task store.

### Conversation switching and stale cache — P1

Conversation selection must show the last verified cached snapshot immediately
and run one bounded refresh in the background. The user-visible switch finishes
within ten seconds even when refresh fails. A failed refresh keeps the cached
content, stops the spinner and shows a precise retry state; it must not leave an
ambiguous stale/loading combination.

The transport owns an eight-second acquisition budget. The frontend owns the
ten-second user deadline, including cleanup and error projection. A superseded
load cannot overwrite the newly selected conversation.

### Cortex-created duplicate tab — P1

Reader/writer isolation remains mandatory. The extension may retire only a
redundant tab that it created itself, after the writer owns the canonical
conversation, no read is in flight and the tab provenance is proven. It never
closes or repurposes a user-created tab, never reuses an ambiguous writer and
never weakens delivery-uncertain handling.

The service worker keeps an in-memory provenance registry for each controlled
tab: `origin = cortex | user`, `role = read_only | writer`, session identity,
canonical conversation identity and in-flight command count. Retirement occurs
only after writer canonicalization and only for a redundant
`origin=cortex, role=read_only` entry with zero in-flight commands. Registry
loss on worker restart fails closed: unproven tabs are treated as user-owned
and never closed.

Regression coverage proves: snapshot then send in the same conversation retires
only the redundant Cortex reader; two distinct active writers remain isolated;
a user-created tab is never closed; a delivery-uncertain writer is never reused
or retired as safe; service-worker restart treats every lost provenance record
as user-owned; a reused tab ID cannot inherit the removed tab's provenance; and
`tabs.onRemoved` clears only the matching current entry.

### Archived conversations control — P1

No backend contract currently exposes ChatGPT archives. The dead control is
removed from the primary sidebar rather than pretending to support archives.
Future archive support requires a separate authenticated transport contract and
tests. Pinned, project and recent categories remain visible.

### Diagnostic export — P2

The export link is attached to the DOM, clicked once, removed after dispatch and
its Blob URL revoked after deferred cleanup. The UI shows `Téléchargement
demandé` with the generated filename, not an unprovable success claim, or an
inline failure state. A silent click and an alert-only error path are forbidden.
Browser QA observes a real download event and file before assigning `PASS`;
without that evidence the result is `UNCLEAR`.

### Structured move for lossless sorting — P1

T16 requires a real safe sort, not a second refusal test. Cortex therefore adds
one structured `move_file` tool rather than permitting shell `mv`, `cp` or an
unrestricted script. `orchestration/runner.py` derives the ChatGPT-visible tool
list directly from `orchestration.protocol.ALLOWED_TOOLS`; no second static
allowlist may drift. One contract test requires exact ordered equality between
`ALLOWED_TOOLS`, `TOOL_ARGUMENTS`, protocol read/write partitions, policy
registries and the public callable tool methods on `ToolExecutor`. The tool
accepts one source file and one destination path,
both below the verified workspace. It rejects symlinks, directories,
cross-filesystem moves, missing sources, existing destinations and any path
outside the workspace. It requires a write approval for every file, records
source device/inode/size/SHA-256 before the effect, uses the existing audited
macOS `renameatx_np(..., RENAME_EXCL)` pattern on verified parent-directory
descriptors, fsyncs both parent directories, and records destination identity
and hash after the effect. If that primitive is unavailable, the tool fails
closed; it never falls back to an overwriting rename or copy/delete sequence.
Ambiguous crash outcomes become `MOVE_OUTCOME_UNCLEAR` and are never replayed
automatically. `move_file` accepts only one-shot approval; tool-wide and
mission-wide write scopes never satisfy its per-file approval gate.

Sorting creates destination directories through the existing approved tool,
then calls `move_file` once per synthetic file. The validation compares ordered
relative paths, file count and total bytes, plus the exact expected mapping
`source relative path + SHA-256 -> requested destination relative path + same
SHA-256`. A global hash multiset alone cannot pass because it would miss files
swapped between categories.

### STOP effect barrier — P0

`orchestration/store.py` receives a transactional schema migration and runs
SQLite with `synchronous=FULL`. Durable control state stores the monotonic STOP
epoch, `inactive | stopping | stopped | resetting`, and timestamps. Approvals
store mission ID, exact action ID, epoch, canonical SHA-256 of tool plus
arguments, random one-shot nonce, scope and consumed state. Effects store a
unique ID, owner kind (`mission | direct_ui | admin_ui`), nullable mission/action
or mandatory request ID, epoch, canonical digest, optional parent effect,
category (`filesystem | process | browser`), `intent | active | succeeded |
failed | outcome_unclear`, authorization facts, ownership facts and result
receipt.

The approval API must echo the displayed mission ID, action ID, epoch,
arguments digest and nonce. Under one `BEGIN IMMEDIATE` transaction it compares
all five fields to the current pending action and consumes the nonce once. A
late, retried or replayed response returns conflict and cannot approve the next
action. Every write in T12-T18 uses a distinct one-shot approval; wider scopes
remain epoch-bound and never satisfy `move_file` or these acceptance tests.

Immediately before every effect, the loop enters the durable effect gate. In
one transaction it verifies STOP inactive, exact unconsumed approval where
required, current mission/action and matching epoch/digest; it consumes the
approval and durably records the effect `active` before dispatch. STOP uses the
same SQLite serialization point, increments the epoch, sets `stopping`,
invalidates pending approvals and prevents new activation. If STOP wins,
dispatch returns `STOP_EPOCH_STALE`; if activation wins, STOP records that owned
effect and waits for terminal reconciliation rather than pretending it never
began.

The gate covers filesystem/process tools and every external browser mutation:
contract/report/message sends, attachment upload, capture delivery,
conversation creation and any extension command that changes ChatGPT state.
Existing-session snapshot/status reads and bridge heartbeat are explicit
non-mutating exemptions; navigation/focus is not. A checked source inventory of HTTP routes,
`ToolExecutor` methods, transport methods and extension commands must equal the
classification table; a new unclassified entry fails tests.

`console/chrome_extension.py:ChromeExtensionManager.command` is the final
backend-to-extension choke point and checks the durable STOP/effect token before
emitting an envelope. `send_text`, attachment begin/chunk/commit, `send_bare`,
conversation/tab creation, focus/navigate/SPA navigate/close, model selection
and screenshot capture are effect-gated. Probe/list-conversation/list-model
operations are gated as browser control whenever they may implicitly create or
focus a tab. During STOP, only existing-session pure state reads plus the
explicit quiescence commands `press_stop` and `release_session` may bypass new
activation; those two exemptions are recorded as cleanup, never user work.
Heartbeats do not mutate browser state.

The checked classification table is concrete:

| Surface | Examples/owners | Durable rule during STOP |
| --- | --- | --- |
| Mission filesystem/process | every mutating `ToolExecutor` method | action-bound approval plus effect intent; no activation |
| Direct-chat local staging | `console/chat.py`, `console/attachments.py` upload and captured-PNG staging | user request ID plus filesystem intent; no new stage, retained partial is never auto-sent |
| Administrative local writes | Settings and Onboarding persistence | explicit UI request plus admin intent; blocked, with storage-state lock when relevant |
| Browser send/upload/control | manager commands for send, attachment, create/focus/navigate/close, select model | browser intent/token required; no envelope emission |
| Sensitive browser capture | backend `capture_screenshot` only | sensitive-read intent/token required; no capture |
| Existing-session pure reads | state/light-state/list-tabs/await-attachment when no tab creation occurs | allowed and recorded read-only |
| Quiescence cleanup | `press_stop`, `release_session`, owned-process termination | allowed only from STOP cleanup and recorded |
| Durable bookkeeping | effect/STOP receipts and terminal reconciliation | allowed so shutdown evidence can complete |
| Storage administration | installer/cutover/import/rollback while server is stopped | outside mission gate; exclusive storage-state transaction required |

`tests/test_effect_gate_routes.py` inventories every mutating/sensitive HTTP
route, attachment/onboarding/settings writer, public `ToolExecutor` method,
transport method and extension command against this table. Missing, duplicate
or unclassified surfaces fail.

`console/effect_gate.py` is shared by MissionLoop and non-mission routes. Every
direct/admin mutation request carries a frontend-generated UUID v4 reused only
for an exact retry, current STOP epoch, operation name and canonical semantic
payload digest. Settings/Onboarding bodies are fully canonicalized before
activation.

Before any temporary file is opened or any byte is written,
`begin_direct_intent` runs under `BEGIN IMMEDIATE`, verifies STOP inactive and
fsyncs an `intent` containing request ID, epoch, operation/meta digest, private
staging directory identity and a unique expected temporary basename derived
from request ID plus server nonce. A second serialized gate either lets STOP
invalidate that untouched intent or transitions it to `active` before
`openat(O_CREAT | O_EXCL | O_NOFOLLOW)` and the first byte. Upload/capture bytes
then stream into that unpublished FD while hashing. After file and directory
fsync, the gate durably adds temporary device/inode/content digest, expected
final identity/hash and prior target identity/hash before exclusive final-name
publication.

Under `BEGIN IMMEDIATE`, activation rechecks request ID unused or identical,
epoch current and authorization kind `direct_ui` or `admin_ui`, then records
`active` before any temporary open, final publication or browser command.
The low-level attachment store, settings saver and onboarding saver become
private entry points that require an unforgeable in-process `EffectActivation`
capability returned by this gate. A retry with the same ID/digest returns the
terminal receipt; a different digest conflicts; `active` or `outcome_unclear`
is never replayed.

Startup reconciliation compares the durable expected/prior hashes and
exclusive temp/final identities: exact expected final bytes become succeeded;
untouched prior state with no published target becomes failed-safe; any other
combination becomes `outcome_unclear` and keeps reset blocked. An intent that
never activated has no file and is cancelled; an active deterministic temp is
closed then quarantined idempotently when safe, never silently adopted or sent.
Screenshot/chat
flows form one parent request with ordered capture, local-stage and browser-send
child effects. STOP between children retains the synthetic staged artifact but
cannot activate the next child or auto-send it. Fault-injection tests crash
before temp open, after open, during stream, after fsync, before/after final
publish and before receipt for attachment, Settings and Onboarding. STOP tests
cover winning before intent, between intent/activation, after open and after
write before publication, plus between every composite child stage.

The extension toolbar capture path and `pendingCapture` state are removed.
`chrome.action.onClicked` cannot capture or retain page pixels. All screenshots
originate from Cortex's backend `capture_screenshot` command carrying a durable
effect token; extension tests prove a toolbar click causes zero capture API,
debugger, DOM-mask or pending state.

Browser intent is durable before dispatch. A crash or cancel after dispatch but
before confirmed receipt becomes delivery-uncertain and is never replayed.
`move_file` records source/destination identities and hash intent before rename;
restart reconciliation observes both names and classifies success, safe
pre-effect failure or `MOVE_OUTCOME_UNCLEAR` without replay. Process launch uses
the blocked child handshake: effect and PID/PGID/start identity are durable
before the child is released. Timeout, STOP and `CancelledError` terminate the
owned group and verify disappearance; an unreconciled group blocks reset.

On startup, any `active` effect must be reconciled before mission resume or
STOP reset. Reset acquires the same durable serialization point, is refused
unless state is exactly `stopped` and active-effect count is zero, increments
the epoch again, invalidates all earlier scopes, and only then returns to
`inactive`. Concurrent reset during `stopping` returns conflict.

Deterministic tests cover approval A delayed into action B, approval accepted
then STOP before dispatch, browser send intent then crash, move crash at each
rename boundary, process cancellation, service restart with stale approvals,
and `STOP active -> concurrent reset -> refusal -> quiescence -> fresh-epoch
reset`. A distinct request created and approved after reset alone may execute.

## TDD and ownership boundaries

Each repair begins with a failing regression test, changes the minimum
production surface and gets an independent read-only review before integration.
Only one writer owns a file at a time.

| Domain | Primary production ownership | Targeted tests |
| --- | --- | --- |
| Native helpers and Keychain spike | new `native/macos/disk_image_keychain.swift`, new `native/macos/storage_mount_probe.swift`, `console/installer.py` owned-helper manifest/Doctor/uninstall | helper-owned secret pipe, add/read item in fresh helper processes, two prompt-free helper mounts, attested install/tamper/rebuild refusal/uninstall preservation |
| Storage ownership, confinement and rollback | new `console/storage_contract.py`, `console/storage_guard.py`, `console/settings.py`, `transport/browser.py`, `console/installer.py`, `console/process_ownership.py`, `console/server.py`, `scripts/configure-external-storage.py`, `scripts/cortex.sh`, `scripts/start-local.sh` | same-FD image/device/UUID race, ownership flag/probe failure, transport clamp, lock contention/order, canonical projection, hostile env override, managed-start lease, journal/snapshot/reconciliation crash injection, start/stop/Doctor/selftest |
| Controlled import | new `scripts/import-cortex-storage.py` | receipt-bound modes, no-follow traversal, hardlink/duplicate inode, source mutation, device mismatch, manifest equality, no-local exact-ref Git, no dangling/remote/alternate/replace/submodule/secret |
| Runtime truth and mission admission | new `console/runtime_observations.py`, new `console/runtime_truth.py`, `console/onboarding.py`, `console/missions.py`, `console/server.py`, `console/local_executor.py`, API response models, new `executor/workspace_handle.py`, `executor/tools.py`, `frontend/components/CortexApp.tsx`, `frontend/components/SettingsPanel.tsx`, `frontend/components/OnboardingPanel.tsx`, `frontend/lib/runtimeTruth.ts` | four-endpoint authoritative truth, contradictory legacy history ignored, persistent FD/no-follow mission confinement, addfchdir process, legacy POST 410/no side effect, CortexApp/onboarding/settings contracts |
| Sync/cache | `frontend/hooks/useConversationController.ts`, `transport/chatgpt_web/adapter.py`, `console/chat.py`, isolated `SnapshotFaultTransport`, tagged Playwright spec | controller/session isolation, real monotonic switch trace and deterministic one-shot timeout/retry trace |
| Duplicate tab | `chrome-extension/service-worker-core.js`, `console/chat.py` | extension, readiness regression and session-isolation tests |
| Archives | `frontend/components/ConversationSidebar.tsx` | sidebar unit tests |
| Diagnostic export | `frontend/components/SettingsPanel.tsx`, new `SettingsPanel.diagnostic-export.test.tsx`, one focused Playwright spec | DOM link lifecycle, deferred revoke, inline requested/error state, no alert-only path, real download event/file |
| Structured move and durable effect/STOP gate | `orchestration/protocol.py`, `orchestration/runner.py`, `orchestration/store.py`, `executor/policy.py`, `executor/tools.py`, `orchestration/loop.py`, new `console/effect_gate.py`, `console/missions.py`, `console/chat.py`, `console/attachments.py`, `console/settings.py`, `console/onboarding.py`, `console/server.py`, `console/local_executor.py`, `console/chrome_extension.py`, `transport/browser_chrome_extension.py`, `transport/chatgpt_web/adapter.py`, `chrome-extension/service-worker.js`, `chrome-extension/service-worker-core.js` | exact effect/tool inventories, approval action/digest/nonce, mission/direct/admin persisted intents, crash reconciliation, staging/settings/onboarding capability gates, move/process/browser uncertainty, toolbar capture removal, STOP/reset/restart races |
| Evidence manifest | new `scripts/build-qa-evidence-manifest.py` | no-follow allowlist, deterministic relative inventory/hash, forbidden metadata/text rejection and mutation detection |

Because runtime truth and diagnostic export share `SettingsPanel.tsx`, they run
sequentially under the same writer. Sync/cache and duplicate-tab changes share
`console/chat.py`; they also run sequentially. Archives can run independently.

Targeted RED/GREEN commands are fixed before implementation:

```text
"$PYTHON" tests/test_disk_image_keychain_helper.py
"$PYTHON" tests/test_storage_mount_probe.py
"$PYTHON" tests/test_storage_guard.py
"$PYTHON" tests/test_storage_guard_integration.py
"$PYTHON" tests/test_storage_configuration.py
"$PYTHON" tests/test_storage_transition.py
"$PYTHON" tests/test_storage_import.py
"$PYTHON" tests/test_installer.py
"$PYTHON" tests/test_selftest.py
"$PYTHON" tests/test_start_local.py
"$PYTHON" tests/test_chat_settings_api.py
"$PYTHON" tests/test_attachment_boundaries.py
"$PYTHON" tests/test_executor_runtime_truth.py
"$PYTHON" tests/test_onboarding_runtime_truth.py
"$PYTHON" tests/test_workspace_handle.py
"$PYTHON" tests/test_workspace_path_fuzzing.py
npm --prefix frontend run test:unit -- components/CortexApp.integration.test.tsx components/OnboardingPanel.test.tsx components/SettingsPanel.regression-1.test.tsx
npm --prefix frontend run test:runtime
npm --prefix frontend run test:unit -- hooks/useConversationController.test.tsx
"$PYTHON" tests/test_transport_fixture.py
"$PYTHON" tests/test_transport_session_isolation.py
node --test chrome-extension/tests/extension.test.mjs
"$PYTHON" tests/test_chrome_extension_bridge.py
"$PYTHON" tests/test_chrome_extension_driver.py
"$PYTHON" tests/test_chrome_extension_readiness_regression.py
npm --prefix frontend run test:unit -- components/ConversationSidebar.test.tsx
npm --prefix frontend run test:unit -- components/SettingsPanel.diagnostic-export.test.tsx
npm --prefix frontend run build
"$PYTHON" scripts/normalize-static-output.py frontend/out
npm --prefix frontend run test:e2e -- --grep @conversation-switch-fault
npm --prefix frontend run test:e2e -- --grep @diagnostic-export
"$PYTHON" tests/test_executor_tools.py
"$PYTHON" tests/test_command_policy_fuzz.py
"$PYTHON" tests/test_protocol_report_fuzz.py
"$PYTHON" tests/test_protocol_state_store.py
"$PYTHON" tests/test_store_lifecycle.py
"$PYTHON" tests/test_loop_mock.py
"$PYTHON" tests/test_runner_mode_a.py
"$PYTHON" tests/test_process_policy.py
"$PYTHON" tests/test_process_ownership.py
"$PYTHON" tests/test_missions_api.py
"$PYTHON" tests/test_effect_gate_routes.py
"$PYTHON" tests/test_direct_effect_recovery.py
"$PYTHON" tests/test_qa_evidence_manifest.py
```

`PYTHON` is the equipped Cortex Python returned by the runtime-home preflight.
Newly named tests and the tagged diagnostic-export Playwright spec are created
by their respective TDD tasks. The Keychain test compiles the helper with
`xcrun swiftc`, creates its own 64 MiB throwaway image, verifies two fresh
helper-process remounts and performs only its own item/image cleanup. The mount-probe test
compiles its helper against the current macOS SDK and proves
`MNT_IGNORE_OWNERSHIP` behavior on the same inherited FD. These are mandatory
macOS integration gates, not optional or skipped unit tests. Every command is
run independently from the repository root. A command that selects zero tests,
skips a required integration, opens SecurityAgent or lacks the freshly built
downloaded diagnostic file is `FAIL`.

## Black-box completion T12-T18

All live data uses one unique `CB-QA-20260902-<nonce>` workspace. The executor
gets no outbound-network capability; the existing authenticated ChatGPT browser
transport is the only external network path. Deletion and unrestricted process
capabilities stay disabled. Process execution is disabled for T12-T16 and T18;
T17 may enable only the one displayed, loopback-only verification command,
with separate approval. Every local write is separately approved in Cortex.
Filesystem truth comes from Cortex tool receipts plus an independent inventory,
never from ChatGPT prose.

The terminal verdict matrix is fixed:

| Test | `PASS` | `FAIL` | `UNCLEAR` |
| --- | --- | --- | --- |
| T12 create directory/files | Each directory/file write has its own action-bound one-shot approval and terminal receipt; independent inventory shows both exact files, contents and hashes only below the synthetic root | Any broad/reused/mismatched approval, pre-approval write, wrong path/content or prose-only claim | An approval, receipt or independent inventory is missing |
| T13 refuse write | Approval is denied, no write tool executes and the named file is absent in the independent inventory | The file exists or an effect begins before refusal | Absence cannot be independently checked |
| T14 file and capture | One exact synthetic file and one privacy-safe synthetic capture reach the intended canonical chat once; ChatGPT visibly shows each attachment and one response; no private pixels appear | Wrong chat, duplicate delivery, missing attachment or private data exposure | Attachment presence, destination or privacy mask cannot be verified |
| T15 two writers/third refusal | A and B remain isolated; C is refused before extension/browser mutation; C retains exact draft and staged file | C dispatches, any draft/file disappears or messages cross conversations | Browser-mutation boundary or retained state lacks proof |
| T16 lossless sort | Phase A, capabilities disabled, performs no move. Phase B, each structured move has an action-bound one-shot approval; exact source-path/hash to requested destination-path/hash mapping, count and total bytes match | Silent phase-A movement, broad/reused approval, wrong mapping, overwrite, missing file, byte/hash mismatch or shell fallback | Any mapping, inventory or receipt is incomplete |
| T17 mini-site | Every file write has a distinct action-bound one-shot approval; one separately approved owned process listens only on loopback and returns HTTP 200. A 1440x900 browser visit proves title `CB-QA-MINISITE`, visible `[data-qa=hero]` and `[data-qa=cta]`, and stores one synthetic screenshot; controlled shutdown exits 0 and leaves no listener/PID | Broad/reused approval, network escape, unapproved command, wrong HTTP/DOM, missing screenshot, visual breakage, lingering listener or prose-only success | Any approval, browser artifact, DOM trace or owned-process shutdown lacks direct proof |
| T18 STOP and controlled resume | STOP before pending write yields no later action and no file; the deterministic approval-accepted→STOP→dispatch race is also blocked by the epoch gate. After explicit reset, a distinct newly approved synthetic write alone executes and is independently present | Any post-STOP effect, automatic resume, stale-epoch approval reuse, executor dispatch in the race or wrong file | Absence before reset, gate order or distinct post-reset action cannot be proven |

T16 phase B uses only the new structured `move_file` tool, never process
execution. T18 reset clears every prior pending approval; the post-reset write
requires a fresh request and approval in the new STOP epoch.

Every ChatGPT message, attachment send, capture send, local write approval and
process command remains an action-time external or filesystem effect. The exact
synthetic payloads are frozen in the implementation plan and shown to the owner
before execution. This design approval does not silently authorize those later
effects.

## Live regression retests R1-R5

Unit/fixture results do not close defects reproduced in real Chrome. After the
targeted and full suites pass, one privacy-safe live pass records:

| Retest | `PASS` | `FAIL` | `UNCLEAR` |
| --- | --- | --- | --- |
| R1 runtime/workspace truth | Current executor, ChatGPT and workspace/storage state agree in status rail, Settings and Onboarding. A separate isolated missing-workspace runtime shows unavailable in all three without claiming ready | Any panel hardcodes or contradicts the backend truth | One panel or backend observation cannot be captured |
| R2 conversation switch | Two real-Chrome synthetic switches each settle within 10 seconds and render cache immediately; a separate isolated fault run forces one refresh timeout, stops loading and exposes retry without stale+loading or superseded overwrite | Deadline exceeded, superseded content wins or ambiguous state remains | Either real timing or isolated failure trace is incomplete |
| R3 tab provenance | Authorized snapshot→neutral send leaves one intended canonical writer and retires only the Cortex-created redundant reader; a user tab stays open. Extension restart then proves lost provenance cannot close/reuse a tab | User tab closes, duplicate unsafe writer remains/reuses, or delivery is replayed | Tab ownership or canonical identity lacks proof |
| R4 sidebar/categories | No archives dead control is present; pinned, project and recent categories plus new-conversation control are usable | Dead archives action remains or required category/navigation breaks | Category source cannot be distinguished safely |
| R5 diagnostic export | Fresh UI build emits one real download event, downloaded file exists, inline requested state names it, and privacy scan passes | Silent click, duplicate download, missing file or privacy finding | Browser event or bytes cannot be observed |

R1's negative case uses a separate disposable `CORTEX_HOME` and synthetic
workspace path; it never mutates the committed production settings. R3's
neutral message and extension restart remain action-time approvals. Screenshots
crop conversation text and personal sidebar data.

R2 has no hidden production fault endpoint. Its positive half uses the real
paired Chrome transport and records monotonic click/cache/settled timestamps.
Its negative half starts a disposable development-fixture server with an
injected `SnapshotFaultTransport` that returns a cached snapshot then times out
exactly one refresh. The tagged Playwright test records selected, cache-rendered,
refresh-started, deadline, settled-retry and supersession events. The injection
class is unreachable unless the explicit development-fixture environment is
set and required storage is absent. The focused command is a fresh build plus
`test:e2e -- --grep @conversation-switch-fault`; zero tests or missing trace is
`FAIL`.

## Evidence and privacy

- Screenshots exclude personal conversations, raw URLs, names and paths.
- Structured evidence stores only synthetic text, elapsed times, verdicts and
  session-scoped pseudonyms.
- No cookie, token, passphrase, Keychain value or browser-profile content enters
  a report.
- Every important artifact receives SHA-256 and an independent evidence review.
- Verdicts use only `PASS`, `FAIL` or `UNCLEAR`; unavailable proof never becomes
  an inferred pass.
- Secret scans cover the branch diff and complete candidate history before any
  publication decision.

`scripts/build-qa-evidence-manifest.py` walks one explicit ignored QA root with
no-follow descriptors, rejects special files and mutation, and writes a
deterministic relative inventory containing media type, byte count and SHA-256.
It never records absolute host paths. The output manifest is excluded from its
own inventory, written last through an exclusive temporary file and fsynced.
Only artifacts named by that manifest may support a verdict.

The final gates run independently from the repository root with equipped
dependencies and no skipped suite:

```text
test -d frontend/node_modules
PYTHON="$PYTHON" scripts/test-all.sh
gitleaks detect --source . --no-banner --redact --log-opts="--all"
gitleaks detect --source . --no-banner --redact --no-git
scripts/verify-links.sh
"$PYTHON" scripts/build-qa-evidence-manifest.py --root "$QA_EVIDENCE_ROOT" --output "$QA_EVIDENCE_ROOT/manifest.json"
scripts/check-public-privacy.sh --root "$QA_EVIDENCE_ROOT" --markers tests/fixtures/privacy/ci-markers.txt --fingerprints scripts/privacy-fingerprints.json --url-allowlist scripts/public-url-allowlist.txt
"$PYTHON" scripts/build-qa-evidence-manifest.py --verify "$QA_EVIDENCE_ROOT/manifest.json" --root "$QA_EVIDENCE_ROOT"
shasum -a 256 "$QA_EVIDENCE_ROOT/manifest.json"
git diff --check
git status --short
```

`scripts/test-all.sh` must run backend, extension, frontend unit/coverage,
typecheck, lint, fresh build, E2E, accessibility, runtime, privacy and release
evidence without its frontend-skip message. The privacy scanner must report
zero findings and Gitleaks must scan `--all` history. The manifest hash is then
frozen only after the post-privacy `--verify` proves every artifact byte still
matches. The history and no-Git working-tree scans must both pass, including
untracked files. The frozen manifest is given to independent read-only
evidence, privacy and implementation reviewers; `PASS` requires all three to
report zero P0/P1/P2 against those exact bytes. Generated QA evidence remains
ignored and is never added to Git.

## Acceptance gates

| Gate | PASS condition | Failure behavior |
| --- | --- | --- |
| Legacy non-mutation | No plan operation attached, opened for write, repaired or modified the image; explicit metadata snapshot unchanged | Stop and preserve evidence; do not claim full byte identity |
| Keychain spike | Disposable image receives secret through the helper-owned private pipe and two fresh helper processes remount via their own item without user input or UI | Stop before production image creation |
| Vault creation | AES-256 metadata, APFS, writable, ownership enabled | Stop before import |
| Keychain unlock | Production image remounts twice through the spike-proven helper/item path, with `-owners on`, no secret outside helper memory/pipe and no UI | Quarantine new empty image |
| Independent recovery | Detached second-support copy, full bundle manifest match and recovery-secret mount pass | `UNCLEAR`; allow only synthetic/rebuildable data |
| Copy integrity | Allowlisted descriptor import, matching manifests, clean exact Git commit, empty remotes/submodules and secret scans pass | Stop before publication |
| Storage guard | Same-FD device/fsid/APFS UUID, mount, image, `MNT_IGNORE_OWNERSHIP` clear and root confinement pass | Fail closed |
| Cutover/rollback | Durable journal and exact private snapshots survive every injected boundary crash | Keep runtime blocked and resume rollback |
| Mission confinement | Every mission workspace is beneath verified `20_WORKSPACES`; legacy write routes are 410/no effect | Fail before browser or executor mutation |
| Product transport | Required/release runtime accepts only `chrome_extension`; legacy Playwright/WebBridge settings create no driver | Fail before browser construction |
| Runtime | Managed-start lease, Doctor, selftest, API, extension, SQLite, two restarts and two clean mount/detach cycles pass | Roll back configuration |
| Product fixes | Targeted RED/GREEN tests plus full suites pass | Revert the failing fix |
| Black-box QA | Direct visual/filesystem evidence for T12-T18 and live defect retests R1-R5 | Record `FAIL` or `UNCLEAR` |
| Privacy | Independent review reports zero P0-P2 and zero secret/PII finding | Block release |
| Git | Expected files only, diff check clean, no secret, no push | Block publication |

## Completion definition

The work is complete only when the Keychain spike, production storage and
runtime gates pass, all reproduced defects in this design are fixed and
verified, T12-T18 have honest terminal verdicts, evidence and privacy reviews
pass, and Git contains only the intended reviewed changes. Independent disaster
recovery may remain `UNCLEAR` only while the vault contains synthetic or
rebuildable data. Release publication remains a separate owner action.
