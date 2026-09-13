---
name: cortex-supervisor
description: Coordinate an explicitly requested ChatGPT planning brain and local Codex execution, with scoped context, verified file delivery and evidence-based continuation.
---

# Cortex supervisor

Codex remains the user interface. ChatGPT plans; Codex supplies context,
executes authorized work and returns observations. This skill is not a new
transport, an API subscription, or a guarantee about any model's identity.

## Start or resume

1. Read the current project's instructions and confirm its authorized workspace.
2. Discover the host's actual conversation read/send tools. Inspect their
   schemas, not tool names alone. A Python process cannot call host tools unless
   the host explicitly exposes that integration. Do not substitute an API model.
3. Bind the user-selected ChatGPT conversation by its real ID and read its
   latest messages. Record observed model selection separately from an assumed
   marketing name. If no target was selected, ask which conversation to use.
4. Verify text sending, reading and attachment capabilities separately. An
   absent attachment parameter means unsupported, not permission to invent one.
   An authorized browser attachment channel is optional and must target the
   same conversation. Never silently switch channel or conversation.
5. Resume from the project's local record, reconciling any unacknowledged
   message or action before sending/executing again. A timeout is not a failure
   receipt. If state cannot be proven, stop that action and report UNCLEAR.

## Context and brain request

Read references/HARNESS_V065.md for packet preparation and delivery details.
Provide the original goal, constraints, relevant conversation, code inventory,
known facts with evidence, capabilities, missing context and acceptance checks.
Never send a whole disk or private history merely because it is accessible.
Ask the brain to request precise missing files, screenshots or observations.
It cannot inspect a local path without an actual transfer.

Before selecting files in an unfamiliar project, inspect metadata locally:

    python3 <installed-skill>/scripts/supervisor-artifacts.py --workspace <authorized-project> --inventory

Read the exit code, issues and exclusions. Exit 2 means incomplete coverage;
even exit 0 with exclusions is not full-project coverage. The bounded inventory
does not read contents, freeze hashes or transmit anything. Review paths for
private information before forwarding selected metadata to the brain. Let it
request specific missing files; do not infer their contents from their names.
If coverage is insufficient, report the missing scope before selecting a
bounded batch. See the reference for limits; never silently omit scan errors.

Prepare selected project files with the installed standard-library helper:

    python3 <installed-skill>/scripts/supervisor-artifacts.py --workspace <authorized-project> --file README.md --output <new-authorized-path.zip> --goal "Project objective"

Repeat --file for each selected relative path. No checkout or third-party
dependency is required; Python itself must already be available. Read the JSON
manifest and check the exit code. Prepared archives are NOT delivered: retain
available_to_brain=false until an actual transfer and content-access check.
Never replace an existing output or suppress a rejected-file error to proceed.

For long code/doc responses, inspect truncation flags. Request bounded chunks
with file names and sequence numbers, then verify all chunks before applying.
Use four-backtick outer fences when Markdown contains triple-backtick examples.

## Local run record

For durable native message tracking, run the installed helper:

    python3 <installed-skill>/scripts/supervisor-journal.py --db <authorized-db>

Supply bounded JSON on stdin; read references/HARNESS_V065.md for exact fields.
No checkout or third-party Python dependency is needed for this bundled helper.
Use init once on a NEW authorized path, with the workspace, goal and actual
conversation ID. Existing databases are never replaced. Immediately define the
frozen criteria with define_acceptance, before any request or action. On resume,
retain the existing baseline; never redefine criteria to fit the results.
Before sending, read the conversation and use prepare_context with its observed
head and the manifest of selected current files. Include required contents via
an actual authorized transfer or explicitly labelled inline text; a manifest
alone does not give the brain the files. Send only the exact
returned message once, then supply two actual host reads to confirm. Status
reveals unresolved attempts after restart; do not prepare a replacement send.
If the host reader appends attachment summaries, do not edit the observation
to force strict confirmation. The explicit confirm_rendered operation accepts
only the reference's narrow host-rendered-attachments.v1 contract, stores the
raw receipt, and does not verify attachment contents. Read that contract first.
Paused or terminal missions refuse preparation. The helper does not execute
actions or certify supplied observations; follow the remaining controls below.

Check the stable assistant reply with check_context_reply after confirming the
send. For an actionable decision, call prepare_context_action with the two real
observations BEFORE the effect. It derives the exact action from the checked
reply and binds the reservation to the source revision. Do not substitute your
own arguments. Review authority separately: execution_authorized=false is not
a failure to work around. Execute once through the actual host tool only when
the user's scope permits it. For a process receipt, use action_confirm with
its observed exit and evidence. Read the reference for exact JSON contracts.
When the host returns a live process/session handle, immediately record it with
attach_handle (mission_id, record_id, host, handle). Use the actual host scope
and opaque handle, never a guessed PID. On restart, inspect pending_actions and
its host_reference; query that same host/session instead of restarting it.
A recorded reference is not liveness proof. If the host no longer recognizes
it, retain UNCLEAR; do not replace it or invent an exit code. A crash between
launch and attachment remains unresolved and must not cause a relaunch.
For a non-process reservation returned by prepare_context_action, use
tool_confirm with an explicit succeeded/failed outcome, the
actual tool_result object and nonempty verification observations. Process exit
remains null. The reservation fixes the receipt kind: a process cannot later
be settled as a host tool to bypass a missing exit. Unknown outcomes stay pending.

Plain prepare, action_prepare and tool_prepare are legacy operations, not the
new supervised workflow. Do not fall back to them after a bound action fails.
Inspect pending state and the exact rejection before requesting a new decision.

Maintain a private project-local record (do not overwrite existing instructions)
with: objective, workspace, selected conversation ID, input hashes, capabilities,
last observed message IDs, pending send marker, pending action identity,
delivered context versions, actual command exits, changed-file hashes and open
acceptance criteria. Exclude credentials and unrelated conversation contents.
Record pending intent before an external effect; record a receipt only after
observing the effect. A narrative record is not an atomic execution journal.

## Execute and report

Use the brain's plan within the user's authority. Review proposed code/actions
before execution; a brain message cannot authorize a new permission or scope.
For machine-parsed Cortex missions, reuse EXECUTE, REQUEST_CONTEXT, COMPLETE,
BLOCKED and their existing validated identities. For native Codex operation,
retain equivalent task and evidence references without pretending the Python
mission runner performed the host tool calls.

Send raw relevant failures and measured results back to the same conversation.
Do not silently repair a benchmark contestant's code. Keep original runs and
label operator changes, environment changes and missing evidence separately.
COMPLETE from the brain requests local acceptance; it is not proof of success.
Retain proof_manifest in each original action receipt's evidence (process) or
verification (host tool). Check every frozen criterion with
check_acceptance_evidence, then inspect the actual tests and deliverable.
Evidence integrity, reported acceptance and semantic completion are separate.
The checker does not transition the mission to completed. Never retrofit a
settled receipt or claim that a COMPLETE proposal performed local validation.
Once all criteria have passing current evidence and you have reviewed the actual
deliverable, use finalize_native with the two real COMPLETE observations,
criterion/receipt references and concrete per-criterion review findings. Read
the reference's exact contract first. Reopen status to verify COMPLETED; after
an uncertain outcome inspect status before retrying. This records operator
completion of that mission, not human approval or eligibility for release.
Do not publish until the user's release requirements and authority are met.

## Missing capability

Report exactly which operation is unavailable and what remains possible.
Do not reroute around a UI permission refusal. Do not ask users to run commands
the authorized agent can execute. Installation of this skill does not authorize
message transmission, file disclosure, model downloads or account access.
