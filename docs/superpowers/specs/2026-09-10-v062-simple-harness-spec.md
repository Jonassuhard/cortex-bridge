# Cortex Bridge 0.6.2 — Simple Supervisor Harness

## Goal

Make Cortex Bridge easier to understand and safer to operate by keeping one
conversation-first surface and adding an explicit, bounded context harness for
the ChatGPT supervisor. ChatGPT proposes the next step; Cortex reads only the
approved context and reports verified local results.

## Product contract

1. The default screen shows only the conversation, composer, two status chips
   (ChatGPT and executor), and the essential actions.
2. Technical pipeline details remain available behind one clearly labelled
   `Détails techniques` control and are closed by default.
3. ChatGPT is used through the existing signed-in WebBridge conversation. This
   release does not add an OpenAI API client, browser-cookie export, or an
   implicit desktop-app channel.
4. A response may contain one `cortex-context-request.v1` marker. Cortex
   renders it as a proposal; nothing is transmitted until the user approves
   the individual item.
5. Supported context is intentionally small:
   - `file`: a regular file relative to the selected workspace. Documents are
     files and are identified by their filename/MIME metadata.
   - `screenshot`: only `current_chatgpt` or `current_conversation`.
   - `link`: only an `http` or `https` URL.
   - development fixtures may exercise these types but are never release
     evidence.
6. Every approval is bound to the request and item identity and is idempotent.
   Repeating an approval cannot silently resend the same context.
7. The executor remains provider-neutral. A detected model is not a verified
   executor until a run records its model identity and evidence.

## Limits and privacy

- Workspace-relative paths only; reject absolute paths, traversal, NUL and
  symlink escapes.
- At most 10 context items per request and 25 MiB per file.
- Reasons, summaries and links are bounded and redacted for common inline
  secrets before they reach the supervisor packet.
- No passwords, tokens, cookies, private browser history or full-disk scans.
- No automatic retry after uncertain delivery.

## Supervisor loop

```text
prepare bounded packet
  -> send supervisor prompt to selected ChatGPT conversation
  -> parse exactly one cortex-decision block
  -> execute one validated local action or ask for context
  -> return cortex-report with command, result, evidence and unknowns
  -> repeat until COMPLETE, BLOCKED, budget limit or missing approval
```

The desktop application's native attachment capability is an external gate.
Until it is exposed, the local endpoint and UI must report the limitation
instead of claiming that a file or screenshot was delivered.

## Acceptance criteria

- Frontend unit, backend unit, TypeScript, lint and production build pass.
- Synthetic browser run shows a valid three-item request with clear approval
  states and no hydration mismatch.
- A rejected item never calls a transport function.
- A duplicate approval with the same request/item identity is refused or
  returns the existing run without a second transport call.
- File approval cannot escape the selected workspace.
- The docs explain the supervisor role, limits, installation and the external
  desktop-attachment gate without claiming API access or model equivalence.
