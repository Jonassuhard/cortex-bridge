# Cortex Bridge v0.5.4 Live Cutover and Release QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut Cortex Bridge over to a new verified encrypted external vault, prove the complete macOS lifecycle, execute T12-T18, R1-R5, and the distinct `LOCAL_ALIAS` owner acceptance with privacy-safe direct evidence, and prepare an honest v0.5.4 candidate without publishing it.

**Architecture:** This plan is the final integration stage. It consumes the storage/runtime foundation, durable-effect barrier, runtime/UI/browser repairs, hybrid-intent router, and the approved local-alias authority split only after their commits, focused tests, full gates, and independent reviews pass. General missions remain confined to vault-backed `20_WORKSPACES`; the Desktop owner acceptance uses the distinct `local_alias_action` path and must produce zero ChatGPT, writer, mission, outbox, browser, or extension effect. A local evidence recorder observes immutable receipts and files; it never grants approvals, fabricates product actions, or substitutes fixture/ChatGPT prose for real Chrome and filesystem truth.

**Tech Stack:** macOS 14+, APFS sparsebundle on an ExFAT host, Swift/Security.framework, Python 3.11 and 3.14, FastAPI/SQLite, Bash, Chrome MV3, React/Vitest/Playwright, SHA-256, Gitleaks.

**Spec:** `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md` at frozen SHA-256 `2034280b1b4943c2b602eba888b58742e2d77b428bdc63dc5f93a4b59c72cb5f`; `docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md` at frozen SHA-256 `472ae88687f6df00be1aac7bb33af536b0456fdc7fd04b7bb5f95e637e4b38f5`; and the precedence-setting `docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md` at frozen SHA-256 `38dff2d114ddf3a8f2262f3ac2b37dcbec9fd33951934c5d5c03a9a0c4acc08b`.

## Global Constraints

- Do not begin this plan until the four prerequisite implementation plans are committed, reviewed with zero P0/P1/P2, and green. Record their exact commit IDs in the private run header.
- Keep the inaccessible legacy sparsebundle detached. Do not attach, repair, compact, convert, copy, rename, delete, or open it for write. Read its allowlisted metadata only after the host-FD/noatime preflight passes.
- Every vault, Keychain, import, sensitive local read, local write, process, Chrome control, ChatGPT send, attachment, and capture is a separate action-time effect or explicitly approved QA observation. This plan and its implementation commits authorize none of them.
- Never request, accept, display, log, screenshot, persist, or pass a storage secret. The installed helper alone generates, holds, uses, and zeroes the secret.
- Keep `CORTEX_HOME`, SQLite, settings, locks, logs, virtual environment, native helpers, and current attachments on the local internal disk. The new vault receives only synthetic/rebuildable data until independent recovery becomes `PASS`.
- Use the unpacked production extension in the user's real signed-in Chrome profile for live ChatGPT gates. Do not use the OpenAI API, a separate Playwright profile, WebBridge, or a hidden browser.
- Load Chrome's unpacked extension only from the installed local manifest-owned path returned by `scripts/cortex.sh extension-path --json`; never from the external Git checkout, because normal stop detaches that volume.
- Use only synthetic identifiers and content below the unique `CB-QA-20260902-<nonce>` root. Do not record account identity, private conversation titles/IDs, cookies, tokens, raw URLs, absolute paths, or unredacted sidebars.
- A fixture test cannot close a live gate. A ChatGPT sentence cannot prove a local effect. Missing direct evidence is `UNCLEAR`; observed contract violation is `FAIL`.
- Never disable, remove, substitute, or point around the production required-storage marker to make the live local-alias acceptance pass. The same installed runtime must report healthy committed storage and a valid managed-start lease before access verification, finalization, approval, and activation.
- Keep deletion and unrestricted process capability disabled. T17 enables only its displayed Python loopback server command, once per mini-site, with a separate one-shot approval.
- Public repository prose is English; product copy is French. Windows is outside v0.5.4 acceptance because the supported target is macOS 14+ and Chrome 116+.
- Do not push, merge, tag, create a release, delete a duplicate checkout, or modify Dependabot branches in this plan.

---

### Task 1: Freeze the integration baseline

**Files:**
- Inspect: `docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md`
- Inspect: `docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md`
- Inspect: `docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-storage-runtime-foundation.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-durable-effects-and-executor.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-runtime-ui-and-browser-reliability.md`
- Inspect: `docs/superpowers/plans/2026-09-02-v054-hybrid-intent-router.md`
- Create locally and ignore: `.gstack/qa-reports/v054-live/<run-id>/run-header.json`

**Interfaces:**
- Consumes: exact `S_COMMIT`, `E_COMMIT`, `U_COMMIT`, and `I_COMMIT` values from the committed phase ledger plus a clean candidate worktree.
- Produces: a private run header containing only version, commit IDs, spec hashes, OS/runtime versions, synthetic run ID, and `PASS|FAIL|UNCLEAR` prerequisite verdicts.

- [ ] **Step 1: Verify exact specifications and prerequisite commits**

Run from the repository root:

```bash
shasum -a 256 docs/superpowers/specs/2026-09-02-storage-cutover-and-qa-design.md
shasum -a 256 docs/superpowers/specs/2026-08-31-hybrid-intent-router-design.md
shasum -a 256 docs/superpowers/specs/2026-09-03-local-alias-action-addendum.md
git status --short
git log --oneline --decorate -12
for commit in "$S_COMMIT" "$E_COMMIT" "$U_COMMIT" "$I_COMMIT"; do
  git cat-file -e "${commit}^{commit}"
  git merge-base --is-ancestor "$commit" HEAD
done
```

Expected: all three hashes match the header, every prerequisite commit exists and is an ancestor of `HEAD`, every subordinate plan hash matches the frozen master-plan table, and the only mutable content is explicitly ignored private evidence. Any mismatch is `FAIL` before a runtime action.

- [ ] **Step 2: Re-run all prerequisite focused tests**

Run every focused RED/GREEN command named by the four plans from a fresh equipped environment. A missing test, skip, zero-test selection, or stale frontend build is `FAIL`.

