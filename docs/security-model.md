# Security model

Cortex Bridge gives a cloud conversation the ability to act on your machine.
That power is fenced in at every layer.

## Workspace confinement (executor)

- All paths are **workspace-relative**: absolute paths, `~`, Windows drive
  letters and `..` traversal are rejected at protocol validation
  (`ABSOLUTE_PATH` / `PATH_TRAVERSAL`).
- Every path is resolved and checked to stay inside the workspace root —
  including through symlinks.
- `run_process` only runs an **allowlist of executables** (e.g. `python3`,
  test runners, git read-only subcommands), always with `cwd` inside the
  workspace, with bounded output and hard timeouts.
- No package installs, no `git push`, no network tools, no access to
  secrets files.

## Write policy

Per mission, one of:

| Policy | Behavior |
|---|---|
| `workspace-write-automatic` | Write tools execute immediately (still workspace-confined) |
| `workspace-write-with-approvals` | Every write action pauses the mission until a human clicks Approve (scope: once / tool / all-writes) |
| `read-only` | Write tools are denied outright (`POLICY_DENIED`) |

Approvals are recorded in the audit store (tool, scope, decision, timestamp).

## Delivery and execution integrity

- The orchestrator can only request **one bounded action per iteration**;
  anything else is a protocol violation (3 consecutive violations fail the
  mission).
- Decisions are strictly validated: protocol version, mission id, UUID
  actionId, monotonic iteration, known tool, exact argument schema, path
  safety.
- Duplicate responses/reports are fingerprinted and never re-executed.
- The loop proves each send in the DOM before continuing; uncertain delivery
  pauses for human resolution — it never blindly resends.

## Transport safety

- **Opt-in required** and persisted: the first mission launch is refused
  (HTTP 403) until the user explicitly accepts the experimental-transport
  warning in the console.
- **Loopback only**: the console binds to `127.0.0.1:8420`, the WebBridge
  daemon to `127.0.0.1:10086`. No port is exposed to the network.
- **DOM only**: the transport reads and clicks the page; it never calls
  ChatGPT's private API, never scrapes credentials, never bypasses
  login/CAPTCHA/rate limits — it pauses and asks the human instead.
- **Conversation lock**: a mission is bound to one `/c/<uuid>` identity and
  verifies it before every send; a mismatch pauses instead of leaking
  mission content into the wrong conversation.

## Emergency stop

`POST /api/transport/stop-everything` (or the STOP EVERYTHING button) sets a
global kill switch: running missions are cancelled (`STOP_EVERYTHING`), new
missions and resumes are refused (HTTP 409) until
`POST /api/transport/stop-reset`.

## Audit

Every mission persists to a local SQLite store (WAL): decisions (valid and
invalid), policy decisions, approvals, tool executions with results,
validation results, transport events, conversation bindings. Nothing is
deleted automatically; the database stays on your disk under
`console/data/cortex.db`.
