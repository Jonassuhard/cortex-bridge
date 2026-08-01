# Security policy

## Supported version

Security fixes currently target the v0.5 release line on macOS.

## Reporting a vulnerability

Use the repository’s private security-advisory flow. Do not include credentials, session cookies, personal conversations or real user files in a report. A minimal synthetic reproduction is enough.

If private reporting is unavailable, contact the maintainer privately before publishing details. Public issues are appropriate only after a fix or coordinated disclosure.

## Security boundaries

Cortex Bridge is a local policy boundary, not a hardened virtual machine.

- The service binds to loopback.
- A dedicated browser profile separates Cortex activity from the user’s normal profile.
- The user performs ChatGPT login manually.
- Execution is confined to the approved workspace and explicit capabilities.
- Process execution requires policy review and can require per-command approval.
- Attachment tokens expire and resolve server-side.
- Stop verifies PID, start time, executable, arguments, instance token and port.

The ChatGPT web interface is outside this project’s control. Selector drift, CAPTCHA, account limits and policy changes must fail closed.

## Sensitive data

Never commit:

- browser profiles or cookies;
- real ChatGPT conversations;
- screenshots containing account or personal data;
- absolute user or mounted-volume paths;
- runtime databases, logs, attachments or process records;
- API keys, access tokens or private keys.

Release media must be synthetic and pass text, binary, metadata and OCR scans.

## Release process

A release candidate requires backend, frontend, browser, accessibility, dependency, privacy, link, installer and evidence gates. Live browser missions require explicit owner approval and do not run in CI.

The current dependency-maintainership review is recorded in the [supply-chain risk report](.supply-chain-risk-auditor/results.md).
