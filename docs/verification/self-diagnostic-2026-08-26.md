# Self-diagnostic mission — 2026-08-26

Release-close evidence for Cortex Bridge v0.5.3. The runtime was exercised in a
detached disposable worktree at source commit `1506f2f`; the final source commit
adds documentation and evidence only. The worktree was removed without merge.

Only aggregate technical results appear here. Temporary paths, process IDs,
account data and browser content are intentionally omitted.

## Environment

- macOS 26.5.1, build 25F80, Apple silicon.
- Python 3.12.1 and exact hashed `requirements.lock`.
- Isolated `HOME`, `CORTEX_HOME` and loopback port.
- Cortex Bridge 0.5.3, deterministic executor.

## Successful sequence

| Step | Result |
|---|---|
| Immutable install dry run | Plan hash `80142d49822bbe18f81e74d2be1a9e378703d3c7d95eddcaa80885fcca74c7f2` |
| Exact plan approval | Installed v0.5.3 without `sudo` |
| Replay consumed install hash | Refused with non-zero status |
| Doctor | `ok: true`; every required check passed |
| Start and status | Loopback server became ready and ownership state was `owned` |
| `GET /api/status` | HTTP 200; version `0.5.3` |
| `GET /api/tasks` | HTTP 200; JSON list |
| Stop | Owned process stopped normally |
| Idempotent reinstall | `already_installed`; plan hash `02f24e928bd11f2b7d1b15cb3b31680168232d51901560a7df0f12583de3502d` |
| Exact uninstall approval | `uninstalled`; plan hash `4058502862f03ace22ff1925f069ee9d1006e43114792b9342f353a37328ae6b` |
| Final checks | No loopback listener remained; detached worktree removed |

## Failed evidence-wrapper attempts

Two preliminary wrappers are deliberately not hidden:

1. The complete lifecycle ran, but the final reporting block attempted to parse
   an empty summary value as JSON and exited non-zero.
2. A fresh install completed, but the same collector defect stopped the wrapper
   before the remaining runtime checks.

The second isolated environment was then resumed with one assertion per stage;
the successful sequence above exited zero. These were proof-collection defects,
not accepted product passes, so only the final asserted sequence is counted.

## Verdict

Disposable v0.5.3 self-diagnostic: **PASS**. This proves the local lifecycle on
the current Mac with isolated state. It does not claim a genuinely fresh macOS
account or VM, which remains an open release-checklist item.