- [ ] **Step 3: Run the complete pre-live gate**

```bash
test -d frontend/node_modules
"$PYTHON311" -m unittest discover -s tests -p 'test_*.py' -v
"$PYTHON314" -m unittest discover -s tests -p 'test_*.py' -v
PYTHON="$PYTHON311" scripts/test-all.sh
gitleaks detect --source . --no-banner --redact --log-opts="--all"
gitleaks detect --source . --no-banner --redact --no-git
scripts/verify-links.sh
git diff --check
```

Expected: every suite passes without the frontend-skip message; both secret scans report zero findings.

- [ ] **Step 4: Obtain three independent read-only implementation reviews**

Give the exact candidate commit to storage/runtime, safety/effects, and UI/intent reviewers. Continue only when all report `PASS` with zero P0/P1/P2 on the same bytes.

---

### Task 2: Build the immutable QA evidence manifest

**Files:**
- Create: `tests/test_qa_evidence_manifest.py`
- Create: `scripts/build-qa-evidence-manifest.py`
- Modify: `scripts/test-all.sh`

**Interfaces:**
- Produces: `build_manifest(root_fd: int, output_name: str = "manifest.json") -> dict[str, object]` and CLI modes `--root PATH --output PATH` or `--verify MANIFEST --root PATH`.
- Manifest entry: `{path, media_type, bytes, sha256}` with a relative normalized path only.

- [ ] **Step 1: Write failing no-follow and determinism tests**

Cover ordered regular files, nested directories, symlink/special-file rejection, hardlink rejection, root replacement, file mutation during hashing, absolute/private metadata rejection, output-self-exclusion, existing-output replacement, and byte-identical reruns.

- [ ] **Step 2: Confirm RED**

```bash
"$PYTHON" tests/test_qa_evidence_manifest.py
```

Expected before implementation: import/file-not-found failure.

- [ ] **Step 3: Implement the descriptor-only builder**

Use this public boundary:

```python
def build_manifest(root_fd: int, output_name: str = "manifest.json") -> dict[str, object]: ...
def verify_manifest(root_fd: int, manifest: dict[str, object]) -> None: ...
```

Walk beneath an opened `O_DIRECTORY | O_NOFOLLOW` root, allow regular files/directories only, hash the same opened FD that was statted, reject duplicate `(st_dev, st_ino)`, write the output last via an exclusive temporary file, fsync it and the root, and never serialize an absolute path.

- [ ] **Step 4: Confirm GREEN and wire the full gate**

```bash
"$PYTHON" tests/test_qa_evidence_manifest.py
PYTHON="$PYTHON" scripts/test-all.sh
```

Expected: focused and full gates pass with the new test mandatory.

- [ ] **Step 5: Commit atomically**

Commit only these files as `test(qa): add immutable evidence manifest`.

---

### Task 3: Build the non-authorizing live QA recorder

**Files:**
- Create: `tests/test_live_qa.py`
- Create: `scripts/cortex-live-qa.py`
- Modify: `scripts/test-all.sh`

**Interfaces:**
- `QaVerdict = Literal["PASS", "FAIL", "UNCLEAR"]`.
- `record_observation(root_fd, test_id, step_id, observation, artifact_refs) -> None` appends one fsynced, hash-chained JSONL observation.
- CLI: `init`, `record`, `inventory`, `evaluate`, and `status`; none accepts an approval token or invokes a product mutation.

- [ ] **Step 1: Write failing recorder contract tests**

Prove a unique synthetic run ID, monotonic steps, one terminal verdict per test, immutable artifact references, hash-chain verification, unknown-test rejection, secret/private-path field rejection, interrupted-write recovery, and refusal to execute shell/browser/product commands.

- [ ] **Step 2: Confirm RED**

```bash
"$PYTHON" tests/test_live_qa.py
```

Expected before implementation: import/file-not-found failure.

- [ ] **Step 3: Implement the minimum recorder**

Use fixed test IDs `T12` through `T18`, `R1` through `R5`, `INSTALL`, `STORAGE`, `RUNTIME`, and `LOCAL_ALIAS`. Store artifacts only by relative manifest path and SHA-256. `evaluate` applies the specs' fixed terminal matrices; it cannot turn absent evidence into `PASS`.

- [ ] **Step 4: Confirm GREEN and wire the gate**

```bash
"$PYTHON" tests/test_live_qa.py
PYTHON="$PYTHON" scripts/test-all.sh
```

- [ ] **Step 5: Commit atomically**

Commit only these files as `test(qa): add non-authorizing live recorder`.

---

### Task 4: Prove a clean native macOS lifecycle

**Files:**
- Create privately: `.gstack/qa-reports/v054-live/<run-id>/install/`
- Inspect: `scripts/install.sh`
- Inspect: `scripts/uninstall.sh`
- Inspect: `scripts/cortex.sh`
- Inspect after installation: manifest-owned `executor/local_alias_worker.py`

**Interfaces:**
- Consumes: a fresh private `HOME`, a fresh local `CORTEX_HOME`, and reviewed install/uninstall plan hashes.
- Produces: dry-run plan, install receipt, Doctor/selftest/status/API receipts, reinstall receipt, uninstall receipt, sentinel identity/hash, and port-release evidence.

- [ ] **Step 1: Create an isolated native test home without `sudo`**

Use `mktemp -d` on the internal disk; set `HOME` to that empty directory and `CORTEX_HOME` to its absolute `Library/Application Support/Cortex Bridge` child. Create one foreign sentinel outside every manifest-owned path and freeze its device, inode, mode, byte count, and SHA-256.

- [ ] **Step 2: Review and apply the exact install plan**

```bash
HOME="$QA_HOME" CORTEX_HOME="$QA_CORTEX_HOME" scripts/install.sh --dry-run --json > "$PRIVATE/install-plan.json"
HOME="$QA_HOME" CORTEX_HOME="$QA_CORTEX_HOME" scripts/install.sh --approve-plan "$INSTALL_PLAN_HASH" --json > "$PRIVATE/install-receipt.json"
```

The plan hash must be copied from the just-reviewed dry run. Applying a stale or different hash is `FAIL`.

