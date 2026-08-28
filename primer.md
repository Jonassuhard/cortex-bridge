# Cortex Bridge session primer

Current state: 2026-08-28.

## Current project

- Worktree: `.worktrees/codex-v054-storage-consolidation`.
- Branch: `codex/v054-storage-consolidation`; base commit: `b0c74bb`.
- Target version: 0.5.4, currently marked unreleased.
- The working tree contains the uncommitted storage-consolidation candidate.
- No v0.5.4 tag, clean release commit, checklist, or evidence manifest exists.

## Product invariants

- Product transport is the unpacked local extension in the user's real
  signed-in Chrome profile. No API or separate Playwright profile substitutes
  for that flow.
- Cortex writes only to classic ChatGPT chats. Work/business surfaces fail
  closed with `WORK_SURFACE_REJECTED`.
- At most two distinct conversations may write concurrently. A third retains
  its draft and staged file and is refused before browser action.
- Approval is the default policy. Automatic writes require an explicit
  trusted-workspace setting; process commands keep their policy checks.
- Ambiguous browser delivery is never replayed automatically.

## Completed in the candidate

- Optional encrypted APFS storage is bound to an exact volume UUID, mount,
  writable state, storage root, and encrypted sparse-bundle backing path.
- Runtime startup fails closed if the configured external storage proof fails.
- Relative deterministic manifests inventory canonical storage without
  following external symlinks or exposing absolute paths.
- Mutable private runtime state stays under local owner-only `CORTEX_HOME`;
  large workspaces, evidence, archives, and rebuildable caches can live on the
  verified external volume.
- Installer, migration, log rotation, process ownership, and uninstall use
  private locks plus descriptor, device, inode, and hash checks where macOS
  exposes them. Malicious same-UID mutation remains outside the threat model.
- Backend suites pass 822/822 under equipped Python 3.11 and 822/822 under
  equipped Python 3.14. Extension passes 130/130. Frontend passes 155/155 unit
  tests, 36/36 runtime/privacy contracts, 12 E2E tests with one intentional
  guide skip, and 4/4 accessibility viewports.
- A real isolated install, Doctor, start/status/API, two restarts, idempotent
  reinstall, and uninstall completed without `sudo`; the foreign sentinel kept
  the same inode and hash and no listener remained.
- Python compilation, Bash syntax, ShellCheck, runtime verification, privacy
  scanning over 343 files and 43 images, Gitleaks history scanning over 241
  commits, link/version tests, and diff checks pass on the final candidate.
- Independent clean-room review reproduced and closed lifecycle-lock poisoning,
  unverified process cleanup, late-fsync log loss, symlinked manifest roots,
  and public-parent lock replacement. Its final P0-P2 verdict is PASS.

## Open blockers

- The external volume reports `Owners: Disabled`. Changing that setting is an
  administrator decision and is not automated.
- Chrome currently loads the unpacked extension from the old Desktop source;
  that source cannot be removed until Chrome is manually reloaded from the
  canonical extension path.
- The provider-terms conflict and owner-only live/release approvals are
  unchanged. No v0.5.4 release evidence may be claimed yet.

## Next exact action

Create the local branch commit, build canonical external and minimal local app
copies from that exact commit, then switch and verify the live service without
deleting any prior source.
