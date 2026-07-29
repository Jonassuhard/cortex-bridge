# Security model

Cortex Bridge reduces the authority of browser-driven instructions; it is not a virtual machine or a substitute for backups.

## Browser boundary

- The service binds to loopback.
- A dedicated persistent profile separates Cortex activity from the normal browser profile.
- The user performs login and account decisions.
- The adapter does not call private ChatGPT endpoints or bypass blockers.
- A conversation identity is checked before delivery.
- Uncertain delivery fails closed and is never retried automatically.

## Execution boundary

- Chat messages cannot directly trigger local tools.
- Execution starts only after a preflight identifies the workspace, capabilities, approval policy and limits.
- Paths must resolve inside the approved workspace; absolute paths, traversal and symlink escapes are rejected.
- Writes and processes follow the selected approval policy.
- Process arguments are validated as vectors without a shell and are bounded by time and output limits.
- Deployment, publishing, payment, credentials and account modification are unsupported.

## Attachments

- The backend validates extension, MIME signature and supported Office containers.
- Images are limited to 20 MiB; other supported files are limited to 512 MiB.
- Client paths are rejected. Opaque attachment tokens expire and resolve server-side.
- Staged files are cleaned on expiry and restart.

## Runtime ownership

Mutable state lives under the absolute `CORTEX_HOME`. Start and stop records include process identity data. Stop refuses a foreign listener, a stale record and PID reuse rather than signalling an unverified process.

## Release privacy

Public media must be synthetic. The release gate scans tracked and untracked public files for private markers, encoded home paths, unapproved links, unknown binaries, image metadata and OCR text in English and French. Secret scanning covers the current tree and repository history.

See [SECURITY.md](../SECURITY.md) for reporting and release requirements.