- [ ] **Step 3: Prove Doctor, start, selftest, API, and stop**

Run `doctor --json`, `start`, `status --json`, `selftest`, `/api/status`, SQLite `quick_check`, then `stop`. Confirm the owned listener disappears. Optional Accessibility may be reported separately; no system permission is granted automatically.

- [ ] **Step 4: Prove idempotent reinstall**

Generate a new dry-run hash, apply it, and repeat Doctor/selftest. Verify installed manifest identities and the foreign sentinel are unchanged.

- [ ] **Step 5: Review and apply uninstall**

Generate and inspect the uninstall dry run, apply only that exact hash, then prove manifest-owned runtime resources are removed/preserved according to contract, the sentinel retains the same identity/hash, and no listener/PID remains. Never delete the temporary home as part of product uninstall; keep it until evidence review finishes.

- [ ] **Step 6: Record `INSTALL` verdict**

`PASS` requires real native execution with no `sudo`, all expected receipts, unchanged sentinel, and released port. Otherwise record `FAIL` or `UNCLEAR` with the exact missing proof.

- [ ] **Step 7: Install the reviewed candidate into the actual local runtime**

With the isolated lifecycle stopped and uninstalled, return to the real local `HOME`/`CORTEX_HOME`. Generate `scripts/install.sh --dry-run --json`, show the exact plan hash, changed manifest-owned files, native-helper and `executor/local_alias_worker.py` identities, and local extension destination, and await a distinct action-time installation authorization. Apply only that hash, then require Doctor/selftest to pass and prove installed source/helper/local-worker/extension hashes and version match `HEAD`; the local worker must be owned by the effective user, non-writable by group/other, and byte-identical to the reviewed manifest entry. Do not copy from or point Chrome at the external checkout.

---

### Task 5: Execute storage preflight and the disposable Keychain spike

**Files:**
- Create privately: `.gstack/qa-reports/v054-live/<run-id>/storage/`
- Inspect: `scripts/cortex-storage.py`
- Inspect: `native/macos/disk_image_keychain.swift`
- Inspect: `native/macos/storage_mount_probe.swift`

**Interfaces:**
- Consumes: installed attested helpers and the frozen `StorageContract`/storage CLI.
- Produces: redacted structured preflight, throwaway create/mount/detach receipts, negative `UIFail` receipt, and either an approved cleanup receipt or a quarantine receipt.

- [ ] **Step 1: Run code-ready preflight without external mutation**

Run:

```bash
"$PYTHON" scripts/cortex-storage.py preflight --host-volume "$HOST_VOLUME" --legacy-image "$LEGACY_IMAGE" --json
```

It must prove host UUID/filesystem/noatime from the retained FD, free space at least 320 GiB, legacy detached, new target absent, controlled mount absent/empty, Cortex stopped, and no concurrent storage transition. A preflight failure stops before any legacy metadata read or external write.

- [ ] **Step 2: Present the exact disposable effect plan for action-time approval**

Generate it with:

```bash
"$PYTHON" scripts/cortex-storage.py keychain-spike --host-volume "$HOST_VOLUME" --dry-run --json
```

Show image basename, 64 MiB size, service/account metadata fields, helper hashes, expected mount/detach sequence, mandatory integration command, and private evidence destination. Extract the exact `sha256_<64hex>` value from the `plan_hash` check. Do not show or ask for a password. Await explicit authorization for this spike only.

- [ ] **Step 3: Run the authorized spike**

Apply only the freshly reviewed plan:

```bash
"$PYTHON" scripts/cortex-storage.py keychain-spike --host-volume "$HOST_VOLUME" --approve-plan "$SPIKE_PLAN_HASH" --json
```

Create the throwaway image through a fresh helper process, detach normally, mount/detach from a second process, then mount/detach from a third process. Require the same encryption UUID, no SecurityAgent, no UI, and no secret in argv/environment/files/output.

- [ ] **Step 4: Run the mandatory real disposable integration gate**

After a separate authorization for this exact disposable 64 MiB test only, run:

```bash
CORTEX_KEYCHAIN_TEST_EFFECT_AUTHORIZATION=YES_DISPOSABLE_64_MIB_ONLY \
  "$PYTHON311" tests/test_disk_image_keychain_helper.py \
  --integration --allow-effects
```

Require two fresh helper-process remounts, exact cleanup of only the test item/image, no SecurityAgent/UI, and exit zero. Missing either command gate must exit before `SecItemAdd` or `hdiutil`.

- [ ] **Step 5: Prove fail-closed interaction handling**

Run `"$PYTHON311" tests/test_disk_image_keychain_helper.py` without effect flags and require the injected `errSecInteractionNotAllowed` case to emit a stable non-secret error, zero `hdiutil` call, and zero UI.

- [ ] **Step 6: Handle cleanup as a separate action**

Generate the separate cleanup plan with:

```bash
"$PYTHON" scripts/cortex-storage.py keychain-spike --host-volume "$HOST_VOLUME" --cleanup-approved --dry-run --json
```

Ask separately before applying its exact hash with `--cleanup-approved --approve-plan "$CLEANUP_PLAN_HASH"`. Without that authorization, quarantine both and record cleanup `UNCLEAR`; never broaden the selection or delete a production/unknown item.

---

### Task 6: Create, verify, import into, and publish the production vault

**Files:**
- Create privately: `.gstack/qa-reports/v054-live/<run-id>/storage/production/`
- Modify only through the storage transaction: local `CORTEX_HOME/settings.json`
- Modify only through the storage transaction: local `CORTEX_HOME/storage-bootstrap.json`
- Modify only through the storage transaction: local `CORTEX_HOME/storage-required`
- Create externally only after approval: `NEW_IMAGE`, `NEW_MOUNT`, and the canonical `NEW_ROOT` layout

**Interfaces:**
- Consumes: a `PASS` Keychain spike and fresh preflight.
- Produces: a committed journaled cutover or an exact idempotent rollback; no intermediate state is runtime-readable.

- [ ] **Step 1: Present the exact production creation plan**

Show the resolved host identity, exact new basename, 256 GiB virtual size, expected APFS name, transaction ID, local snapshot files, recovery limitation, and the fact that only synthetic/rebuildable data is permitted. Await action-time authorization.

