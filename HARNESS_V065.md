# Cortex supervisor operator guide — 0.6.5 candidate

Implementation status: partial. Artifact preparation is implemented; the
complete delivery/recovery loop and release acceptance are not validated.

## Bootstrap in Codex

Read primer.md, PLAN_V065.md and V065_TESTS_BENCHMARK.md. Confirm the current
project, user objective and authorization. Discover the actual host tools;
do not invent attachment parameters or assume tools available on another host.
Bind the selected ChatGPT conversation. Record the current last message ID
and an operator-generated unique turn marker before any transmission.

Give the brain the original request, success criteria, constraints, inventory,
selected context, previous verified report and missing information. Explain:
"You design the steps. I provide observations and execute authorized actions.
You cannot inspect local files that I have not transmitted. Ask for precise
missing context. Completion is checked against actual local results."

## Prepare files without asking the user to run a terminal

The agent may invoke the installed Python environment itself:

```sh
python -m orchestration.artifacts --workspace PROJECT --file README.md --file src/example.py --output NEW_BUNDLE.zip --goal "The user objective"
```

Replace placeholders with the authorized project and new output path. The
command exclusively creates the output: existing files are never overwritten.
Its JSON manifest contains item hashes, sizes, types and prepared status.
Check exit code. Preparation is not delivery or approval. Secret detection is
heuristic; inspect the selected scope before any external transmission.

With `--goal`, JSON also contains `context_packet` in the existing
`desktop-supervisor.v1` format. Sizes and hashes are derived from the same
frozen bytes packed into the archive. Send this packet with the supervisor
bootstrap; it lists files as proposals, not delivered content. The goal is
bounded and redacted by the existing context validator before publication.
An invalid goal creates no final archive. This command is run by the agent;
it is not an additional terminal setup step for the user.

## Delivery contract

Before relying on a prepared selection as current, retain its exact JSON
manifest in an authorized workspace file and run the read-only check:

```sh
python -m orchestration.artifacts --workspace PROJECT --verify-manifest manifest.json
```

The installed supervisor-artifacts.py supports the same flags with Python -I.
Use your retained manifest, not one rewritten by the brain. Changed bytes,
missing files, symlinks, invalid entries or rejected content fail closed.
Successful sources_match is a point-in-time match of selected sources only:
it does not authenticate supplied metadata, verify the archive, prove delivery,
include unselected files, or prevent later edits. After a relevant change,
prepare a new revision and explicitly send the delta; never relabel the old
brain context as updated. Context/decision binding is still a separate gate.

1. Verify exact conversation URL/ID and most recent confirmed marker. Two
   surfaces showing the same URL may still show different message branches.
2. Verify composer is empty and the expected conversation is idle. If another
   surface sent a message, refresh/reconcile before adding any attachment.
3. Upload only approved frozen artifacts using the available supported channel.
4. Confirm the expected attachment appears before sending the question.
5. Send exactly once. If the tool times out, reconcile message history first.
6. Record actual message reference and reception result. File-specific questions
   establish content access; the filename alone does not.
7. Only then set available_to_brain=true for the corresponding version.

Keep an operator checkpoint with conversation ID, observed last user/assistant
IDs when exposed, a last-turn marker, outbound content hash and delivery state.
Before switching channels, compare the latest observed turn on both surfaces.
If one is stale, empty or generating, do not send. Reload only an empty
composer and reconcile; do not interpret loading time as lost history.
After uncertain delivery, search for the actual sent message in the bound
history. No match is not proof of non-delivery: retain `uncertain` and never
retry automatically. A tool acknowledgement is not the matching message.
These are operator rules, not an implemented portable persistence adapter.
The available host tools do not offer atomic expected-parent enforcement;
single-writer discipline reduces races but does not provide a server-side CAS.

Never follow a UI security refusal through another automation mechanism.
Chrome attachments are explicitly authorized for this project; Codex UI control
remains denied. Neither implies permission to access unrelated tabs or files.
When another operator controls native Chrome, use an isolated supported tab
control or wait; do not issue coordinate clicks against a changing foreground.

## Decisions and execution

Use the existing validated protocol with EXECUTE, REQUEST_CONTEXT, COMPLETE,
BLOCKED. Start with one action per turn. Require mission, iteration and action
identity and the context version used. Reject obsolete or malformed decisions.
For context requests, send only in-scope information; report inaccessible items.
For execution, provide the worker prerequisites, owned files, exact outcome and
acceptance tests. Do not infer success from a generated plan or exit prose.

