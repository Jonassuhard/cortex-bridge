# 0.6 development checkpoint — 2026-09-10

## Release decision: FAIL

This is an incomplete development checkpoint, not a 0.6 release or a verified
upgrade recommendation. VERSION remains 0.5.4. No new test suite was run during
publication preparation, at the owner's request. Results below are recorded
runs, not a fresh full-candidate acceptance run.

## Evidence matrix

| Area | Verdict | Evidence and limits |
|---|---|---|
| Storage proof consumption | PASS | 48 targeted tests, 67.601 s; [report](../superpowers/plans/2026-09-10-image-binding-proof.md). Positive image proofs are synthetic. |
| Workspace UUID admission/revalidation | PASS | 118 tests, 44.595 s; then 66 tests, 0.283 s including read denial; [report](../superpowers/plans/2026-09-10-workspace-volume-identity.md). Not a live ChatGPT mission. |
| Installed native mount reader | PASS | Real native probe plus targeted factory/negative tests; [report](../superpowers/plans/2026-09-10-native-probe-invocation.md). Not clean-machine installation. |
| Native private image proof | FAIL | Production method still reports BROKER_UNAVAILABLE without an injected transport. |
| Persistent native effects and terminal protocol | FAIL | Valid START still rejected with INVALID_STATE; effect dispatch, durable terminal ACK and recovery remain incomplete. |
| Full encrypted installation/update/uninstall | UNCLEAR | Complete live acceptance has not been performed on this candidate. |
| Profiles, continuity and executor adapters | UNCLEAR | Components and experiments exist; production dispatch and real cross-harness resume are incomplete. |
| Chrome, attachments and simple/complex missions | UNCLEAR | No full current-candidate live acceptance. Fixture successes must not be substituted. |
| Windows | UNCLEAR | Live verification explicitly deferred by the owner. |
| Visual guide and animated diagram | UNCLEAR | Historical assets are not evidence of the current candidate; no fresh visual acceptance. |

PASS applies only to the stated component and run, never to the application as
a whole. The [full scope](../superpowers/specs/2026-09-09-v06-product.md) remains
open; the [implementation plan](../superpowers/plans/2026-09-09-v06-completion.md)
retains outstanding acceptance work.

## Publication scope

Publish source, tests and English technical documentation only as a development
checkpoint. Do not create a 0.6 tag/release or merge into main as ready. Local
session notes in primer.md are excluded from the new commit; that does not
remove existing repository history. No new personal screenshots or provider
session exports are included. Existing bundled frontend output is retained as
checkpoint data, not claimed as a freshly rebuilt distribution.

## Next work

Implement the native private image probe and effect/terminal/recovery path;
complete retained host identity and race handling; finish supported adapters
and the approved live acceptance matrix. Resume testing only when requested.