- [ ] **Step 2: Create and bind the new vault**

Generate a `create-vault --host-volume "$HOST_VOLUME" --dry-run --json` plan, show it, then after separate authorization apply only its exact hash with `--approve-plan "$VAULT_PLAN_HASH"`. Require AES-256, one passphrase slot, zero private-key slots, non-empty encryption UUID, add-only Keychain publication, APFS, writable state, ownership enabled, exact host/image/mount identity, `diskutil verifyVolume`, two normal prompt-free remounts, and a third verified live mount.

- [ ] **Step 3: Initialize the canonical layout**

Generate `initialize-layout --dry-run --json`, approve its exact hash separately, then apply `initialize-layout --approve-plan "$LAYOUT_PLAN_HASH" --json`. Create exactly `00_INDEX`, `10_SOURCE`, `20_WORKSPACES`, `30_EVIDENCE`, `50_CACHE_REBUILDABLE/browser-profiles`, `90_ARCHIVES`, and `99_QUARANTINE`, all through verified descriptors with mode `0700` and current-user ownership. `40_ARCHIVES` is forbidden.

- [ ] **Step 4: Import only allowlisted data**

Use `scripts/cortex-storage.py import` separately for `--mode synthetic`, `--mode evidence`, and `--mode git`. Each command first uses `--dry-run --json`, gets its own action-time approval, then replaces `--dry-run` with `--approve-plan "$IMPORT_PLAN_HASH"`; all other arguments remain byte-identical. Import the exact clean reviewed Git commit into `10_SOURCE/cortex-bridge`; import only synthetic/rebuildable workspaces with `--qa-transaction-id "$QA_TX"`; import privacy-reviewed evidence only with its `--privacy-manifest-sha256` and two frozen `--review-id` values. Require source/destination manifest equality, clean exact Git `HEAD`, no remotes/submodules/alternates/replacements/dangling objects, and both secret scans. Leave every source intact.

- [ ] **Step 5: Publish the journaled cutover**

Generate `publish-cutover --dry-run --json`, obtain separate authorization, then apply only `publish-cutover --approve-plan "$CUTOVER_PLAN_HASH" --json`. Under `.install.lock` then `storage-state.lock`, publish only the three storage control files, re-open and verify their hashes/projection, run the offline contract, and fsync `committed`. Any injected or real failure first generates a `rollback --dry-run --json` plan and applies its exact separately authorized hash; it does not guess among snapshots.

- [ ] **Step 6: Prove two full mount/start/stop/detach cycles**

For each cycle: start owns mount, verifies storage, publishes/consumes the managed-start lease before bind, Doctor/selftest/API/SQLite pass, Chrome extension reconnects, STOP quiesces effects, and normal detach leaves no mapping/listener/PID. Any forced detach or direct uvicorn success is `FAIL`.

---

### Task 7: Reload and pair the installed Chrome extension

**Files:**
- Inspect: installed extension path returned by `scripts/cortex.sh extension-path --json`
- Create privately: `.gstack/qa-reports/v054-live/<run-id>/chrome/`

**Interfaces:**
- Consumes: a running verified runtime, real signed-in Chrome, local installed extension path, and explicit action-time browser-control authorization.
- Produces: extension version/protocol/pairing readiness receipt without account or conversation identifiers.

- [ ] **Step 1: Verify the canonical local extension copy**

Require a real owner-only local path, manifest ownership, expected hash/version, and no dependency on the mounted external checkout.

- [ ] **Step 2: Present the browser action**

Show that Chrome will open `chrome://extensions`, reload the exact unpacked local path, open Cortex and `https://chatgpt.com/` in the same Chrome window/tab group, and run the pairing check. Await explicit control authorization.

- [ ] **Step 3: Reload, pair, and prove readiness**

Require protocol v3 consistently in the installed manifest, backend status, pairing receipt, and extension report; require current heartbeat, zero pending command, enrolled identity/surface proof readiness, classic ChatGPT writer surface, ready composer/send button, and no 404 WebSocket handshake. If ChatGPT is signed out, show the product's French retry/close prompt; do not handle credentials.

- [ ] **Step 4: Prove restart behavior**

After a normal Cortex stop/detach and start/remount, require the locally loaded extension to reconnect. A Chrome entry pointing to the detached external checkout is `FAIL`.

---

### Task 8: Execute T12 and T13 from Cortex

**Files:**
- Create externally after individual approvals: `NEW_ROOT/20_WORKSPACES/CB-QA-20260902-<nonce>/T12/brief.txt`
- Create externally after individual approvals: `NEW_ROOT/20_WORKSPACES/CB-QA-20260902-<nonce>/T12/data.json`
- Must remain absent: `NEW_ROOT/20_WORKSPACES/CB-QA-20260902-<nonce>/T13/denied.txt`

**Interfaces:**
- Exact T12 contents: `brief.txt = "CORTEX BRIDGE QA T12\n"`; `data.json = "{\"marker\":\"CB-QA-T12\",\"value\":12}\n"`.
- Exact T13 denied content: `"CORTEX BRIDGE QA T13 DENIED\n"`.

- [ ] **Step 1: Send the exact T12 mission through Cortex**

Use: `Dans l’espace de test, crée le dossier T12, puis brief.txt contenant exactement CORTEX BRIDGE QA T12 suivi d’un saut de ligne, et data.json contenant exactement {"marker":"CB-QA-T12","value":12} suivi d’un saut de ligne.`

- [ ] **Step 2: Approve three one-shot actions separately**

Approve only `create_directory("T12")`, then each exact `write_file` digest. Require three distinct nonces and three terminal effect receipts.

- [ ] **Step 3: Inventory independently**

Using descriptor-based inventory, prove exact relative paths, modes, byte counts, contents, and SHA-256. Do not rely on the ChatGPT response.

- [ ] **Step 4: Send T13 and deny it**

Use: `Crée T13/denied.txt contenant exactement CORTEX BRIDGE QA T13 DENIED suivi d’un saut de ligne.` Deny the displayed write. Require no activated effect/tool call and independently prove absence.