Reports contain actual changed files/diff, command and exit code, test outputs,
screenshots where relevant, failures and unresolved questions. Send reports
to the same current branch of the bound conversation. If the brain lacks a
necessary artifact, do not compensate by asserting its contents were received.

## Recovery and completion

Checkpoint the last confirmed message, pending action and actual execution
result. An action with unknown execution state is reconciled before replay.
The mission runner now reserves an outbound payload in SQLite before sending.
An unresolved reservation blocks further sending for that mission, including
a different payload. A transport error explicitly classified before delivery
records MESSAGE_SEND_ABORTED and permits a new attempt without deleting history.
The web mission adapter stores a head checkpoint and adds a UUID marker to
technical mission messages. On resume it requires exactly one matching receipt
after the saved anchor, with a stable real message ID across two observations.
It refuses missing/truncated history or ambiguous receipts without resending.
The pre-send head check is local, not an atomic server-side guarantee.
Do not manually erase a reservation to unblock an uncertain delivery. The
portable desktop-tool reconciliation adapter is still incomplete; this runner
guard alone is not the complete host-operated supervision loop.
Stop when user requests it, hard budget expires or a material choice exceeds
existing authority. Ordinary fixes remain the operator's responsibility.
COMPLETE is a request for final verification. Run acceptance, inspect the diff
and record unresolved gates. Update the Markdown status after each stage.

## Native journal helper (candidate)

### Explicit rendered attachment observations

The default confirm remains exact. An observed host rendering may instead use
operation="confirm_rendered" with mission_id, first, second and
attachment_counts (for example {"file":1,"image":1}). Do not preprocess text.
This opt-in contract accepts only one or two newlines immediately before the
transport marker, followed by the exact English host summaries, file then image:
`[User attached 1 file; file contents were not included]` and
`[User attached 1 image; image contents were not included]`, each preceded by
two newlines. Counts are positive integers up to 100, with plural nouns for
counts above one. Unknown summaries and any change to the interior message
bytes are rejected; the original body hash, anchor, ID and two-read checks remain.
It records raw_receipt and observation_contract=host-rendered-attachments.v1.
Expected counts are operator declarations, not file-identity evidence;
attachment_contents_verified is false. Independently verify actual content
access in the brain response. Never treat appended summaries as proof alone.
The old failed attempt remains historical evidence when a newer explicit
contract reconciles the same actual message; never resend to repair a receipt.

When the full Cortex checkout/runtime is available, the agent can run:

    python -m orchestration.native_journal --db AUTHORIZED_DATABASE

Provide one JSON object on stdin, not prompt text in shell arguments.
For a new explicitly authorized database path, operation="init" accepts
mission_id, objective, workspace and conversation_id. It creates a new bound
mission, never replaces an existing database, and reports executor_verified=false
and release_eligible=false. A partial initialization is retained on error.
Subsequent operations require the existing database. Preparation refuses paused
and terminal missions; confirmation may still record a late actual receipt.
New native message/action reservations also check persisted started_at plus
max_duration_seconds. Expired, invalid or future-start wall-clock records fail
closed; reopening the database does not reset the deadline. Receipts remain
recordable after expiry. This is a pre-reservation guard, not a watchdog that
kills a running external process or prevents an operator acting outside the
journal. Iteration/action-count enforcement remains a separate requirement.
Preparation fields: operation="prepare", mission_id, conversation_id,
before_message_id and message. The result contains the exact technical message
including its send marker. Reservation is committed before this result returns.
Send those bytes once with the native host tool; this helper does not send them.

For operation="confirm", supply mission_id, first and second. Each observation
contains conversation_id and ordered messages [{id, role, text}], reconstructed
from two actual host reads. Do not fabricate snapshots or reuse an old read.
Confirmation requires a unique receipt after the saved anchor, unchanged ID and
text, marker and exact logical-payload hash. Markdown normalization differences
remain uncertain rather than authorizing a resend.

Operation="status" with mission_id returns the pending reservation. Unknown
fields and oversized input fail. An absent receipt never authorizes retry.
Evidence is labelled host_observation_supplied: the helper cannot authenticate
the supplied observations. It does not attest external execution or completion.
This short-lived client does not trigger the server's startup recovery; the
runtime owner retains that responsibility. Single-writer ownership is still
required. Fully automatic host-tool wiring remains open.
Outbound reservation reads and writes use one immediate SQLite transaction:
competing different payloads cannot each reserve an outstanding send for the
same mission. This guards local intent records, not remote exactly-once delivery
or concurrent edits to the actual ChatGPT conversation.
For native missions, max_iterations is a conservative outbound-attempt cap
(default25): every MESSAGE_SEND_STARTED on native_host consumes one unit,
including later pre-delivery aborts and context/report messages. Reopening the
database never resets this count. It is not an action counter or a claim that
one message equals one completed reasoning cycle. Legacy web loops retain
their existing iteration semantics. After exhaustion, keep observations and
receipts; do not create a replacement mission merely to bypass the budget.

