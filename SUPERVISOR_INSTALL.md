# Native Codex supervisor installation — 0.6.5 candidate

This installs instructions and bundled standard-library Python journal and
selected-file archive preparation helpers. Python must already be available.
It does not install the Cortex server, Chrome extension, third-party Python
packages, models, account credentials or OS permissions.
The complete 0.6.5 release is not yet validated.

## Agent workflow

Host requirement: a native conversation reader/sender must actually be exposed
to the coordinating agent. Installing this skill does not add those tools to
an independent CLI process. Bundled Python helpers are callable through that
process's shell, but they only journal/package; they do not contact ChatGPT.
If a worker lacks conversation tools, the capable desktop coordinator must
retain the ChatGPT link and pass it bounded jobs/results. That complete external
worker relay remains an open validation gate, not an automatic installer feature.

1. Verify the selected checkout and read cortex-supervisor/SKILL.md plus
   HARNESS_V065.md. Confirm the user's intended workspace and ChatGPT target.
2. Discover the actual local skill directory from the host configuration. Do
   not assume a personal path from this repository. Select a new
   `cortex-supervisor` child of an existing authorized directory.
3. Run `python3 scripts/install-supervisor.py --target TARGET` from the checkout.
   This returns the complete source hashes, target, scope and plan hash without
   writing to TARGET. Use an explicit physical path; links are refused.
4. Show the target and instructions/journal/archive-preparation scope. After the user's approval of
   that plan, the agent runs the same command with `--approve-plan PLAN_HASH`.
   A clear affirmative approval of the displayed plan suffices; the agent
   supplies the hash. A changed plan requires review again.
5. Check exit status and JSON state, then compare installed files to the plan.
   Installation does not prove host conversation/attachment capabilities.
6. Reload skill discovery through the host's supported mechanism. Verify that
   the skill is visible; if not, report discovery as unverified.
7. Read the installed skill, perform its capability preflight, and run a
   uniquely marked text round-trip in the user-approved ChatGPT conversation.
   Test real file/image delivery separately if requested and supported.

The user need not type terminal commands. A capable, authorized agent runs them.
After installation, the local journal entrypoint is
`python3 <installed-skill>/scripts/supervisor-journal.py --db <authorized-db>`.
It runs independently of the original checkout; JSON stdin operations are
documented in the bundled reference. It never sends a message by itself.
Selected-file packaging uses
`python3 <installed-skill>/scripts/supervisor-artifacts.py --workspace PROJECT --file README.md --output NEW.zip --goal "Objective"`.
This returns hashes and a context packet; it does not upload the archive.
The installation has no background service or startup modification. Existing
targets are refused, including partial installations. Do not delete or overwrite
them to force success. The installer creates .cortex-install.json with the
reviewed file hashes. This is an integrity/ownership record, not a signature.

## Update and uninstall by archival

Stop active users of the skill and ensure a single writer before applying.
Discover the actual host skill root. TARGET must be a direct child of it.
Choose a NEW archive path outside all host discovery roots, on the same disk.
The lifecycle tool validates exclusion from the explicitly supplied root;
the operator must check any additional roots configured by the host.

```sh
python3 TARGET/scripts/supervisor-lifecycle.py --skills-root SKILLS --target TARGET --archive NEW_ARCHIVE
```

Review the full plan and its hash with the user. With approval, repeat the
command adding --approve-plan PLAN_HASH. The skill directory is moved intact
to NEW_ARCHIVE, not deleted. Reload host discovery and verify it disappeared.
Existing files in the archive destination are never intentionally overwritten.
Changed, unowned or symlink files cause refusal before any move.

For an update, first install the new version into a fresh staging directory
outside discovery, using the normal approved installation plan. Pass that
complete path as --replacement STAGING to the lifecycle command. Review and
approve this separate update plan. The old target is archived first, then the
verified replacement is activated at TARGET. Reload discovery and run preflight.

The two moves are not an atomic swap. A failure after archival can leave TARGET
absent while old and new copies remain elsewhere. The error reports the phase:
inspect those paths and prepare recovery; do not erase files or blindly retry.
When TARGET is absent and both archive and replacement remain intact, rerun
the lifecycle command with --recover-activation and the same explicit paths.
This emits a NEW recovery plan. Review it, then apply with its new hash.
Recovery verifies both copies again and activates only the replacement; it
does not move or delete the archive. A re-created target or modified candidate
causes refusal. It does not infer that a previously activated target is valid:
inspect that state separately instead of invoking recovery over it.
The tool is cooperative, not protection against an adversarial concurrent writer.
Older installations without a receipt are refused: no inferred ownership or
automatic migration. Review them separately and install a new verified copy.

## Current evidence and limits

A real read-only model preflight on Codex CLI0.144.1, requested Luna, loaded the
installed instructions and correctly reported missing conversation tools. This
invocation used --ignore-user-config; it does not characterize all configured
CLIs. The synthetic project remained unchanged. This validates truthful missing-
capability reporting, not full autonomous use. Private evidence is indexed in
.qa-live-v061/INSTALLED_OPERATOR_PROBE.md; no provider identity claim.

Disposable subprocess tests verify plan/apply bytes, hash refusal, existing
target preservation and ancestor-link refusal. Real Codex CLI prompt discovery
passes with an isolated CODEX_HOME: the installed description and its skill
path (resolved through Codex's root-alias map) appear in the model-visible input.
This does not prove a model has followed the instructions or that desktop live
tools are available in that CLI. Global installation, legacy migration
and another user's installation remain unverified.
Nine targeted tests cover archival uninstall, replacement activation, subsequent
uninstall, changed/unowned files, wrong approval and occupied archive refusal.
Actual isolated Codex CLI discovery sees the installed skill before archival
and no longer sees it afterward; the archive remains intact. This does not
validate an already-running desktop session's reload behavior or crash recovery.
Update: twelve targeted tests now cover injected activation failure, abrupt
process exit after archival, explicit recovery, and refusal when a target or
candidate changed. Power-loss durability and adversarial races remain unproven.
An isolated-Python subprocess outside the repository verifies that the installed
journal can initialize and inspect a new mission using only bundled modules.
The same isolated subprocess test prepares an actual ZIP and checks its file
bytes, manifest hashes and non-delivered state outside the source checkout.
It also reserves a native action, runs a separate Python process that creates
a synthetic file, confirms its actual exit and file hash, and verifies replay
is refused both before and after the receipt. This is a subprocess integration
test, not a ChatGPT-directed mission or proof of arbitrary host tool support.
The installer is not a filesystem sandbox or a concurrent hostile-writer defense.
No message is sent merely by installing these instructions.