---

### Task 9: Execute T14 file/capture delivery and T15 writer isolation

**Files:**
- Create after approval: `.../<run-id>/T14/attachment.txt`
- Create from a synthetic local-only page: `.../<run-id>/T14/capture.png`
- Stage for refused writer C: `.../<run-id>/T15/T15-C.txt`

**Interfaces:**
- T14 file content: `CORTEX BRIDGE QA T14 ATTACHMENT\n`.
- T14 local capture source bytes are exactly `<!doctype html><html lang="fr"><meta charset="utf-8"><title>CB-QA-T14-CAPTURE</title><style>html,body{margin:0;width:100%;height:100%;display:grid;place-items:center;background:#0B1220;color:#F8FAFC;font:700 56px system-ui}</style><body>CB-QA-T14-CAPTURE</body></html>\n`; viewport is 1280x720 and output is PNG.
- T14 message: `Réponds uniquement : CB-QA-T14-RECU`.
- T15 messages: `Réponds uniquement : CB-QA-T15-A`, `Réponds uniquement : CB-QA-T15-B`, and retained unsent draft `Réponds uniquement : CB-QA-T15-C`.

- [ ] **Step 1: Create and privacy-check the T14 artifacts**

Approve the synthetic file and local capture separately. Scan the PNG before any ChatGPT interaction; it must contain no Chrome chrome, sidebar, account data, path, or conversation content.

- [ ] **Step 2: Present and authorize the exact T14 external delivery**

Show destination pseudonym, message, both filenames/hashes, and the two browser effects. Await action-time approval for exactly one file attachment, one capture attachment, and one message send.

- [ ] **Step 3: Prove T14 visible delivery once**

The intended canonical chat visibly shows both attachments and exactly one user message, followed by one response containing `CB-QA-T14-RECU`. Record cropped evidence and extension receipts; duplicate or uncertain delivery is not replayed.

- [ ] **Step 4: Open two writers and authorize only A/B**

Choose two synthetic classic chats A and B, send their exact messages concurrently through Cortex, and record isolation plus exact responses. Every ChatGPT send is separately approved.

- [ ] **Step 5: Attempt writer C and prove pre-browser refusal**

Enter the exact C draft and stage `T15-C.txt` containing `CB-QA-T15-C\n`. Require refusal before extension/browser mutation, with draft and staged file still visible and byte-identical. Capture extension command count before/after.

---

### Task 10: Execute T16 lossless structured sorting

**Files:**
- Create after individual approvals: `.../<run-id>/T16/source/alpha.txt` with `alpha\n`
- Create after individual approvals: `.../<run-id>/T16/source/bravo.txt` with `bravo\n`
- Move to: `.../<run-id>/T16/sorted/text/alpha.txt`
- Move to: `.../<run-id>/T16/sorted/text/bravo.txt`

**Interfaces:**
- Uses only `move_file(source, destination, *, activation)`; process execution and shell fallback remain disabled.

- [ ] **Step 1: Freeze the source inventory**

Approve creation of `T16`, `source`, each source file, `sorted`, and `sorted/text` as distinct actions; no implicit parent creation is allowed. Record relative path, byte count, SHA-256, device and inode for both source files plus total count/bytes.

- [ ] **Step 2: Prove phase A cannot move**

Ask Cortex to sort while move capability is disabled. Require no prompt-based claim of success, no effect activation, and identical inventory.

- [ ] **Step 3: Enable only structured move and approve each mapping**

Approve `alpha.txt -> sorted/text/alpha.txt` and `bravo.txt -> sorted/text/bravo.txt` separately with exact digests/nonces. Refuse overwrite and any source/destination outside T16.

- [ ] **Step 4: Prove lossless mapping**

Require both source paths absent, both exact destination paths present, per-file hashes unchanged, count and total bytes unchanged, two terminal receipts, and zero process command.

---

### Task 11: Execute three independent T17 mini-site missions

**Files:**
- Create after per-write approvals: `.../<run-id>/T17-A/index.html`, `styles.css`
- Create after per-write approvals: `.../<run-id>/T17-B/index.html`, `styles.css`
- Create after per-write approvals: `.../<run-id>/T17-C/index.html`, `styles.css`
- Create by local browser capture: `.../<run-id>/T17-A/browser.png`, `T17-B/browser.png`, `T17-C/browser.png`

**Interfaces:**
- Every `index.html` has `<title>CB-QA-MINISITE</title>`, one visible `[data-qa="hero"]`, one visible `[data-qa="cta"]`, and a visible variant marker `CB-QA-T17-A|B|C`.
- A uses dark aurora, B uses editorial paper, C uses geometric cobalt. Each stylesheet must be distinct and responsive at 1440x900.
- Approved commands use the verified workspace FD as cwd: `[$PYTHON, "-m", "http.server", "49217|49218|49219", "--bind", "127.0.0.1"]`.
- Exact mission prompts are:
  - A: `Crée dans T17-A un mini-site local autonome, sans ressource externe, avec le titre CB-QA-MINISITE, un hero sombre de style aurore, un bouton visible et le marqueur CB-QA-T17-A. Utilise seulement index.html et styles.css, puis lance le serveur local approuvé.`
  - B: `Crée dans T17-B un mini-site local autonome, sans ressource externe, avec le titre CB-QA-MINISITE, un hero éditorial sur papier clair, un bouton visible et le marqueur CB-QA-T17-B. Utilise seulement index.html et styles.css, puis lance le serveur local approuvé.`
  - C: `Crée dans T17-C un mini-site local autonome, sans ressource externe, avec le titre CB-QA-MINISITE, un hero géométrique cobalt, un bouton visible et le marqueur CB-QA-T17-C. Utilise seulement index.html et styles.css, puis lance le serveur local approuvé.`

- [ ] **Step 1: Freeze exact site bytes before sending each mission**

Add the following deterministic fixture objects to the private run plan and record their hashes, ports, selectors, and screenshot outputs. The terminal newline shown by each triple-quoted literal is part of the file. No remote font, image, script, analytics, or network URL is allowed.