## Native action records

### Retain the actual host session reference

After the host returns a process handle, call attach_handle with mission_id,
record_id, host and handle. Both reference strings are bounded to512 characters;
host must identify the actual session namespace (for example host plus task),
not a generic provider label shared by unrelated namespaces. Do not put secrets
in either field. The pending process must belong to that mission. Identical
reattachment is idempotent; replacement and reuse by another action in this DB
are refused. A late observed handle after stop may be retained for reconciliation,
but a settled action cannot be changed. No process is launched, signalled or
declared alive by this operation. pending_actions includes host_reference.

On resume, query the exact host capability using that reference. Its stored
liveness_verified=false deliberately requires a fresh host observation. An
unrecognized/expired handle remains unresolved; never reinterpret it as a PID,
silently replace it, relaunch the action or infer an exit from absent output.
The launch-to-attachment crash window and loss of the host's own session registry
remain limits. This is durable metadata, not an OS process supervisor or a
guarantee that sessions survive a desktop restart.

### Inventory before selecting context

Run the installed supervisor-artifacts.py with --workspace PROJECT --inventory.
It lists relative paths/sizes, explicit exclusions and scan issues without
reading file payloads or creating an archive. Optional --inventory-limit N is
bounded to1..10000 (default1000). Private/hidden paths follow the preparation
policy; links and special files are not followed. Excluded subtrees are not
counted as fully inspected. eligible_scan_complete differs from
full_project_coverage: exclusions prevent a full-project claim. Limits or read
errors return exit2 and incomplete coverage, never silently truncated success.
The5s traversal budget is cooperative and cannot preempt a blocked filesystem
call. This is point-in-time metadata, not an atomic tree snapshot or a hash of
current contents. Review the index/exclusions locally before forwarding selected
metadata. Then prepare explicit file batches with the existing artifact helper;
only preparation freezes bytes/hashes, and neither operation transmits them.

### Freeze acceptance before work

Immediately after init, use operation=define_acceptance with mission_id and
criteria, a nonempty list of {id,description}. IDs are unique. The contract is
stored once before any message/action/decision; identical repeats are harmless,
but changed criteria and retrospective definition are refused. prepare_context
includes the frozen contract alongside the source reference when it exists.
Descriptions are requirements, not completed tests or human approvals:
completion_verified and approval_recorded remain false. Existing runs cannot
be retroactively declared preregistered. Final evidence evaluation is still
incomplete; do not convert this declaration into a success verdict.

### Link criteria to retained proof

When recording an actual action receipt, include proof_manifest in its evidence
(process) or verification (host tool). Use the artifact manifest for explicit
proof files in the mission workspace. Do not retrofit or change a settled receipt.
Then call check_acceptance_evidence with mission_id and evidence, exactly one
{criterion_id,verdict,record_id} per frozen criterion. Verdict is PASS, FAIL or
UNCLEAR. The checker verifies full coverage, same-mission completed records,
recorded proof-file bytes, and refuses reported PASS backed by a failed action.
Pending work must be reconciled first. Total proof reads are capped at50MiB.
It returns evidence_integrity separately from reported_acceptance; both are
distinct from completion_verified=false. Review whether each test actually
covers its requirement and the current deliverable before concluding. A digest
does not authenticate the observer or make a weak test adequate. No mission
transition, user approval or publication follows from this read-only command.

### Persist native completion after local review

After checking actual deliverables against every frozen criterion, use
operation=finalize_native with mission_id, first, second, evidence (the same
criterion/record references as check_acceptance_evidence), and review:
{"reviewer":"actual operator label","criteria":[{"criterion_id":"frozen ID",
"finding":"Concrete explanation of the inspected evidence and coverage"}]}.
This is operator-supplied review, not an authenticated human approval. Each
criterion needs a nonempty finding; labels alone cannot establish test adequacy.
The command requires an IDLE native mission within its deadline, a current
checked COMPLETE reply, no pending work and passing current proof for all
criteria. Checks and decision/validation/COMPLETED writes share a SQLite writer
transaction. Stopped missions, stale proof, missing review and replay are refused.
The result reports completion_recorded=true, approval_recorded=false and
release_eligible=false. Read-only check operations remain non-finalizing.
External files are not locked: this is point-in-time verification, not durable
authenticity or proof that arbitrary operator assertions are truthful. On an
uncertain CLI outcome inspect stored state before retrying; no second completion
record is created. status exposes the persisted state and iteration alongside
pending and pending_actions, so a restarted operator can distinguish a completed
mission from an idle one. Finalizing one pilot never finalizes the Cortex release.

