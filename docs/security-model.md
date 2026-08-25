# Security model

Cortex Bridge reduces the authority of browser-driven instructions. It is not
a virtual machine or a substitute for backups.

## Chrome boundary

- HTTP and WebSocket services bind to loopback.
- The Manifest V3 extension has host access only to `chatgpt.com` and
  `127.0.0.1:8420`.
- It requests no cookie, password, history, or all-sites permission. Its
  `debugger` permission is limited in code to the selected ChatGPT tab for a
  bounded trusted-input or exact-tab screenshot operation, then detached.
- Pairing tokens contain 256 bits of entropy, expire after 60 seconds, and are
  consumed once.
- Unpaired connections may heartbeat and request pairing only.
- Commands use a fixed allowlist and structured payloads. Raw remote
  JavaScript is rejected.
- The user performs login, terms, CAPTCHA, rate-limit, and account decisions.
- Conversation identity is checked before delivery; uncertain delivery is
  never retried automatically.
- A disconnect fails closed and never falls back to Playwright.

## Execution boundary

- Chat messages cannot directly trigger local tools.
- Execution starts after a preflight identifies workspace, capabilities,
  approval policy, and limits.
- Paths must resolve inside the approved workspace; traversal, absolute paths,
  and symlink escapes are rejected.
- Process arguments are vectors without a shell and are bounded by time and
  output limits.
- Deployment, publishing, payment, credentials, and account modification are
  unsupported.

## Attachments and screenshots

- The backend validates extension, MIME signature, and Office containers.
- Client paths are rejected; opaque attachment tokens expire and resolve only
  to managed files.
- The extension v0.5 transfer limit is 25 MiB.
- Transfers use bounded chunks and require a visible ChatGPT attachment chip.
- The extension does not claim that DOM `.click()` is a trusted attachment
  send. It prepares the exact URL, filename and unique control, then hands one
  press to a local macOS Accessibility helper.
- The helper is compiled from the tracked Swift source into
  `CORTEX_HOME/bin`, installed with owner-only execution permission, and
  rejects symlinked source, output and override paths.
- macOS Accessibility permission is a manual user grant. It is not requested
  through `sudo`, scripted System Settings clicks, or TCC database changes.
- The helper receives a maximum 64 KiB JSON request on standard input with the
  expected ChatGPT HTTPS URL, plain filename and `expected_text_sha256`. This
  digest is the SHA-256 of the whitespace-normalized composer value; the full
  plaintext prompt never enters the helper request.
- The activation argument vector contains only the helper executable. No
  target URL, prompt, attachment path, file content, or credential is written
  to process arguments or logs. AX diagnostics contain structural counts and
  booleans only.
- The helper sets a 250 ms global AX messaging timeout before inspecting
  Chrome. It scans all Chrome applications and windows and requires exactly
  one stable global target with exactly one visible omnibox under `AXToolbar`
  and outside `AXWebArea`. The omnibox must contain the expected canonical
  ChatGPT URL.
- In that window, exactly one visible composer must hash to
  `expected_text_sha256`. The expected file control, composer and unique send
  control must share the exact bounded common AX ancestor, remain inside the
  window, and pass alignment checks. Discovery and focus have 5-second and
  2.5-second absolute deadlines, and the complete helper process is capped at
  10 seconds. Any ambiguity, unreadable AX state, timeout, target change, or
  permission mismatch fails closed before the press.
- After the press, the browser driver requires a new DOM user message with the
  exact normalized text and structured attachment name. It never retries an
  uncertain activation.
- Screenshots must be PNG data captured by CDP from the exact bound ChatGPT
  tab. Private mask cycles are serialized per tab and must be restored on the
  same document before pixels are accepted. Files are written atomically under
  `CORTEX_HOME`.

### Doctor integrity boundary

Doctor takes the shared installer lock, opens the helper without following a
symlink, hashes that open file descriptor, and checks the path's device and
inode identity immediately before and after running `--check-permissions`.
This closes races with cooperating Cortex install, update, and uninstall
operations and detects ordinary path replacement.

This check is not a containment boundary against a process that can already
write as the same macOS user. Darwin's Python runtime provides neither
`fexecve` nor `execveat`, and `/dev/fd` is not executable on macOS, so Doctor
must ask the OS to execute the verified path again. Such a process could
theoretically replace that path for execution and restore it between Doctor's
identity checks. A same-UID local attacker is outside the current threat model.
Covering that case would require a signed helper and a native launcher that can
bind verification to execution without reopening a mutable path.

## Runtime ownership and release privacy

Start/stop records contain exact process identity. Stop refuses foreign
listeners, stale records, and PID reuse. Start holds the installer's shared
lifecycle lock until ownership is recorded; uninstall takes the exclusive
lock and proceeds only when the runtime is verified stopped.

Public media must be synthetic or redacted. Release gates scan the tree and
history for secrets, private markers, paths, links, unknown binaries, metadata,
and OCR text. Live evidence never records account identity, cookies,
conversation content, or unredacted screenshots.

See [SECURITY.md](../SECURITY.md) for reporting requirements.