```python
T17_VARIANTS = {
    "A": {
        "port": 49217,
        "index.html": """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CB-QA-MINISITE</title><link rel="stylesheet" href="styles.css"></head><body><main data-qa="hero"><p>CB-QA-T17-A</p><h1>Construire sans bruit.</h1><a data-qa="cta" href="#preuve">Voir la preuve</a></main><section id="preuve">Local. Vérifiable. Réversible.</section></body></html>
""",
        "styles.css": """*{box-sizing:border-box}body{margin:0;background:#07111f;color:#f8fafc;font-family:system-ui,sans-serif}main{min-height:78vh;display:grid;place-content:center;padding:8vw;background:radial-gradient(circle at 30% 20%,#2dd4bf66,transparent 34%),radial-gradient(circle at 75% 45%,#7c3aed88,transparent 38%)}p{letter-spacing:.18em;text-transform:uppercase}h1{font-size:clamp(3rem,8vw,7rem);margin:.2em 0}a{width:max-content;padding:1rem 1.4rem;border:1px solid #5eead4;border-radius:999px;color:inherit}section{padding:5rem 8vw;font-size:1.5rem}
""",
    },
    "B": {
        "port": 49218,
        "index.html": """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CB-QA-MINISITE</title><link rel="stylesheet" href="styles.css"></head><body><main data-qa="hero"><p>CB-QA-T17-B · ÉDITION 01</p><h1>La preuve avant la promesse.</h1><a data-qa="cta" href="#note">Lire la note</a></main><section id="note">Une interface calme, une exécution mesurable.</section></body></html>
""",
        "styles.css": """*{box-sizing:border-box}body{margin:0;background:#f1eadc;color:#211d18;font-family:Georgia,serif;border:18px solid #211d18}main{min-height:72vh;padding:8vw;display:flex;flex-direction:column;justify-content:space-between;border-bottom:2px solid #211d18}p{font:700 .85rem system-ui;letter-spacing:.14em}h1{max-width:11ch;font-size:clamp(3.4rem,8vw,7.4rem);line-height:.9;margin:.6em 0}a{font:700 1rem system-ui;color:#f1eadc;background:#211d18;padding:1rem 1.3rem;width:max-content}section{padding:4rem 8vw;font-size:1.4rem;font-style:italic}
""",
    },
    "C": {
        "port": 49219,
        "index.html": """<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CB-QA-MINISITE</title><link rel="stylesheet" href="styles.css"></head><body><main data-qa="hero"><span>CB-QA-T17-C</span><h1>Signal net.<br>Action locale.</h1><a data-qa="cta" href="#systeme">Explorer</a></main><section id="systeme">Trois formes. Un chemin contrôlé.</section></body></html>
""",
        "styles.css": """*{box-sizing:border-box}body{margin:0;background:#dbeafe;color:#081a4b;font-family:Arial,sans-serif}main{min-height:80vh;padding:7vw;position:relative;overflow:hidden;display:grid;align-content:center}main:before,main:after{content:'';position:absolute;width:34vw;aspect-ratio:1;background:#1d4ed8;transform:rotate(24deg);right:-5vw;top:-9vw}main:after{background:#60a5fa;right:16vw;top:46vh;width:20vw}span,h1,a{position:relative;z-index:1}span{font-weight:800;letter-spacing:.16em}h1{font-size:clamp(3rem,7vw,6.6rem);line-height:.94;margin:.35em 0}a{color:white;background:#081a4b;padding:1rem 1.5rem;width:max-content;font-weight:800}section{padding:4rem 7vw;font-size:1.5rem}
""",
    },
}
```

- [ ] **Step 2: Run mission A from Cortex**

Approve its directory and two file writes separately. Then separately approve only the displayed port-49217 loopback server command. Require owned-process receipt before child release.

- [ ] **Step 3: Verify and stop A**

Require HTTP 200 on `127.0.0.1:49217`, exact title, visible hero/CTA/variant, no horizontal overflow at 1440x900, and one PNG. Stop through owned-process control; require exit 0, no listener, and no PID.

- [ ] **Step 4: Repeat independently for B and C**

Use distinct workspaces, action nonces, ports, receipts, inventories, and screenshots. Each `browser.png` capture is a distinct sensitive-read/file effect with its own action-time authorization, nonce, activation, and terminal receipt. Do not reuse approval scope, files, processes, captures, or evidence between variants.

- [ ] **Step 5: Record the aggregate T17 verdict**

`PASS` requires all three sites to pass every write/process/HTTP/DOM/visual/shutdown gate. One failed or incomplete variant makes T17 `FAIL` or `UNCLEAR`; two successful sites do not average it away.

---

### Task 12: Execute T18 durable STOP and controlled reset

**Files:**
- Must remain absent: `.../<run-id>/T18/pre-stop.txt`
- Must remain absent: `.../<run-id>/T18/race.txt`
- Create only after reset and new approval: `.../<run-id>/T18/post-reset.txt`

**Interfaces:**
- Contents are respectively `CB-QA-T18-PRE-STOP\n`, `CB-QA-T18-RACE\n`, and `CB-QA-T18-POST-RESET\n`.

- [ ] **Step 1: STOP with a pending approval**

Create but do not decide the `pre-stop.txt` approval, request STOP, settle it, then attempt the old approval. Require stale epoch/refusal, no activation, no tool dispatch, and independent absence.

- [ ] **Step 2: Run the deterministic accepted-to-dispatch race**

Pause at the test seam after approval acceptance and before activation, issue STOP, then release. Require the epoch gate to block dispatch and `race.txt` to remain absent.

- [ ] **Step 3: Restart while stopped**

Restart the service and prove durable `stopped`, no automatic reset, zero new effect, and both files absent.

- [ ] **Step 4: Reset explicitly and use a fresh action**

Bootstrap a bounded UI session from the exact configured frontend Origin using `POST /api/ui/session`, then call `POST /api/transport/stop-reset/prepare` with the dedicated UI-session header. Present the returned two-minute single-use 256-bit nonce plus displayed STOP state version and authorization epoch. The explicit reset request to `POST /api/transport/stop-reset` carries exactly `{resetAttemptId, expectedStateVersion, expectedAuthorizationEpoch, nonce}` with the same session header and exact Origin; only the server wrapper calls internal `EffectGate.reset_stop(expected_epoch=...)`. Prove stale origin/session/version/epoch/nonce attempts fail closed, the matching retry returns the durable canonical receipt, reset restores no consent/work, and a new authorization epoch appears. Then separately approve the new `post-reset.txt` write and prove only that file exists with exact bytes/hash and a terminal receipt.