### Revision-bound request preparation

Use operation=prepare_context instead of prepare with the same mission_id,
conversation_id, before_message_id and message, plus the retained artifact
manifest object. It rechecks selected bytes in the mission's stored workspace,
then records selection_sha256 and validated path/bytes/hash items in the send
checkpoint. The returned wire message includes the same reference and explicitly
states that metadata is not file delivery. Arbitrary manifest extensions and
claimed delivery fields are not forwarded. Send exactly the returned message.
The brain is asked for a JSON object containing exactly selection_sha256 and
decision (the existing cortex.v1 contract). To check its actual response, use
operation=check_context_reply with mission_id, first and second: two fresh host
observations in the same shape used by confirm. This read-only check requires
the latest request's confirmed receipt, the immediately following assistant
reply, stable reply ID/text, matching source revision and current source bytes.
Wrong mission/iteration/action schema uses the existing protocol validator.
It returns execution_authorized=false and completion_verified=false even for
COMPLETE. It cannot authenticate caller-supplied observations or prove attachment
reading. For a context-bound action use operation=prepare_context_action with
mission_id, first and second. It derives actionId/tool/arguments from the checked
EXECUTE or actionable REQUEST_CONTEXT decision; COMPLETE cannot prepare effects.
It rechecks current sources/request under the writer lock, persists the decision
and reservation together, and advances the mission iteration. A used decision
cannot prepare another action. Once a mission has a bound context request, plain
action_prepare/tool_prepare are refused; a later plain send cannot remove that
requirement. Legacy missions without bound requests retain their prior behavior.
The returned execution_authorized=false is intentional: host permission/policy
must still allow the exact effect. Process tools use action_confirm; other tools
use tool_confirm. Evidence is caller-supplied, not an OS sandbox or attestation.
Changes after reservation and final acceptance remain separate gates.

To stop future journaled work for one mission, send JSON to the same helper:

```json
{"operation":"stop","mission_id":"selected-mission","reason":"Operator requested stop"}
```

The scoped cancellation is persisted and repeat requests are idempotent without
overwriting the original reason. Pending sends/actions remain visible and can
still receive actual late receipts. Other terminal verdicts are not rewritten.
New native reservations recheck cancellation inside the SQLite writer transaction.
The response explicitly returns external_processes_stopped=false: inspect and
stop each owned active process using its real host handle when authorized.
Never claim all work has stopped from a journal cancellation alone.

The same installed journal accepts these additional JSON stdin operations:

```json
{"operation":"action_prepare","mission_id":"MISSION","action_id":"UNIQUE-ACTION","tool":"actual-host-tool","arguments":{"path":"selected-relative-path"}}
```

This commits an intent into the existing tool_executions table before returning
record_id. It does not execute or authorize anything. Check the user's scope and
actual tool permissions independently. Paused/terminal missions refuse new
reservations. One unresolved native action blocks all later native reservations
for that mission; changing an action ID cannot bypass it. Used action IDs cannot
be replayed, including after a failed result.

After observing the actual result:

```json
{"operation":"action_confirm","mission_id":"MISSION","record_id":"RETURNED-ID","exit_code":0,"evidence":{"observation":"actual tool output and relevant file checks"}}
```

Supply actual evidence, never this example's placeholder. Status exposes
pending_actions after a restart. If a process is still running, observe its
existing handle. Unknown exit/effects remain unresolved; neither a timeout nor
a file's existence alone proves full completion. Confirmation stores supplied
evidence with host_observation_supplied provenance, not independent attestation
or mission success. Nonzero exits remain failures even when some files exist.
Receipts are immutable. This is a cooperative journal, not a sandbox or a
transaction spanning SQLite and external tools. Concurrent cancellation after
reservation and reconciliation of lost process handles remain open limitations.

### Tools without process exit codes

Use tool_prepare (same fields as action_prepare) before a non-process tool call.
After observing its result, tool_confirm accepts mission_id, record_id, outcome
(succeeded or failed), tool_result (the actual object, which may be empty) and
verification (nonempty relevant observations, such as file bytes/hash checks).
It stores exit_code=null and host_observation_supplied provenance. Unknown
outcomes are not confirmation. The receipt kind is fixed at reservation and
cannot be changed to evade a missing process exit. Legacy reservations retain
their process kind. This record does not independently authenticate host data
or establish mission acceptance.