---

### Task 13: Execute the local-alias owner acceptance

**Files:**
- Observe only after the explicit access check: the exact `desktop/cortex-live-test` leaf resolved server-side from `getuid()` plus `getpwuid_r()`
- Must be absent before write approval: `~/Desktop/cortex-live-test`
- Create only after the displayed one-shot approval: `~/Desktop/cortex-live-test`
- Record privately: `.gstack/qa-reports/v054-live/<run-id>/local-alias/`

**Interfaces:**
- Exact Cortex input: `cree moi un dossier cortex-live-test sur mon bureau`.
- Expected route facts: `source=rules`, `modelAttempted=false`, `modelUsed=null`, `executionClass=local_alias_action`, alias `desktop`, label `Bureau`, operation `create_directory`, leaf `cortex-live-test`, write approval true, and chat/writer/read/process/network/deletion false.
- Access-check effect: server-derived `owner_kind=direct_ui`, `category=sensitive_read`, operation `verify_local_alias_access`, strict 60-second worker deadline, and one 15-minute observation on success.
- Directory effect: server-derived `owner_kind=local_alias_action`, `category=filesystem`; it may invoke only the installed attested `executor/local_alias_worker.py` operation `create_directory`.

- [ ] **Step 1: Freeze storage and no-side-effect baselines without opening Desktop**

Require the installed production runtime to report the same healthy committed required-storage transaction, valid managed-start lease, authorization epoch, STOP state, and `runtime_truth_digest` at the status API and visible UI. Record canonical counts/last IDs for ChatGPT sends, writer leases, missions, outboxes, uploads, browser commands, extension commands, local grants/actions, approvals, and effects. Do not run `lstat`, list Desktop, open the alias, remove the required-storage marker, start a no-required-storage runtime, or use a test-only alias root.

- [ ] **Step 2: Explicitly verify access to Bureau**

In Cortex, click `Vérifier l’accès à Bureau`, review the exact alias and warning, and obtain separate action-time authorization for that `direct_ui/sensitive_read` effect. If macOS presents a privacy prompt, the owner decides it directly; Cortex does not click it. Require readiness at prepare, then the runner's exact three opaque readiness barriers: immediately before blocked spawn, through a single-use `BlockedWorkerActivationPermit` after durable PID/PGID/start ownership, and immediately before release. The fixed worker must exit within 60 monotonic seconds, with its owned identity closed and reaped. `PASS` requires one terminal access-check receipt and one fresh observation bound to the current catalog revision, alias identity and authorization epoch, plus zero ChatGPT, writer, mission, outbox, upload, browser or extension delta. Denial is `FAIL`; timeout, crash, EOF, malformed receipt or an unobserved/dismissed decision is `UNCLEAR` and creates no observation or automatic retry.

- [ ] **Step 3: Prove the exact target is absent without mutation**

Only after Step 2 succeeds and after separate authorization for this exact privacy-sensitive QA observation, use descriptor-safe `lstat` evidence for the exact server-resolved leaf. If any file, directory, symlink or dangling symlink exists, record `LOCAL_ALIAS=UNCLEAR` and stop; do not delete, rename, reuse it, or choose a substitute name. Freeze an allowlisted immediate-child inventory digest so the later check can prove no unrelated Desktop entry changed without committing names or absolute paths.

- [ ] **Step 4: Enter the exact request only in Cortex**

Press Enter in Cortex; do not type in ChatGPT and do not use the manual `Exécuter…` fallback. Require deterministic rules, zero Ollama call, no ChatGPT send/refusal, the original draft retained, and the visible French preflight: `Action locale`, `Créer le dossier « cortex-live-test » dans Bureau.`, `Accès : créer uniquement ce dossier`, `ChatGPT : aucun message envoyé`, and `Lecture, suppression, processus et réseau : désactivés`. The UI must not name ChatGPT, a model or the generic executor as the actor.

- [ ] **Step 5: Finalize the local action without approving the write**

Finalize with `action=start_local_alias_action` using the same runtime-bound UI session and server-minted route/conversation/catalog values. Require exactly one `local_alias_grants` row and one `local_alias_actions` row in `awaiting_approval`, no protected-alias open or worker release during finalization, and a byte-identical idempotent retry returning the canonical action. Require zero activated filesystem effect and no creation claim; do not reopen Desktop merely to restate the Step-3 observation. The frozen ChatGPT-send, writer, mission, outbox, upload, browser-command and extension-command baselines must remain unchanged.

- [ ] **Step 6: Present and approve only the exact directory action**

Await a distinct action-time authorization bound to the action/grant IDs, catalog ID/revision, alias, operation, normalized leaf, payload digest, single-use nonce, STOP epoch and authorization epoch. After approval, require exactly the runner's three opaque readiness barriers: `spawn_blocked()` checks before attestation/spawn, `assert_pre_activation_ready()` returns the single-use permit required by local activation after durable PID/PGID/start ownership, and `run()` checks again immediately before release. Any failed barrier closes/reaps the exact worker and yields zero alias walk or mutation; a failure after activation but before release terminalizes the effect as `failed` and the action as `failed_safe`. Only the third successful barrier may release one blocked and attested worker. If macOS asks again because access was revoked, the owner decides the system prompt directly and the worker still dies within 60 seconds. Require one `mkdirat` of mode `0700`, full root-to-home-to-alias descriptor-chain validation before and after it, one new inode, parent fsync, a terminal `created` receipt, and no automatic retry. Any chain change after `mkdirat` is `LOCAL_ALIAS_CHANGED` plus `outcome_unclear`, never success. A timeout, crash, EOF, cancellation, or missing sufficient terminal receipt after worker release is `LOCAL_ACTION_OUTCOME_UNCLEAR`; it is never replayed, and STOP reset remains disabled until explicit reconciliation.

- [ ] **Step 7: Prove authority separation and preserve the result**

After separate authorization for this exact post-action privacy-sensitive QA observation, recompute the allowlisted Desktop inventory digest and require exactly the approved leaf/inode delta. Compare all frozen ledgers: `PASS` requires one access-check effect, one local filesystem effect, one grant/action, and zero ChatGPT send, writer, mission, outbox, upload, browser-command or extension-command delta. Confirm the writer-slot count is unchanged; the automated checkpoint-I test separately proves that two already-active ChatGPT writers neither block nor are consumed by a local action. Record `LOCAL_ALIAS=PASS` only with those direct receipts. Do not remove the folder automatically; cleanup, if desired, is a separate deletion decision after acceptance and is not part of v0.5.4 PASS.

---

### Task 14: Execute R1-R5 live regression retests

**Files:**
- Create privately: `.gstack/qa-reports/v054-live/<run-id>/regressions/`

**Interfaces:**
- R2 real switches use monotonic timestamps and a 10,000 ms deadline.
- R2 fault fixture is reachable only with the explicit development-fixture environment and absent required-storage marker.
- R3 neutral message: `Réponds uniquement : CB-QA-R3`.

- [ ] **Step 1: R1 runtime/workspace truth**

Capture the same backend `runtime_truth_digest` reflected in status rail, Settings, and Onboarding. In a separate disposable local `CORTEX_HOME` with an absent synthetic workspace, require all three to show unavailable; never alter production settings.

- [ ] **Step 2: R2 conversation switching**

With explicit real-Chrome authorization, switch A→B and B→A. Record click, immediate cache paint, refresh start, and settled timestamps; each must settle within 10 seconds with no superseded overwrite. Separately run a fresh build and `npm --prefix frontend run test:e2e -- --grep @conversation-switch-fault`; require one selected test and the cache→timeout→retry trace.

- [ ] **Step 3: R3 tab provenance**

With separate approval for snapshot, neutral send, and extension restart, prove one canonical writer remains, only a Cortex-created redundant reader retires, a user-created tab remains open, and lost provenance after restart cannot close/reuse a tab or replay delivery.

- [ ] **Step 4: R4 sidebar/categories**

Prove pinned, project, and recent sections plus new-conversation control are usable, message counts are visible where specified, no more than 50 conversations load, and no dead archives action is rendered.

- [ ] **Step 5: R5 diagnostic export**

From a fresh UI build, click once, observe exactly one browser download event, verify the downloaded file exists, confirm the inline state is exactly `Téléchargement demandé : <filename>`, and privacy-scan its bytes. Alert-only, silent, duplicate, or invented success state is `FAIL`.

---

### Task 15: Freeze, review, and prepare v0.5.4 evidence

**Files:**
- Modify after every live gate passes: `docs/verification/v0.5.4.json`
- Modify after every live gate passes: `docs/testing.md`
- Modify after every live gate passes: `docs/release-checklist.md`
- Modify after every live gate passes: `ROADMAP.md`
- Modify: `primer.md`
- Never add: `.gstack/qa-reports/v054-live/`

**Interfaces:**
- Consumes: immutable private manifest plus terminal verdicts for INSTALL, STORAGE, RUNTIME, LOCAL_ALIAS, T12-T18, and R1-R5.
- Produces: public aggregate evidence with no private paths/data and no release/publication claim.

- [ ] **Step 1: Build and verify the private manifest**

```bash
"$PYTHON" scripts/build-qa-evidence-manifest.py --root "$QA_EVIDENCE_ROOT" --output "$QA_EVIDENCE_ROOT/manifest.json"
scripts/check-public-privacy.sh --root "$QA_EVIDENCE_ROOT" --markers tests/fixtures/privacy/ci-markers.txt --fingerprints scripts/privacy-fingerprints.json --url-allowlist scripts/public-url-allowlist.txt
"$PYTHON" scripts/build-qa-evidence-manifest.py --verify "$QA_EVIDENCE_ROOT/manifest.json" --root "$QA_EVIDENCE_ROOT"
shasum -a 256 "$QA_EVIDENCE_ROOT/manifest.json"
```

Expected: zero privacy findings and stable bytes after verification.

- [ ] **Step 2: Obtain independent frozen-byte reviews**

Give the manifest hash and named artifacts to independent evidence, privacy, and implementation reviewers. `PASS` requires all three to report zero P0/P1/P2 on those exact bytes.

- [ ] **Step 3: Update public evidence only when supported**

Record aggregate counts, synthetic labels, verdicts, limitations, exact candidate commit, and manifest hash. Do not commit raw captures, account/chat identifiers, absolute paths, Keychain metadata values, secrets, or a claim of independent recovery.

- [ ] **Step 4: Run final gates from the repository root**

```bash
test -d frontend/node_modules
"$PYTHON311" -m unittest discover -s tests -p 'test_*.py' -v
"$PYTHON314" -m unittest discover -s tests -p 'test_*.py' -v
PYTHON="$PYTHON311" scripts/test-all.sh
gitleaks detect --source . --no-banner --redact --log-opts="--all"
gitleaks detect --source . --no-banner --redact --no-git
scripts/verify-links.sh
scripts/check-public-privacy.sh --markers tests/fixtures/privacy/ci-markers.txt --fingerprints scripts/privacy-fingerprints.json --url-allowlist scripts/public-url-allowlist.txt
"$PYTHON" scripts/verify-release-evidence.py
git diff --check
git status --short
```

Expected: complete green gate, no private evidence tracked, and only intended release-document changes.

- [ ] **Step 5: Commit evidence atomically**

Commit supported documentation/evidence as `test(release): record v0.5.4 live acceptance`. If any mandatory gate is `FAIL` or `UNCLEAR`, preserve that truthful verdict, keep release blockers open, and do not use this commit subject.

- [ ] **Step 6: Stop safely and report the publication boundary**

Stop Cortex through durable STOP, close owned processes, detach normally, and prove no listener/PID/mapping. Report the candidate commit and Git status. Push, merge, tag, GitHub release, duplicate cleanup, and independent recovery remain separate owner decisions.
